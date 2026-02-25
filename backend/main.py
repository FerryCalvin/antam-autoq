import asyncio
import sys

# Fix for Playwright asyncio subprocess error on Windows
if sys.version_info[0] == 3 and sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from contextlib import asynccontextmanager
from backend.config.database import engine, AsyncSessionLocal
from backend.models import Base
from backend.models.account_node import AccountNode

from backend.websockets import ws_manager
from backend.bot_manager import BotManager
from fastapi import WebSocket, WebSocketDisconnect

# Lifespan for initializing DB
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    except asyncio.CancelledError:
        pass
    # Shutdown logic can go here if needed

app = FastAPI(title="Antam Auto-Queue Web Control Panel", lifespan=lifespan)
bot_manager = BotManager(ws_manager)

# Disable CORS restrictions for React default Vite port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Pydantic Schemas
class AccountNodeCreate(BaseModel):
    nama_lengkap: str
    nik: str
    no_hp: str
    email: str
    password: str
    target_location: str
    target_date: str
    proxy: Optional[str] = None

class AccountNodeResponse(AccountNodeCreate):
    id: int
    is_active: bool
    status_message: str

    model_config = ConfigDict(from_attributes=True)

# --- REST ENDPOINTS ---

@app.get("/api/nodes", response_model=List[AccountNodeResponse])
async def get_nodes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AccountNode))
    return result.scalars().all()

@app.post("/api/nodes", response_model=AccountNodeResponse)
async def create_node(node: AccountNodeCreate, db: AsyncSession = Depends(get_db)):
    db_node = AccountNode(**node.dict())
    db.add(db_node)
    await db.commit()
    await db.refresh(db_node)
    
    # Broadcast addition log
    await ws_manager.broadcast(f"[System] ⚙️ Added new node: {db_node.nama_lengkap}")
    return db_node

@app.delete("/api/nodes/{node_id}")
async def delete_node(node_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AccountNode).filter(AccountNode.id == node_id))
    db_node = result.scalars().first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Ensure it's not running when deleted
    await bot_manager.stop_node(node_id)
    
    await db.delete(db_node)
    await db.commit()
    await ws_manager.broadcast(f"[System] 🗑️ Deleted node: {db_node.nama_lengkap}")
    return {"message": "Node deleted successfully"}

@app.post("/api/nodes/{node_id}/start")
async def api_start_node(node_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AccountNode).filter(AccountNode.id == node_id))
    db_node = result.scalars().first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    await bot_manager.start_node(node_id, {
        "nama_lengkap": db_node.nama_lengkap,
        "nik": db_node.nik,
        "no_hp": db_node.no_hp,
        "email": db_node.email,
        "target_location": db_node.target_location,
        "target_date": db_node.target_date,
        "proxy": db_node.proxy
    })
    db_node.is_active = True
    db_node.status_message = "Hunting"
    await db.commit()
    return {"message": "Started", "is_active": True, "status": "Hunting"}

@app.post("/api/nodes/{node_id}/stop")
async def api_stop_node(node_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AccountNode).filter(AccountNode.id == node_id))
    db_node = result.scalars().first()
    if not db_node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    await bot_manager.stop_node(node_id)
    db_node.is_active = False
    db_node.status_message = "Ready"
    await db.commit()
    return {"message": "Stopped", "is_active": False, "status": "Ready"}

# --- WEBSOCKET ENDPOINT ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    await ws_manager.broadcast("[System] 🟢 Web panel connected successfully. Waiting for commands...")
    try:
        while True:
            # We just hold connection to keep live streaming
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    # Do not use reload=True here, as it spawns a subprocess that breaks WindowsProactorEventLoopPolicy
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
