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
        
        # Proactive: if landing on /users profile page, click 'Menu Antrean'
        if "/users" in page.url:
            print("📍 Landed on Profile page. Navigating to Menu Antrean...")
            # Try to find the purple button by text or specific color
            menu_btn = page.ele('text:Menu Antrean', timeout=3) or \
                       page.ele('@@class*=btn@@text():Menu Antrean', timeout=1) or \
                       page.ele('@@style*background-color: rgb(86, 44, 255)', timeout=0.5)
            if menu_btn:
                menu_btn.click()
                page.wait.load_start(timeout=5)

        # PRO-TIP: Here is the official numerical mapping for Antam Boutiques from your HTML:
        # ATGM-Gedung Antam: 31, ATGM-Graha Dipta: 30
        # Balikpapan: 4, Bandung: 1, Bekasi: 19, Bintaro: 16, Bogor: 17, Denpasar: 5
        # Djuanda: 20, Gedung Antam: 6, Graha Dipta: 3, Makassar: 11, Medan: 10
        # Palembang: 12, Pekanbaru: 24, Puri Indah: 21, Semarang: 15, Serpong: 23
        # Setiabudi One: 8, Surabaya 1 Darmo: 13, Surabaya 2 Pakuwon: 14, Yogyakarta: 9
        
        # Current Target: Surabaya 1 Darmo
        site_id = "13" 
        target_url = f"https://antrean.logammulia.com/antrean?site={site_id}"
        page.get(target_url)
        
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
        page.run_js('''
            var sel = document.querySelector('select#wakda');
            if(!sel) {
                sel = document.createElement('select');
                sel.id = 'wakda';
                sel.name = 'wakda';
                sel.style.position = 'fixed';
                sel.style.top = '10%';
                sel.style.left = '10%';
                sel.style.width = '300px';
                sel.style.height = '50px';
                sel.style.zIndex = '10000';
                sel.style.border = '5px solid red';
                sel.style.fontSize = '20px';
                sel.style.display = 'block';
                sel.style.visibility = 'visible';
                document.body.appendChild(sel);
            }
            // Clear and add realistic simulation options
            sel.innerHTML = ''; 
            
            // Opsi 1: Placeholder (akan dilewati oleh sniper karena index == 0)
            var opt0 = document.createElement('option');
            opt0.value = "";
            opt0.text = "-- Pilih Jadwal --";
            sel.add(opt0);
            
            // Opsi 2: Data Simulasi (akan dipilih oleh sniper karena index > 0)
            var opt1 = document.createElement('option');
            opt1.value = "SIMULASI_VAL_123";
            opt1.text = "08:00 - 09:00 (Tersedia 5/50)";
            sel.add(opt1);
            
            sel.value = ""; // Start with placeholder
            
            // Inject dummy inputs if they don't exist
            ['nama', 'nik', 'phone', 'email'].forEach(name => {
                if(!document.querySelector('[name="' + name + '"]')) {
                    let inp = document.createElement('input');
                    inp.name = name;
                    inp.type = 'hidden';
                    document.body.appendChild(inp);
                }
            });

            // Inject dummy "Lanjut" button (Sniper searches for 'Lanjut' or 'Submit')
            if(!document.getElementById('sim-submit')) {
                let btn = document.createElement('button');
                btn.id = 'sim-submit';
                btn.type = 'submit';
                btn.textContent = 'Lanjut';
                btn.style = "position:fixed; bottom:10%; right:10%; padding:20px; font-size:24px; z-index:10000; background:green; color:white; border-radius:10px; cursor:pointer;";
                btn.onclick = function(e) { 
                    console.log('Simulated Submit Clicked'); 
                    alert('Simulasi: Pendaftaran Berhasil Dikirim!');
                    e.preventDefault(); 
                };
                document.body.appendChild(btn);
            }

            // Highlight for visibility
            var msg = document.getElementById('simulation-msg');
            if(!msg) {
                msg = document.createElement('div');
                msg.id = 'simulation-msg';
                msg.style = "color:red; background:white; position:fixed; top:30%; left:50%; transform:translateX(-50%); z-index:10001; padding:20px; border:3px solid red; font-size:24px; font-weight:bold; box-shadow: 0 0 20px rgba(0,0,0,0.5);";
                document.body.appendChild(msg);
            }
            msg.innerHTML = '🔥 SIMULASI KUOTA AKTIF! 🔥<br><small>Menjalankan Sniper dalam 2 detik...</small>';
            
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        ''')
        
        time.sleep(2.0) # Let DOM settle
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
