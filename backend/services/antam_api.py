import time
import datetime
import os
import re
import httpx
import logging
from typing import Dict, Any

from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import ElementNotFoundError

# CRITICAL: Fix Windows DPI Awareness BEFORE importing pyautogui
# Without this, PyAutoGUI silently fails on 125%+ DPI scaling monitors
import sys
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass

try:
    import pyautogui
    pyautogui.FAILSAFE = False  # Prevent abort if mouse hits corner
    pyautogui.PAUSE = 0.3      # Small delay between actions for human-like behavior
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

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

# Jam operasional akan dideteksi secara dinamis dari website

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
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--no-first-run')
    co.set_argument('--password-store=basic')
    co.set_argument('--use-mock-keychain')
    # DO NOT override user_agent! It breaks Sec-CH-UA sync causing Turnstile infinite loops!
    
    if proxy:
        co.set_proxy(proxy)
        
    page = ChromiumPage(addr_or_opts=co)
    
    # 💥 ULTIMATE CLOUDFLARE BYPASS: Inject scripts before any page loads
    # This completely erases the webdriver flag from the JavaScript environment
    # Many times, this causes CF to auto-pass without even showing a checkbox!
    anti_detect_js = '''
        Object.defineProperty(navigator, 'webdriver', {
          get: () => undefined
        });
    '''
    # Playwright's add_init_script equivalent in DrissionPage is page.add_init_js or executing CDP directly
    try:
        page.run_cdp('Page.addScriptToEvaluateOnNewDocument', source=anti_detect_js)
    except Exception as e:
        logger.warning(f"Failed to inject Anti-Detect JS: {e}")
    page.set.timeouts(page_load=15, script=15)
    return page

def safe_get(page, attr="url", retries=5):
    """Safely access page properties (url, title, html) with retries for 'The page is refreshed' errors."""
    for i in range(retries):
        try:
            if attr == "url": return page.url
            if attr == "title": return page.title
            if attr == "html": return page.html
        except Exception as e:
            if "refreshed" in str(e).lower() or "loading" in str(e).lower():
                time.sleep(1)
                continue
            raise e
    return ""

def safe_run_js(page, script, retries=5):
    """Safely run JS on page with retries for 'The page is refreshed' errors."""
    for i in range(retries):
        try:
            return page.run_js(script)
        except Exception as e:
            if "refreshed" in str(e).lower() or "loading" in str(e).lower():
                time.sleep(1)
                continue
            raise e
    return None

def handle_oops_modal(page, logger_obj=logger, sync_broadcast=None, node_id=None):
    """Detects and closes the 'Oops' error modal if reCAPTCHA or other errors occur."""
    try:
        # Looking for the "Oops" modal seen in screenshot
        oops_modal = page.ele('text:Oops', timeout=1)
        if oops_modal and oops_modal.is_displayed():
            msg_text = safe_get(page, "html").lower()
            if "recaptcha" in msg_text or "captcha" in msg_text:
                msg = "⚠️ Modal 'Oops' terdeteksi (Masalah CAPTCHA). Menutup dan mencoba ulang..."
                logger_obj.warning(msg)
                if sync_broadcast and node_id: sync_broadcast(f"[Node {node_id}] {msg}")
                
                ok_btn = page.ele('text:OK', timeout=1) or page.ele('css:button.swal2-confirm')
                if ok_btn: 
                    ok_btn.click()
                    time.sleep(1)
                
                # Refresh to start clean
                page.refresh()
                return True
    except:
        pass
    return False

def check_quota(page: ChromiumPage, location_id: str, sync_broadcast=None, node_id=None, nama=None) -> int:
    """
    Returns the integer quota available (or 1 if ANY slot is found), 0 if none.
    -1 means "Needs Login", -2 means "Cloudflare Active".
    """
    # Translate internal bot code to Antam's HTML integer site ID
    site_id = LOCATION_CODE_TO_SITE_ID.get(location_id, location_id)
    logger.info(f"Translating location '{location_id}' -> site_id '{site_id}'")
    
    # RESET opening hour detection state for this run
    page.run_js('window.__detected_opening_hour = null')
    
    url = f"https://antrean.logammulia.com/antrean?site={site_id}"
    
    # --- SMART STATE DETECTION & STATUS REPORTING ---
    # Robustly handle the DrissionPage refresh exception using safe_get helper
    title_lower = safe_get(page, "title").lower()
    html_lower = safe_get(page, "html").lower()
    page_url = safe_get(page, "url")
    
    try:
    # Stricter CF Detection: Don't just look at HTML (Rocket Loader false positive), look at Title OR visible challenge iframe
        is_cf = ("just a moment" in title_lower or "verifying your connection" in title_lower) or \
                (page.ele('css:iframe[src*="challenges.cloudflare.com"]', timeout=0.5) and "challenges.cloudflare.com" in html_lower)
        
        is_login = "/masuk" in page_url or "/login" in page_url or "/home" in page_url
        is_boutique = ("select" in html_lower and "tampilkan butik" in html_lower) or \
                      ("antrean belm" in html_lower and "pilih belm" in html_lower)
        is_quota_page = "select#wakda" in html_lower
        is_announcement = page.ele('text:Pengumuman', timeout=0.5) or page.ele('css:.modal-content', timeout=0.5)
        
        # ACTIVE PAGE GUARD: If we are on login or boutique selection, we are NOT in night mode.
        is_active_page = is_login or is_boutique or is_quota_page
        
        # --- DYNAMIC STATUS REPORTING (ADAPTIVE LOGS) ---
        if sync_broadcast and node_id:
            if is_cf:
                sync_broadcast(f"[Node {node_id}] [{nama or 'Bot'}] 🛡️ Cloudflare challenge active (Title: {page.title}).")
            elif is_announcement:
                sync_broadcast(f"[Node {node_id}] [{nama or 'Bot'}] 📢 Announcement Pop-up detected.")
            elif is_login:
                sync_broadcast(f"[Node {node_id}] [{nama or 'Bot'}] 🔑 On Login/Home page.")
            elif is_boutique:
                sync_broadcast(f"[Node {node_id}] [{nama or 'Bot'}] 🏬 On Boutique Selection page.")
            elif is_quota_page:
                sync_broadcast(f"[Node {node_id}] [{nama or 'Bot'}] ✅ On Quota Selection page.")

        # --- SMART NAVIGATION ---
        # ONLY navigate if we are totally lost (not on any of the above pages)
        # We also check if we are on a login or boutique page - if so, we DON'T reload.
        if not (is_cf or is_login or is_boutique or is_quota_page):
            logger.info(f"Navigating to {url} to check slots...")
            try:
                page.get(url, retry=0, timeout=12)
                page.wait.load_complete(timeout=5) # Ensure stable state
            except:
                pass 
        else:
            logger.info(f"Adaptive: State recognized as {page.url}. No reload needed.")

        # --- ERROR & BLOCK DETECTION ---
        # 1. Action Not Allowed (CSRF/Session Error)
        if "the action you have requested is not allowed" in html_lower or page.ele('text:An Error Was Encountered', timeout=1):
            if "not allowed" in html_lower:
                msg = "⚠️ Session Error (Action Not Allowed) detected. Resetting..."
                if sync_broadcast and node_id: sync_broadcast(f"[Node {node_id}] {msg}")
                kembali_btn = page.ele('text:Kembali', timeout=1) or page.ele('tag:button@@text():Kembali')
                if kembali_btn:
                    kembali_btn.click()
                else:
                    page.get("https://antrean.logammulia.com/login", retry=0, timeout=10)
                return 0 # Immediate retry

        # 2. IP Blocking detection
        if "pemblokiran ip" in html_lower:
            if sync_broadcast and node_id:
                sync_broadcast(f"[Node {node_id}] [{nama or 'Bot'}] ⛔ IP Blocked/Limit detected.")
            return -3
            
        # --- BOUTIQUE AUTO-SELECTION BUSTER ---
        is_boutique_page = page.run_js(
            'return !!(document.querySelector("select[name=site]") && '
            'document.querySelector("button") && '
            'document.body.innerText.includes("Tampilkan Butik"))'
        )
        if is_boutique_page:
            logger.info(f"Pre-flight: Selecting target BELM site_id='{site_id}'...")
            page.run_js(f'''
                var sel = document.querySelector('select[name="site"]');
                if (sel) {{
                    var nativeSetter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
                    nativeSetter.call(sel, '{site_id}');
                    sel.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            ''')
            time.sleep(1)
            submit_btn = page.ele('tag:button@@text():Tampilkan Butik', timeout=2)
            cf_input = page.ele('css:input[name="cf-turnstile-response"]', timeout=1)
            if cf_input and hasattr(cf_input, 'attr'):
                for _ in range(15):
                    if cf_input.attr('value') or cf_input.value:
                        if submit_btn: submit_btn.click()
                        page.wait.load_start(timeout=5)
                        break
                    time.sleep(1)
            elif submit_btn:
                submit_btn.click()
                page.wait.load_start(timeout=5)

        # Final checks
        page_url = safe_get(page, "url")
        if "/masuk" in page_url or "/login" in page_url or "/home" in page_url:
            return -1
        if "/users" in page_url:
            menu_btn = page.ele('text:Menu Antrean', timeout=2)
            if menu_btn and str(menu_btn.tag) != 'NoneElement':
                menu_btn.click()
                page.wait.load_start(timeout=5)
            
        if not page.wait.ele_displayed('select#wakda', timeout=15):
            title = safe_get(page, "title").lower()
            h = safe_get(page, "html").lower()
            
            # 1. Deteksi Jam Operasional Otomatis (Regex)
            # Mencari teks spesifik yang menunjukkan antrean ditutup
            target_text = re.search(r'(antrean\s+dibuka|kembali)\s+pukul\s*(\d{1,2})[:.]?(\d{0,2})', h)
            if target_text and not is_active_page:
                detected_hour = int(target_text.group(2))
                logger.info(f"Jam operasional terdeteksi secara otomatis: Jam {detected_hour}")
                page.run_js(f'window.__detected_opening_hour = {detected_hour}')
                return -5 # CODE -5: Standby Mode (Night Mode)

            # 2. Strict CF verification again
            if "just a moment" in title or "verifying your connection" in title or \
               (page.ele('css:iframe[src*="challenges.cloudflare.com"]', timeout=0.5) and "challenges.cloudflare.com" in h):
                return -2
            
            page_url = safe_get(page, "url")
            if "/masuk" in page_url or "/login" in page_url or "/home" in page_url:
                return -1
            return 0 

        if sync_broadcast and node_id:
            sync_broadcast(f"[Node {node_id}] [{nama or 'Bot'}] ⏳ Extracting slots from dropdown...")
            
        # Jika berhasil sampai sini, hapus deteksi jam karena sudah buka
        page.run_js('window.__detected_opening_hour = null')

        select_wakda = page.ele('select#wakda')
        options = select_wakda.eles('tag:option')
        available_slots = []
        for index, opt in enumerate(options):
            if index > 0 and opt.attr('value') and not opt.attr('disabled'):
                available_slots.append({'value': opt.attr('value'), 'text': opt.text})
        
        return len(available_slots) if available_slots else 0
            
    except Exception as e:
        logger.error(f"Error checking quota: {e}")
        error_str = str(e).lower()
        if "disconnected" in error_str or "targetclosed" in error_str:
            return -4
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
    """Answers the math captcha by looking at the label connected to the answer input."""
    try:
        time.sleep(1.5)
        # 1. Direct approach: Find the input and its parent label/text
        math_input = page.ele('css:input[placeholder*="Jawaban"]') or page.ele('css:input[name*="captcha"]')
        if not math_input:
            # Fallback to whole page search
            html = safe_get(page, "html").lower()
            math_match = re.search(r'(\d+\s+(ditambah|dikurangi|dikali|dibagi)\s+\d+)', html)
            if not math_match: return False
            question = math_match.group(1)
        else:
            # Get text from the parent or preceding element (usually "Hitunglah X + Y ?")
            question_context = math_input.parent().text if math_input.parent() else ""
            math_match = re.search(r'(\d+\s+(ditambah|dikurangi|dikali|dibagi)\s+\d+)', question_context)
            if not math_match:
                # Try siblings
                question_context = page.html # Last resort
                math_match = re.search(r'(\d+\s+(ditambah|dikurangi|dikali|dibagi)\s+\d+)', question_context)
            
            if not math_match: return False
            question = math_match.group(1)

        answer = solve_math_question(question)
        if not answer: return False
        
        logger_obj.info(f"Solved Math: {question} = {answer}")
        if sync_broadcast and node_id:
            sync_broadcast(f"[Node {node_id}] 🧠 Solved Math: {question} = {answer}")
        
        # Input answer
        if math_input:
            math_input.clear()
            math_input.input(str(answer))
        
        # JS Injection for fast coverage
        page.run_js(f'''
            let inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
            for(let inp of inputs) {{
                let p = (inp.placeholder || "").toLowerCase();
                let n = (inp.name || "").toLowerCase();
                if((p.includes("jawaban") || n.includes("captcha")) && inp.value === "") {{
                    inp.value = "{answer}";
                }}
            }}
        ''')
        return True
    except Exception as ex:
        logger_obj.warning(f"Math Captcha Error: {ex}")
    return False

# ============================================================================
# CDP-BASED CLOUDFLARE TURNSTILE BYPASS (Based on cf-autoclick technique)
# Uses Chrome DevTools Protocol Input.dispatchMouseEvent to generate
# genuine isTrusted:true click events that Cloudflare's iframe accepts.
# NO PyAutoGUI needed, NO physical mouse, WORKS with multiple bots!
# ============================================================================

def solve_cloudflare_cdp(page: ChromiumPage, logger_obj=logger, sync_broadcast=None, node_id=None) -> bool:
    """
    Bypass Cloudflare Turnstile using CDP Input.dispatchMouseEvent.
    
    Strategy (from cf-autoclick Chrome Extension):
    1. Use DOM.getFlattenedDocument with pierce:true to find the Turnstile iframe.
    2. Use DOM.getBoxModel to get its pixel coordinates.
    3. Calculate checkbox position using empirical ratios.
    4. Fire Input.dispatchMouseEvent (generates isTrusted:true click).
    """
    try:
        # --- SAFE ACCESS PAGE PROPERTIES ---
        title = safe_get(page, "title").lower()
        html = safe_get(page, "html").lower()
            
        is_active_cf = "just a moment" in title or "verifying your connection" in title or \
                       (page.ele('css:iframe[src*="challenges.cloudflare.com"]', timeout=0.5) and "challenges.cloudflare.com" in html)

        if not is_active_cf:
            logger_obj.info("✅ Cloudflare challenge not active (Title check passed). Skipping CDP.")
            return True

        msg = "🔍 Mencari iframe Cloudflare Turnstile via CDP..."

        # Step 1: Enable DOM and find the Turnstile iframe (with retry)
        page.run_cdp('DOM.enable')
        
        iframe_node = None
        for attempt in range(15): # Retry for up to 15 seconds
            result = page.run_cdp('DOM.getFlattenedDocument', depth=-1, pierce=True)
            nodes = result.get('nodes', [])

            for node in nodes:
                if node.get('nodeName') == 'IFRAME':
                    attrs = node.get('attributes', [])
                    for i in range(0, len(attrs), 2):
                        if attrs[i] == 'src' and 'challenges.cloudflare.com' in attrs[i + 1]:
                            iframe_node = node
                            break
                    if iframe_node:
                        break
            
            if iframe_node:
                break
            time.sleep(1)

        if not iframe_node:
            msg = "❌ Iframe Cloudflare Turnstile tidak ditemukan di DOM setelah 15 detik."
            logger_obj.warning(msg)
            if sync_broadcast and node_id:
                sync_broadcast(f"[Node {node_id}] {msg}")
            return False

        logger_obj.info(f"✅ Turnstile iframe found (nodeId={iframe_node['nodeId']})")

        # Step 2: Get iframe box model coordinates
        box = page.run_cdp('DOM.getBoxModel', nodeId=iframe_node['nodeId'])
        content = box['model']['content']
        x_start, y_start = content[0], content[1]
        x_end, y_end = content[4], content[5]
        iframe_w = x_end - x_start
        iframe_h = y_end - y_start

        logger_obj.info(f"Iframe at ({x_start},{y_start}) size {iframe_w}x{iframe_h}")

        # Step 3: Try multiple checkbox position ratios
        # The checkbox is inside a Shadow DOM within the Turnstile iframe
        ratios = [
            (0.12, 0.52),  # Primary: center of checkbox square
            (0.15, 0.50),  # Slightly right
            (0.10, 0.50),  # Slightly left
            (0.20, 0.50),  # Further right
            (0.08, 0.50),  # Further left
        ]

        for idx, (x_r, y_r) in enumerate(ratios):
            cx = x_start + (iframe_w * x_r)
            cy = y_start + (iframe_h * y_r)

            msg = f"🎯 CDP Click #{idx+1}: ({cx:.0f},{cy:.0f}) ratio=({x_r},{y_r})"
            logger_obj.info(msg)
            if sync_broadcast and node_id:
                sync_broadcast(f"[Node {node_id}] {msg}")

            # Fire CDP mouse events (generates isTrusted:true!)
            page.run_cdp('Input.dispatchMouseEvent',
                type='mouseMoved', x=cx, y=cy, button='none')
            time.sleep(0.15)
            page.run_cdp('Input.dispatchMouseEvent',
                type='mousePressed', x=cx, y=cy, button='left', buttons=1, clickCount=1)
            time.sleep(0.05)
            page.run_cdp('Input.dispatchMouseEvent',
                type='mouseReleased', x=cx, y=cy, button='left', buttons=0, clickCount=1)

            time.sleep(5)

            # Check if Cloudflare passed
            html = safe_get(page, "html").lower()
            if 'just a moment' not in html and 'challenges.cloudflare.com' not in html:
                msg = f"🎉 Cloudflare BERHASIL dilewati via CDP! (ratio {x_r},{y_r})"
                logger_obj.info(msg)
                if sync_broadcast and node_id:
                    sync_broadcast(f"[Node {node_id}] {msg}")
                
                # Settle down for 5 seconds to let redirects or page state update
                time.sleep(5)
                return True

        msg = "❌ Semua CDP click ratios gagal melewati Cloudflare."
        logger_obj.warning(msg)
        if sync_broadcast and node_id:
            sync_broadcast(f"[Node {node_id}] {msg}")
        return False

    except Exception as e:
        logger_obj.error(f"CDP Cloudflare Bypass Error: {e}")
        if sync_broadcast and node_id:
            sync_broadcast(f"[Node {node_id}] ❌ CDP Error: {e}")
        return False




def auto_login(page: ChromiumPage, email: str, password: str, sync_broadcast, node_id: int, nama: str) -> bool:
    """Automates the login sequence if the bot gets redirected to /masuk."""
    sync_broadcast(f"[Node {node_id}] [{nama}] 🤖 Handling Auto-Login sequence...")
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
                
        
        pass_inp = None
        for _ in range(30): # 30 iterations of 2s = 60s
            pass_inp = page.ele('css:input[type="password"]', timeout=2)
            if pass_inp:
                break
            
            # Proactive Cloudflare detection during the wait
            # STRICTOR DETECTION: Use Title + visible indicator
            title = safe_get(page, "title").lower()
            html = safe_get(page, "html").lower()
            is_active_cf = "just a moment" in title or "verifying your connection" in title or \
                           (page.ele('css:iframe[src*="challenges.cloudflare.com"]', timeout=0.5) and "challenges.cloudflare.com" in html)

            if is_active_cf:
                sync_broadcast(f"[Node {node_id}] [{nama}] 🛡️ Cloudflare detected during login wait. Attempting CDP bypass...")
                solve_cloudflare_cdp(page, logger, sync_broadcast, node_id)
                time.sleep(2)
                continue
            
            # Try to close any overlaying Splash Screen, "Oops" modals, or Action Not Allowed errors
            try:
                handle_oops_modal(page, logger, sync_broadcast, node_id)
                
                # Check for Action Not Allowed in Login Wait
                if "the action you have requested is not allowed" in safe_get(page, "html").lower():
                    kembali_btn = page.ele('text:Kembali', timeout=1)
                    if kembali_btn: 
                        kembali_btn.click()
                        time.sleep(1)
                    else:
                        page.get("https://antrean.logammulia.com/login", retry=0, timeout=10)
                
                splash_close = page.ele('text:Tutup', timeout=1) or page.ele('css:.close', timeout=1)
                if splash_close and splash_close.is_displayed():
                    splash_close.click()
                    time.sleep(1)
            except:
                pass

        if not pass_inp:
            sync_broadcast(f"[Node {node_id}] [{nama}] ❌ Timeout! Cloudflare took too long or form not found. Restarting loop...")
            try:
                found_inputs = [f"{e.attr('name')} ({e.attr('type')})" for e in page.eles('tag:input')]
                page_url = safe_get(page, "url")
                sync_broadcast(f"[Node {node_id}] [{nama}] 🔍 DIAGNOSTIC Inputs: {', '.join(found_inputs)} | URL: {page_url}")
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
        page_url = safe_get(page, "url")
        if not page.ele('css:input[type="password"]', timeout=2):
            sync_broadcast(f"[Node {node_id}] [{nama}] ✅ Auto-Login Successful! Returning to Quota Target...")
            
            # If immediately dumped to the profile page, proactively redirect to the queue page
            if "/users" in page_url:
                menu_btn = page.ele('text:Menu Antrean', timeout=2)
                if menu_btn and str(menu_btn.tag) != 'NoneElement':
                    menu_btn.click()
                    page.wait.load_start(timeout=5)
            
            return True
        else:
            # CHECK FOR OOPS MODAL
            if handle_oops_modal(page, logger, sync_broadcast, node_id):
                return False # Let the caller retry
                
            sync_broadcast(f"[Node {node_id}] [{nama}] ❌ Login Form still present (Wrong Password/Captcha?). Retrying...")
            return False
            
    except Exception as e:
        sync_broadcast(f"[Node {node_id}] [{nama}] ⚠️ Login automation error: {e}")
        return False

def submit_booking(page: ChromiumPage, profile_data: Dict[str, str], location_id: str) -> Dict[str, Any]:
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
                text = opt.text.lower()
                if "tersedia 0/" in text:
                    logger.info(f"[SNIPER] Skipping slot with 0 availability: {opt.text}")
                    continue
                target_wakda_value = opt.attr('value')
                break
                
        if not target_wakda_value:
            return {"success": False, "error": "No available slot found during sniper execution."}
            
        logger.info(f"[SNIPER] Selected slot value: {target_wakda_value}")
        
        # 3. Fill the inputs (INSTANT INJECTION MODE)
        logger.info("[SNIPER] Mengisi formulir secara instan...")
        try:
            # Gunakan JavaScript untuk mengisi semua field sekaligus agar jauh lebih cepat dibanding mengetik manual
            form_payload = {
                "nama": profile_data.get('nama_lengkap', ''),
                "nik": profile_data.get('nik', ''),
                "phone": profile_data.get('no_hp', ''),
                "email": profile_data.get('email', '')
            }
            
            page.run_js(f'''
                var data = {form_payload};
                for (var key in data) {{
                    var el = document.querySelector('[name="' + key + '"]');
                    if (el) {{
                        var nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                        nativeSetter.call(el, data[key]);
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}
            ''')
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
            current_date_str = datetime.datetime.now().strftime('%Y%p%d')
            screenshot_filename = f"TICKET_{safe_name}_{current_date_str}_{location_id}.png"
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
                
            quota = check_quota(page, target_location, sync_broadcast, node_id, nama_lengkap)
            
            if quota > 0:
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🟢 SUCCESS: Found {quota} slots! Triggering Sniper...")
                config_payload = {
                    "nama_lengkap": config['nama_lengkap'],
                    "nik": config['nik'],
                    "no_hp": config['no_hp'],
                    "email": config['email']
                }
                res = submit_booking(page, config_payload, target_location)
                
                if res.get("success"):
                   sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🏆 BOOKING SUCCESSFUL! URL: {res.get('url')}")
                   
                   # --- KILL SWITCH (Synchronous thread version) ---
                   kill_targets = []
                   for other_id, node_data in nodes_ref.items():
                       if other_id != node_id and node_data['config'].get('nik') == nik:
                           kill_targets.append(other_id)
                           
                   for t_id in kill_targets:
                       nodes_ref[t_id]["task"].cancel()
                       del nodes_ref[t_id]
                       sync_broadcast(f"[System] 🛑 KILL SWITCH ACTIVATED: Node {t_id} stopped because NIK {nik} already secured a booking.")

                else:
                   sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🔴 SNIPER FAILED: {res.get('error')}")
                   
                break # Stop looping after sniper execution

            elif quota == -1:
                # Trigger Auto-Login flow
                auto_login(page, config['email'], config['password'], sync_broadcast, node_id, nama_lengkap)
                continue 
                
            elif quota == -2:
                # Cloudflare challenge
                solve_cloudflare_cdp(page, logger, sync_broadcast, node_id)
                continue 
                
            elif quota == -3:
                # IP Blocked
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] ⛔ PEMBLOKIRAN IP TERDETEKSI! Server Antam memblokir akses sementara. Cooldown 3 menit...")
                time.sleep(180)
                continue
                
            elif quota == -4:
                # Crash / Disconnect
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] ⚠️ Browser lost! Requesting fresh instance...")
                try: page.quit()
                except: pass
                time.sleep(2)
                page = _get_stealth_page(proxy, node_id)
                continue
                
            elif quota == -5:
                # Night Mode (Wait for opening hour)
                detected_h = safe_run_js(page, 'return window.__detected_opening_hour')
                
                if detected_h is not None:
                    opening_hour = int(detected_h)
                    current_hour = datetime.datetime.now().hour
                    
                    if current_hour < opening_hour:
                        sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🌙 Standby: Butik buka jam {opening_hour} (Sekarang jam {current_hour}). Tidur 5 menit...")
                        time.sleep(300)
                    else:
                        # Closing in on opening time, faster refresh
                        sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🕒 Jam buka mendekat ({opening_hour}:00). Standby tiap 10 detik...")
                        time.sleep(10)
                else:
                    # If we got -5 but NO opening hour was captured, something is wrong or ambiguous.
                    # Do NOT sleep for 5 minutes. Just a moderate refresh.
                    sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] ⚠️ Standby detected but hour unknown. Refreshing in 30s...")
                    time.sleep(30)
                continue
                
            else:
                # quota == 0 (Quota full or unknown)
                sync_broadcast(f"[Node {node_id}] [{nama_lengkap}] 🔴 Quota full. Retrying in 10s...")
                time.sleep(10)
                continue
                
    except Exception as e:
        sync_broadcast(f"[Node {node_id}] 🔴 Critical Thread Error: {str(e)}")
    finally:
        if page:
            try:
                page.quit()
            except:
                pass
