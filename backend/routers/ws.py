"""WebSocket endpoint /ws/stream para eventos en tiempo real."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.ws_manager import ws_manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws/stream")
async def stream(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Mantener conexión viva. Si el cliente envía algo, lo ignoramos.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(websocket)
