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

from .contracts import (
    ActionExecutionStatus,
    ActionExecutor,
    ActionExecutorRegistry,
    ActionResult,
    ExecutionContext,
)
from .schedule import next_run_after, validate_schedule
from .scheduler import (
    SchedulerRunner,
    SchedulerTickResult,
)
from .worker import (
    WorkerRunner,
    WorkerTickResult,
)

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
