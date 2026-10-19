import asyncio
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output", "domain_check")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_rdap_whois(domain: str) -> dict:
    """Fetch domain registration data via ICANN standard RDAP protocol (Zero LLM, no external binary needed)."""
    clean_domain = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]

    rdap_url = f"https://rdap.org/domain/{clean_domain}"
    print(f"\n[RDAP] Querying registry records for: {clean_domain} ...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KYC-Digital-Audit/1.0",
        "Accept": "application/rdap+json, application/json"
    }

    try:
        req = urllib.request.Request(rdap_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                
                # Extract creation/registration dates
                events = data.get("events", [])
                created_date = None
                last_changed_date = None
                expiration_date = None
                
                for ev in events:
                    action = ev.get("eventAction", "").lower()
                    date_val = ev.get("eventDate")
                    if "registration" in action or "created" in action:
                        created_date = date_val
                    elif "last changed" in action or "updated" in action:
                        last_changed_date = date_val
                    elif "expiration" in action:
                        expiration_date = date_val

                # Extract registrar
                registrar = None
                entities = data.get("entities", [])
                for ent in entities:
                    roles = ent.get("roles", [])
                    if "registrar" in roles:
                        vcard = ent.get("vcardArray", [])
                        if len(vcard) > 1 and isinstance(vcard[1], list):
                            for item in vcard[1]:
                                if item[0] == "fn":
                                    registrar = item[3]
                                    break
                
                # Nameservers
                nameservers = [ns.get("ldhName") for ns in data.get("nameservers", []) if ns.get("ldhName")]

                # Calculate domain age if created_date found
                age_days = None
                if created_date:
                    try:
                        clean_dt_str = created_date[:10]
                        dt_obj = datetime.strptime(clean_dt_str, "%Y-%m-%d")
                        age_days = (datetime.now() - dt_obj).days
                    except Exception:
                        pass

                result = {
                    "domain": clean_domain,
                    "rdap_status": "SUCCESS",
                    "registered_date": created_date,
                    "last_updated": last_changed_date,
                    "expiration_date": expiration_date,
                    "domain_age_days": age_days,
                    "registrar": registrar,
                    "nameservers": nameservers
                }
                print(f"      [+] RDAP Success: Registered {created_date} (~{age_days} days ago)")
                print(f"      [+] Registrar: {registrar}")
                return result
    except Exception as e:
        print(f"      [-] RDAP lookup notice: {e}")

    return {
        "domain": clean_domain,
        "rdap_status": "LOOKUP_UNAVAILABLE",
        "registered_date": None,
        "domain_age_days": None,
        "registrar": None,
        "nameservers": []
    }


async def test_domain_crawler(target_url: str = "https://www.glbank.com/", headless: bool = False):
    print("=" * 65)
    print(" DIGITAL FOOTPRINT & WEBSITE CRAWLER TEST")
    print(f" Target Site:  {target_url}")
    print(f" Output Dir:   {OUTPUT_DIR}")
    print(" LLM Status:   BYPASSED (0 tokens)")
    print("=" * 65)

    domain_match = re.search(r"https?://([^/]+)", target_url)
    domain_name = domain_match.group(1) if domain_match else target_url

    # Step 1: RDAP / Domain Age check
    rdap_info = fetch_rdap_whois(domain_name)

    # Step 2: Playwright Crawl
    async with async_playwright() as p:
        print("\n[Playwright] Launching browser (Headed Mode) ...")
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=600
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 850},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"\n[1/3] Navigating to Homepage: {target_url}")
        try:
            resp = await page.goto(target_url, timeout=35000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            http_status = resp.status if resp else None
        except Exception as e:
            print(f"[!] Navigation error: {e}")
            http_status = None

        # Screenshot Homepage
        home_ss = os.path.join(OUTPUT_DIR, "1_homepage.png")
        await page.screenshot(path=home_ss, full_page=True)
        print(f"      [Screenshot saved] -> {home_ss}")

        title = await page.title()
        home_body = await page.inner_text("body")

        # Discover internal links (About, Contact, Services/Products, Leadership)
        all_links = await page.eval_on_selector_all(
            "a",
            """els => els.map(e => ({
                text: e.innerText.trim(),
                href: e.href
            })).filter(e => e.href && e.href.startsWith("http"))"""
        )

        about_links = []
        product_links = []
        contact_links = []

        for l in all_links:
            href_lower = l["href"].lower()
            text_lower = l["text"].lower()
            
            if any(k in href_lower or k in text_lower for k in ["about", "who-we-are", "company", "leadership", "management"]):
                if l not in about_links:
                    about_links.append(l)
            elif any(k in href_lower or k in text_lower for k in ["product", "service", "solution", "banking", "financing"]):
                if l not in product_links:
                    product_links.append(l)
            elif any(k in href_lower or k in text_lower for k in ["contact", "reach", "location", "help"]):
                if l not in contact_links:
                    contact_links.append(l)

        print(f"\n[2/3] Link Analysis on Homepage:")
        print(f"      - Found {len(about_links)} About/Company link(s)")
        print(f"      - Found {len(product_links)} Products/Services link(s)")
        print(f"      - Found {len(contact_links)} Contact link(s)")

        # Visit About Page if discovered
        about_body_text = ""
        if about_links:
            target_about = about_links[0]["href"]
            print(f"\nNavigating to About Page: {target_about}")
            try:
                await page.goto(target_about, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2500)
                about_ss = os.path.join(OUTPUT_DIR, "2_about_page.png")
                await page.screenshot(path=about_ss, full_page=True)
                print(f"      [Screenshot saved] -> {about_ss}")
                about_body_text = await page.inner_text("body")
            except Exception as e:
                print(f"      [-] Could not navigate to about page: {e}")

        # Visit Contact Page if discovered
        contact_body_text = ""
        if contact_links:
            target_contact = contact_links[0]["href"]
            print(f"\nNavigating to Contact Page: {target_contact}")
            try:
                await page.goto(target_contact, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2500)
                contact_ss = os.path.join(OUTPUT_DIR, "3_contact_page.png")
                await page.screenshot(path=contact_ss, full_page=True)
                print(f"      [Screenshot saved] -> {contact_ss}")
                contact_body_text = await page.inner_text("body")
            except Exception as e:
                print(f"      [-] Could not navigate to contact page: {e}")

        print("\n[3/3] Parsing Corporate Information from Collected Content ...")
        combined_text = home_body + "\n" + about_body_text + "\n" + contact_body_text

        # 1. Search for Singapore addresses (Postal code regex / street patterns)
        addresses = set()
        sg_addr_pattern = r"(?:(?:Level|#)\s*\d+[-–]\d+.*?)?(?:Singapore\s*\d{6}|\b\d{6}\b|Marina\s+Bay|Raffles\s+Place|Robinson\s+Road|Shenton\s+Way|Cecil\s+Street|Battery\s+Road|Collyer\s+Quay)"
        for match in re.finditer(sg_addr_pattern, combined_text, re.IGNORECASE):
            # grab surrounding context
            start = max(0, match.start() - 60)
            end = min(len(combined_text), match.end() + 60)
            snip = " ".join(combined_text[start:end].split())
            if len(snip) > 15:
                addresses.add(snip)

        # 2. Extract phone numbers & emails
        phones = set(re.findall(r"(?:\+65\s*)?[689]\d{3}\s*\d{4}", combined_text))
        emails = set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", combined_text))
        # Filter static asset false positives from emails
        emails = {em for em in emails if not em.endswith((".png", ".jpg", ".webp", ".svg"))}

        # 3. Detect Key Services / Product Lines mentioned
        detected_services = []
        service_keywords = [
            "Digital Bank", "Wholesale Bank", "Corporate Banking", "Trade Finance",
            "Working Capital", "Treasury", "Cross-Border", "SME Banking", "Supply Chain",
            "Deposits", "Loans", "Current Account", "Financing"
        ]
        for kw in service_keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", combined_text, re.IGNORECASE):
                detected_services.append(kw)

        # 4. Check for Leadership / Management mentions
        leadership_candidates = []
        lead_match = re.search(r"(?:Board of Directors|Leadership|Management Team|Key Executives)([\s\S]{50,600})", combined_text, re.IGNORECASE)
        if lead_match:
            lines = [l.strip() for l in lead_match.group(1).split("\n") if len(l.strip()) > 3]
            leadership_candidates = lines[:8]

        extracted_footprint = {
            "target_url": target_url,
            "http_status": http_status,
            "website_title": title,
            "rdap_registration": rdap_info,
            "discovered_links": {
                "about_count": len(about_links),
                "products_count": len(product_links),
                "contact_count": len(contact_links),
                "about_samples": [l["href"] for l in about_links[:3]],
                "contact_samples": [l["href"] for l in contact_links[:3]],
            },
            "corporate_data_extracted": {
                "detected_services_and_products": detected_services,
                "detected_addresses": list(addresses)[:5],
                "contact_phones": list(phones),
                "contact_emails": list(emails),
                "leadership_snippets": leadership_candidates
            }
        }

        # Save to JSON
        json_path = os.path.join(OUTPUT_DIR, "domain_extracted_data.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(extracted_footprint, f, indent=2, ensure_ascii=False)
        print(f"\n[Extracted Data JSON saved] -> {json_path}")

        print("\n" + "=" * 65)
        print(" EXTRACTED DIGITAL FOOTPRINT SUMMARY")
        print("=" * 65)
        print(f" Domain:            {rdap_info.get('domain')}")
        print(f" Registered Date:   {rdap_info.get('registered_date')} (Age: {rdap_info.get('domain_age_days')} days)")
        print(f" Registrar:         {rdap_info.get('registrar')}")
        print(f" Website Title:     {title}")
        print(f" Detected Services: {', '.join(detected_services) if detected_services else 'None detected'}")
        print(f" Extracted Phones:  {list(phones)}")
        print(f" Extracted Emails:  {list(emails)}")
        print(f" Extracted Addrs:   {len(addresses)} address snippet(s)")
        print("=" * 65)

        print("\nClosing browser in 3 seconds ...")
        await page.wait_for_timeout(3000)
        await browser.close()
        print("[OK] Test run completed successfully.")


if __name__ == "__main__":
    url_arg = sys.argv[1] if len(sys.argv) > 1 else "https://www.glbank.com/"
    asyncio.run(test_domain_crawler(url_arg, headless=False))
