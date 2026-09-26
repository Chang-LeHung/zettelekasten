"""Launch the storage foundation and unchanged frontend."""

import asyncio
import os
from datetime import datetime

import typer
import uvicorn
from zett_agent import new_uuid7

from ._compat import UTC
from .config import settings
from .infra.log import configure_logging, get_logger, uvicorn_log_config
from .infra.persistence.database import init_db
from .infra.scheduler import ActionExecutorRegistry, SchedulerRunner, WorkerRunner
from .infra.scheduler.processes import ProcessHeartbeatPublisher
from .infra.scheduler.runtime_state import RuntimeProcessController, RuntimeStateStore, RuntimeWatchdog
from .schemas import ProcessRole, ServerRuntimeState

app = typer.Typer(help="Zett")
logger = get_logger(__name__)
SCHEDULER_LOG_FILE_NAME = "scheduler.log"
WORKER_LOG_FILE_NAME = "worker.log"


@app.callback()
def initialize() -> None:
    configure_logging()


@app.command()
def start(
    host: str = typer.Option(settings.host, "--host", help="Bind address"),
    port: int = typer.Option(settings.port, "--port", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Reload on source changes"),
) -> None:
    """Serve the storage foundation and existing frontend."""
    settings.host = host
    settings.port = port
    try:
        asyncio.run(RuntimeProcessController().prepare_start(port=port))
    except RuntimeError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    asyncio.run(
        RuntimeStateStore().write(
            ServerRuntimeState(
                server_pid=os.getpid(),
                port=port,
                started_at=datetime.now(UTC),
            )
        )
    )
    # Prepare the schema before Uvicorn owns a loop; the lifespan repeats it
    # idempotently for `uvicorn zett.main:app` and test clients.
    asyncio.run(init_db())
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    logger.info("Starting Zett service; host=%s port=%d reload=%s", host, port, reload)
    typer.echo(f"http://{display_host}:{port}")
    # RequestLogMiddleware owns access logging so the sampling rules apply; a
    # second, unsampled uvicorn access line would undo them.
    uvicorn.run(
        "zett.main:app",
        host=host,
        port=port,
        reload=reload,
        access_log=False,
        log_config=uvicorn_log_config(),
    )


@app.command()
def stop(
    timeout: float = typer.Option(10.0, "--timeout", min=1.0, max=60.0),
) -> None:
    """Stop the recorded FastAPI, scheduler, and worker processes."""
    configure_logging()
    state = asyncio.run(RuntimeProcessController().stop(timeout=timeout))
    if state is None:
        typer.echo("Zett is not running")
        return
    typer.echo(
        f"Stopped Zett; server_pid={state.server_pid} "
        f"scheduler_pids={state.scheduler_pids} worker_pids={state.worker_pids}"
    )


@app.command()
def scheduler(
    poll_interval: float = typer.Option(1.0, "--poll-interval", min=0.1, max=60.0),
    instance_id: str | None = typer.Option(None, "--instance-id", help="Stable process instance ID"),
) -> None:
    """Queue due background tasks without executing their actions."""
    log_path = configure_logging(file_name=SCHEDULER_LOG_FILE_NAME)
    asyncio.run(init_db())
    runner = SchedulerRunner(poll_interval=poll_interval)
    resolved_instance_id = instance_id or new_uuid7()
    logger.info(
        "Zett scheduler started; log_file=%s instance_id=%s",
        log_path,
        resolved_instance_id,
    )
    try:
        asyncio.run(_run_with_heartbeat(runner, ProcessRole.SCHEDULER, resolved_instance_id))
    except KeyboardInterrupt:
        logger.info("Zett scheduler interrupted")
    finally:
        logger.info("Zett scheduler stopped")


@app.command()
def worker(
    poll_interval: float = typer.Option(1.0, "--poll-interval", min=0.1, max=60.0),
    instance_id: str | None = typer.Option(None, "--instance-id", help="Stable process instance ID"),
) -> None:
    """Claim queued background tasks and execute their registered actions."""
    from .infra.scheduler.agent_prompt import scheduled_agent_executor

    log_path = configure_logging(file_name=WORKER_LOG_FILE_NAME)
    asyncio.run(init_db())
    runner = WorkerRunner(
        executors=ActionExecutorRegistry((scheduled_agent_executor,)),
        poll_interval=poll_interval,
    )
    resolved_instance_id = instance_id or new_uuid7()
    logger.info("Zett worker started; log_file=%s instance_id=%s", log_path, resolved_instance_id)
    try:
        asyncio.run(_run_with_heartbeat(runner, ProcessRole.WORKER, resolved_instance_id))
    except KeyboardInterrupt:
        logger.info("Zett worker interrupted")
    finally:
        logger.info("Zett worker stopped")


async def _run_with_heartbeat(runner: SchedulerRunner | WorkerRunner, role: ProcessRole, instance_id: str) -> None:
    """Run one scheduler or worker alongside its independent heartbeat task."""
    heartbeat = ProcessHeartbeatPublisher(role=role, instance_id=instance_id)

    async def stop_orphaned(reason: str) -> None:
        logger.error(
            "Runtime watchdog stopped orphaned process; role=%s instance_id=%s reason=%s",
            role.value,
            instance_id,
            reason,
        )
        if isinstance(runner, WorkerRunner):
            await runner.stop()
        else:
            runner.stop()

    watchdog = RuntimeWatchdog(role=role, on_orphaned=stop_orphaned) if settings.process_watchdog_enabled else None
    heartbeat_started = False
    try:
        try:
            await heartbeat.start()
            heartbeat_started = True
        except Exception:
            logger.exception("Could not start process heartbeat; role=%s instance_id=%s", role.value, instance_id)
        if watchdog is not None:
            await watchdog.start()
        await runner.run_forever()
    finally:
        if watchdog is not None:
            await watchdog.stop()
        if heartbeat_started:
            await heartbeat.stop()


if __name__ == "__main__":
    app()
