"""Serve the API and the frontend, detached unless asked to stay attached."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from ..config import settings
from . import PROGRAM_NAME
from .arguments import bounded_int


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``zett start``."""
    parser = argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} start",
        description=(
            "Serve the API and the frontend. The default detaches the server, waits until it answers "
            "on its port, and returns to the shell; `zett status` reports it and `zett stop` ends it. "
            "--foreground blocks in this terminal instead, which is how the detached child runs itself."
        ),
    )
    parser.add_argument("--host", default=settings.host, help="Bind address (default: %(default)s)")
    parser.add_argument(
        "-p",
        "--port",
        type=bounded_int(1, 65_535),
        default=settings.port,
        help="Bind port (default: %(default)s)",
    )
    parser.add_argument("-r", "--reload", action="store_true", help="Reload on source changes")
    background = parser.add_mutually_exclusive_group()
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
    parser.set_defaults(background=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Serve in the background, or in the foreground with ``--foreground``."""
    args = build_parser().parse_args(argv)
    if not args.background:
        return run_server(host=args.host, port=args.port, reload=args.reload)
    from ..application.runtime import RuntimeService

    try:
        result = asyncio.run(RuntimeService().start_in_background(host=args.host, port=args.port, reload=args.reload))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Zett is running in the background; pid={result.pid}")
    print(result.url)
    print(f"Console log: {result.log_path}")
    return 0


def run_server(*, host: str, port: int, reload: bool) -> int:
    """Serve in the foreground until the process is stopped."""
    import os
    from datetime import datetime

    import uvicorn

    from .._compat import UTC
    from ..infra.log import get_logger, uvicorn_log_config
    from ..infra.persistence.database import init_db
    from ..infra.scheduler import process_platform
    from ..infra.scheduler.runtime_state import RuntimeProcessController, RuntimeStateStore
    from ..schemas import ServerRuntimeState

    logger = get_logger(__name__)
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
