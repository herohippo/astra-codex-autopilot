from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import (
    AUTOPILOT_DIR,
    BLOCKED_MARKER,
    COMPLETE_MARKER,
    STOP_MARKER,
    STOP_NOW_MARKER,
    SupervisorLock,
    project_paths,
    start_background,
    add_steering,
    clear_marker,
    get_status,
    init_project,
    ensure_git_repo,
    load_config,
    run_loop,
    validate_codex,
    set_marker,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="astra-autopilot",
        description="Run Codex/Astra autonomously with checkpoints and usage-limit retry.",
    )
    p.add_argument("--project", default=".", help="Target Git repository (default: current directory)")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize .autopilot control files and AGENTS.md")
    init.add_argument("--goal", default="", help="Natural-language project goal")
    init.add_argument("--goal-file", help="Read project goal from a text/Markdown file")
    init.add_argument("--init-git", action="store_true", help="Run git init if needed")
    init.add_argument("--force", action="store_true", help="Overwrite existing control files")

    once = sub.add_parser("once", help="Run exactly one autonomous Codex turn")
    once.add_argument("--force-lock", action="store_true")

    run = sub.add_parser("run", help="Run continuously until COMPLETE, BLOCKED, STOP, or fatal error")
    run.add_argument("--force-lock", action="store_true")

    run.add_argument("--ready-file", help=argparse.SUPPRESS)
    sub.add_parser("start", help="Start a detached local supervisor")

    sub.add_parser("status", help="Print supervisor state as JSON")
    sub.add_parser("doctor", help="Validate Git/Codex/config prerequisites")

    steer = sub.add_parser("steer", help="Queue a natural-language instruction for the next successful turn")
    steer.add_argument("text", nargs="+", help="Steering instruction")

    stop = sub.add_parser("stop", help="Stop after the current turn")
    stop.add_argument("--now", action="store_true", help="Terminate active Codex and child processes")
    resume = sub.add_parser("resume", help="Clear STOP and optionally BLOCKED, then allow future runs")
    resume.add_argument("--start", action="store_true", help="Start a detached supervisor after clearing markers")
    resume.add_argument("--blocked", action="store_true", help="Also clear BLOCKED marker")
    reset = sub.add_parser("reset-complete", help="Clear COMPLETE marker to continue work")
    reset.add_argument("--yes", action="store_true", help="Required confirmation flag")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = Path(args.project).resolve()
    try:
        if args.command == "init":
            goal = args.goal
            if args.goal_file:
                goal = Path(args.goal_file).read_text(encoding="utf-8")
            created = init_project(project, goal, init_git=args.init_git, force=args.force)
            print("Initialized Astra Autopilot.")
            for path in created:
                print(f"  created: {path.relative_to(project)}")
            print(f"Edit {AUTOPILOT_DIR}/MASTER_TASK.md if you want to refine the acceptance criteria.")
            return 0
        if args.command == "once":
            return run_loop(project, once=True, force_lock=args.force_lock)
        if args.command == "run":
            return run_loop(project, once=False, force_lock=args.force_lock, ready_file=Path(args.ready_file) if args.ready_file else None)
        if args.command == "start":
            print(json.dumps(start_background(project)))
            return 0
        if args.command == "status":
            print(json.dumps(get_status(project), indent=2, ensure_ascii=False))
            return 0
        if args.command == "doctor":
            ensure_git_repo(project)
            cfg = load_config(project)
            version = validate_codex(project, cfg)
            print(json.dumps({"ok": True, "codex": version, "model": cfg["model"], "auth_mode": cfg["auth_mode"], "chatgpt_login_verified": str(cfg.get("auth_mode", "")).lower() == "chatgpt"}, indent=2))
            return 0
        if args.command == "steer":
            text = " ".join(args.text)
            add_steering(project, text)
            print("Queued steering instruction for the next turn.")
            return 0
        if args.command == "stop":
            path = set_marker(project, STOP_MARKER, "Stopped by user.\n")
            if args.now:
                set_marker(project, STOP_NOW_MARKER, "Immediate stop requested by user.\n")
            print(f"Created {path}")
            return 0
        if args.command == "resume":
            with SupervisorLock(project_paths(project)["lock"]):
                clear_marker(project, STOP_MARKER)
                clear_marker(project, STOP_NOW_MARKER)
                if args.blocked:
                    clear_marker(project, BLOCKED_MARKER)
            if args.start:
                print(json.dumps(start_background(project)))
            else:
                print("Resume markers cleared. Run start or run to continue.")
            return 0
        if args.command == "reset-complete":
            if not args.yes:
                print("Refusing to clear COMPLETE without --yes", file=sys.stderr)
                return 2
            clear_marker(project, COMPLETE_MARKER)
            print("COMPLETE marker cleared.")
            return 0
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
