import asyncio
import json
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://eservices.mas.gov.sg/fid/institution?sector=Banking&category=Merchant%20Bank", timeout=30000)
        await page.wait_for_timeout(3000)
        
        links = await page.eval_on_selector_all(
            "a",
            """els => els
                .map(e => ({text: e.innerText.trim(), href: e.href}))
                .filter(e => e.href.includes("institution/detail"))"""
        )
        print("Detail links found:", len(links))
        if links:
            for l in links[:3]:
                print(l)
                
            first_url = links[0]["href"]
            print("\nNavigating to first detail page:", first_url)
            await page.goto(first_url, timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Print page text overview
            body_text = await page.inner_text("body")
            print("\n--- FIRST 1500 CHARACTERS OF PROFILE PAGE ---")
            print(body_text[:1500])
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect())
