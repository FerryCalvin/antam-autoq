from seleniumbase import SB
import time

def test_seleniumbase_verbose():
    print("Launching SeleniumBase in UC Mode with verbose logging...")
    
    # Using the SB context manager is recommended for UC mode stability on Windows
    # We turn on uc_subprocess and disable incognito strictly for Turnstile
    with SB(uc=True, uc_subprocess=True, incognito=False, headless=False, user_data_dir="uc_profile") as sb:
        print("Browser launched successfully.")
        
        url = 'https://antrean.logammulia.com/antrean?site=13'
        print(f"Opening {url}")
        
        # uc_open_with_reconnect drops connections and reconnects to avoid CDP detection
        sb.uc_open_with_reconnect(url, 4)
        
        print("Waiting 6 seconds for page analysis...")
        time.sleep(6)
        
        # Check if we hit the Cloudflare fence
        source = sb.get_page_source()
        if 'challenges.cloudflare.com' in source or 'Just a moment' in source:
            print("🛡️ Cloudflare detected. Engaging uc_gui_click_captcha()...")
            
            try:
                # SeleniumBase magic clicker
                sb.uc_gui_click_captcha()
                print("Click attempted.")
            except Exception as e:
                print(f"Error clicking captcha: {e}")
                
            time.sleep(5)
            
            current = sb.get_current_url()
            print(f"URL after click: {current}")
            
            sb.save_screenshot('sb_verbose_result.png')
            
            if 'logammulia.com' in current and '/antrean?site=13' in current:
                print("✅ Bypass SUCCESSFUL via GUI Click!")
            else:
                print("⚠️ Bypass FAILED. Turnstile still blocking.")
        else:
            print("✅ Auto-Pass successful! No Turnstile challenge presented.")
            sb.save_screenshot('sb_verbose_autopass.png')

if __name__ == '__main__':
    try:
        test_seleniumbase_verbose()
    except Exception as e:
        print("Fatal test error:", e)
