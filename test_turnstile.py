import time
from DrissionPage import ChromiumPage, ChromiumOptions

def test_shadow_turnstile():
    try:
        co = ChromiumOptions()
        co.set_local_port(39222) 
        page = ChromiumPage(co)
        print('Connected to', page.url)
        
        frames = page.get_frames()
        cf_frame = None
        for f in frames:
            if 'challenges.cloudflare.com' in f.url:
                cf_frame = f
                break
                
        if not cf_frame:
            print("No CF turnstile frame found.")
            return

        print('Found CF Frame.')
        
        # Turnstile hides the checkbox deep inside a shadow DOM
        # .sr is DrissionPage's shadow_root method. We need to go down to the input box.
        try:
            # We look for ANY checkbox input inside the entire frame, piercing shadow roots recursively
            cb = cf_frame.ele('css:input[type="checkbox"]')
            if cb:
               print("Found checkbox directly!")
               cb.click()
               print("Clicked directly.")
               return
        except: pass
        
        print("Direct find failed. Looking inside shadow roots...")
        # The Turnstile wrapper usually has id="turnstile-wrapper" or similar
        try:
            # Method 2: Click the center of the iframe element itself from the TOP Level Page
            # The iframe exists in the main page document.
            iframe_ele = page.ele('@src^https://challenges.cloudflare.com')
            if iframe_ele:
                print("Found Iframe Node on Main Page. Clicking its center...")
                iframe_ele.click()
                print("Clicked iframe wrapper!")
                return
        except Exception as e:
            print(f"Iframe click failed: {e}")
            
        print("All DOM clicks failed. Turnstile is likely blocking Trusted Events.")
        
    except Exception as e:
        print('Error:', e)

if __name__ == '__main__':
    test_shadow_turnstile()
