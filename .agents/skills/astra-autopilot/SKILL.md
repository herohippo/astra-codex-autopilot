---
name: astra-autopilot
description: Continue a local project toward saved acceptance criteria across Codex usage-limit interruptions. Use for persistent project work, native app follow-ups, a CLI worker, status, pause, resume, or steering for Astra Autopilot.
---

# Astra Autopilot

Two separate modes share project checkpoints. Native **app mode** continues the current Codex app task using a thread heartbeat. **CLI mode** runs a local Python supervisor invoking `codex exec --json`. Do not silently substitute a CLI worker for native app work. This plugin does not increase allowances, purchase credits, or promise an exact reset time.

Use `scripts/astra_supervisor.py` for CLI operations and `scripts/astra_app.py` for native app coordination, resolved relative to this skill directory. Both bundle their Python package; no pip installation is required for plugin use. Require Python 3.10+, Git, a local project folder, and compatible Codex CLI signed in through ChatGPT (both modes use its documented quota metadata). Never read credentials.

## Start: select the requested mode

- In a Codex app task, default to native app mode unless the user asks for a CLI/background worker. In a terminal/CLI session, use CLI mode.
- Missing app automation tools are a real capability limit. Explain it and offer CLI mode; do not fabricate an automation or call a CLI worker app-native continuation.
- Identify the actual project/worktree path. Summarize the current conversation into `.autopilot/MASTER_TASK.md`, `STATUS.md`, and `TASKS.md`: goal, explicit acceptance tests, constraints, completed work, outstanding work. Only initialize once. Preserve existing instructions and edits. These local files are the durable handoff if a run is interrupted before a fresh checkpoint.
- For a new project use `init --init-git --goal "..."`; for an existing Git project use `init --goal "..."`. Avoid `--force` for an existing goal. Do not infer permission to publish, deploy, spend money, or bypass approvals from a request to keep working.

## Native app mode

Read [native-app.md](references/native-app.md). Discover the host's `automation_update` tool. The supported integration is a **heartbeat attached to this task**, not a cron task in a separate conversation. A normal local process cannot revive an app task by itself.

1. Run the app helper `--project "PATH" claim` using this task's `CODEX_THREAD_ID`, or `--owner ACTUAL_THREAD_ID` if the host provides it. Never invent an ID. It refuses another app owner or a running CLI supervisor.
2. Inspect the saved `automation_id` and existing host automation before creating anything. Reuse the existing heartbeat. For a new one, create it paused, attached to the current task, at a 30-minute continuation interval (not a quota work-retry timer); record its returned real ID with `attach --automation-id ID`, then activate it. Use the host tool schema; never print raw automation directives as if created. Roll back incomplete setup by pausing any created automation, setting STOP, and releasing ownership only when no work is active.
3. Use the continuation prompt in the reference, inserting actual project/helper paths. Keep unchanged/non-actionable checks quiet. Notify only for meaningful changes, completion, failure, or required user action.
4. Begin useful project work in this task. Before each work segment and on every heartbeat run `check` and require `may_work=true`. The helper queries official quota metadata and returns `next_check_at` and `quota_wait_reason`. When quota is exhausted or metadata is unavailable, do not edit the project. If the host supports delaying the next heartbeat until that time, update the existing automation through the host tool, preserving its fields; never invent unsupported schedule fields or edit scheduler files. Otherwise retain the heartbeat and disclose that wakeups can occur but project work remains gated, with resumption delayed by up to its interval. Do not pause quota waits unless a supported automatic future wakeup is retained. Never launch `once`, `run`, or `start` in app mode. Do not spawn a second app task to edit the same project.
5. Checkpoint after each meaningful unit and before yielding. Complete only after all acceptance criteria and relevant validation are satisfied; save evidence and create COMPLETE, then delete only the saved heartbeat through the host tool and acknowledge confirmed deletion with helper `finish --automation-id ID --automation-deleted`. Follow the cleanup protocol below, including when `may_work=false`. A genuine blocker gets BLOCKED and the heartbeat is paused.

Pause: pause the saved heartbeat with the host tool, run app helper `pause`, and stop further edits. If a turn is actively running, use the app's Stop control to interrupt it; a heartbeat pause prevents future wakeups. Resume: verify the same owner and blocker resolution, clear STOP via supervisor helper `resume` (and `--blocked` only if resolved), reactivate the saved heartbeat, and continue. Do not create a duplicate.

Switch to CLI: first pause the heartbeat and stop active native work, set STOP, then app helper `release --automation-paused`. Only then clear STOP and launch CLI. Switching from CLI requires stopping and waiting for its worker to exit before claiming app ownership. The file binding is coordination, not a sandbox enforcing mutual exclusion against arbitrary app edits.

## CLI mode

Use `python "SKILL_DIR/scripts/astra_supervisor.py" --project "PATH" COMMAND`.

- `doctor`: validate prerequisites without a model call.
- `once`: one turn; quota exit does not auto-retry.
- `run`: foreground continuation loop.
- `start`: detached continuation with startup verification; appropriate for app-requested **CLI worker mode**.
- `status`: status/retry time. Distinguish observed tokens from unavailable usage; counts are not remaining account allowance.
- `steer "instruction"`: queue next-turn guidance.
- `stop`: finish current turn, then stop. `stop --now`: terminate the managed process tree; partial edits remain.
- `resume --start`: clear STOP and restart background worker; add `--blocked` only after resolving it. Never clear COMPLETE unless the user requests more work.

After `start`, verify `status`; report mode and how to stop. Do not claim exact quota recovery, app transcript continuation, reboot persistence, or tests unless verified. PCs must remain awake and logged in; app mode also depends on its scheduler. CLI mode never intentionally changes to API-key authentication. Existing account credit settings remain outside this plugin's control.

## Quota-aware waiting (0.3.0)

CLI quota errors trigger `account/rateLimits/read` through the documented local app-server. Wait until the latest exhausted window reset plus 60 seconds, persist the deadline, then re-read before executing. Unknown metadata causes metadata-only rechecks (default 30 minutes), never periodic model retries. The `codex` bucket is the default; do not infer a different bucket from a model name. App `check` applies the same work gate; it cannot prevent host wakeups that already started or guarantee scheduler execution during exhausted allowance. Existing saved heartbeat prompts must be updated when upgrading.

## Automatic schedule cleanup on completion (0.4.0)

Completion authorizes deletion of only this project's saved heartbeat. Verify every acceptance criterion and relevant tests first; write evidence to STATUS.md and a nonempty COMPLETE. The helper does not independently prove project correctness.

1. Run `check` under the actual owner. If `cleanup_action=delete_automation`, handle cleanup even though `may_work=false`; do not return before cleanup or restart project work. Use the exact `binding.automation_id` and verify the host automation belongs to this owner/project.
2. Delete that saved heartbeat with the host automation tool's supported delete operation. Preserve all other tasks, schedules, code, checkpoints, and logs. Do not edit scheduler files. Confirm successful deletion or definitive not-found for that exact automation (authorization/network errors are not not-found).
3. Only after confirmation, run `finish --automation-id ID --automation-deleted` with the same owner. This records deletion time and previous ID, clears the active binding, and retains COMPLETE and ownership. Repeating this acknowledgement is safe.
4. If deletion fails/is unsupported, keep the ID, pause that same heartbeat if supported, and report cleanup pending. Never claim deletion or call finish until confirmed. A later user request/check can retry cleanup; do not create a replacement cleanup automation.

STOP or BLOCKED without completed validation means pause and preserve the schedule for resume. Quota waits keep the existing reset-aware waiting policy. CLI mode exits at COMPLETE and has no host schedule to delete. After completed cleanup, new work requires an explicit user request, updated acceptance criteria, `reset-complete --yes`, and a newly attached heartbeat; ordinary resume must not recreate completed work. Existing saved automation prompts and helper paths need migration when upgrading; installing files alone does not update them.
