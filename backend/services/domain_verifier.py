import asyncio
import json
import os
import re
import urllib.request
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright

from backend.models import DigitalFootprintProfile


def fetch_rdap_whois(domain: str) -> dict:
    """Fetch domain registration data via ICANN standard RDAP protocol (Zero LLM, no external binary needed)."""
    clean_domain = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]

    rdap_url = f"https://rdap.org/domain/{clean_domain}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KYC-Digital-Audit/1.0",
        "Accept": "application/rdap+json, application/json"
    }

    try:
        req = urllib.request.Request(rdap_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                
                events = data.get("events", [])
                created_date = None
                
                for ev in events:
                    action = ev.get("eventAction", "").lower()
                    date_val = ev.get("eventDate")
                    if "registration" in action or "created" in action:
                        created_date = date_val
                        break

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

                age_days = None
                if created_date:
                    try:
                        clean_dt_str = created_date[:10]
                        dt_obj = datetime.strptime(clean_dt_str, "%Y-%m-%d")
                        age_days = (datetime.now() - dt_obj).days
                    except Exception:
                        pass

                return {
                    "domain": clean_domain,
                    "registered_date": created_date,
                    "domain_age_days": age_days,
                    "registrar": registrar,
                }
    except Exception:
        pass

    return {
        "domain": clean_domain,
        "registered_date": None,
        "domain_age_days": None,
        "registrar": None,
    }


async def crawl_and_verify_domain(target_url: str, headless: bool = True) -> DigitalFootprintProfile:
    """Crawl company website and verify digital footprint, domain age, services, and contacts."""
    if not target_url:
        return DigitalFootprintProfile(target_url="", domain="", is_live=False)

    clean_url = target_url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = f"https://{clean_url}"

    domain_match = re.search(r"https?://([^/]+)", clean_url)
    domain_name = domain_match.group(1) if domain_match else clean_url
    clean_domain = domain_name[4:] if domain_name.startswith("www.") else domain_name

    rdap_info = fetch_rdap_whois(clean_domain)

    profile = DigitalFootprintProfile(
        target_url=clean_url,
        domain=clean_domain,
        domain_created_date=rdap_info.get("registered_date"),
        domain_age_days=rdap_info.get("domain_age_days"),
        registrar=rdap_info.get("registrar"),
    )

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            resp = await page.goto(clean_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            profile.is_live = True
            profile.http_status = resp.status if resp else 200
            profile.website_title = await page.title()
            home_body = await page.inner_text("body")

            # Look for Contact page
            all_links = await page.eval_on_selector_all(
                "a",
                """els => els.map(e => ({
                    text: e.innerText.trim(),
                    href: e.href
                })).filter(e => e.href && e.href.startsWith("http"))"""
            )

            contact_body = ""
            contact_links = [
                l for l in all_links 
                if any(k in l["href"].lower() or k in l["text"].lower() for k in ["contact", "reach", "location", "help"])
            ]
            if contact_links:
                try:
                    await page.goto(contact_links[0]["href"], timeout=20000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    contact_body = await page.inner_text("body")
                except Exception:
                    pass

            await browser.close()
        except Exception as e:
            profile.notes.append(f"Website unreachable or navigation error: {str(e)[:150]}")
            return profile

    combined_text = home_body + "\n" + contact_body

    # Extract Services & Keywords
    service_keywords = [
        "Digital Bank", "Wholesale Bank", "Corporate Banking", "Trade Finance",
        "Working Capital", "Treasury", "Cross-Border", "SME Banking", "Supply Chain",
        "Deposits", "Loans", "Current Account", "Financing", "Commercial Banking",
        "Investment Banking", "Asset Management"
    ]
    detected_services = [kw for kw in service_keywords if re.search(r"\b" + re.escape(kw) + r"\b", combined_text, re.IGNORECASE)]
    profile.detected_services = detected_services

    # Extract SG Phones
    phones = set(re.findall(r"(?:\+65\s*)?[689]\d{3}\s*\d{4}", combined_text))
    profile.contact_phones = list(phones)

    # Extract corporate emails
    emails = set(re.findall(r"[a-zA-Z0-9_.+-]+@" + re.escape(clean_domain), combined_text, re.IGNORECASE))
    profile.contact_emails = list(emails)

    # Extract SG Address context
    addresses = set()
    sg_addr_pattern = r"(?:(?:Level|#)\s*\d+[-–]\d+.*?)?(?:Singapore\s*\d{6}|\b\d{6}\b|Marina\s+Bay|Raffles\s+Place|Robinson\s+Road|Shenton\s+Way|Cecil\s+Street|Battery\s+Road|Collyer\s+Quay)"
    for match in re.finditer(sg_addr_pattern, combined_text, re.IGNORECASE):
        start = max(0, match.start() - 50)
        end = min(len(combined_text), match.end() + 50)
        snip = " ".join(combined_text[start:end].split())
        if len(snip) > 15:
            addresses.add(snip)
    profile.scraped_addresses = list(addresses)[:4]

    # Evaluate Shelf Company Risk
    if profile.domain_age_days is not None and profile.domain_age_days < 30:
        profile.is_shelf_company_risk = True
        profile.notes.append(f"High shelf/shell risk: Domain registered only {profile.domain_age_days} days ago.")

    return profile
