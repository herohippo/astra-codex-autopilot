# Native Codex app continuation

This adapter relies on the app's available `automation_update` heartbeat tool. Tool names and scheduling support can vary by host/version; inspect the actual tool schema. Do not implement app control through private databases, copied tokens, browser scraping, or undocumented thread endpoints.

Persist only the returned automation ID and actual task ID in `.autopilot/mode.json` using the bundled helper. Use the tool to inspect/update the schedule; do not edit scheduler files. A recurring work request authorizes a heartbeat, not a new project task or publication.

## Saved continuation prompt

Adapt these paragraphs with absolute paths, keeping the result readable to the user:

> Continue the existing project at PROJECT_PATH toward the acceptance criteria in .autopilot/MASTER_TASK.md. First use APP_HELPER_PATH with --project PROJECT_PATH check; use the current task ID as owner. If ownership differs or may_work is false, perform no project edits. For quota waits, use returned next_check_at to defer this existing heartbeat if supported by the host; otherwise do no project work and retain the scheduled check. Never invent schedule fields or disable automatic future recovery. If COMPLETE has validation evidence, handle cleanup_action=delete_automation even when may_work=false: verify the saved heartbeat belongs to this task/project, delete it through the host tool, then run helper finish --automation-id ID --automation-deleted only after confirmed deletion or definitive absence. On failure retain its ID, pause if possible, and report cleanup pending. If only STOP or BLOCKED exists, pause and preserve the heartbeat for resume.
>
> Read the project's instructions, STATUS.md, TASKS.md, and pending steering. Inspect actual files and Git status to recover partial work from an interrupted turn. Continue one useful bounded segment in this app task, run relevant validation, and checkpoint the result and next step. Do not launch a CLI supervisor or a second editing task. Check STOP between segments. Apply only steering you actually read; leave later instructions pending.
>
> When every acceptance criterion is satisfied and validated, write COMPLETE with evidence and delete this saved heartbeat using the cleanup protocol. Keep project files and checkpoints. If progress needs missing information, permissions, or a decision that cannot safely be inferred, write BLOCKED and pause this heartbeat. Preserve existing authorization boundaries. Do not purchase credits, switch to API billing, or redeem resets automatically. Stay quiet while state is unchanged or non-actionable; notify only on completion, failure, a meaningful change, or required user action.

## What recovery means

Native app steering: inspect `.autopilot/STEERING.md` and the individual Markdown files in `.autopilot/steering-queue/`. Record which queue filenames you read. After applying them and checkpointing successfully, move only those exact files to `.autopilot/steering-history/`; leave files arriving later for the next segment. Manually edited STEERING.md stays persistent until the user changes it.

The next eligible scheduler invocation reads checkpoints and current files. It is not resurrection of a terminated process. The host may decline or delay scheduled turns when allowance is exhausted, the app is closed, or the computer is asleep. A plugin cannot guarantee retry exactly at reset or that the scheduler remains enabled after repeated failures. Check the host automation status if a native app task stops waking up. For explicit local retry/error handling, choose CLI mode.

App pause stops future scheduled runs; the app's Stop control interrupts an active turn. A different task can inspect status but must not take ownership while the original task may edit. If the original task is unavailable, the user must stop its work and pause its automation before explicit manual recovery; never automatically expire ownership on a timer.

## Quota timing

The helper checks documented CLI app-server metadata. It caches exhausted/reset-unknown waits in state.json, avoids metadata reads before the next_check_at deadline, and rechecks availability at that deadline. Both modes require a compatible logged-in Codex CLI. Native scheduling and wakeup consumption belong to the host: a Python helper cannot defer a host turn before that turn runs it. Report this limit honestly. Use CLI mode when no model turns should be started during the wait.

## Automatic schedule cleanup on completion (0.4.0)

Completion authorizes deletion of only this project's saved heartbeat. Verify every acceptance criterion and relevant tests first; write evidence to STATUS.md and a nonempty COMPLETE. The helper does not independently prove project correctness.

1. Run `check` under the actual owner. If `cleanup_action=delete_automation`, handle cleanup even though `may_work=false`; do not return before cleanup or restart project work. Use the exact `binding.automation_id` and verify the host automation belongs to this owner/project.
2. Delete that saved heartbeat with the host automation tool's supported delete operation. Preserve all other tasks, schedules, code, checkpoints, and logs. Do not edit scheduler files. Confirm successful deletion or definitive not-found for that exact automation (authorization/network errors are not not-found).
3. Only after confirmation, run `finish --automation-id ID --automation-deleted` with the same owner. This records deletion time and previous ID, clears the active binding, and retains COMPLETE and ownership. Repeating this acknowledgement is safe.
4. If deletion fails/is unsupported, keep the ID, pause that same heartbeat if supported, and report cleanup pending. Never claim deletion or call finish until confirmed. A later user request/check can retry cleanup; do not create a replacement cleanup automation.

STOP or BLOCKED without completed validation means pause and preserve the schedule for resume. Quota waits keep the existing reset-aware waiting policy. CLI mode exits at COMPLETE and has no host schedule to delete. After completed cleanup, new work requires an explicit user request, updated acceptance criteria, `reset-complete --yes`, and a newly attached heartbeat; ordinary resume must not recreate completed work. Existing saved automation prompts and helper paths need migration when upgrading; installing files alone does not update them.
