import sys
import os
import time
import logging

# Setup Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.antam_api import _get_stealth_page, auto_login, submit_booking, safe_get
from backend.config.database import AsyncSessionLocal
from backend.models.account_node import AccountNode
from sqlalchemy import select
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Simulation")

async def run_simulation():
    """
    Simulation script to verify sniper speed without waiting for real quota.
    It will:
    1. Open browser.
    2. Request you to login manually OR use the first account in DB.
    3. Once on any page, it will force trigger submit_booking to SUB-01 Pakuwon/Darmo.
    """
    print("\n=== ANTAM AUTO-Q SIMULATION MODE ===\n")
    
    # 1. Get first account from DB for testing
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AccountNode))
        node = result.scalars().first()
        
    if not node:
        print("❌ No account found in database. Please add an account in the Web Panel first.")
        return

    print(f"Using account: {node.nama_lengkap} (NIK: {node.nik})")
    print("Opening browser...")
    
    page = _get_stealth_page(proxy=node.proxy, node_id=999)
    try:
        # Navigate to login
        page.get("https://antrean.logammulia.com/login")
        
        # 2. Automated login
        print("🤖 Attempting Auto-Login...")
        success = auto_login(page, node.email, node.password, print, 999, node.nama_lengkap)
        
        if not success:
            print("❌ Login failed. Please check credentials or solve captcha manually.")
            # Give user 60s to login manually if auto fails
            page.wait.url_change("/users", timeout=60)
            
        print("✅ Login detected. Redirecting to Boutique Selection...")
        site_id = "SUB-01" # Surabaya 1 Darmo
        page.get(f"https://antrean.logammulia.com/antrean?site=SUB-01")
        
        print("\n🔥 WE ARE ON THE TARGET PAGE.")
        print("I will now SIMULATE quota discovery and trigger high-speed JS submission.")
        input("\nPress ENTER to trigger the Sniper Simulation...")
        
        # 3. Force Sniper Execution
        config_payload = {
            "nama_lengkap": node.nama_lengkap,
            "nik": node.nik,
            "no_hp": node.no_hp,
            "email": node.email
        }
        
        print("🚀 EXECUTING SNIPER NOW!")
        
        # We MUST inject the dummy option BEFORE calling submit_booking
        # so that it passes the initial 'select#wakda' display check.
        page.run_js('''
            var sel = document.querySelector('select#wakda');
            if(!sel) {
                // Create a VISIBLE dummy select to pass .ele_displayed() check
                sel = document.createElement('select');
                sel.id = 'wakda';
                sel.style.position = 'fixed';
                sel.style.top = '50%';
                sel.style.left = '50%';
                sel.style.width = '200px';
                sel.style.height = '40px';
                sel.style.zIndex = '10000';
                sel.style.border = '2px solid red';
                sel.style.display = 'block';
                sel.style.visibility = 'visible';
                document.body.appendChild(sel);
            }
            // Clear existing and add simulation option
            sel.innerHTML = ''; 
            var opt = document.createElement('option');
            opt.value = "SIMULATION_VALUE";
            opt.text = "08:00 - 09:00 (Simulation)";
            sel.add(opt);
            sel.value = "SIMULATION_VALUE";
            
            // Highlight for visibility
            var msg = document.createElement('div');
            msg.innerHTML = '<h1 style="color:red; background:white; position:fixed; top:40%; left:50%; z-index:10001; padding:20px; border:3px solid red;">🔥 SIMULASI KUOTA AKTIF! 🔥</h1>';
            document.body.appendChild(msg);
            
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        ''')
        
        time.sleep(1) # Let DOM settle
        start_time = time.time()
        res = submit_booking(page, config_payload, site_id)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n✅ Simulation Finished in {duration:.4f} seconds.")
        if res.get("success"):
            print(f"🏆 SIMULATED SUCCESS! Booking URL: {res.get('url')}")
            print(f"📸 Screenshot saved at: {res.get('screenshot')}")
        else:
            print(f"🔴 Simulation Failed: {res.get('error')}")
            
        print("\nExiting in 10 seconds...")
        time.sleep(10)
        
    finally:
        page.quit()

if __name__ == "__main__":
    asyncio.run(run_simulation())
