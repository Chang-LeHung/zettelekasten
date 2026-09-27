"""Infrastructure scheduler core exposed to application process entry points.

End-to-end scheduled task sequence::

               +-----+             +-----+         +-------------+      +-----------+       +-----------+        +---------+        +-----------+
               | API |             | Web |         |  Supervisor |      | Scheduler |       | SQLite/DB |        |  Worker |        |  Executor |
               +--+--+             +--+--+         +------+------+      +-----+-----+       +-----+-----+        +----+----+        +-----+-----+
                  |                   |                   |                   |                   |                   |                   |
                  |    create task    |                   |                   |                   |                   |                   |
                  |------------------->                   |                   |                   |                   |                   |
                  |                   |                   |    write task     |                   |                   |                   |
                  |                   |----------------------------------------------------------->                   |                   |
                  |                   | start supervisor  |                   |                   |                   |                   |
                  |                   |------------------->                   |                   |                   |                   |
                  |                   |                   |  spawn scheduler  |                   |                   |                   |
                  |                   |                   |------------------->                   |                   |                   |
                  |                   |                   |                   |   spawn worker    |                   |                   |
                  |                   |                   |----------------------------------------------------------->                   |
                  |                   |                   |                   |                   |                   |                   |
                  |                   |                   |                   |     scan due      |                   |                   |
                  |                   |                   |                   |------------------->                   |                   |
                  |                   |                   |                   |     due tasks     |                   |                   |
                  |                   |                   |                   <-------------------|                   |                   |
                  |                   |                   |                   | queue run + lease |                   |                   |
                  |                   |                   |                   |------------------->                   |                   |
                  |                   |                   |                   |                   |    pending run    |                   |
                  |                   |                   |                   |                   |------------------->                   |
                  |                   |                   |                   |                   |     claim run     |                   |
                  |                   |                   |                   |                   <-------------------|                   |
                  |                   |                   |                   |                   |      running      |                   |
                  |                   |                   |                   |                   |------------------->                   |
                  |                   |                   |                   |                   |                   |      execute      |
                  |                   |                   |                   |                   |                   |------------------->
                  |                   |                   |                   |                   |                   |      result       |
                  |                   |                   |                   |                   |                   <-------------------|
                  |                   |                   |                   |                   |  terminal status  |                   |
                  |                   |                   |                   |                   <-------------------|                   |
                  |                   |                   |                   |                   |   release lease   |                   |
                  |                   |                   |                   |                   <-------------------|                   |
                  |                   |                   |                   |                   |                   |                   |
                  |                   |                   |     heartbeat     |                   |                   |                   |
                  |                   |                   <-------------------|                   |                   |                   |
                  |                   |      heartbeat    |                   |                   |                   |                   |
                  |                   |<--------------------------------------|                   |                   |                   |
                  |                   |  read heartbeats  |                   |                   |                   |                   |
                  |                   |<------------------|                   |                   |                   |                   |

Lifecycle:

1. The Web process validates and stores a Cron task definition.
2. The supervisor tracks local ``Popen`` handles and starts missing scheduler
   and worker CLI processes as independent subprocesses.
3. The scheduler scans due tasks, advances ``next_run_at``, creates a ``pending``
   run, and assigns the task lease.
4. A worker claims the pending run, changes it to ``running``, and executes the
   action through its registered ``ActionExecutor``.
5. The worker writes the terminal run status and releases the task lease.
6. Scheduler and worker POST heartbeats to the FastAPI health endpoint. FastAPI
   keeps them in memory and the supervisor reads that registry directly.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import (
        ActionExecutionStatus,
        ActionExecutor,
        ActionExecutorRegistry,
        ActionResult,
        ExecutionContext,
    )
    from .schedule import next_run_after, validate_schedule
    from .scheduler import SchedulerRunner, SchedulerTickResult
    from .worker import WorkerRunner, WorkerTickResult

#: Every re-export and the module that defines it. Importing this package used
#: to import the scheduler loop, the worker loop, the action registry, and
#: through them SQLAlchemy, for every caller — including `zett status` and
#: `zett stop`, which only read the runtime-state file. Each name is now
#: imported the first time a caller asks for it, so `from ...scheduler import
#: SchedulerRunner` still works and costs what the name actually needs.
_EXPORTS = {
    "ActionExecutionStatus": ".contracts",
    "ActionExecutor": ".contracts",
    "ActionExecutorRegistry": ".contracts",
    "ActionResult": ".contracts",
    "ExecutionContext": ".contracts",
    "SchedulerRunner": ".scheduler",
    "SchedulerTickResult": ".scheduler",
    "WorkerRunner": ".worker",
    "WorkerTickResult": ".worker",
    "next_run_after": ".schedule",
    "validate_schedule": ".schedule",
}

__all__ = [
    "ActionExecutionStatus",
    "ActionExecutor",
    "ActionExecutorRegistry",
    "ActionResult",
    "ExecutionContext",
    "SchedulerRunner",
    "SchedulerTickResult",
    "WorkerRunner",
    "WorkerTickResult",
    "next_run_after",
    "validate_schedule",
]


def __getattr__(name: str) -> object:
    """Import one re-exported name on first access."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name, __package__), name)
    globals()[name] = value
    return value
