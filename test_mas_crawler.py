import asyncio
import json
import os
import re
import sys
from playwright.async_api import async_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def test_mas_crawler(entity_name: str, headless: bool = False):
    print(f"\n=======================================================")
    print(f" Testing MAS Scraper (Playwright Headed Debug Mode)")
    print(f" Target Entity: '{entity_name}'")
    print(f" LLM Status: BYPASSED (0 tokens used)")
    print(f" Output Folder: {OUTPUT_DIR}")
    print(f"=======================================================\n")

    clean_name = entity_name.strip()
    if not clean_name:
        print("[!] Entity name is empty.")
        return

    async with async_playwright() as p:
        print("[1/5] Launching Chromium browser (visible on screen)...")
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=800  # slow down actions by 800ms so you can observe the actions
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 850},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        search_url = f"https://eservices.mas.gov.sg/fid/institution?term={clean_name.replace(' ', '%20')}"
        print(f"[2/5] Navigating to MAS search portal:\n      {search_url}")
        
        try:
            await page.goto(search_url, timeout=35000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[!] Page navigation error: {e}")

        # Capture search results screenshot & HTML
        search_screenshot = os.path.join(OUTPUT_DIR, "1_mas_search_results.png")
        await page.screenshot(path=search_screenshot, full_page=True)
        print(f"      [Screenshot saved] -> {search_screenshot}")

        # Extract search links
        links = await page.eval_on_selector_all(
            "a",
            """els => els
                .map(e => ({text: e.innerText.trim(), href: e.href}))
                .filter(e => e.href.includes("institution/detail/"))"""
        )
        print(f"\n[3/5] Search returned {len(links)} institution link(s):")
        for idx, l in enumerate(links[:5], 1):
            print(f"      {idx}. {l['text']} -> {l['href']}")

        if not links:
            print("[!] No institution records found matching this name on MAS.")
            await browser.close()
            return

        # Target matching logic
        norm_query = re.sub(r"[^A-Za-z0-9]", "", clean_name).upper()
        target_link = None
        for l in links:
            norm_link = re.sub(r"[^A-Za-z0-9]", "", l["text"]).upper()
            if norm_query == norm_link:
                target_link = l
                print(f"      -> Exact match found: '{l['text']}'")
                break

        if not target_link:
            words = set(re.findall(r"[A-Z]{3,}", norm_query))
            for l in links:
                l_words = set(re.findall(r"[A-Z]{3,}", l["text"].upper()))
                common = words.intersection(l_words)
                common_meaningful = [w for w in common if w not in {"PTE", "LTD", "LIMITED", "SINGAPORE", "ASIA", "BANK"}]
                if len(common_meaningful) >= 1:
                    target_link = l
                    print(f"      -> Partial match found: '{l['text']}'")
                    break

        if not target_link:
            target_link = links[0]
            print(f"      -> Defaulting to first link: '{target_link['text']}'")

        print(f"\n[4/5] Navigating to Detail Page:\n      {target_link['href']}")
        await page.goto(target_link["href"], timeout=35000)
        await page.wait_for_timeout(2500)

        # Capture detail screenshot & full HTML
        detail_screenshot = os.path.join(OUTPUT_DIR, "2_mas_institution_detail.png")
        await page.screenshot(path=detail_screenshot, full_page=True)
        print(f"      [Screenshot saved] -> {detail_screenshot}")

        html_dump_path = os.path.join(OUTPUT_DIR, "mas_page_raw.html")
        html_content = await page.content()
        with open(html_dump_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"      [Raw HTML saved]   -> {html_dump_path}")

        # Extraction logic
        body_text = await page.inner_text("body")
        
        # Save raw body text
        text_dump_path = os.path.join(OUTPUT_DIR, "mas_body_text.txt")
        with open(text_dump_path, "w", encoding="utf-8") as f:
            f.write(body_text)

        # Parse Fields
        country_match = re.search(r"Incorporated in\s+([^\n\r]+)", body_text, re.IGNORECASE)
        country = country_match.group(1).strip() if country_match else None
        if country and ("Licence" in country or "Status" in country):
            country = country.split("Licence")[0].strip()

        licence_type = None
        licence_section_match = re.search(r"Licence Type/Status\s*\n+([^\n]+)", body_text, re.IGNORECASE)
        if licence_section_match:
            licence_type = licence_section_match.group(1).strip()

        if "Ceased" in body_text or "CEASED" in body_text:
            licence_status = "Ceased"
        elif "Suspended" in body_text or "SUSPENDED" in body_text:
            licence_status = "Suspended"
        elif "Revoked" in body_text or "REVOKED" in body_text:
            licence_status = "Revoked"
        else:
            licence_status = "Current"

        key_personnel = []
        kp_match = re.search(r"Key Personnel\s*\n+(.*?)(?=\n+Contact|\n+Home|\n+About MAS|$)", body_text, re.DOTALL | re.IGNORECASE)
        if kp_match:
            lines = [line.strip() for line in kp_match.group(1).split("\n") if line.strip()]
            for i in range(0, len(lines) - 1, 2):
                key_personnel.append({
                    "role": lines[i],
                    "name": lines[i+1]
                })

        registered_address = None
        contact_match = re.search(r"Contact\s*\n+(.*?)(?=\n+Home|\n+About MAS|\n+Copyright|$)", body_text, re.DOTALL | re.IGNORECASE)
        if contact_match:
            c_lines = [line.strip() for line in contact_match.group(1).split("\n") if line.strip()]
            addr_lines = [l for l in c_lines if not l.startswith("+") and not l.isdigit()]
            if addr_lines:
                registered_address = " ".join(addr_lines)

        extracted_data = {
            "search_name_used": entity_name,
            "matched_institution_name": target_link["text"],
            "mas_profile_url": target_link["href"],
            "is_found_on_mas": True,
            "country_of_incorporation": country,
            "licence_type": licence_type,
            "licence_status": licence_status,
            "registered_address": registered_address,
            "key_personnel_count": len(key_personnel),
            "key_personnel": key_personnel,
        }

        json_out_path = os.path.join(OUTPUT_DIR, "mas_extracted_data.json")
        with open(json_out_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)
        print(f"      [Extracted JSON]   -> {json_out_path}")

        print("\n[5/5] Extracted Data Results:")
        print("-------------------------------------------------------")
        print(json.dumps(extracted_data, indent=2))
        print("-------------------------------------------------------")

        print("\nClosing browser in 3 seconds...")
        await page.wait_for_timeout(3000)
        await browser.close()
        print("[OK] Done. Test run completed successfully.")

if __name__ == "__main__":
    test_company = sys.argv[1] if len(sys.argv) > 1 else "AAREAL BANK ASIA LIMITED"
    asyncio.run(test_mas_crawler(test_company, headless=False))
