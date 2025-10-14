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
from .routers.google_auth import router as google_auth_router
from .routers.mcp_servers import router as mcp_router
from .routers.presets import router as presets_router
from .routers.settings import router as settings_router
from .routers.stt import router as stt_router
from .routers.uploads import router as uploads_router
from .services.attachments import AttachmentService
from .services.mcp_server_settings import MCPServerSettingsService
from .services.model_settings import ModelSettingsService
from .services.presets import PresetService


def create_app() -> FastAPI:
    settings = get_settings()

    project_root = Path(__file__).resolve().parent.parent.parent

    def _resolve_under(base: Path, p: Path) -> Path:
        # Allow absolute paths as-is (useful for tests and external mounts).
        if p.is_absolute():
            return p.resolve()
        resolved = (base / p).resolve()
        if not resolved.is_relative_to(base):
            raise ValueError(f"Configured path {resolved} escapes project root {base}")
        return resolved

    model_settings_path = _resolve_under(project_root, settings.model_settings_path)

    model_settings_service = ModelSettingsService(
        model_settings_path,
        settings.default_model,
        default_system_prompt=settings.openrouter_system_prompt,
    )

    mcp_servers_path = _resolve_under(project_root, settings.mcp_servers_path)

    default_mcp_servers = [
        {
            "id": "local-calculator",
            "module": "backend.mcp_servers.calculator_server",
        },
        {
            "id": "housekeeping",
            "module": "backend.mcp_servers.housekeeping_server",
            "enabled": True,
        },
        {
            "id": "custom-calendar",
            "module": "backend.mcp_servers.calendar_server",
            "enabled": True,
        },
        {
            "id": "custom-gmail",
            "module": "backend.mcp_servers.gmail_server",
            "enabled": True,
        },
        {
            "id": "custom-gdrive",
            "module": "backend.mcp_servers.gdrive_server",
            "enabled": True,
        },
        {
            "id": "custom-pdf",
            "module": "backend.mcp_servers.pdf_server",
            "enabled": True,
        },
    ]

    mcp_settings_service = MCPServerSettingsService(
        mcp_servers_path,
        fallback=default_mcp_servers,
    )

    presets_path = _resolve_under(project_root, settings.presets_path)

    preset_service = PresetService(
        presets_path,
        model_settings_service,
        mcp_settings_service,
    )

    orchestrator = ChatOrchestrator(
        settings,
        model_settings_service,
        mcp_settings_service,
    )

    attachments_dir = _resolve_under(project_root, settings.attachments_dir)

    attachment_service = AttachmentService(
        orchestrator.repository,
        attachments_dir,
        max_size_bytes=settings.attachments_max_size_bytes,
        retention_days=settings.attachments_retention_days,
        public_base_url=(
            str(settings.attachments_public_base_url)
            if settings.attachments_public_base_url
            else None
        ),
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
    app.state.preset_service = preset_service
    app.state.attachment_service = attachment_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(settings_router)
    app.include_router(presets_router)
    app.include_router(mcp_router)
    app.include_router(stt_router)
    app.include_router(uploads_router)
    app.include_router(
        google_auth_router,
        prefix="/api/google-auth",
        tags=["google-auth"],
    )

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
