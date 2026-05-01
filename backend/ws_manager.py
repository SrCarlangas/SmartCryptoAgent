"""WebSocket connection manager con broadcast thread-safe.

El bot loop corre en el hilo principal; FastAPI corre en un thread daemon con
su propio asyncio loop. `broadcast_threadsafe` permite emitir desde cualquier
hilo programando la corutina en el loop del backend.
"""
import asyncio
import time
from typing import Optional


class WebSocketManager:
    def __init__(self):
        self._connections = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket):
        await websocket.accept()
        self._connections.add(websocket)

    async def disconnect(self, websocket):
        self._connections.discard(websocket)

    async def _broadcast_async(self, event_type: str, data: dict):
        if not self._connections:
            return
        msg = {"type": event_type, "data": data, "ts": time.time()}
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    def broadcast_threadsafe(self, event_type: str, data: dict):
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_async(event_type, data), self._loop
            )
        except Exception:
            pass

    def num_connections(self) -> int:
        return len(self._connections)


ws_manager = WebSocketManager()
