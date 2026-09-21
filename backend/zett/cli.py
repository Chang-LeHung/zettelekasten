"""Launch the storage foundation and unchanged frontend."""

import asyncio

import typer
import uvicorn
from zett_agent import new_uuid7

from .config import settings
from .infra.database import init_db
from .infra.log import configure_logging, get_logger, uvicorn_log_config
from .infra.processes import ProcessHeartbeatPublisher
from .infra.scheduler import ActionExecutorRegistry, SchedulerRunner, WorkerRunner
from .schemas import ProcessRole

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
    # Prepare the schema before Uvicorn owns a loop; the lifespan repeats it
    # idempotently for `uvicorn zett.main:app` and test clients.
    asyncio.run(init_db())
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    logger.info("Starting Zett service; host=%s port=%d reload=%s", host, port, reload)
    typer.echo(f"http://{display_host}:{port}")
    uvicorn.run("zett.main:app", host=host, port=port, reload=reload, log_config=uvicorn_log_config())


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
    heartbeat_started = False
    try:
        try:
            await heartbeat.start()
            heartbeat_started = True
        except Exception:
            logger.exception("Could not start process heartbeat; role=%s instance_id=%s", role.value, instance_id)
        await runner.run_forever()
    finally:
        if heartbeat_started:
            await heartbeat.stop()


if __name__ == "__main__":
    app()
