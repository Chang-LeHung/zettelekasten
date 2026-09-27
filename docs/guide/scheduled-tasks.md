# Scheduled tasks

A scheduled task runs an Agent prompt on a cron schedule, without a browser
attached. Ask the Agent in any conversation, or use the form in the
`Scheduled tasks` view; both write the same durable definition.

| Field | Meaning |
| --- | --- |
| Name | Short label shown in the task list |
| Schedule | A cron expression plus an IANA time zone |
| Provider | Which enabled provider the run uses |
| Message | The prompt, sent in a fresh session |
| Reasoning effort | Off, Low, Medium, or High |
| Enabled | Whether the scheduler may queue it |
| Timeout | Maximum runtime in seconds (default ten minutes) |

Ask the Agent for a provider list first if you are not sure which IDs are
available — that is what the `list_providers` tool is for.

## How a run behaves

Every run creates a **new isolated session** with session type `scheduled`. It
never joins or continues one of your conversations and never waits for a
browser: `ask_user` is off and shell commands run without approval. Runs are
headless by design, so keep a task's prompt and provider appropriate for
unattended execution.

Updates to artifacts owned by the scheduled session are written directly to
their published content and clear any pending draft, because there is no user
in the loop to press save. Updates aimed at artifacts from other conversations
stay draft-only, exactly like in an interactive session.

## Enabling, running, and history

Each task row shows the next run, the last outcome, and its action. From there
you can run a task immediately, enable or disable it, and open its run history.

The Agent gets `create_scheduled_task`, `list_scheduled_tasks`,
`get_scheduled_task`, `update_scheduled_task`, and `disable_scheduled_task` —
deliberately not a delete tool. Disabling preserves the definition and the run
history, so an Agent can stop future runs without erasing what already happened.
Physical deletion stays a user action.

Each run records its status, timing, error, and output, and links to the session
it created so you can read the whole transcript afterwards — including the
artifacts and assets that run produced.

## Processes and failure handling

Scheduling and execution are separate processes, never part of the web
application itself:

```bash
uv run --directory backend zett scheduler   # queues due runs
uv run --directory backend zett worker      # claims and executes them
```

`zett start` supervises both as child processes, `zett status` reports their
recorded PIDs, and `zett stop` stops them along with the API. The scheduler only
writes pending run rows; one or more workers claim and execute them with
leases, so a crashed worker does not hold a task forever. A watchdog makes each
child verify that the runtime state is complete and that the web process that
owns it is still alive, and exit after a bounded number of failures, so an
unclean crash cannot leave permanent orphan workers behind.

If a task's provider is disabled or deleted, the scheduler refuses to queue it
instead of failing silently, and a provider cannot be disabled while a task
still references it.
