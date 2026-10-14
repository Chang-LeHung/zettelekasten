"""Stop the running server and start it again on the same address."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence

from . import PROGRAM_NAME
from .arguments import bounded_float, bounded_int


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``zett restart``."""
    parser = argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} restart",
        description=(
            "Stop the recorded server and its scheduler and worker, then start Zett again in the "
            "background. Host, port, and reload mode default to what the running server recorded, "
            "so a restart after an update brings back the same address. With nothing running it "
            "just starts."
        ),
    )
    parser.add_argument("--host", default=None, help="Bind address (default: the running server's)")
    parser.add_argument(
        "-p",
        "--port",
        type=bounded_int(1, 65_535),
        default=None,
        help="Bind port (default: the running server's)",
    )
    parser.add_argument("-r", "--reload", action="store_true", default=None, help="Reload on source changes")
    parser.add_argument(
        "--timeout",
        type=bounded_float(1.0, 60.0),
        default=10.0,
        help="Seconds to wait for each process to stop (default: %(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=bounded_float(0.0, 30.0),
        default=0.0,
        help="Seconds to wait before stopping, so the process that asked can finish answering (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Restart the server in the background and report where it is."""
    args = build_parser().parse_args(argv)
    from ..application.runtime import RuntimeService

    if args.delay:
        time.sleep(args.delay)
    try:
        result = asyncio.run(
            RuntimeService().restart_in_background(
                host=args.host,
                port=args.port,
                reload=args.reload,
                stop_timeout=args.timeout,
            )
        )
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Zett restarted in the background; pid={result.pid}")
    print(result.url)
    print(f"Console log: {result.log_path}")
    return 0
