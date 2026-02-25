import asyncio
from playwright.async_api import async_playwright, Response
import json

async def intercept_network():
    """
    Launches a visible Chromium browser to intercept and print network requests/responses 
    specifically for the Antam site, aiding in manually finding location IDs, API endpoints, and tokens.
    """
    async with async_playwright() as p:
        # Launch visible system Google Chrome instead of bundled Chromium to bypass Cloudflare
        browser = await p.chromium.launch(
            channel="chrome", 
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        ) 
        page = await browser.new_page()

        # Intercept and log all requests
        page.on("request", lambda request: print(f">>> Request: {request.method} {request.url}"))
        
        async def handle_response(response: Response):
            # Filter for API/location endpoints
            if "api" in response.url or "location" in response.url or "branch" in response.url.lower():
                print(f"<<< Response: {response.status} {response.url}")
                try:
                    body = await response.json()
                    print(f"Payload JSON: {json.dumps(body, indent=2)}")
                except Exception:
                    # Ignore errors for non-JSON or unreadable responses
                    pass
        
        page.on("response", handle_response)

        print("Opening antrean.logammulia.com... Please interact with the page to find endpoints.")
        await page.goto("https://antrean.logammulia.com/")
        
        # Keep the browser open for 60 seconds for manual interaction
        await page.wait_for_timeout(60000)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(intercept_network())
