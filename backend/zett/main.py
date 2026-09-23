"""Asynchronous FastAPI entry point and packaged Vue frontend."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .application.api.router import api_router
from .application.channels import channel_service
from .application.health import ProcessSupervisor, process_heartbeat_registry
from .config import settings
from .infra.agent.runtime import close_agent_runtime_storage, get_agent_runtime_storage
from .infra.log import configure_logging, get_logger, shutdown_logging
from .infra.persistence.database import init_db
from .infra.scheduler import process_platform
from .infra.scheduler.runtime_state import RuntimeStateStore
from .schemas import ServerRuntimeState

logger = get_logger(__name__)


def _pid_running(pid: int) -> bool:
    return process_platform.is_process_running(pid)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """Initialize and release owned resources without blocking the ASGI loop."""
    log_path = await run_in_threadpool(configure_logging)
    try:
        await init_db()
        get_agent_runtime_storage()
        await process_heartbeat_registry.clear()
        runtime_state_store = RuntimeStateStore()
        existing_state = await runtime_state_store.read()
        server_pid = os.getpid()
        if (
            existing_state is not None
            and existing_state.port == settings.port
            and existing_state.server_pid is not None
            and _pid_running(existing_state.server_pid)
        ):
            server_pid = existing_state.server_pid
        await runtime_state_store.write(
            ServerRuntimeState(
                server_pid=server_pid,
                port=settings.port,
                scheduler_pids=existing_state.scheduler_pids if existing_state is not None else [],
                worker_pids=existing_state.worker_pids if existing_state is not None else [],
                started_at=datetime.now(UTC),
            )
        )
        supervisor: ProcessSupervisor | None = None
        try:
            await channel_service.initialize()
            supervisor = ProcessSupervisor(runtime_state_store=runtime_state_store)
            await supervisor.start()
            logger.info("Zett service started; log_file=%s", log_path)
            yield
        finally:
            await channel_service.shutdown()
            if supervisor is not None:
                await supervisor.stop()
            await runtime_state_store.remove()
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
