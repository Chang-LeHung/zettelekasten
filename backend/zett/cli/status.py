"""Report whether the local server and the roles it supervises are running."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from . import PROGRAM_NAME

if TYPE_CHECKING:
    from ..schemas import RuntimeStatus


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``zett status``."""
    return argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} status",
        description=(
            "Report the recorded server and the scheduler and worker roles it supervises, and exit "
            "non-zero when nothing runs."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Report the runtime state file and exit non-zero when nothing runs."""
    from ..application.runtime import RuntimeService

    build_parser().parse_args(argv)
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
    for role in ("scheduler", "worker"):
        recorded = [child for child in report.children if child.role.value == role]
        if not recorded:
            lines.append(f"{_role_label(role)} not recorded")
            continue
        rendered = ", ".join(f"pid={child.pid} {'running' if child.running else 'not running'}" for child in recorded)
        lines.append(f"{_role_label(role)} {rendered}")
    return lines


def _role_label(role: str) -> str:
    """Return the aligned column prefix for one process role."""
    return f"  {role + ':':<10}"
