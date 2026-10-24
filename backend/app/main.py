"""TraceHeal Autonomous Incident Investigation & Shadow-Verified Self-Healing Engine.

Main FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.chaos import router as chaos_router
from backend.app.api.v1.incidents import router as incidents_router
from backend.app.api.v1.integrations import router as integrations_router
from backend.app.api.v1.orchestrator import router as orchestrator_router
from backend.app.api.v1.postmortem import router as postmortem_router
from backend.app.api.v1.remediations import router as remediations_router
from backend.app.api.v1.sandbox import router as sandbox_router
from backend.app.api.v1.stream import router as stream_router
from backend.app.api.v1.telemetry import router as telemetry_router
from backend.app.api.v1.traffic import router as traffic_router
from backend.app.incidents.daemon import anomaly_detector_daemon
from backend.app.telemetry.otlp import router as otlp_router
from backend.app.telemetry.queue import telemetry_buffer
from target_services.traffic_controller import traffic_controller
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.session import close_db, init_db
import os
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    logger.info("Initializing TraceHeal database schema...")
    try:
        await init_db()
    except Exception as e:
        logger.warning(f"Database init warning: {e}")

    is_vercel = bool(os.environ.get("VERCEL"))
    if not is_vercel:
        await telemetry_buffer.start()
        if settings.auto_detector_enabled:
            await anomaly_detector_daemon.start()
        if settings.continuous_traffic_enabled:
            await traffic_controller.start(rate_rps=2.0)
        logger.info("TraceHeal Core API, Telemetry Buffer, and Anomaly Observer initialized.")
    yield
    logger.info("Shutting down TraceHeal Core API...")
    if not is_vercel:
        await traffic_controller.stop()
        await anomaly_detector_daemon.stop()
        await telemetry_buffer.stop()
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Autonomous Incident Investigation & Shadow-Verified Self-Healing Platform",
    lifespan=lifespan,
)

# CORS configuration for UI dashboard and external API clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(incidents_router, prefix="/api/v1")
app.include_router(sandbox_router, prefix="/api/v1")
app.include_router(remediations_router, prefix="/api/v1")
app.include_router(postmortem_router, prefix="/api/v1")
app.include_router(stream_router, prefix="/api/v1")
app.include_router(chaos_router, prefix="/api/v1")
app.include_router(traffic_router, prefix="/api/v1")
app.include_router(orchestrator_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(otlp_router)

# Mount Static Assets & Front-End SPA
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
frontend_dir = os.path.join(project_root, "frontend")
patches_dir = os.path.join(project_root, "patches")

if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

if os.path.exists(patches_dir):
    app.mount("/patches", StaticFiles(directory=patches_dir), name="patches")


@app.get("/", include_in_schema=False)
@app.get("/ui", include_in_schema=False)
async def serve_command_center():
    """Serves the single-page SRE Command Center application."""
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>TraceHeal SRE Command Center initializing...</h1>")


@app.get("/health", tags=["System"])
@app.get("/api/v1/health", tags=["System"])
async def system_health():
    """System health check endpoint."""
    return {
        "status": "UP",
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.env,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.host, port=settings.port, reload=True)
