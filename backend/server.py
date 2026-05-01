"""FastAPI app + uvicorn runner para el panel de SmartCryptoAgent.

Lanzamiento desde main.py:
    from backend.server import start_api_thread
    start_api_thread(host="127.0.0.1", port=8088)

El thread es daemon: muere cuando termina el proceso principal.
"""
import asyncio
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers import config as config_router
from backend.routers import dashboard as dashboard_router
from backend.routers import instructions as instructions_router
from backend.routers import parameters as parameters_router
from backend.routers import ws as ws_router
from backend.ws_manager import ws_manager

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title="SmartCryptoAgent Panel",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # CORS para dev: el frontend Vite corre en :5173
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(dashboard_router.router)
    app.include_router(instructions_router.router)
    app.include_router(config_router.router)
    app.include_router(parameters_router.router)
    app.include_router(ws_router.router)

    @app.on_event("startup")
    async def _on_startup():
        ws_manager.set_loop(asyncio.get_running_loop())

    # Servir build de producción del frontend si existe
    if FRONTEND_DIST.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(FRONTEND_DIST), html=True),
            name="frontend",
        )

    return app


app = create_app()


def _run_uvicorn(host: str, port: int):
    import uvicorn

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    asyncio.new_event_loop().run_until_complete(server.serve())


def start_api_thread(host: str = "127.0.0.1", port: int = 8088) -> threading.Thread:
    """Lanza el API en un daemon thread y retorna el handle."""
    thread = threading.Thread(
        target=_run_uvicorn,
        kwargs={"host": host, "port": port},
        name="api-server",
        daemon=True,
    )
    thread.start()
    return thread
