# Scheduled tasks

A scheduled task sends Zett the same message on a schedule, even when no
browser is open: a Monday reading digest, a nightly tidy of yesterday's notes,
a monthly summary of a project.

## Create a task

Open **Scheduled tasks** in the sidebar and fill in the form, or simply ask in
any conversation: “Every Monday at 9:00, summarize what I saved last week into
one card.” Both create the same kind of task.

| Field | What it means |
| --- | --- |
| **Name** | The label shown in the task list. |
| **Schedule** | When it runs, as a cron expression, plus the time zone it is read in, for example `0 9 * * 1` in `Asia/Shanghai` for Mondays at 9:00. |
| **Provider** | Which of your providers answers. |
| **Message** | What Zett is asked each time. Each run starts from a fresh conversation. |
| **Reasoning effort** | **Off**, **Low**, **Medium**, or **High**. |
| **Enabled** | Whether the task runs on its schedule. |
| **Timeout** | How long a run may take before it is stopped. The default is ten minutes. |

When you ask Zett to create the task, name the provider you want it to use;
Zett can look up your providers instead of guessing.

## Write a message that runs alone

No one is there to answer a question while a task runs, so Zett cannot stop to
ask you what you meant. A task also cannot run commands or change files on your
computer: it works with what is in Zett, such as your library, your assets, and
your collections. Write the message as a complete instruction (what to read,
what to make, and where to file it).

Artifacts a run creates are saved to your library directly, because no one is
there to press **Save**. If the run changes an artifact from one of your other
conversations, that change still waits as a draft for you to review.

## Run, pause, and review

Each task in the list shows when it runs next, how the last run went, and its
actions.

- **Run now** starts a run immediately, without changing the schedule.
- Turn **Enabled** off to pause a task. It keeps its settings and its history.
- Open its history to see every run: when it ran, how long it took, whether it
  succeeded, and the error if it did not. Each run links to its conversation,
  so you can read exactly what Zett did and open what it made.

Only you can delete a task.

## If a task does not run

1. Run `zett status`. The server, the scheduler, and the worker should all read
   `running`. If one does not, run `zett stop` and then `zett start`.
2. Check that the task is enabled and that its next run is the time you expect
   in the time zone you chose.
3. Check that its provider is still enabled in [Settings](settings.md).
4. Open the task's history: a run that started but failed shows its error
   there.
