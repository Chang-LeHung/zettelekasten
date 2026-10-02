# Zett startup performance: where the time went

Internal engineering note. It is deliberately not part of the published site:
`docs/.vitepress/config.mts` excludes this directory through `srcExclude`, so
the file stays in the repository and never reaches `site/docs/`.

Measured 2026-09-27 on macOS (Apple silicon), Python 3.14 from `backend/.venv`,
warm page cache, median of three runs unless noted.

## Result

Three states, measured with the same script on the same machine (warm cache,
median of three runs). `start` is the detached CLI until the recorded port
answers; `server boot` is a foreground spawn until `/api/health` answers. The
last three columns are speed-ups: **upgrade** against the 0.1.3 baseline,
**lazy** against the upgrade-only state, and **total** against the baseline.

| Command | 0.1.3 baseline | 0.1.4 upgrade only | + Zett's lazy imports | upgrade | lazy | total |
| --- | --- | --- | --- | --- | --- | --- |
| `zett -h` | 1.38 s | 0.37 s | **0.05 s** | 3.7× | 7.4× | **28×** |
| `zett status` | 1.33 s | 0.39 s | **0.10 s** | 3.4× | 3.9× | **13×** |
| `zett stop` | 1.33 s | 0.36 s | **0.10 s** | 3.7× | 3.6× | **13×** |
| `zett start` (detached, until the port answers) | 3.51 s | 1.49 s | **1.01 s** | 2.4× | 1.5× | **3.5×** |
| server: spawn → `/api/health` answers | 1.26 s | 0.82 s | **0.59 s** | 1.5× | 1.4× | **2.1×** |

Import attribution with `python -X importtime -c "import …"` (cumulative cost of
the module named), with the same three speed-ups:

| Import | 0.1.3 baseline | 0.1.4 upgrade only | + Zett's lazy imports | upgrade | lazy | total |
| --- | --- | --- | --- | --- | --- | --- |
| `zett.cli` | 942.5 ms | 268.3 ms | **46.3 ms** | 3.5× | 5.8× | **20×** |
| `zett.application.runtime` | 979.0 ms | 245.6 ms | **85.5 ms** | 4.0× | 2.9× | **11×** |
| `zett.schemas` | 976.5 ms | 118.7 ms | **5.9 ms** | 8.2× | 20.1× | **165×** |
| `zett.main` | 1387.6 ms | 737.0 ms | **510.3 ms** | 1.9× | 1.4× | **2.7×** |
| worker role (`zett.infra.scheduler.agent_prompt`) | 1240.8 ms | 608.4 ms | **271.9 ms** | 2.0× | 2.2× | **4.6×** |

Read the two speed-up columns as "what the zett-agent upgrade bought on its
own" and "what Zett's own lazy imports bought on top of the upgrade": `zett -h`
went 1.38 s → 0.37 s in the upgrade (3.7×) and 0.37 s → 0.05 s in Zett's own
work (7.4× more), for 28× in total.

## Where each win came from

The zett-agent upgrade and Zett's own work are separate commits, and they are
separately measurable. Share of the total saving each step delivered:

| Command | zett-agent 0.1.4 + import rewrite | Zett's own lazy imports |
| --- | --- | --- |
| `zett -h` | 1.01 s of 1.33 s (**76%**) | 0.32 s (24%) |
| `zett status` | 0.94 s of 1.23 s (**76%**) | 0.29 s (24%) |
| `zett stop` | 0.97 s of 1.23 s (**79%**) | 0.26 s (21%) |
| `zett start` | 2.02 s of 2.50 s (**81%**) | 0.48 s (19%) |
| server boot | 0.44 s of 0.67 s (**66%**) | 0.23 s (34%) |
| worker role import | 632 ms of 969 ms (**65%**) | 336 ms (35%) |

The upgrade is the bigger half because 0.1.3's package `__init__` was the root
cause: it re-exported the runtime, so even `zett -h` paid for the client, the
extension stack, and four provider SDKs. Zett's own work is the difference
between "the process imports a large part of the application" (0.37 s) and
"the process imports what this command runs" (0.05 s).

## What was slow

1. `zett_agent/__init__.py` in 0.1.3 re-exported the entire runtime, so importing
   any name pulled `zett_agent.client` → extensions (`mcp` 299 ms) and providers
   (`openai` 283 ms, `anthropic` 367 ms, `google-genai` 232 ms, `ollama` 121 ms).
2. Zett's own modules imported heavy things at module level:
   - `zett/agent/extensions/context_composition.py` built the `tiktoken` o200k BPE
     table while importing (108 ms), even in processes that never count tokens.
   - `zett/agent/extensions/deferred_tools.py` imported
     `zett_agent.extensions.tool_search`, which imports `openai` at module level
     (~300 ms), for turns that never search tools.
   - `zett/cli.py` imported uvicorn, SQLAlchemy, the agent runtime, and the whole
     scheduler package for every command, including `--help`.
   - `zett/infra/scheduler/__init__.py` and `zett/schemas/__init__.py` re-exported
     every submodule eagerly, so reading one small runtime-state file pulled in
     the scheduler loop, the worker loop, the DAOs, SQLAlchemy, and all fourteen
     schema domains.
3. A measurement trap worth remembering: the `uv tool`-installed `zett` on `PATH`
   is a snapshot of the package built into its own Python 3.12 environment. It
   kept the old code and `zett-agent==0.1.3`, so `zett status` there stayed at
   ~1.2 s until `make install` (or
   `uv tool install --force --refresh-package zett ./backend`) refreshed it.
   Always say which installation a number came from, or use
   `uv tool install --editable ./backend` so the command tracks the checkout.

## What changed

From zett-agent 0.1.4 (commit `chore(deps): upgrade to zett-agent 0.1.4 and
import from defining modules`):

1. Its package `__init__` holds only `__version__` — importing the runtime no
   longer pulls the client, the extensions, or any provider SDK.
2. Each provider SDK (`openai`, `anthropic`, `google-genai`, `ollama`) and `mcp`
   is imported by the method that uses it.
3. Every name is now imported from the module that defines it
   (`zett_agent.agent`, `zett_agent.messages`, `zett_agent.model`,
   `zett_agent.tools.base`, `zett_agent.extensions.<domain>`, `zett_agent.ids`),
   so Zett's 73 call sites were rewritten mechanically.

From Zett itself (commit `perf: cut CLI and server startup time`):

4. **Lazy tool search**: `DeferredToolExtension.__init__` imports
   `ToolSearchExtension` when it builds its search host, so `openai` arrives with
   a Responses-API turn instead of with the process.
5. **Lazy tokenizer**: `context_composition` loads `tiktoken` and the `o200k_base`
   encoding on the first token count instead of at import.
6. **Per-command CLI modules**: the CLI is a `zett/cli/` package with one module
   per command, and `zett.cli.main` — the jump function the console script calls
   — reads the command name, imports that module, and hands the rest over. So
   `--help` imports only the package `__init__` (a static table plus argparse),
   `status` and `stop` import the runtime-state controller, and `uvicorn`,
   `init_db`, and the role runners are imported inside the commands that run
   them. `zett start -h` costs 0.02 s because it imports `zett/cli/start.py` and
   nothing else.
7. **Lazy package re-exports (PEP 562)**: `zett/infra/scheduler/__init__.py` and
   `zett/schemas/__init__.py` resolve a name through module `__getattr__`, so
   `from ...scheduler import SchedulerRunner` still works, but
   `import zett.infra.scheduler.runtime_state` no longer loads the scheduler
   loop, the worker loop, SQLAlchemy, or the other thirteen schema domains.
8. **Launcher import at its use site**: `RuntimeService` resolves
   `launch_background_server` (and with it `httpx`) inside
   `start_in_background`, so `status` and `stop` do not import it.

## How it was measured

- Wall clock: warm cache, median of three runs, with an isolated
  `ZETT_STORAGE_ROOT` and `ZETT_PORT` per installation so a live server is never
  touched.
- The three states are real checkouts: `main` on `zett-agent==0.1.3`, the
  upgrade commit on `0.1.4` (eager imports kept), and this branch (lazy
  imports). Each has its own `backend/.venv`.
- Attribution: `python -X importtime -c "import <module>"`; the last line of the
  output carries the cumulative cost of the module named.
- Server boot: spawn `zett start --foreground` and poll `/api/health` every
  20 ms until it answers.

## What is left

- `zett.main` is still ~424 ms: FastAPI 113 ms (of which `fastapi.openapi.models`
  33 ms), SQLAlchemy 241 ms, SQLite/DSN setup, and the app wiring. A server needs
  these; there is no lazy-loading trick that keeps `/api` working.
- The worker role still builds the whole agent container before its first run
  (~272 ms). Machines running several `ZETT_WORKER_PROCESSES` could defer that
  build to the first claimed run.
- ~15 ms of every CLI invocation is the Python interpreter itself, so no further
  change can take `zett status` much below its current 0.08 s without replacing
  the entry point.
- `uvicorn --reload`'s parent/child pair still records the reload child as
  `server_pid` in `runtime.json`, so `zett stop` can leave the reloader parent
  alive. Unrelated to startup time, but it shows up whenever the CLI work touches
  the runtime state.
