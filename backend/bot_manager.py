import asyncio
import logging
from typing import Dict, Any

from backend.services.antam_api import check_quota, submit_booking

class BotManager:
    """
    Manages isolated Playwright instances for each Account Node asynchronously.
    """
    def __init__(self, websocket_manager):
        # Store both task and config
        self.nodes: Dict[int, Dict[str, Any]] = {}
        self.ws_manager = websocket_manager

    async def start_node(self, node_id: int, config: Dict[str, Any]):
        """Starts an infinite loop for a specific Bot Node."""
        if node_id in self.nodes:
            await self.ws_manager.broadcast(f"[Node {node_id}] Warning: Node is already running.")
            return

        await self.ws_manager.broadcast(f"[Node {node_id}] 🟢 Starting Bot for {config['nama_lengkap']} targeting {config['target_location']}")

        # Wrap the actual logic in an isolated asyncio task
        task = asyncio.create_task(self._bot_loop(node_id, config))
        self.nodes[node_id] = {"task": task, "config": config}

    async def stop_node(self, node_id: int):
        """Cancels a running Node Task."""
        if node_id in self.nodes:
            self.nodes[node_id]["task"].cancel()
            del self.nodes[node_id]
            await self.ws_manager.broadcast(f"[Node {node_id}] 🔴 Bot task manually stopped.")
        else:
            await self.ws_manager.broadcast(f"[Node {node_id}] Not currently running.")

    async def _bot_loop(self, node_id: int, config: Dict[str, Any]):
        """The core logic that runs isolated in the background per Node."""
        
        target_location = config['target_location']
        target_date = config['target_date']
        proxy = config.get('proxy')
        nama_lengkap = config['nama_lengkap']
        nik = config['nik']

        from playwright.async_api import async_playwright
        from backend.services.antam_api import _get_stealth_page
        
        try:
            async with async_playwright() as p:
                launch_args = {
                    "channel": "chrome",
                    "headless": False, 
                    # Comprehensive Cloudflare Evasion Arguments
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-site-isolation-trials",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-web-security",
                        "--start-maximized",
                        "--disable-dev-shm-usage",
                        "--disable-accelerated-2d-canvas",
                        "--disable-gpu"
                    ],
                    "ignore_default_args": ["--enable-automation"]
                }
                if proxy:
                    launch_args["proxy"] = {"server": proxy}
                    
                browser = await p.chromium.launch(**launch_args)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await _get_stealth_page(context)
                
                try:
                    while True:
                        await self.ws_manager.broadcast(f"[Node {node_id}] [{nama_lengkap}] ⏳ Checking quota for {target_location} (Proxy: {proxy or 'None'})")
                        
                        quota = await check_quota(page, target_location, target_date)
                        
                        if quota > 0:
                            await self.ws_manager.broadcast(f"[Node {node_id}] [{nama_lengkap}] 🟢 SUCCESS: Found {quota} slots! Triggering Sniper...")
                            # Trigger submit_booking
                            config_payload = {
                                "nama_lengkap": config['nama_lengkap'],
                                "nik": config['nik'],
                                "no_hp": config['no_hp'],
                                "email": config['email']
                            }
                            res = await submit_booking(page, config_payload, target_location, target_date)
                            
                            if res.get("success"):
                               await self.ws_manager.broadcast(f"[Node {node_id}] [{nama_lengkap}] 🏆 BOOKING SUCCESSFUL! URL: {res.get('url')}")
                               
                               # --- KILL SWITCH ---
                               # Stop all other running nodes that use the same NIK
                               kill_targets = []
                               for other_id, node_data in self.nodes.items():
                                   if other_id != node_id and node_data['config'].get('nik') == nik:
                                       kill_targets.append(other_id)
                                       
                               for t_id in kill_targets:
                                   self.nodes[t_id]["task"].cancel()
                                   del self.nodes[t_id]
                                   await self.ws_manager.broadcast(f"[System] 🛑 KILL SWITCH ACTIVATED: Node {t_id} stopped because NIK {nik} already secured a booking.")

                            else:
                               await self.ws_manager.broadcast(f"[Node {node_id}] [{nama_lengkap}] 🔴 SNIPER FAILED: {res.get('error')}")
                               
                            break # Stop looping after sniper execution
                        elif quota == -1:
                            await self.ws_manager.broadcast(f"[Node {node_id}] [{nama_lengkap}] 🟡 HARAP LOGIN DAHULU! Jendela Browser butuh aksi manual Anda.")
                            await asyncio.sleep(5) # Slow down loop to let user login
                        elif quota == -2:
                            await self.ws_manager.broadcast(f"[Node {node_id}] [{nama_lengkap}] 🛡️ Cloudflare aktif. Membaca halaman... Silakan centang manual jika diminta di Chrome.")
                            await asyncio.sleep(5) # Wait for user to verify, then check again
                        else:
                            await self.ws_manager.broadcast(f"[Node {node_id}] [{nama_lengkap}] 🔴 Quota full. Retrying in 10s...")
                            await asyncio.sleep(10)
                finally:
                    try:
                        await context.close()
                        await browser.close()
                    except Exception:
                        pass
                    
        except asyncio.CancelledError:
            pass # Task was stopped normally
        except Exception as e:
            # Silence TargetClosedError which happens normally on shutdown
            if "TargetClosedError" not in str(type(e)):
                try:
                    await self.ws_manager.broadcast(f"[Node {node_id}] 🔴 Critical Error: {str(e)}")
                except:
                    pass
            if node_id in self.nodes:
                del self.nodes[node_id]
