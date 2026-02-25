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
        
        # We need a bridge to broadcast messages from the synchronous DrissionPage thread
        # back to the async FastAPI websocket manager.
        loop = asyncio.get_running_loop()
        def sync_broadcast(message: str):
            # Fire and forget the broadcast coroutine into the main event loop
            asyncio.run_coroutine_threadsafe(self.ws_manager.broadcast(message), loop)
            
        sync_broadcast(f"[Node {node_id}] 🟢 Starting DrissionPage Engine for {config['nama_lengkap']}...")

        from backend.services.antam_api import run_drission_bot_loop
        
        try:
            # Run the synchronous DrissionPage loop in a separate thread so it doesn't block FastAPI
            await asyncio.to_thread(
                run_drission_bot_loop, 
                node_id, 
                config, 
                sync_broadcast,
                self.nodes, # Pass nodes ref so it can trigger the Kill Switch
                nik=config['nik']
            )
        except asyncio.CancelledError:
            pass # Task was stopped normally
        except Exception as e:
            if "TargetClosedError" not in str(type(e)):
                sync_broadcast(f"[Node {node_id}] 🔴 Critical Error: {str(e)}")
            if node_id in self.nodes:
                del self.nodes[node_id]
