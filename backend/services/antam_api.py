import time
import datetime
import os
import re
import logging
from typing import Dict, Any

from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import ElementNotFoundError

logger = logging.getLogger(__name__)

# Mapping from internal bot codes (stored in DB) to Antam website's HTML <select> integer values
# These were extracted from the live website's <select name="site"> element
LOCATION_CODE_TO_SITE_ID = {
    "JKT-06": "31",  # ATGM-Gedung Antam
    "JKT-01": "30",  # ATGM-Graha Dipta
    "BPN-01": "4",   # Butik Emas LM - Balikpapan
    "BDG-01": "1",   # Butik Emas LM - Bandung
    "BKS-01": "19",  # Butik Emas LM - Bekasi
    "TGR-01": "16",  # Butik Emas LM - Bintaro
    "BGR-01": "17",  # Butik Emas LM - Bogor
    "DPS-01": "5",   # Butik Emas LM - Denpasar
    "SDA-01": "20",  # Butik Emas LM - Djuanda
    "JKT-04": "6",   # Butik Emas LM - Gedung Antam
    "JKT-05": "3",   # Butik Emas LM - Graha Dipta
    "MKS-01": "11",  # Butik Emas LM - Makassar
    "MDN-01": "10",  # Butik Emas LM - Medan
    "PLB-01": "12",  # Butik Emas LM - Palembang
    "PKU-01": "24",  # Butik Emas LM - Pekanbaru
    "JKT-07": "21",  # Butik Emas LM - Puri Indah
    "SMR-01": "15",  # Butik Emas LM - Semarang
    "TGR-02": "23",  # Butik Emas LM - Serpong
    "JKT-08": "8",   # Butik Emas LM - Setiabudi One
    "SUB-01": "13",  # Butik Emas LM - Surabaya 1 Darmo
    "SUB-02": "14",  # Butik Emas LM - Surabaya 2 Pakuwon
    "YOG-01": "9",   # Butik Emas LM - Yogyakarta
}

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
    
    # Hide automation features and disable the infobars
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
    # Translate internal bot code to Antam's HTML integer site ID
    site_id = LOCATION_CODE_TO_SITE_ID.get(location_id, location_id)
    logger.info(f"Translating location '{location_id}' -> site_id '{site_id}'")
    
    url = f"https://antrean.logammulia.com/antrean?site={site_id}"
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
            
        # --- BOUTIQUE AUTO-SELECTION BUSTER ---
        # The user might be dumped on the intermediate Boutique Selection page.
        try:
            # Check if we are on the Boutique Selection page using JS (avoids NoneElement issues)
            is_boutique_page = page.run_js(
                'return !!(document.querySelector("select[name=site]") && '
                'document.querySelector("button") && '
                'document.body.innerText.includes("Tampilkan Butik"))'
            )
            if is_boutique_page:
                logger.info(f"Pre-flight: Selecting target BELM site_id='{site_id}' via Vue-aware JS...")
                
                # Use the native HTMLSelectElement prototype setter to trigger Vue.js v-model reactivity.
                # Vue 2 intercepts the native setter via Object.defineProperty, and Vue 3 via Proxy.
                # Simply setting `.value` on the element directly does NOT trigger the setter.
                # We must use the ORIGINAL native setter from the prototype chain.
                page.run_js(f'''
                    var sel = document.querySelector('select[name="site"]');
                    if (sel) {{
                        // Use the native setter from the HTMLSelectElement prototype
                        var nativeSetter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
                        nativeSetter.call(sel, '{site_id}');
                        
                        // Dispatch events that Vue.js v-model listens for
                        sel.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                ''')
                
                time.sleep(1)  # Let Vue process the change
                
                # Verify the selection actually took effect
                verify_js = 'var s=document.querySelector("select[name=site]"); return s ? s.value : "";'

                current_val = page.run_js(verify_js)

                logger.info(f"Dropdown value after JS injection: '{current_val}'")
                
                # Check if Cloudflare Turnstile is present and find the submit button
                # We find the button here (AFTER confirming we're on the boutique page) to avoid NoneElement issues
                submit_btn = page.ele('tag:button@@text():Tampilkan Butik', timeout=2)
                cf_input = page.ele('css:input[name="cf-turnstile-response"]', timeout=1)
                
                if cf_input and hasattr(cf_input, 'attr'):
                    logger.info("Waiting up to 15s for Cloudflare Turnstile token...")
                    for _ in range(15):
                        try:
                            token_val = cf_input.attr('value') or cf_input.value
                        except:
                            token_val = None
                        if token_val:
                            logger.info("Turnstile generated token! Auto-clicking Tampilkan Butik...")
                            if submit_btn and hasattr(submit_btn, 'click'):
                                submit_btn.click()  # Native isTrusted click
                            else:
                                page.run_js('document.querySelector("button[type=submit]").click()')
                            page.wait.load_start(timeout=5)
                            break
                        time.sleep(1)
                    else:
                        logger.warning("Turnstile token not generated in 15s, clicking anyway...")
                        if submit_btn and hasattr(submit_btn, 'click'):
                            submit_btn.click()
                        else:
                            page.run_js('document.querySelector("button[type=submit]").click()')
                        page.wait.load_start(timeout=5)
                else:
                    logger.info("No Turnstile detected, clicking Tampilkan Butik directly...")
                    if submit_btn and hasattr(submit_btn, 'click'):
                        submit_btn.click()  # Native isTrusted click
                    else:
                        page.run_js('document.querySelector("button[type=submit]").click()')
                    page.wait.load_start(timeout=5)
        except Exception as e:
            logger.warning(f"Boutique auto-selection error: {e}")

        # Post-navigation check
        if "/masuk" in page.url or "/login" in page.url or "/home" in page.url:
            return -1
            
        # Post-login redirect trap check: the user might be dumped on the /users profile page
        if "/users" in page.url:
            logger.info("Redirected to /users profile page. Looking for 'Menu Antrean' button...")
            menu_btn = page.ele('text:Menu Antrean', timeout=2)
            if menu_btn and str(menu_btn.tag) != 'NoneElement':
                menu_btn.click()
                page.wait.load_start(timeout=5)
            
        # Wait for the select box (wakda / quota options)
        if not page.wait.ele_displayed('select#wakda', timeout=15):
            if "/masuk" in page.url or "/login" in page.url or "/home" in page.url:
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
        error_str = str(e).lower()
        if "disconnected" in error_str or "targetclosed" in error_str:
            return -4  # Signal the main loop that the browser crashed/disconnected
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
                if sync_broadcast and node_id:
                    sync_broadcast(f"[Node {node_id}] 🧠 Solved Math: {question} = {answer}")
                
                # Natively input if possible
                try:
                    for inp in page.eles('css:input[type="text"]'):
                        if not inp.value and "email" not in str(inp.attr('name')):
                            inp.input(str(answer))
                            break
                except:
                    pass
                
                # Inject answer into empty text/number fields (skipping email) as fallback
                page.run_js(f'''
                    let inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
                    for(let inp of inputs) {{
                        if(inp.value === "" && (!inp.name || !inp.name.includes("email"))) {{
                            inp.value = "{answer}";
                        }}
                    }}
                ''')
                return True
    except Exception as ex:
        logger_obj.warning(f"Math Captcha Error: {ex}")
    return False

def solve_cloudflare_turnstile(page: ChromiumPage, logger_obj=logger, sync_broadcast=None, node_id=None):
    """Attempts to auto-click the Cloudflare Turnstile verification checkbox."""
    try:
        cf_iframe = page.get_frame('@src^https://challenges.cloudflare.com', timeout=3)
        if cf_iframe:
            cb = cf_iframe.ele('.cb-c', timeout=2) or cf_iframe.ele('tag:body', timeout=1)
            if cb:
                msg = "🤖 Auto-clicking Cloudflare Verifikasi Checkbox..."
                if sync_broadcast and node_id:
                    sync_broadcast(f"[Node {node_id}] {msg}")
                logger_obj.info(msg)
                cb.click()
                time.sleep(3)
                return True
    except Exception as e:
        pass
    return False

def auto_login(page: ChromiumPage, email: str, password: str, sync_broadcast, node_id: int, nama: str) -> bool:
    """Automates the login sequence if the bot gets redirected to /masuk."""
    sync_broadcast(f"[Node {node_id}] [{nama}] 🔑 Redirected to Login form. Starting Auto-Login...")
    try:
        # Handle the /home redirect trap
        if "/home" in page.url or page.url.rstrip('/') == "https://antrean.logammulia.com":
            sync_broadcast(f"[Node {node_id}] [{nama}] 🏠 Bypassing Homepage/Announcement...")
            login_btn = page.ele('text:Log In', timeout=2) or page.ele('text:Login', timeout=2) or page.ele('tag:a@@text():Log In', timeout=1)
            if login_btn:
                try: login_btn.click()
                except: page.get("https://antrean.logammulia.com/login", retry=0, timeout=15)
            else:
                page.get("https://antrean.logammulia.com/login", retry=0, timeout=15)
                
        # ⏳ Wait up to 60 seconds for the password input to appear in the DOM
        sync_broadcast(f"[Node {node_id}] [{nama}] 🛡️ Waiting up to 60s for Cloudflare/Splash Form to appear...")
        pass_inp = page.ele('css:input[type="password"]', timeout=60)
        
        # Try to close any overlaying Splash Screen if one appears on the Login page
        try:
            splash_close = page.ele('text:Tutup', timeout=1) or page.ele('css:.close', timeout=1)
            if splash_close and splash_close.is_displayed():
                splash_close.click() # Native click
                time.sleep(1)
        except:
            pass
            
        if not pass_inp:
            sync_broadcast(f"[Node {node_id}] [{nama}] ❌ Timeout! Cloudflare took too long or form not found. Restarting loop...")
            try:
                found_inputs = [f"{e.attr('name')} ({e.attr('type')})" for e in page.eles('tag:input')]
                sync_broadcast(f"[Node {node_id}] [{nama}] 🔍 DIAGNOSTIC Inputs: {', '.join(found_inputs)} | URL: {page.url}")
            except:
                pass
            return False
        
        email_inp = page.ele('@name=email') or page.ele('css:input[type="email"]') or page.ele('@name=username')
        
        if email_inp: 
            try:
                email_inp.clear()
                email_inp.input(email)
            except Exception as e:
                logger.warning(f"Ignorable invalid element error for email: {e}")
            
        if pass_inp: 
            try:
                pass_inp.clear()
                pass_inp.input(password)
            except Exception as e:
                logger.warning(f"Ignorable invalid element error for password: {e}")
        
        # Check and solve captcha
        solve_generic_math_captcha(page, logger, sync_broadcast, node_id)
        
        sync_broadcast(f"[Node {node_id}] [{nama}] 🚀 Submitting login credentials...")
        
        # NATIVE TRUSTED CLICK: Turnstile requires a real browser event, not a JS generated synthetic event
        try:
            login_form = pass_inp.parent('tag:form')
            if login_form:
                submit_btn = login_form.ele('tag:button', timeout=1) or login_form.ele('css:input[type="submit"]')
                if submit_btn:
                    submit_btn.click() # Real human click!
                else:
                    pass_inp.input('\n')
            else:
                pass_inp.input('\n')
        except Exception as e:
            logger.warning(f"Native trusted form submit failed: {e}")
            pass_inp.input('\n')
        
        # Wait for redirect to antrean home
        page.wait.load_start(timeout=5)
        time.sleep(4) # Let cookie sink into DrissionPage
        
        # Only verify success if the password field is no longer on the screen
        if not page.ele('css:input[type="password"]', timeout=2):
            sync_broadcast(f"[Node {node_id}] [{nama}] ✅ Auto-Login Successful! Returning to Quota Target...")
            
            # If immediately dumped to the profile page, proactively redirect to the queue page
            if "/users" in page.url:
                menu_btn = page.ele('text:Menu Antrean', timeout=2)
                if menu_btn and str(menu_btn.tag) != 'NoneElement':
                    menu_btn.click()
                    page.wait.load_start(timeout=5)
            
            return True
        else:
            sync_broadcast(f"[Node {node_id}] [{nama}] ❌ Login Form still present (Wrong Password/Captcha?). Retrying...")
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
                    select_belm = page.ele('tag:select', timeout=1)
                    if select_belm:
                        try:
                            select_belm.select(location_id)
                        except:
                            for opt in select_belm.eles('tag:option'):
                                if location_id.lower() in opt.text.lower() or location_id.lower() in str(opt.attr('value')).lower():
                                    select_belm.select(opt.attr('value'))
                                    break
                                    
                        time.sleep(1)
                        submit_btn = page.ele('text:Tampilkan Butik', timeout=1) or page.ele('css:button[type="submit"]')
                        if submit_btn:
                            submit_btn.click() # Native trusted click
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
        
        # Click submit natively to trigger JS event listeners (trusted event)
        final_btn = page.ele('text:Lanjut', timeout=1) or page.ele('text:Submit', timeout=1) or page.ele('css:button[type="submit"]')
        if final_btn:
            final_btn.click() # Native trusted
        else:
            page.ele('css:form').submit()
        
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
            elif quota == -2:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🛡️ Cloudflare aktif. Mencoba auto-verifikasi checklist...")
                time.sleep(2)
                solve_cloudflare_turnstile(page, logger, sync_broadcast, node_id)
            elif quota == -3:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] ⛔ PEMBLOKIRAN IP TERDETEKSI! Server Antam memblokir akses sementara karena terlalu banyak request. Bot akan beristirahat selama 3 menit sebelum mencoba lagi...")
                time.sleep(180) # 3-minute cooldown
                continue
            elif quota == -4:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] ⚠️ Browser connection lost! Requesting a fresh browser instance...")
                try:
                    page.quit()
                except:
                    pass
                time.sleep(2)
                page = _get_stealth_page(proxy, node_id)
                continue
            else:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🔴 Quota full.")
                
            # Smart Idle check applied to non-critical loops (quota 0, -1, -2)
            current_hour = datetime.datetime.now().hour
            if current_hour < 7:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🌙 Smart Idle: Antrean belum buka (Jam {current_hour}). Refresh setiap 5 menit...")
                time.sleep(300)
            else:
                # Normal operational hour delays
                if quota == -1:
                    time.sleep(3)
                elif quota == -2:
                    time.sleep(5)
                else:
                    sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] Retrying in 10s...")
                    time.sleep(10)
                
    except Exception as e:
        sync_broadcast(f"[Node {node_id}] 🔴 Critical Thread Error: {str(e)}")
    finally:
        if page:
            try:
                page.quit()
            except:
                pass
