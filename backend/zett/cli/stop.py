"""Stop the recorded server and the roles it supervises."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from . import PROGRAM_NAME
from .arguments import bounded_float


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``zett stop``."""
    parser = argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} stop",
        description="Stop the recorded FastAPI server and the scheduler and worker roles it supervises.",
    )
    parser.add_argument(
        "--timeout",
        type=bounded_float(1.0, 60.0),
        default=10.0,
        help="Seconds to wait for each process to stop (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Stop the recorded FastAPI, scheduler, and worker processes."""
    from ..infra.scheduler.runtime_state import RuntimeProcessController

    args = build_parser().parse_args(argv)
    state = asyncio.run(RuntimeProcessController().stop(timeout=args.timeout))
    if state is None:
        print("Zett is not running")
        return 0
    print(
        f"Stopped Zett; server_pid={state.server_pid} "
        f"scheduler_pids={state.scheduler_pids} worker_pids={state.worker_pids}"
    )
    return 0
