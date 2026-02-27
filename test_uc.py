from seleniumbase import Driver
import time

def test_seleniumbase_uc():
    print("Launching SeleniumBase in UC (Undetected-Chromedriver) Mode...")
    # Initialize the SeleniumBase driver in UC Mode.
    # user_data_dir keeps the session profile isolated
    driver = Driver(uc=True, user_data_dir="./uc_profile", headless=False)
    
    try:
        print("Navigating to Antam Queue URL...")
        driver.uc_open_with_reconnect('https://antrean.logammulia.com/antrean?site=13', reconnect_time=4)
        
        # Wait a moment for Cloudflare or the page to load
        time.sleep(5)
        
        # We need to pierce the shadow DOM or iframe to see if the Cloudflare box is there.
        # But UC Mode might Auto-Pass it!
        page_source = driver.get_page_source()
        
        if 'challenges.cloudflare.com' in page_source or 'Just a moment...' in page_source:
            print("🛡️ Cloudflare Challenge detected! Attempting uc_gui_click_captcha()...")
            
            # This is SeleniumBase's built-in stealth captcha clicker
            driver.uc_gui_click_captcha()
            print("Click command sent.")
            
            # Give it time to solve and redirect
            time.sleep(6)
            
            # Confirm if we passed
            current_url = driver.current_url
            print(f"Current URL after bypass attempt: {current_url}")
            
            driver.save_screenshot('uc_result.png')
            print("Saved screenshot to uc_result.png")
            
            if 'logammulia.com' in current_url and '/antrean?site=13' in current_url:
                print("✅ BYPASS SUCCESSFUL! We are on the target page.")
            else:
                print("⚠️ Bypass may have failed or redirected elsewhere.")
                
        else:
            print("✅ No Cloudflare box detected! UC Mode bypassed it automatically (Auto-Pass).")
            driver.save_screenshot('uc_autopass.png')
            
    except Exception as e:
        print(f"An error occurred: {e}")
        
    finally:
        print("Closing the UC browser in 5 seconds...")
        time.sleep(5)
        driver.quit()

if __name__ == '__main__':
    test_seleniumbase_uc()
