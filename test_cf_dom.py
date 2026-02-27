import time
from DrissionPage import ChromiumPage, ChromiumOptions

def test_cf():
    print("Connecting to open Chrome (Node 1/2)...")
    
    # We will try to connect to localhost port 39222 (Node 1) or 39223 (Node 2)
    # based on the user's config
    try:
        co = ChromiumOptions()
        co.set_local_port(39222) 
        page = ChromiumPage(co)
        print(f"Connected! URL: {page.url}")
        
        # Look for challenge iframe
        cf_iframe = page.get_frame('@src^https://challenges.cloudflare.com', timeout=3)
        if cf_iframe:
            print("Found Turnstile iframe!")
            print(cf_iframe.html)
            
            # Find checkbox
            cb = cf_iframe.ele('css:input[type="checkbox"]', timeout=2) or cf_iframe.ele('.cb-c', timeout=2) or cf_iframe.ele('xpath://input', timeout=2)
            if cb:
                print("Found checkbox element!")
                print(cb.html)
                # cb.click()
            else:
                print("Could not find checkbox inside iframe.")
                print("Iframe body elements:", cf_iframe.eles('tag:*'))
        else:
            print("No visible Turnstile iframe found!")
            print("Looking for native checkbox on page...")
            cb = page.ele('css:input[type="checkbox"]', timeout=2)
            if cb:
                print("Found native checkbox!")
                print(cb.html)
                
    except Exception as e:
        print(f"Error connecting: {e}")

if __name__ == "__main__":
    test_cf()
