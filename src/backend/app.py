"""Application factory for the FastAPI service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .chat import ChatOrchestrator
from .config import get_settings
from .routers.chat import router as chat_router
from .routers.mcp_servers import router as mcp_router
from .routers.settings import router as settings_router
from .routers.stt import router as stt_router
from .services.mcp_server_settings import MCPServerSettingsService
from .services.model_settings import ModelSettingsService


def create_app() -> FastAPI:
    settings = get_settings()

    project_root = Path(__file__).resolve().parent.parent.parent
    model_settings_path = settings.model_settings_path
    if not model_settings_path.is_absolute():
        model_settings_path = project_root / model_settings_path

    model_settings_service = ModelSettingsService(
        model_settings_path,
        settings.default_model,
        default_system_prompt=settings.openrouter_system_prompt,
    )

    mcp_servers_path = settings.mcp_servers_path
    if not mcp_servers_path.is_absolute():
        mcp_servers_path = project_root / mcp_servers_path

    default_mcp_servers = [
        {
            "id": "local-calculator",
            "module": "backend.mcp_server",
        },
        {
            "id": "test-toolkit",
            "module": "backend.mcp_servers.sample_server",
            "enabled": True,
        },
    ]

    mcp_settings_service = MCPServerSettingsService(
        mcp_servers_path,
        fallback=default_mcp_servers,
    )

    orchestrator = ChatOrchestrator(
        settings,
        model_settings_service,
        mcp_settings_service,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await orchestrator.initialize()
        try:
            yield
        finally:
            await orchestrator.shutdown()

    app = FastAPI(
        title="OpenRouter Chat Backend",
        version="0.1.0",
        description="Streaming chat backend powered by OpenRouter and MCP.",
        lifespan=lifespan,
    )

    app.state.model_settings_service = model_settings_service
    app.state.chat_orchestrator = orchestrator
    app.state.mcp_server_settings_service = mcp_settings_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(settings_router)
    app.include_router(mcp_router)
    app.include_router(stt_router)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        """Serve a basic favicon to prevent 404 errors in browser console."""
        # Return a simple transparent 1x1 pixel PNG as favicon
        # This prevents the common favicon.ico 404 error
        # 1x1 transparent PNG in base64
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        return Response(content=png_data, media_type="image/png")

    @app.get("/health", tags=["health"])
    async def healthcheck() -> dict[str, str | None]:
        active_model, _ = await model_settings_service.get_openrouter_overrides()
        return {
            "status": "ok",
            "default_model": settings.default_model,
            "active_model": active_model,
        }

    return app


app = create_app()


__all__ = ["app", "create_app"]
