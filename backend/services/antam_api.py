import asyncio
import logging
from typing import Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup

from backend.models import Profile, TargetLocation

logger = logging.getLogger(__name__)

async def _get_stealth_page(context):
    """
    Helper function to create a new page with stealth applied
    to help bypass Cloudflare Turnstile.
    """
    page = await context.new_page()
    stealth = Stealth()
    await stealth.apply_stealth_async(page)
    return page

async def check_quota(page, location_id: str, target_date: str) -> int:
    """
    Tracker Module:
    Navigates to the designated Antrean page for the specific location.
    Uses Playwright and BeautifulSoup to parse the HTML and find available slots.
    Returns the integer quota available (or 1 if ANY slot is found), 0 if none.
    """
    url = f"https://antrean.logammulia.com/antrean?site={location_id}"
    logger.info(f"Navigating to {url} to check slots...")

    try:
        await page.goto(url, timeout=30000)
        
        # Wait for either the Cloudflare challenge to pass or the select box to appear
        try:
            await page.wait_for_selector('select#wakda', timeout=20000)
        except Exception:
            logger.warning("Timeout waiting for 'select#wakda'. Cloudflare block or page structural change.")
            # We can dump HTML for debugging
            html_content = await page.content()
            if "cloudflare" in html_content.lower() or "challenge" in html_content.lower():
                 logger.error("Cloudflare challenge detected and not passed.")
            return 0

        # Page is loaded, let's parse the HTML using BeautifulSoup
        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        select_wakda = soup.find('select', id='wakda')
        if not select_wakda:
            logger.error("Could not find <select id='wakda'> in the DOM.")
            return 0
            
        options = select_wakda.find_all('option')
        available_slots = []
        
        for index, opt in enumerate(options):
            # Skip the first default/placeholder option
            if index == 0 or not opt.get('value'):
                continue
                
            # Check if it lacks the 'disabled' attribute
            if not opt.has_attr('disabled'):
                val = opt.get('value')
                text = opt.text.strip()
                available_slots.append({'value': val, 'text': text})
        
        if available_slots:
            logger.info(f"Available slots found: {available_slots}")
            # Return the number of available time slots as proxy for quota
            return len(available_slots) 
        else:
            logger.info("No available slots found (all options disabled).")
            return 0
            
    except Exception as e:
        logger.error(f"Error checking quota via Playwright: {e}")
        return 0


import re

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

async def submit_booking(page, profile_data: Dict[str, str], location_id: str, target_date: str) -> Dict[str, Any]:
    """
    Sniper Module:
    If slots are found, this will immediately navigate, extract the CSRF token and wakda value,
    inject user data, and submit the form explicitly via Playwright.
    """
    url = f"https://antrean.logammulia.com/antrean?site={location_id}"
    logger.info(f"[SNIPER] Starting sequence for {profile_data.get('nama_lengkap', 'Unknown')} at {location_id}")
    
    try:
        # 1. Navigate to the form page
        await page.goto(url, timeout=30000)
        await page.wait_for_selector('select#wakda', timeout=20000)
        
        # 2. Re-parse to find best available slot (wakda)
        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        select_wakda = soup.find('select', id='wakda')
        options = select_wakda.find_all('option') if select_wakda else []
        
        target_wakda_value = None
        for index, opt in enumerate(options):
            if index > 0 and opt.get('value') and not opt.has_attr('disabled'):
                target_wakda_value = opt.get('value')
                break # Take the first available
                
        if not target_wakda_value:
            return {"success": False, "error": "No available slot found during sniper execution."}
            
        logger.info(f"[SNIPER] Selected slot value: {target_wakda_value}")
        
        # 3. Extract CSRF token
        # Expected tag: <input type="hidden" name="csrf_test_name" value="...">
        csrf_input = soup.find('input', {'name': 'csrf_test_name'})
        csrf_token = csrf_input.get('value') if csrf_input else None
        
        if not csrf_token:
            logger.error("[SNIPER] Failed to extract CSRF token!")
            return {"success": False, "error": "CSRF token extraction failed."}
            
        logger.info(f"[SNIPER] Extracted CSRF token: {csrf_token[:10]}...")
        
        # 4. Inject Values and Submit Form
        # Based on standard logic, we fill the inputs by their ID or Name.
        # Assuming these IDs/Names exist on the form based on standard profiling
        
        # Fill the select dropdown using Playwright's native select_option
        await page.select_option('select#wakda', value=target_wakda_value)
        
        # Fill the inputs
        # Modify these selectors according to the exact form IDs from the real website parsing
        try:
             await page.fill('input[name="nama"]', profile_data.get('nama_lengkap', ''))
             await page.fill('input[name="nik"]', profile_data.get('nik', ''))
             await page.fill('input[name="phone"]', profile_data.get('no_hp', ''))
             await page.fill('input[name="email"]', profile_data.get('email', ''))
        except Exception as e:
             logger.warning(f"[SNIPER] Error filling input fields automatically. Attempting force submit. Msg: {e}")

        # Sometimes bots use JavaScript to bypass UI blocks
        # Here we demonstrate setting value directly via evaluate if UI is tricky
        await page.evaluate(f'''() => {{
            document.querySelector('input[name="csrf_test_name"]').value = "{csrf_token}";
        }}''')
        
        logger.info("[SNIPER] Submitting form ...")
        
        # Helper to check Math Captcha
        async def handle_math_captcha(page_obj):
            try:
                # Generic Math Label check (e.g. looks for any block tracking "?", "+", "-", "ditambah", "dikali")
                # In real-world, we narrow this down with the specific modal selector.
                # We wait 2s to see if a Math Modal appears.
                await asyncio.sleep(2)
                page_html = await page_obj.content()
                
                if "ditambah" in page_html.lower() or "dikurangi" in page_html.lower() or "dikali" in page_html.lower():
                    logger.info("[SNIPER] 🧮 Math Verification Detected! Deploying Solver...")
                    # Seek the exact label holding the question. Often it's a <label> or standard <div>
                    # Extract the body text and run through solver
                    soup2 = BeautifulSoup(page_html, 'html.parser')
                    all_text = soup2.get_text().lower()
                    
                    # Find the segment containing the math
                    math_match = re.search(r'(\d+\s+(ditambah|dikurangi|dikali|dibagi)\s+\d+)', all_text)
                    
                    if math_match:
                        question = math_match.group(1)
                        answer = solve_math_question(question)
                        logger.info(f"[SNIPER] Solved Math: {question} = {answer}")
                        
                        # Find the likely input (usually type="text" or "number" strictly before the submit button)
                        # Since we don't have exact selector, we inject the answer to ANY empty input field that looks like captcha
                        await page_obj.evaluate(f'''(ans) => {{
                            let inputs = document.querySelectorAll('input[type="text"], input[type="number"]');
                            for(let inp of inputs) {{
                                if(inp.value === "") inp.value = ans;
                            }}
                        }}''', answer)
                        
                        # Click the second submit button for the modal
                        await page_obj.evaluate('''() => {
                            let btns = Array.from(document.querySelectorAll('button'));
                            let submitBtn = btns.find(b => b.textContent.toLowerCase().includes('verifikasi') || b.textContent.toLowerCase().includes('lanjut') || b.textContent.toLowerCase().includes('submit'));
                            if(submitBtn) submitBtn.click();
                        }''')
                        await asyncio.sleep(2)
            except Exception as ex:
                logger.warning(f"[SNIPER] Math Captcha Handling skipped/failed: {ex}")

        # Submit form to /antrean-ambil
        async with page.expect_response(lambda response: "antrean-ambil" in response.url or response.status == 200, timeout=15000) as response_info:
             # Better way if standard click is intercepted:
             await page.evaluate('''() => {
                  const form = document.querySelector('form');
                  if(form) form.submit();
             }''')
             
        # After submitting the main form, attempt to answer the Math Captcha popup if it blocks us.
        await handle_math_captcha(page)

        final_response = await response_info.value
        
        # --- TICKET SAVING ---
        screenshot_path = None
        if final_response.ok:
            import os
            ticket_dir = os.path.join(os.getcwd(), "tickets")
            os.makedirs(ticket_dir, exist_ok=True)
            # Save screenshot named with NIK and Date
            safe_name = profile_data.get('nik', 'unknown').replace(" ", "_")
            safe_date = target_date.replace("-", "")
            screenshot_filename = f"TICKET_{safe_name}_{safe_date}_{location_id}.png"
            screenshot_path = os.path.join(ticket_dir, screenshot_filename)
            
            # Wait briefly for success animation/text to render
            await asyncio.sleep(2)
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"[SNIPER] 📸 Ticket Screenshot Saved: {screenshot_path}")
        
        return {
            "success": final_response.ok,
            "status_code": final_response.status,
            "url": final_response.url,
            "screenshot": screenshot_path
        }
            
    except Exception as e:
        logger.error(f"[SNIPER] Error during sniper execution: {e}")
        return {"success": False, "error": str(e)}
