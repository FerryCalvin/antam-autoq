import time
import os
import re
import logging
from typing import Dict, Any

from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import ElementNotFoundError

logger = logging.getLogger(__name__)

def _get_stealth_page(proxy: str = None, node_id: int = 1) -> ChromiumPage:
    """
    Initializes a DrissionPage ChromiumPage which inherently bypasses Cloudflare
    by avoiding CDP webdriver flags used by Playwright/Selenium natively.
    """
    co = ChromiumOptions()
    
    # Give each node its own port and profile so multiple bots don't fight over the same Chrome
    port = 9222 + int(node_id)
    co.set_local_port(port)
    
    user_data_dir = os.path.join(os.getcwd(), f"chrome_profile_{node_id}")
    co.set_user_data_path(user_data_dir)
    
    # Hide automation features and disable the infobars (unsupported command-line flag warning)
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--disable-infobars')
    # DO NOT override user_agent! It breaks Sec-CH-UA sync causing Turnstile infinite loops!
    
    if proxy:
        co.set_proxy(proxy)
        
    page = ChromiumPage(addr_or_opts=co)
    page.set.timeouts(page_load=15, script=15)
    return page

def check_quota(page: ChromiumPage, location_id: str, target_date: str) -> int:
    """
    Returns the integer quota available (or 1 if ANY slot is found), 0 if none.
    -1 means "Needs Login", -2 means "Cloudflare Active".
    """
    url = f"https://antrean.logammulia.com/antrean?site={location_id}"
    logger.info(f"Navigating to {url} to check slots...")

    try:
        # Navigate directly to the queuing page
        try:
            page.get(url, retry=0, timeout=15)
        except Exception:
            pass # Timeout is normal if Cloudflare delays loading; we let post-checks handle it
            
        # --- IP BLOCK AUTO-COOLDOWN BUSTER ---
        if page.ele('text:pemblokiran IP', timeout=1) or page.ele('text:An Error Was Encountered', timeout=1):
            logger.warning("IP Ban / Rate Limit Detected!")
            return -3
            
        # --- SPLASH SCREEN BUSTER ---
        # If we see the Splash Screen, it means we are purely guests and need to login!
        try:
            if page.ele('text:Log In', timeout=1) or page.ele('text:Login', timeout=1) or page.ele('text:Masuk', timeout=1):
                logger.info("Splash screen detected! We are logged out. Forcing Auto-Login...")
                return -1
        except Exception:
            pass

        # Post-navigation check
        if "/masuk" in page.url or "/login" in page.url:
            return -1
            
        # BOUTIQUE AUTO-SELECTION BUSTER
        # The URL /antrean sometimes intercepts us with a location selection form.
        try:
            if not page.ele('select#wakda', timeout=2):
                loc_opt = page.ele(f'tag:option@@value={location_id}', timeout=1)
                if loc_opt:
                    logger.info(f"Boutique selection page detected. Forcing selection of {location_id}...")
                    parent = loc_opt.parent('tag:select')
                    if parent:
                        parent.select(location_id)
                        time.sleep(1)
                    page.run_js('''
                        let form = document.querySelector('form');
                        if (form) {
                            form.submit();
                        } else {
                            let btns = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
                            let submitBtn = btns.find(b => b.textContent.toLowerCase().includes('lanjut') || b.textContent.toLowerCase().includes('pilih') || (b.value && b.value.toLowerCase().includes('lanjut')));
                            if(submitBtn) submitBtn.click();
                        }
                    ''')
                    page.wait.load_start(timeout=5)
        except Exception as ex:
            logger.warning(f"Boutique Auto-Select skipped: {ex}")
            
        # Wait for the select box (wakda / quota options)
        if not page.wait.ele_displayed('select#wakda', timeout=15):
            if "/masuk" in page.url or "/login" in page.url:
                 return -1
            return -2

        # DrissionPage makes DOM extraction very easy
        select_wakda = page.ele('select#wakda')
        options = select_wakda.eles('tag:option')
        
        available_slots = []
        for index, opt in enumerate(options):
            if index == 0 or not opt.attr('value'):
                continue
                
            # Check if it lacks the 'disabled' attribute
            if not opt.attr('disabled'):
                available_slots.append({'value': opt.attr('value'), 'text': opt.text})
        
        if available_slots:
            logger.info(f"Available slots found: {available_slots}")
            return len(available_slots) 
        else:
            logger.info("No available slots found (all options disabled).")
            return 0
            
    except Exception as e:
        logger.error(f"Error checking quota via DrissionPage: {e}")
        return 0


def solve_math_question(question_text: str) -> str:
    """Parses text like '10 ditambah 6' and returns the math result."""
    text = question_text.lower()
    nums = re.findall(r'\d+', text)
    if len(nums) >= 2:
        n1, n2 = int(nums[0]), int(nums[1])
        if 'tambah' in text or '+' in text or 'plus' in text:
            return str(n1 + n2)
        elif 'kurang' in text or '-' in text or 'minus' in text:
            return str(n1 - n2)
        elif 'kali' in text or '*' in text or 'x' in text:
            return str(n1 * n2)
        elif 'bagi' in text or '/' in text:
            return str(n1 // n2)
    return ""

def solve_generic_math_captcha(page: ChromiumPage, logger_obj=logger, sync_broadcast=None, node_id=None):
    """Answers the math captcha and injects the result into empty fields, returning True if found."""
    try:
        time.sleep(2)
        page_html = page.html.lower()
        
        if "ditambah" in page_html or "dikurangi" in page_html or "dikali" in page_html:
            msg = "🧮 Math Verification Detected! Deploying Solver..."
            if sync_broadcast and node_id:
                sync_broadcast(f"[Node {node_id}] {msg}")
            logger_obj.info(msg)
            
            math_match = re.search(r'(\d+\s+(ditambah|dikurangi|dikali|dibagi)\s+\d+)', page_html)
            
            if math_match:
                question = math_match.group(1)
                answer = solve_math_question(question)
                logger_obj.info(f"Solved Math: {question} = {answer}")
                
                # Inject answer into empty text/number fields (skipping email)
                page.run_js(f'''
                    let inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
                    for(let inp of inputs) {{
                        if(inp.value === "" && !inp.name.includes("email")) {{
                            inp.value = "{answer}";
                        }}
                    }}
                ''')
                return True
    except Exception as ex:
        logger_obj.warning(f"Math Captcha Error: {ex}")
    return False

def auto_login(page: ChromiumPage, email: str, password: str, sync_broadcast, node_id: int, nama: str) -> bool:
    """Automates the login sequence if the bot gets redirected to /masuk."""
    sync_broadcast(f"[Node {node_id}] [{nama}] 🔑 Redirected to Login form. Starting Auto-Login...")
    try:
        # Navigate strictly to login page if not already there
        if "masuk" not in page.url and "login" not in page.url:
            page.get("https://antrean.logammulia.com/login", retry=0, timeout=15)
            
        # ⏳ Wait up to 60 seconds for Cloudflare / Splash Screens to be solved by the user or the bot
        sync_broadcast(f"[Node {node_id}] [{nama}] 🛡️ Waiting up to 60s for Cloudflare/Splash Form to appear...")
        if not page.wait.ele_displayed('@name=email', timeout=60):
            sync_broadcast(f"[Node {node_id}] [{nama}] ❌ Timeout! Cloudflare took too long or form not found. Restarting loop...")
            return False
            
        # Try to close any overlaying Splash Screen if one appears on the Login page
        try:
            splash_close = page.ele('text:Tutup', timeout=1) or page.ele('css:.close', timeout=1)
            if splash_close and splash_close.is_displayed:
                splash_close.click(by_js=True)
                time.sleep(1)
        except:
            pass
        
        email_inp = page.ele('@name=email')
        pass_inp = page.ele('@name=password')
        
        if email_inp: 
            email_inp.clear()
            email_inp.input(email)
        if pass_inp: 
            pass_inp.clear()
            pass_inp.input(password)
        
        # Check and solve captcha
        solve_generic_math_captcha(page, logger, sync_broadcast, node_id)
        
        sync_broadcast(f"[Node {node_id}] [{nama}] 🚀 Submitting login credentials...")
        
        # We must specifically submit the LOGIN form, not the CF form
        try:
            # First look for the login button
            submit_btn = page.ele('text:Masuk', timeout=1) or page.ele('text:Login', timeout=1) or page.ele('css:button[type="submit"]')
            if submit_btn:
                submit_btn.click(by_js=True) # JS click bypasses overlays
            else:
                email_inp.submit()
        except Exception as e:
            logger.warning(f"Could not click submit normally: {e}. Falling back to JS form submit.")
            page.run_js('''
                let forms = document.querySelectorAll('form');
                for(let f of forms) {
                    if(f.innerHTML.includes('password') || f.innerHTML.includes('email')) {
                        f.submit();
                        break;
                    }
                }
            ''')
        
        # Wait for redirect to antrean home
        page.wait.load_start(timeout=5)
        time.sleep(4) # Let cookie sink into DrissionPage
        
        # Only verify success if the URL completely escaped the login bounds
        if "masuk" not in page.url and "login" not in page.url:
            sync_broadcast(f"[Node {node_id}] [{nama}] ✅ Auto-Login Successful! Returning to Quota Target...")
            return True
        else:
            sync_broadcast(f"[Node {node_id}] [{nama}] ❌ Login Failed. Retrying...")
            return False
            
    except Exception as e:
        sync_broadcast(f"[Node {node_id}] [{nama}] ⚠️ Login automation error: {e}")
        return False

def submit_booking(page: ChromiumPage, profile_data: Dict[str, str], location_id: str, target_date: str) -> Dict[str, Any]:
    url = f"https://antrean.logammulia.com/antrean?site={location_id}"
    logger.info(f"[SNIPER] Starting sequence for {profile_data.get('nama_lengkap', 'Unknown')} at {location_id}")
    
    try:
        # 1. Fast Sniper: Skip reload if we are already sitting on the quota page from check_quota!
        if not page.ele('select#wakda', timeout=1):
            try:
                page.get(url, retry=0, timeout=15)
            except Exception:
                pass
                
            # Boutique selection auto-bypass for Sniper (in case we did reload)
            try:
                if not page.ele('select#wakda', timeout=2):
                    loc_opt = page.ele(f'tag:option@@value={location_id}', timeout=1)
                    if loc_opt:
                        parent = loc_opt.parent('tag:select')
                        if parent: parent.select(location_id)
                        time.sleep(1)
                        page.run_js('''
                            let form = document.querySelector('form');
                            if(form) form.submit();
                            else {
                                let btns = Array.from(document.querySelectorAll('button'));
                                let submitBtn = btns.find(b => b.textContent.toLowerCase().includes('lanjut'));
                                if(submitBtn) submitBtn.click();
                            }
                        ''')
                        page.wait.load_start(timeout=5)
            except Exception:
                pass
            
        if not page.wait.ele_displayed('select#wakda', timeout=20):
             return {"success": False, "error": "Select dropdown never loaded during sniper execution."}
        
        # 2. Find best available slot
        select_wakda = page.ele('select#wakda')
        options = select_wakda.eles('tag:option')
        
        target_wakda_value = None
        for index, opt in enumerate(options):
            if index > 0 and opt.attr('value') and not opt.attr('disabled'):
                target_wakda_value = opt.attr('value')
                break
                
        if not target_wakda_value:
            return {"success": False, "error": "No available slot found during sniper execution."}
            
        logger.info(f"[SNIPER] Selected slot value: {target_wakda_value}")
        
        # 3. Fill the dropdown
        select_wakda.select(target_wakda_value)
        
        # 4. Fill the inputs
        # Note: adjust selectors if the actual site uses different name attributes
        try:
             nama_input = page.ele('@name=nama')
             if nama_input: nama_input.input(profile_data.get('nama_lengkap', ''))
             
             nik_input = page.ele('@name=nik')
             if nik_input: nik_input.input(profile_data.get('nik', ''))
             
             phone_input = page.ele('@name=phone')
             if phone_input: phone_input.input(profile_data.get('no_hp', ''))
             
             email_input = page.ele('@name=email')
             if email_input: email_input.input(profile_data.get('email', ''))
        except Exception as e:
             logger.warning(f"[SNIPER] Error filling input fields automatically: {e}")

        logger.info("[SNIPER] Submitting form ...")
        
        # Click submit using JS to bypass interceptors
        page.run_js('''
            const form = document.querySelector('form');
            if(form) form.submit();
        ''')
        
        # Wait for the next page to load after form submission
        page.wait.load_start(timeout=5) 
        
        # Attempt Math Captcha if blocked on an error modal or verification
        if solve_generic_math_captcha(page, logger):
            # If a modal appeared and we solved it, submit the modal
            page.run_js('''
                let btns = Array.from(document.querySelectorAll('button'));
                let submitBtn = btns.find(b => b.textContent.toLowerCase().includes('verifikasi') || b.textContent.toLowerCase().includes('lanjut') || b.textContent.toLowerCase().includes('submit'));
                if(submitBtn) submitBtn.click();
            ''')
            time.sleep(3) # Wait for final response

        # Check if URL reflects success
        is_success = "antrean-ambil" in page.url or "success" in page.url # Adjust to actual success criteria
        
        # --- TICKET SAVING ---
        screenshot_path = None
        if is_success:
            ticket_dir = os.path.join(os.getcwd(), "tickets")
            os.makedirs(ticket_dir, exist_ok=True)
            safe_name = profile_data.get('nik', 'unknown').replace(" ", "_")
            safe_date = target_date.replace("-", "")
            screenshot_filename = f"TICKET_{safe_name}_{safe_date}_{location_id}.png"
            screenshot_path = os.path.join(ticket_dir, screenshot_filename)
            
            time.sleep(2) # Wait for render
            page.get_screenshot(path=screenshot_path, full_page=True)
            logger.info(f"[SNIPER] 📸 Ticket Screenshot Saved: {screenshot_path}")
        
        return {
            "success": is_success,
            "url": page.url,
            "screenshot": screenshot_path
        }
            
    except Exception as e:
        logger.error(f"[SNIPER] Error during sniper execution: {e}")
        return {"success": False, "error": str(e)}


def run_drission_bot_loop(node_id: int, config: Dict[str, Any], sync_broadcast, nodes_ref: dict, nik: str):
    """
    The synchronous DrissionPage loop. This runs in a background thread.
    Uses ChromiumPage which completely evades Cloudflare by not using DevTools Protocol.
    """
    target_location = config['target_location']
    target_date = config['target_date']
    proxy = config.get('proxy')
    nama_lengkap = config['nama_lengkap']
    
    page = None
    try:
        page = _get_stealth_page(proxy, node_id)
        
        while True:
            # IMPORTANT: Check if we have been cancelled by the kill switch!
            # Since this is a thread, we can't be easily cancelled by asyncio unless we check a flag.
            if node_id not in nodes_ref:
                sync_broadcast(f"[Node {node_id}] Thread gracefully exiting...")
                break
                
            sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] ⏳ Checking quota for {target_location} (Proxy: {proxy or 'None'})")
            
            quota = check_quota(page, target_location, target_date)
            
            if quota > 0:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🟢 SUCCESS: Found {quota} slots! Triggering Sniper...")
                config_payload = {
                    "nama_lengkap": config['nama_lengkap'],
                    "nik": config['nik'],
                    "no_hp": config['no_hp'],
                    "email": config['email']
                }
                res = submit_booking(page, config_payload, target_location, target_date)
                
                if res.get("success"):
                   sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🏆 BOOKING SUCCESSFUL! URL: {res.get('url')}")
                   
                   # --- KILL SWITCH (Synchronous thread version) ---
                   kill_targets = []
                   for other_id, node_data in nodes_ref.items():
                       if other_id != node_id and node_data['config'].get('nik') == nik:
                           kill_targets.append(other_id)
                           
                   for t_id in kill_targets:
                       # This cancels the asyncio task in the main thread mapping
                       nodes_ref[t_id]["task"].cancel()
                       del nodes_ref[t_id]
                       sync_broadcast(f"[System] 🛑 KILL SWITCH ACTIVATED: Node {t_id} stopped because NIK {nik} already secured a booking.")

                else:
                   sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🔴 SNIPER FAILED: {res.get('error')}")
                   
                break # Stop looping after sniper execution
            elif quota == -1:
                # Trigger Auto-Login flow
                auto_login(page, config['email'], config['password'], sync_broadcast, node_id, nama_lengkap)
                time.sleep(3) # Briefly pause before loop restarts to check quota on target page
            elif quota == -2:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🛡️ Cloudflare aktif. Membaca halaman... Silakan centang manual jika diminta di Chrome.")
                time.sleep(5)
            elif quota == -3:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] ⛔ PEMBLOKIRAN IP TERDETEKSI! Server Antam memblokir akses sementara karena terlalu banyak request. Bot akan beristirahat selama 3 menit sebelum mencoba lagi...")
                time.sleep(180) # 3-minute cooldown
            else:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🔴 Quota full. Retrying in 10s...")
                time.sleep(10)
                
    except Exception as e:
        sync_broadcast(f"[Node {node_id}] 🔴 Critical Thread Error: {str(e)}")
    finally:
        if page:
            try:
                page.quit()
            except:
                pass
