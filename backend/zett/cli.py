"""Launch the storage foundation and unchanged frontend."""

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Sequence
from datetime import datetime

import uvicorn
from zett_agent import new_uuid7

from ._compat import UTC
from .application.runtime import RuntimeService
from .config import settings
from .infra.log import configure_logging, get_logger, uvicorn_log_config
from .infra.persistence.database import init_db
from .infra.scheduler import ActionExecutorRegistry, SchedulerRunner, WorkerRunner, process_platform
from .infra.scheduler.processes import ProcessHeartbeatPublisher
from .infra.scheduler.runtime_state import RuntimeProcessController, RuntimeStateStore, RuntimeWatchdog
from .schemas import ProcessRole, RuntimeStatus, ServerRuntimeState

PROGRAM_NAME = "zett"
#: One-line introduction, identical to the README tagline and the project's
#: packaged ``description`` so `zett --help`, the README, and the PyPI page
#: introduce the product the same way.
PROGRAM_DESCRIPTION = (
    "A local-first, AI-assisted workspace for turning fleeting thoughts, "
    "conversations, links, and assets into reusable knowledge."
)
SCHEDULER_LOG_FILE_NAME = "scheduler.log"
WORKER_LOG_FILE_NAME = "worker.log"

logger = get_logger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one command, run it, and return its exit status.

    The console script and ``python -m zett.cli`` both call this function, so
    every command is a handler that returns an exit code instead of raising
    one. Parsing stays in the standard library and runs before logging is
    configured, so ``--help`` and a usage error neither create the log
    directory nor print a log line above the usage text.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    configure_logging()
    return handler(args)


def build_parser() -> argparse.ArgumentParser:
    """Build the command surface: start, status, and stop.

    ``scheduler`` and ``worker`` are internal roles: ``zett start`` supervises
    one of each, and a role process is started as ``python -m zett.cli <role>``.
    They are deliberately absent from ``help``, so the listing above describes
    what a user runs and nothing else, while a role can still be watched on its
    own with its full ``--help``.
    """
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=PROGRAM_DESCRIPTION,
    )
    subcommands = parser.add_subparsers(dest="command", metavar="COMMAND")

    start = subcommands.add_parser(
        "start",
        help="Serve the API and the frontend, detached by default",
        description=(
            "Serve the API and the frontend. The default detaches the server, waits until it answers "
            "on its port, and returns to the shell; `zett status` reports it and `zett stop` ends it. "
            "--foreground blocks in this terminal instead, which is how the detached child runs itself."
        ),
    )
    start.add_argument("--host", default=settings.host, help="Bind address (default: %(default)s)")
    start.add_argument(
        "-p",
        "--port",
        type=_bounded_int(1, 65_535),
        default=settings.port,
        help="Bind port (default: %(default)s)",
    )
    start.add_argument("-r", "--reload", action="store_true", help="Reload on source changes")
    background = start.add_mutually_exclusive_group()
    background.add_argument(
        "-b",
        "--background",
        dest="background",
        action="store_true",
        help="Detach and return (default)",
    )
    background.add_argument(
        "-f",
        "--foreground",
        dest="background",
        action="store_false",
        help="Keep the server attached to this terminal",
    )
    start.set_defaults(background=True, handler=_start)

    status = subcommands.add_parser(
        "status",
        help="Report whether Zett is running",
        description=(
            "Report the recorded server and the scheduler and worker roles it supervises, and exit "
            "non-zero when nothing runs."
        ),
    )
    status.set_defaults(handler=_status)

    stop = subcommands.add_parser(
        "stop",
        help="Stop the running Zett server",
        description="Stop the recorded FastAPI server and the scheduler and worker roles it supervises.",
    )
    stop.add_argument(
        "--timeout",
        type=_bounded_float(1.0, 60.0),
        default=10.0,
        help="Seconds to wait for each process to stop (default: %(default)s)",
    )
    stop.set_defaults(handler=_stop)

    # No ``help`` on either internal role: argparse lists a subcommand only when
    # it has one, which is how these stay out of ``zett --help`` while remaining
    # the entry point the supervisor spawns.
    scheduler = subcommands.add_parser(
        "scheduler",
        description=(
            "Internal role: queue due background tasks without executing their actions. `zett start` "
            "supervises one of these; run it here only to watch it on its own."
        ),
    )
    scheduler.add_argument(
        "--poll-interval",
        type=_bounded_float(0.1, 60.0),
        default=1.0,
        help="Seconds between due-task scans (default: %(default)s)",
    )
    scheduler.add_argument("--instance-id", default=None, help="Stable process instance ID")
    scheduler.set_defaults(handler=_scheduler)

    worker = subcommands.add_parser(
        "worker",
        description=(
            "Internal role: claim queued background tasks and execute their registered actions. `zett "
            "start` supervises `ZETT_WORKER_PROCESSES` of these; run it here only to watch one on its own."
        ),
    )
    worker.add_argument(
        "--poll-interval",
        type=_bounded_float(0.1, 60.0),
        default=1.0,
        help="Seconds between claim attempts (default: %(default)s)",
    )
    worker.add_argument("--instance-id", default=None, help="Stable process instance ID")
    worker.set_defaults(handler=_worker)
    return parser


def _bounded_int(minimum: int, maximum: int) -> Callable[[str], int]:
    """Return an argparse type that rejects an integer outside ``minimum..maximum``."""

    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse


def _bounded_float(minimum: float, maximum: float) -> Callable[[str], float]:
    """Return an argparse type that rejects a number outside ``minimum..maximum``."""

    def parse(value: str) -> float:
        try:
            number = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse


def _start(args: argparse.Namespace) -> int:
    """Serve in the background, or in the foreground with ``--foreground``."""
    if not args.background:
        return _run_server(host=args.host, port=args.port, reload=args.reload)
    try:
        result = asyncio.run(RuntimeService().start_in_background(host=args.host, port=args.port, reload=args.reload))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Zett is running in the background; pid={result.pid}")
    print(result.url)
    print(f"Console log: {result.log_path}")
    return 0


def _run_server(*, host: str, port: int, reload: bool) -> int:
    """Serve in the foreground until the process is stopped."""
    settings.host = host
    settings.port = port
    # Every child process — the reload worker and the supervised scheduler and
    # workers — re-reads the configuration from the environment, so the
    # effective bind address has to reach them there. Without it they heartbeat,
    # and the reload worker records runtime state, for the default port instead
    # of this one, which leaves `zett status` and `zett stop` pointing at a
    # process that is not this server.
    os.environ["ZETT_HOST"] = host
    os.environ["ZETT_PORT"] = str(port)
    try:
        asyncio.run(RuntimeProcessController().prepare_start(port=port))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
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
    display_host = process_platform.dialable_host(host)
    logger.info("Starting Zett service; host=%s port=%d reload=%s", host, port, reload)
    print(f"http://{display_host}:{port}")
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
    return 0


def _status(_: argparse.Namespace) -> int:
    """Report whether the server and its supervised workers are running."""
    report = asyncio.run(RuntimeService().status())
    print(_format_status(report))
    return 0 if report.running else 1


def _format_status(report: RuntimeStatus) -> str:
    """Render one runtime status report for the terminal."""
    if not report.running:
        if report.state_recorded:
            return f"Zett is not running (stale runtime state: server_pid={report.server_pid} port={report.port})"
        return "Zett is not running"
    lines = ["Zett is running"]
    if report.url is not None:
        lines.append(f"  url:      {report.url}")
    if report.server_pid is not None:
        lines.append(f"  server:   pid={report.server_pid} {'running' if report.server_running else 'not running'}")
    if report.started_at is not None:
        lines.append(f"  started:  {report.started_at.astimezone().isoformat(timespec='seconds')}")
    lines.extend(_format_children(report))
    return "\n".join(lines)


def _format_children(report: RuntimeStatus) -> list[str]:
    """Render each supervised role from its recorded PID and liveness."""
    lines = []
    for role in (ProcessRole.SCHEDULER, ProcessRole.WORKER):
        recorded = [child for child in report.children if child.role is role]
        if not recorded:
            lines.append(f"{_role_label(role)} not recorded")
            continue
        rendered = ", ".join(f"pid={child.pid} {'running' if child.running else 'not running'}" for child in recorded)
        lines.append(f"{_role_label(role)} {rendered}")
    return lines


def _role_label(role: ProcessRole) -> str:
    """Return the aligned column prefix for one process role."""
    return f"  {role.value + ':':<10}"


def _stop(args: argparse.Namespace) -> int:
    """Stop the recorded FastAPI, scheduler, and worker processes."""
    state = asyncio.run(RuntimeProcessController().stop(timeout=args.timeout))
    if state is None:
        print("Zett is not running")
        return 0
    print(
        f"Stopped Zett; server_pid={state.server_pid} "
        f"scheduler_pids={state.scheduler_pids} worker_pids={state.worker_pids}"
    )
    return 0


def _scheduler(args: argparse.Namespace) -> int:
    """Queue due background tasks without executing their actions."""
    log_path = configure_logging(file_name=SCHEDULER_LOG_FILE_NAME)
    asyncio.run(init_db())
    runner = SchedulerRunner(poll_interval=args.poll_interval)
    resolved_instance_id = args.instance_id or new_uuid7()
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
    return 0


def _worker(args: argparse.Namespace) -> int:
    """Claim queued background tasks and execute their registered actions."""
    from .infra.scheduler.agent_prompt import scheduled_agent_executor

    log_path = configure_logging(file_name=WORKER_LOG_FILE_NAME)
    asyncio.run(init_db())
    runner = WorkerRunner(
        executors=ActionExecutorRegistry((scheduled_agent_executor,)),
        poll_interval=args.poll_interval,
    )
    resolved_instance_id = args.instance_id or new_uuid7()
    logger.info("Zett worker started; log_file=%s instance_id=%s", log_path, resolved_instance_id)
    try:
        asyncio.run(_run_with_heartbeat(runner, ProcessRole.WORKER, resolved_instance_id))
    except KeyboardInterrupt:
        logger.info("Zett worker interrupted")
    finally:
        logger.info("Zett worker stopped")
    return 0


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
    raise SystemExit(main())
