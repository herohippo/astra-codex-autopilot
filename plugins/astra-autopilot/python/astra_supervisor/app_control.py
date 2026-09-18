"""Local coordination for native Codex app heartbeats; never starts a CLI worker."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .core import (SupervisorLock, get_status, iso_now, project_paths, set_marker,
                   load_config, load_state, save_state, utc_now)
from datetime import datetime


def binding_path(project: Path) -> Path:
    return project_paths(project)["base"] / "mode.json"


def binding(project: Path) -> dict:
    path = binding_path(project)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_binding(project: Path, data: dict) -> None:
    path = binding_path(project)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def require_owner(data: dict, owner: str) -> None:
    if not owner:
        raise RuntimeError("Current app task ID is required (--owner or CODEX_THREAD_ID).")
    if data.get("mode") != "app" or data.get("owner") != owner:
        raise RuntimeError("This app task does not own the project. Use the original task to pause/release it.")


def control(project: Path, action: str, owner: str, automation_id: str = "",
            automation_paused: bool = False, automation_deleted: bool = False) -> dict:
    project = project.resolve()
    p = project_paths(project)
    if not p["master"].exists():
        raise RuntimeError("Initialize the project first with init --goal.")
    if action == "status":
        return {**get_status(project), "binding": binding(project)}
    # Brief OS lock also serializes mode switching with supervisor startup.
    with SupervisorLock(p["lock"]):
        data = binding(project)
        if action == "claim":
            if not owner:
                raise RuntimeError("Current app task ID is required (--owner or CODEX_THREAD_ID).")
            if data.get("mode") == "app" and data.get("owner") != owner:
                raise RuntimeError("Another app task owns this project. Pause and release it there first.")
            data = {**data, "mode": "app", "owner": owner, "updated_at": iso_now()}
            write_binding(project, data)
        elif action == "attach":
            require_owner(data, owner)
            if p["complete"].exists():
                raise RuntimeError("Project is complete. Explicitly reset completion before attaching new work.")
            if not automation_id.strip():
                raise RuntimeError("A successfully created automation ID is required.")
            if data.get("automation_id") not in (None, automation_id):
                raise RuntimeError("A heartbeat is already attached. Update that automation instead of creating another.")
            data.update(automation_id=automation_id, updated_at=iso_now())
            write_binding(project, data)
        elif action == "finish":
            require_owner(data, owner)
            if not p["complete"].exists() or not p["complete"].read_text(encoding="utf-8").strip():
                raise RuntimeError("Record COMPLETE with validation evidence before finishing.")
            if not automation_deleted or not automation_id:
                raise RuntimeError("Confirm host deletion first; pass --automation-deleted and the exact --automation-id.")
            if data.get("automation_id") is None and data.get("deleted_automation_id") == automation_id:
                pass  # Idempotent acknowledgement after confirmed host deletion.
            elif data.get("automation_id") != automation_id:
                raise RuntimeError("Automation ID does not match this project's saved heartbeat.")
            else:
                data.update(automation_id=None, deleted_automation_id=automation_id,
                            automation_deleted_at=iso_now(), updated_at=iso_now())
                write_binding(project, data)
        elif action == "check":
            require_owner(data, owner)
            if not any(p[k].exists() for k in ("complete", "blocked", "stop")):
                from .quota import refresh_quota
                state = load_state(project)
                due = not state.next_retry_at or datetime.fromisoformat(state.next_retry_at).timestamp() <= utc_now().timestamp()
                if due:
                    refresh_quota(project, load_config(project), state)
                    save_state(project, state)
        elif action == "pause":
            require_owner(data, owner)
            set_marker(project, "STOP", "Paused from the Codex app.\n")
        elif action == "release":
            require_owner(data, owner)
            if not automation_paused or not p["stop"].exists():
                raise RuntimeError("Pause the app automation, stop active app work, and set STOP before release; then pass --automation-paused.")
            write_binding(project, {"mode": "cli", "updated_at": iso_now()})
            data = binding(project)
        # We hold this short control lock ourselves; it is not a running worker.
        status = {**get_status(project), "running": False, "binding": data}
        status["cleanup_action"] = (
            "delete_automation" if data.get("mode") == "app" and data.get("owner") == owner
            and p["complete"].exists() and p["complete"].read_text(encoding="utf-8").strip()
            and data.get("automation_id") else None)
        status["may_work"] = (data.get("mode") == "app" and data.get("owner") == owner
                              and not any(p[k].exists() for k in ("complete", "blocked", "stop")))
        if action == "check":
            state = load_state(project)
            status["may_work"] = status["may_work"] and state.quota_wait_reason == "available"
            if state.next_retry_at and datetime.fromisoformat(state.next_retry_at).timestamp() > utc_now().timestamp():
                status["may_work"] = False
            status["next_check_at"] = state.next_retry_at
            status["quota_wait_reason"] = state.quota_wait_reason
        return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("action", choices=["claim", "attach", "check", "pause", "release", "status", "finish"])
    parser.add_argument("--owner", default=os.environ.get("CODEX_THREAD_ID", ""))
    parser.add_argument("--automation-id", default="")
    parser.add_argument("--automation-paused", action="store_true")
    parser.add_argument("--automation-deleted", action="store_true", help="Acknowledge confirmed deletion through the host automation tool")
    args = parser.parse_args(argv)
    try:
        result = control(Path(args.project), args.action, args.owner,
                         args.automation_id, args.automation_paused, args.automation_deleted)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
