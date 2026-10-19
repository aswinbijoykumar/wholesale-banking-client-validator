import asyncio
import json
import re
from typing import Optional, List
from playwright.async_api import async_playwright
from backend.models import MasVerificationProfile

async def parse_detail_page(page, url: str, entity_name: str) -> MasVerificationProfile:
    await page.goto(url, timeout=30000)
    await page.wait_for_timeout(2000)
    
    body_text = await page.inner_text("body")
    
    # Check country of incorporation
    # Look for "Incorporated in Singapore" or "Incorporated in [Country]"
    country_match = re.search(r"Incorporated in\s+([^\n\r]+)", body_text, re.IGNORECASE)
    country = country_match.group(1).strip() if country_match else None
    if country and ("Licence" in country or "Status" in country):
        country = country.split("Licence")[0].strip()
    
    # Extract Licence Type/Status section
    # The structure has "Licence Type/Status" followed by the licence type (e.g. Merchant Bank, Wholesale Bank)
    # and status (Active, Ceased, or implied Current)
    licence_type = None
    licence_status = "Current"
    
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

    # Key Personnel section:
    # "Key Personnel\n[Role]\n\t[Name]"
    key_personnel = []
    kp_match = re.search(r"Key Personnel\s*\n+(.*?)(?=\n+Contact|\n+Home|\n+About MAS|$)", body_text, re.DOTALL | re.IGNORECASE)
    if kp_match:
        lines = [line.strip() for line in kp_match.group(1).split("\n") if line.strip()]
        # Typically pairs: Role then Name
        for i in range(0, len(lines) - 1, 2):
            key_personnel.append({
                "role": lines[i],
                "name": lines[i+1]
            })
            
    # Contact & Registered Address section:
    # "Contact\n\thttp://www.dbs.com\n\t+65 68788888\n\t12 MARINA BOULEVARD..."
    registered_address = None
    website_url = None
    phone_number = None
    contact_match = re.search(r"Contact\s*\n+(.*?)(?=\n+Home|\n+About MAS|\n+Copyright|$)", body_text, re.DOTALL | re.IGNORECASE)
    if contact_match:
        c_lines = [line.strip() for line in contact_match.group(1).split("\n") if line.strip()]
        for l in c_lines:
            if re.match(r"^https?://", l, re.IGNORECASE) or (l.startswith("www.") and "." in l):
                if not website_url:
                    website_url = l if l.startswith("http") else f"https://{l}"
            elif l.startswith("+") or (re.sub(r"\D", "", l) and len(re.sub(r"\D", "", l)) >= 8 and not re.search(r"[a-zA-Z]", l)):
                if not phone_number:
                    phone_number = l
        
        # Address is the line(s) that are neither URL nor phone
        addr_lines = [
            l for l in c_lines 
            if not re.match(r"^https?://", l, re.IGNORECASE) 
            and not l.startswith("www.")
            and not (l.startswith("+") and not re.search(r"[a-zA-Z]", l))
        ]
        if addr_lines:
            registered_address = " ".join(addr_lines)
            
    return MasVerificationProfile(
        is_fi_nbfi=True,
        search_name_used=entity_name,
        mas_profile_url=url,
        is_found_on_mas=True,
        licence_type=licence_type,
        licence_status=licence_status,
        country_of_incorporation=country,
        key_personnel=key_personnel,
        registered_address=registered_address,
        website=website_url,
        phone=phone_number,
        raw_notes=body_text[:500]
    )

async def search_and_verify_mas(entity_name: str) -> MasVerificationProfile:
    """Search MAS FID by legal company name and extract details."""
    clean_name = entity_name.strip()
    if not clean_name:
        return MasVerificationProfile(search_name_used=entity_name, is_found_on_mas=False)
        
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        search_url = f"https://eservices.mas.gov.sg/fid/institution?term={clean_name.replace(' ', '%20')}"
        await page.goto(search_url, timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Get result links
        links = await page.eval_on_selector_all(
            "a",
            """els => els
                .map(e => ({text: e.innerText.trim(), href: e.href}))
                .filter(e => e.href.includes("institution/detail/"))"""
        )
        
        if not links:
            await browser.close()
            return MasVerificationProfile(
                is_fi_nbfi=True,
                search_name_used=entity_name,
                is_found_on_mas=False
            )
            
        # Find exact or best matching link
        target_link = None
        norm_query = re.sub(r"[^A-Za-z0-9]", "", clean_name).upper()
        
        for l in links:
            norm_link = re.sub(r"[^A-Za-z0-9]", "", l["text"]).upper()
            if norm_query == norm_link:
                target_link = l
                break
                
        if not target_link:
            # Token similarity match (at least 2 matching words from name)
            words = set(re.findall(r"[A-Z]{3,}", norm_query))
            for l in links:
                l_words = set(re.findall(r"[A-Z]{3,}", l["text"].upper()))
                common = words.intersection(l_words)
                # Ignore common corporate stop words
                common_meaningful = [w for w in common if w not in {"PTE", "LTD", "LIMITED", "SINGAPORE", "ASIA", "BANK"}]
                if len(common_meaningful) >= 1:
                    target_link = l
                    break

        if not target_link:
            await browser.close()
            return MasVerificationProfile(
                is_fi_nbfi=True,
                search_name_used=entity_name,
                is_found_on_mas=False
            )
            
        profile = await parse_detail_page(page, target_link["href"], clean_name)
        await browser.close()
        return profile


if __name__ == "__main__":
    test_ent = "AAREAL BANK ASIA LIMITED"
    res = asyncio.run(search_and_verify_mas(test_ent))
    print(res.model_dump_json(indent=2))
