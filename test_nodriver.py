import asyncio
import sys
import nodriver as uc
import cv2

# Fix Windows asyncio bug
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def test_antam_cloudflare():
    print("Launching nodriver Chromium instance...")
    # Expert mode must be False for cf_verify() to work according to docs
    browser = await uc.start()
    
    try:
        print("Opening Antam Queue URL...")
        tab = await browser.get('https://antrean.logammulia.com/antrean?site=13')
        
        # Wait for the page to load or challenge to appear
        print("Waiting for page load/challenge...")
        await asyncio.sleep(8)
        
        html = await tab.get_content()
        if 'challenges.cloudflare.com' in html or 'Just a moment...' in html:
            print("🛡️ Cloudflare Challenge detected! Attempting cf_verify()...")
            try:
                # nodriver's built in magic method
                result = await tab.cf_verify()
                print(f"cf_verify() returned: {result}")
                
                # Wait to see if it redirects to the queue page
                await asyncio.sleep(5)
                
                url = await tab.evaluate('window.location.href')
                print(f"Current URL after bypass attempt: {url}")
                
                # Take screenshot to verify
                await tab.save_screenshot('nodriver_result.png')
                print("Saved screenshot to nodriver_result.png")
                
                if 'logammulia.com' in url and '/antrean?site=13' in url:
                    print("✅ BYPASS SUCCESSFUL! We are on the target page.")
                else:
                    print("⚠️ Bypass may have failed or redirected elsewhere.")
            except Exception as e:
                print(f"Error during cf_verify: {e}")
        else:
            print("✅ No Cloudflare detected! The stealth browser bypassed it automatically (Auto-Pass).")
            # Take screenshot to verify auto-pass
            await tab.save_screenshot('nodriver_autopass.png')
            print("Saved screenshot to nodriver_autopass.png")
            
    finally:
        print("Closing browser...")
        try:
            await browser.stop()
        except:
            pass
        await asyncio.sleep(1) # Let subprocesses die gently

if __name__ == '__main__':
    try:
        asyncio.run(test_antam_cloudflare())
    except Exception as e:
        print(f"Fatal error: {e}")
