"""Asynchronous FastAPI entry point and packaged Vue frontend."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .application.health import ProcessSupervisor, process_heartbeat_registry
from .application.router import api_router
from .infra.agent_runtime import close_agent_runtime_storage, get_agent_runtime_storage
from .infra.database import init_db
from .infra.log import configure_logging, get_logger, shutdown_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """Initialize and release owned resources without blocking the ASGI loop."""
    log_path = await run_in_threadpool(configure_logging)
    try:
        await init_db()
        get_agent_runtime_storage()
        await process_heartbeat_registry.clear()
        supervisor = ProcessSupervisor()
        await supervisor.start()
        logger.info("Zett service started; log_file=%s", log_path)
        try:
            yield
        finally:
            await supervisor.stop()
    finally:
        logger.info("Zett service stopped")
        try:
            await close_agent_runtime_storage()
        finally:
            await run_in_threadpool(shutdown_logging)


app = FastAPI(title="Zett API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


app.include_router(api_router)


static_directory = Path(__file__).with_name("static")
if static_directory.joinpath("index.html").is_file():
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
