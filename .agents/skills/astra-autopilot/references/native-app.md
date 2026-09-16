# Native Codex app continuation

This adapter relies on the app's available `automation_update` heartbeat tool. Tool names and scheduling support can vary by host/version; inspect the actual tool schema. Do not implement app control through private databases, copied tokens, browser scraping, or undocumented thread endpoints.

Persist only the returned automation ID and actual task ID in `.autopilot/mode.json` using the bundled helper. Use the tool to inspect/update the schedule; do not edit scheduler files. A recurring work request authorizes a heartbeat, not a new project task or publication.

## Saved continuation prompt

Adapt these paragraphs with absolute paths, keeping the result readable to the user:

> Continue the existing project at PROJECT_PATH toward the acceptance criteria in .autopilot/MASTER_TASK.md. First use APP_HELPER_PATH with --project PROJECT_PATH check; use the current task ID as owner. If ownership differs or may_work is false, perform no project edits. If STOP, BLOCKED, or COMPLETE exists, pause this heartbeat using the saved automation ID and report only a meaningful new condition.
>
> Read the project's instructions, STATUS.md, TASKS.md, and pending steering. Inspect actual files and Git status to recover partial work from an interrupted turn. Continue one useful bounded segment in this app task, run relevant validation, and checkpoint the result and next step. Do not launch a CLI supervisor or a second editing task. Check STOP between segments. Apply only steering you actually read; leave later instructions pending.
>
> When every acceptance criterion is satisfied and validated, write COMPLETE with evidence and pause this heartbeat. If progress needs missing information, permissions, or a decision that cannot safely be inferred, write BLOCKED and pause this heartbeat. Preserve existing authorization boundaries. Do not purchase credits, switch to API billing, or redeem resets automatically. Stay quiet while state is unchanged or non-actionable; notify only on completion, failure, a meaningful change, or required user action.

## What recovery means

Native app steering: inspect `.autopilot/STEERING.md` and the individual Markdown files in `.autopilot/steering-queue/`. Record which queue filenames you read. After applying them and checkpointing successfully, move only those exact files to `.autopilot/steering-history/`; leave files arriving later for the next segment. Manually edited STEERING.md stays persistent until the user changes it.

The next eligible scheduler invocation reads checkpoints and current files. It is not resurrection of a terminated process. The host may decline or delay scheduled turns when allowance is exhausted, the app is closed, or the computer is asleep. A plugin cannot guarantee retry exactly at reset or that the scheduler remains enabled after repeated failures. Check the host automation status if a native app task stops waking up. For explicit local retry/error handling, choose CLI mode.

App pause stops future scheduled runs; the app's Stop control interrupts an active turn. A different task can inspect status but must not take ownership while the original task may edit. If the original task is unavailable, the user must stop its work and pause its automation before explicit manual recovery; never automatically expire ownership on a timer.
