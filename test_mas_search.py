import asyncio
from playwright.async_api import async_playwright

async def test_form_submit():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://eservices.mas.gov.sg/fid/institution", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Check form details around #txtSearch
        form_info = await page.eval_on_selector(
            "#txtSearch",
            """el => {
                const form = el.closest('form');
                const btn = form ? form.querySelector('button, input[type=\"submit\"], .btn-search') : null;
                return {
                    formAction: form ? form.action : null,
                    formMethod: form ? form.method : null,
                    btnHtml: btn ? btn.outerHTML : null,
                    name: el.name,
                    id: el.id
                };
            }"""
        )
        print("Form Info:", form_info)
        
        # Type into txtSearch specifically and click search button
        txt_input = page.locator("#txtSearch")
        await txt_input.fill("AAREAL BANK ASIA LIMITED")
        await page.wait_for_timeout(1000)
        
        # Look for search button inside the search form
        search_btn = page.locator("#txtSearch ~ button, #txtSearch + button, form:has(#txtSearch) button, form:has(#txtSearch) .btn-search, form:has(#txtSearch) a.search").first
        if await search_btn.count() > 0:
            print("Found button! Clicking...")
            await search_btn.click()
        else:
            print("Pressing enter on #txtSearch...")
            await txt_input.press("Enter")
            
        await page.wait_for_timeout(4000)
        print("Current URL after search:", page.url)
        
        links = await page.eval_on_selector_all(
            "a",
            """els => els
                .map(e => ({text: e.innerText.trim(), href: e.href}))
                .filter(e => e.href.includes("institution/detail"))"""
        )
        print("Results count:", len(links))
        for l in links[:5]:
            print(" -", l)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_form_submit())
