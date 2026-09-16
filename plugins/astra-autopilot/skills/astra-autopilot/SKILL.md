---
name: astra-autopilot
description: Continue a local project toward saved acceptance criteria across Codex usage-limit interruptions. Use for persistent project work, native app follow-ups, a CLI worker, status, pause, resume, or steering for Astra Autopilot.
---

# Astra Autopilot

Two separate modes share project checkpoints. Native **app mode** continues the current Codex app task using a thread heartbeat. **CLI mode** runs a local Python supervisor invoking `codex exec --json`. Do not silently substitute a CLI worker for native app work. This plugin does not increase allowances, purchase credits, or promise an exact reset time.

Use `scripts/astra_supervisor.py` for CLI operations and `scripts/astra_app.py` for native app coordination, resolved relative to this skill directory. Both bundle their Python package; no pip installation is required for plugin use. Require Python 3.10+, Git, a local project folder, and (CLI only) compatible Codex CLI signed in through ChatGPT. Never read credentials.

## Start: select the requested mode

- In a Codex app task, default to native app mode unless the user asks for a CLI/background worker. In a terminal/CLI session, use CLI mode.
- Missing app automation tools are a real capability limit. Explain it and offer CLI mode; do not fabricate an automation or call a CLI worker app-native continuation.
- Identify the actual project/worktree path. Summarize the current conversation into `.autopilot/MASTER_TASK.md`, `STATUS.md`, and `TASKS.md`: goal, explicit acceptance tests, constraints, completed work, outstanding work. Only initialize once. Preserve existing instructions and edits. These local files are the durable handoff if a run is interrupted before a fresh checkpoint.
- For a new project use `init --init-git --goal "..."`; for an existing Git project use `init --goal "..."`. Avoid `--force` for an existing goal. Do not infer permission to publish, deploy, spend money, or bypass approvals from a request to keep working.

## Native app mode

Read [native-app.md](references/native-app.md). Discover the host's `automation_update` tool. The supported integration is a **heartbeat attached to this task**, not a cron task in a separate conversation. A normal local process cannot revive an app task by itself.

1. Run the app helper `--project "PATH" claim` using this task's `CODEX_THREAD_ID`, or `--owner ACTUAL_THREAD_ID` if the host provides it. Never invent an ID. It refuses another app owner or a running CLI supervisor.
2. Inspect the saved `automation_id` and existing host automation before creating anything. Reuse the existing heartbeat. For a new one, create it paused, attached to the current task, at a 30-minute interval; record its returned real ID with `attach --automation-id ID`, then activate it. Use the host tool schema; never print raw automation directives as if created. Roll back incomplete setup by pausing any created automation, setting STOP, and releasing ownership only when no work is active.
3. Use the continuation prompt in the reference, inserting actual project/helper paths. Keep unchanged/non-actionable checks quiet. Notify only for meaningful changes, completion, failure, or required user action.
4. Begin useful project work in this task. Before each work segment and on every heartbeat run `check` and require `may_work=true`. Never launch `once`, `run`, or `start` in app mode. Do not spawn a second app task to edit the same project.
5. Checkpoint after each meaningful unit and before yielding. Complete only after all acceptance criteria and relevant validation are satisfied; save evidence and create COMPLETE, then pause the heartbeat using its saved ID. A genuine blocker gets BLOCKED and the heartbeat is paused.

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
