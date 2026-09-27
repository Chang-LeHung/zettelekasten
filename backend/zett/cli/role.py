"""The internal scheduler and worker roles ``zett start`` supervises.

Neither role is a user command: the Web process starts one scheduler and
``ZETT_WORKER_PROCESSES`` workers as ``python -m zett.cli <role>``. They live in
this module because they are the same process with a different loop, and they
keep their arguments and their ``--help`` so a role can be watched on its own
while debugging.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..config import settings
from ..infra.log import configure_logging, get_logger
from . import PROGRAM_NAME
from .arguments import bounded_float

if TYPE_CHECKING:
    from ..infra.scheduler.scheduler import SchedulerRunner
    from ..infra.scheduler.worker import WorkerRunner
    from ..schemas import ProcessRole

SCHEDULER_LOG_FILE_NAME = "scheduler.log"
WORKER_LOG_FILE_NAME = "worker.log"

logger = get_logger(__name__)


def build_parser(role: str) -> argparse.ArgumentParser:
    """Build the parser for one internal role."""
    summary = {
        "scheduler": "Internal role: queue due background tasks without executing their actions.",
        "worker": "Internal role: claim queued background tasks and execute their registered actions.",
    }.get(role, "Internal role process.")
    parser = argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} {role}",
        description=f"{summary} `zett start` supervises this role; run it here only to watch it on its own.",
    )
    parser.add_argument(
        "--poll-interval",
        type=bounded_float(0.1, 60.0),
        default=1.0,
        help="Seconds between scans or claim attempts (default: %(default)s)",
    )
    parser.add_argument("--instance-id", default=None, help="Stable process instance ID")
    return parser


def run_scheduler(argv: Sequence[str] | None = None) -> int:
    """Queue due background tasks without executing their actions."""
    return _run_role("scheduler", argv)


def run_worker(argv: Sequence[str] | None = None) -> int:
    """Claim queued background tasks and execute their registered actions."""
    return _run_role("worker", argv)


def _run_role(role: str, argv: Sequence[str] | None) -> int:
    """Parse one role's arguments and run its loop until it is stopped."""
    from zett_agent.ids import new_uuid7

    from ..infra.persistence.database import init_db
    from ..schemas import ProcessRole

    args = build_parser(role).parse_args(argv)
    process_role = ProcessRole(role)
    log_file = SCHEDULER_LOG_FILE_NAME if process_role is ProcessRole.SCHEDULER else WORKER_LOG_FILE_NAME
    log_path = configure_logging(file_name=log_file)
    asyncio.run(init_db())
    runner = _build_runner(process_role, args.poll_interval)
    instance_id = args.instance_id or new_uuid7()
    logger.info("Zett %s started; log_file=%s instance_id=%s", role, log_path, instance_id)
    try:
        asyncio.run(_run_with_heartbeat(runner, process_role, instance_id))
    except KeyboardInterrupt:
        logger.info("Zett %s interrupted", role)
    finally:
        logger.info("Zett %s stopped", role)
    return 0


def _build_runner(role: ProcessRole, poll_interval: float) -> SchedulerRunner | WorkerRunner:
    """Build the loop for one role.

    The worker import stays inside its branch so the scheduler process never
    pays for the Agent runtime a worker needs to execute an action.
    """
    from ..schemas import ProcessRole

    if role is ProcessRole.SCHEDULER:
        from ..infra.scheduler import SchedulerRunner

        return SchedulerRunner(poll_interval=poll_interval)
    from ..infra.scheduler import ActionExecutorRegistry, WorkerRunner
    from ..infra.scheduler.agent_prompt import scheduled_agent_executor

    return WorkerRunner(
        executors=ActionExecutorRegistry((scheduled_agent_executor,)),
        poll_interval=poll_interval,
    )


async def _run_with_heartbeat(runner: SchedulerRunner | WorkerRunner, role: ProcessRole, instance_id: str) -> None:
    """Run one scheduler or worker alongside its independent heartbeat task."""
    from ..infra.scheduler.processes import ProcessHeartbeatPublisher
    from ..infra.scheduler.runtime_state import RuntimeWatchdog
    from ..infra.scheduler.worker import WorkerRunner

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
