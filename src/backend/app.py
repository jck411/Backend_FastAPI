"""Application factory for the FastAPI service."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chat import ChatOrchestrator
from .config import get_settings
from .routers.chat import router as chat_router

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "Test_Frontend"


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="OpenRouter Chat Backend",
        version="0.1.0",
        description="Streaming chat backend powered by OpenRouter and MCP.",
    )

    orchestrator = ChatOrchestrator(settings)
    app.state.chat_orchestrator = orchestrator

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        await orchestrator.initialize()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await orchestrator.shutdown()

    app.include_router(chat_router)

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

        @app.get("/settings", include_in_schema=False)
        async def settings_page() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "settings.html")

    @app.get("/health", tags=["health"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "default_model": settings.default_model}

    return app


app = create_app()


__all__ = ["app", "create_app"]
