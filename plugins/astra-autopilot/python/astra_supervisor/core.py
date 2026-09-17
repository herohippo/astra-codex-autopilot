from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUTOPILOT_DIR = ".autopilot"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
MASTER_TASK = "MASTER_TASK.md"
STATUS_FILE = "STATUS.md"
TASKS_FILE = "TASKS.md"
PROMPT_FILE = "PROMPT.md"
POLICY_FILE = "AUTOPILOT_POLICY.md"
STEERING_FILE = "STEERING.md"
COMPLETE_MARKER = "COMPLETE"
BLOCKED_MARKER = "BLOCKED"
STOP_MARKER = "STOP"
LOCK_FILE = "supervisor.lock"

DEFAULT_CONFIG: dict[str, Any] = {
    "model": "gpt-6-astra",
    "sandbox": "workspace-write",
    "auth_mode": "chatgpt",
    "require_chatgpt_login": True,
    "quota_retry_seconds": 1800,
    "quota_reset_margin_seconds": 60,
    "quota_limit_id": "codex",
    "transient_retry_seconds": 180,
    "unknown_retry_seconds": 900,
    "success_pause_seconds": 30,
    "max_consecutive_unknown_errors": 8,
    "codex_executable": "codex",
    "extra_codex_args": [],
    "minimum_astra_codex_version": "0.153.0",
    "log_dir": ".autopilot/logs",
}

DEFAULT_AGENTS = """# AGENTS.md — Astra Autopilot project policy

## Mission
Work toward the goal in `.autopilot/MASTER_TASK.md` autonomously and incrementally.
Read `.autopilot/STATUS.md`, `.autopilot/TASKS.md`, and `.autopilot/STEERING.md` before choosing work.
Explicit user instructions and newer steering take precedence over this file when they conflict.

## Operating rules
- Prefer action over asking questions when a reasonable, reversible assumption is available.
- Work on the highest-priority unfinished task that can be completed or materially advanced in one turn.
- Inspect existing code before editing. Preserve user-authored behavior unless the goal requires changing it.
- Run focused tests or validation for the files you change. Do not run needlessly broad or destructive tests.
- Keep changes reviewable. Do not rewrite unrelated areas.
- Never read, print, commit, or exfiltrate secrets such as `.env`, tokens, API keys, or `~/.codex/auth.json`.
- Do not push to remotes, publish packages, deploy, purchase anything, or perform irreversible external actions unless `.autopilot/MASTER_TASK.md` explicitly requires it and credentials/approval are already available.

## Checkpoint protocol
Before ending each successful turn:
1. Update `.autopilot/STATUS.md` with what changed, validation performed, and the next concrete step.
2. Update `.autopilot/TASKS.md` checkboxes/priorities when progress changes them.
3. If new user steering exists in `.autopilot/STEERING.md`, apply it and reflect any durable change in the status/task files.
4. If all acceptance criteria in `MASTER_TASK.md` are satisfied, create `.autopilot/COMPLETE` with a short completion note.

## Blocking protocol
Do not repeatedly retry a task that genuinely requires missing secrets, an irreversible external action, or a material product decision that cannot be safely inferred.
In that case, write the exact blocker and required human action to `.autopilot/BLOCKED` and update `STATUS.md`.
The supervisor will stop until the blocker is cleared.
"""

DEFAULT_MASTER = """# Master task

## Goal
{goal}

## Acceptance criteria
- [ ] The requested outcome is implemented, not merely described.
- [ ] Relevant tests or validation pass.
- [ ] User-facing setup/usage documentation is updated when needed.
- [ ] No known critical regression remains unresolved.

## Constraints
- Make reversible assumptions for routine ambiguity and record them in STATUS.md.
- Do not expose secrets or bypass security controls.
- Do not push/deploy/publish unless explicitly required here.
"""

DEFAULT_STATUS = """# Current status

State: READY

## Completed
- Autopilot scaffold initialized.

## Current focus
- Select the first concrete task from MASTER_TASK.md.

## Validation
- Not started.

## Next
- Inspect the repository and create/update TASKS.md with an actionable plan.
"""

DEFAULT_TASKS = """# Task queue

- [ ] Inspect repository structure and current implementation.
- [ ] Translate MASTER_TASK.md acceptance criteria into concrete implementation tasks.
- [ ] Implement the highest-priority task.
- [ ] Run focused validation/tests.
- [ ] Update documentation and completion status.
"""

DEFAULT_PROMPT = """You are an autonomous continuation turn for this repository.

Read the repository AGENTS.md if present, then read these Autopilot control files first:
- .autopilot/AUTOPILOT_POLICY.md
- .autopilot/MASTER_TASK.md
- .autopilot/STATUS.md
- .autopilot/TASKS.md
- .autopilot/STEERING.md (if non-empty)

Then continue the project rather than merely reporting on it. Choose the highest-priority unfinished unit of work that can be completed or materially advanced now. Inspect the relevant code, make concrete edits, and run focused validation.

Do not ask the user a routine clarification question. Make a reasonable reversible assumption and record it in STATUS.md. If you are genuinely blocked by a missing secret, irreversible external action, or material decision that cannot be inferred, write the blocker to .autopilot/BLOCKED and stop cleanly.

Before finishing this turn, update STATUS.md and TASKS.md. If every acceptance criterion is satisfied and validation is complete, create .autopilot/COMPLETE.
"""


# Runtime uses only the standard library. Control files are private local state.
import signal
import threading
import uuid

STOP_NOW_MARKER = "STOP_NOW"
DEFAULT_CONFIG.update({
    "max_turns": 0, "max_runtime_seconds": 0, "turn_timeout_seconds": 0,
    "max_consecutive_transient_errors": 8, "max_log_files": 20,
    "log_tail_bytes": 262144,
})


@dataclass
class RunResult:
    kind: str
    returncode: int
    thread_id: str | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    error_text: str = ""
    stdout: str = ""
    stderr: str = ""
    steering_ids: tuple[str, ...] = ()
    legacy_steering: str = ""


@dataclass
class SupervisorState:
    started_at: str | None = None
    updated_at: str | None = None
    successful_turns: int = 0
    attempted_turns: int = 0
    quota_waits: int = 0
    transient_errors: int = 0
    unknown_errors: int = 0
    consecutive_unknown_errors: int = 0
    consecutive_transient_errors: int = 0
    total_input_tokens: int | None = None
    total_cached_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_reasoning_output_tokens: int | None = None
    usage_observed_turns: int = 0
    usage_unavailable_turns: int = 0
    last_result: str | None = None
    last_thread_id: str | None = None
    last_error: str | None = None
    next_retry_at: str | None = None
    quota_wait_reason: str | None = None
    quota_reset_at: str | None = None
    quota_check_at: str | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def project_paths(project: Path) -> dict[str, Path]:
    base = project / AUTOPILOT_DIR
    # Control paths must stay inside this project's local state, including junctions.
    if base.resolve() != project.resolve() / AUTOPILOT_DIR:
        raise ValueError(".autopilot must not redirect outside the project")
    if base.exists():
        for name in (CONFIG_FILE, STATE_FILE, MASTER_TASK, STATUS_FILE, TASKS_FILE,
                     PROMPT_FILE, POLICY_FILE, STEERING_FILE, LOCK_FILE, "mode.json",
                     "start.lock", "logs", "steering-queue", "steering-history"):
            child = base / name
            if child.resolve() != base.resolve() / name:
                raise ValueError(f"Autopilot control path must not be a link: {name}")
    return {"base": base, **{k: base / v for k, v in {
        "config": CONFIG_FILE, "state": STATE_FILE, "master": MASTER_TASK,
        "status": STATUS_FILE, "tasks": TASKS_FILE, "prompt": PROMPT_FILE,
        "policy": POLICY_FILE, "steering": STEERING_FILE, "complete": COMPLETE_MARKER,
        "blocked": BLOCKED_MARKER, "stop": STOP_MARKER, "stop_now": STOP_NOW_MARKER,
        "lock": LOCK_FILE, "mode": "mode.json",
    }.items()}}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def ensure_git_repo(project: Path, init_git: bool = False) -> None:
    probe = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=15)
    if probe.returncode == 0:
        return
    if not init_git:
        raise RuntimeError("Run git init first or use init --init-git.")
    subprocess.run(["git", "-C", str(project), "init"], check=True, timeout=15)


def init_project(project: Path, goal: str, init_git: bool = False, force: bool = False) -> list[Path]:
    project = project.resolve()
    project.mkdir(parents=True, exist_ok=True)
    ensure_git_repo(project, init_git)
    p = project_paths(project)
    created = []
    with SupervisorLock(p["lock"]):
        if force:
            assert_cli_mode(project)
        contents = {"config": json.dumps(DEFAULT_CONFIG, indent=2) + "\n",
                    "policy": DEFAULT_AGENTS, "master": DEFAULT_MASTER.format(goal=goal.strip() or "Describe the desired outcome."),
                    "status": DEFAULT_STATUS, "tasks": DEFAULT_TASKS, "prompt": DEFAULT_PROMPT, "steering": ""}
        for key, content in contents.items():
            if force or not p[key].exists():
                atomic_write(p[key], content)
                created.append(p[key])
        # Preserve repository rules. Never put private goals/logs in Git by default.
        agents = project / "AGENTS.md"
        if not agents.exists():
            atomic_write(agents, DEFAULT_AGENTS)
            created.append(agents)
        atomic_write(p["base"] / ".gitignore", "*\n")
    return created


def validate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **cfg}
    if cfg["sandbox"] not in ("workspace-write", "read-only"):
        raise ValueError("sandbox must be workspace-write or read-only")
    if cfg["auth_mode"] != "chatgpt" or cfg["require_chatgpt_login"] is not True:
        raise ValueError("Only verified ChatGPT login is supported; API billing is disabled")
    if cfg["extra_codex_args"] != []:
        raise ValueError("extra_codex_args must be empty; arbitrary execution overrides are not supported")
    for key in ("quota_retry_seconds", "quota_reset_margin_seconds", "transient_retry_seconds", "unknown_retry_seconds", "success_pause_seconds",
                "max_turns", "max_runtime_seconds", "turn_timeout_seconds", "max_consecutive_unknown_errors",
                "max_consecutive_transient_errors", "max_log_files", "log_tail_bytes"):
        value = cfg[key]
        if type(value) is not int or value < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    if min(cfg["max_log_files"], cfg["max_consecutive_unknown_errors"], cfg["max_consecutive_transient_errors"]) < 1:
        raise ValueError("Log retention and consecutive error limits must be positive")
    if cfg["quota_reset_margin_seconds"] > 86400 or not 1 <= cfg["quota_retry_seconds"] <= 604800:
        raise ValueError("Quota reset margin must be <=86400; metadata retry must be 1..604800 seconds")
    if not 1024 <= cfg["log_tail_bytes"] <= 4 * 1024 * 1024:
        raise ValueError("log_tail_bytes must be between 1024 and 4194304")
    if cfg["log_dir"] != ".autopilot/logs":
        raise ValueError("log_dir must be .autopilot/logs")
    if not isinstance(cfg["model"], str) or not cfg["model"].strip():
        raise ValueError("model must be a nonempty string")
    if not isinstance(cfg["quota_limit_id"], str) or not cfg["quota_limit_id"].strip():
        raise ValueError("quota_limit_id must be a nonempty string")
    if not isinstance(cfg["codex_executable"], str) or not cfg["codex_executable"].strip():
        raise ValueError("codex_executable must be a single executable path")
    return cfg


def load_config(project: Path) -> dict[str, Any]:
    path = project_paths(project)["config"]
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(raw, dict):
        raise ValueError("config.json must contain a JSON object")
    return validate_config(raw)


def load_state(project: Path) -> SupervisorState:
    path = project_paths(project)["state"]
    if not path.exists():
        return SupervisorState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SupervisorState(**{k: v for k, v in raw.items() if k in SupervisorState.__dataclass_fields__})


def save_state(project: Path, state: SupervisorState) -> None:
    state.updated_at = iso_now()
    atomic_write(project_paths(project)["state"], json.dumps(asdict(state), indent=2) + "\n")


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        raise ValueError(f"Could not parse version: {text!r}")
    return tuple(int(v) for v in match.groups())


def codex_environment(cfg: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    return env


def executable_command(cfg: dict[str, Any]) -> list[str]:
    exe = str(cfg["codex_executable"])
    # Portable test/adapter scripts, executed explicitly rather than by shell association.
    if exe.endswith(".py") and Path(exe).is_file():
        return [sys.executable, str(Path(exe).resolve())]
    found = shutil.which(exe)
    if not found:
        raise RuntimeError(f"Codex CLI executable not found: {exe}")
    return [found]


def auth_check(project: Path, cfg: dict[str, Any], env: dict[str, str]) -> None:
    proc = subprocess.run(executable_command(cfg) + ["-c", 'model_provider="openai"', "-c",
                          'forced_login_method="chatgpt"', "login", "status"],
                          cwd=project, env=env, capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    text = ((proc.stdout or "") + (proc.stderr or "")).lower()
    if proc.returncode or "chatgpt" not in text or "api key" in text or "api_key" in text:
        raise RuntimeError("ChatGPT login could not be verified. Run codex login; no API-key fallback is permitted.")


def validate_codex(project: Path, cfg: dict[str, Any]) -> str:
    cfg = validate_config(cfg)
    env = codex_environment(cfg)
    proc = subprocess.run(executable_command(cfg) + ["--version"], cwd=project, env=env,
                          capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
    version = (proc.stdout or proc.stderr).strip()
    if proc.returncode:
        raise RuntimeError("Unable to run Codex --version")
    if "astra" in cfg["model"].lower() and parse_version(version) < parse_version(cfg["minimum_astra_codex_version"]):
        raise RuntimeError(f"Astra requires Codex >= {cfg['minimum_astra_codex_version']}; found {version}")
    auth_check(project, cfg, env)
    return version


def steering_snapshot(project: Path) -> tuple[str, tuple[str, ...], str]:
    paths = project_paths(project)
    queue = paths["base"] / "steering-queue"
    items = sorted(queue.glob("*.md")) if queue.exists() else []
    legacy = paths["steering"].read_text(encoding="utf-8") if paths["steering"].exists() else ""
    chunks = [legacy] + [path.read_text(encoding="utf-8") for path in items]
    return "\n\n".join(chunks).strip(), tuple(path.name for path in items), legacy


def build_prompt(project: Path, steering: str | None = None) -> str:
    path = project_paths(project)["prompt"]
    prompt = path.read_text(encoding="utf-8") if path.exists() else DEFAULT_PROMPT
    if steering is None:
        steering = steering_snapshot(project)[0]
    if steering:
        prompt += "\n\nUser steering snapshot for this turn:\n" + steering
    return prompt


def add_steering(project: Path, text: str) -> None:
    if not text.strip():
        raise ValueError("Steering must not be empty")
    path = project_paths(project)["base"] / "steering-queue" / (utc_now().strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex + ".md")
    atomic_write(path, f"## {iso_now()}\n{text.strip()}\n")


def archive_steering(project: Path, result: RunResult | None = None) -> None:
    # Only acknowledge the immutable snapshot consumed by this successful turn.
    if result is None:
        return
    base = project_paths(project)["base"]
    history = base / "steering-history"
    history.mkdir(exist_ok=True)
    for name in result.steering_ids:
        path = base / "steering-queue" / name
        if path.exists():
            path.replace(history / name)
    # Legacy editable STEERING.md is deliberately retained: no racing truncation.


def classify_error(text: str) -> str:
    text = text.lower()
    if re.search(r"unauthorized|authentication|not logged in|login required|\b401\b|\b403\b", text):
        return "auth"
    if re.search(r"usage limit|usage.*(?:exhaust|reach|exceed)|allowance.*(?:exhaust|reach|exceed)|quota.*(?:exhaust|reach|exceed)|five[- ]hour|5[- ]hour|weekly limit|limit.*reset|too many requests|\b429\b", text):
        return "quota"
    if re.search(r"timed? out|connection reset|connection refused|network error|temporarily unavailable|service unavailable|internal server error|\b50[234]\b", text):
        return "transient"
    return "unknown"


def parse_jsonl(stdout: str) -> dict[str, Any]:
    result: dict[str, Any] = {"completed": False, "failed": False, "thread_id": None, "usage": {}, "errors": []}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "thread.started" and isinstance(event.get("thread_id"), str):
            result["thread_id"] = event["thread_id"]
        elif kind == "turn.completed":
            result["completed"] = True
            usage = event.get("usage")
            if isinstance(usage, dict):
                result["usage"] = {k: v for k, v in usage.items() if type(v) is int and v >= 0}
        elif kind in ("turn.failed", "error"):
            result["failed"] = True
            result["errors"].append(event)
    return result


class _StreamTail:
    """Drain pipes continuously with bounded retained bytes and bounded JSON lines."""
    def __init__(self, limit: int, events: bool = False):
        self.limit = limit
        self.tail = bytearray()
        self.events = events
        self.parsed = parse_jsonl("")

    def drain(self, pipe) -> None:
        pending = bytearray()
        dropping = False
        try:
            while True:
                data = pipe.read(8192)
                if not data:
                    break
                self.tail.extend(data)
                del self.tail[:-self.limit]
                if not self.events:
                    continue
                for part in data.splitlines(keepends=True):
                    if not dropping:
                        pending.extend(part)
                        if len(pending) > self.limit:
                            pending.clear()
                            dropping = True
                    if part.endswith(b"\n"):
                        if not dropping:
                            self.consume(pending.decode("utf-8", "replace"))
                        pending.clear()
                        dropping = False
            if pending and not dropping:
                self.consume(pending.decode("utf-8", "replace"))
        finally:
            pipe.close()

    def consume(self, line: str) -> None:
        parsed = parse_jsonl(line)
        for key in ("completed", "failed"):
            self.parsed[key] = self.parsed[key] or parsed[key]
        if parsed["thread_id"]:
            self.parsed["thread_id"] = parsed["thread_id"]
        if parsed["completed"]:
            self.parsed["usage"] = parsed["usage"]
        self.parsed["errors"] = (self.parsed["errors"] + parsed["errors"])[-8:]

    def text(self) -> str:
        return self.tail.decode("utf-8", "replace")



class _WindowsJob:
    """Kill-on-close job owns every descendant, including after its parent exits."""
    def __init__(self, proc):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                        ("active_process_limit", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                        ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_mem", ctypes.c_size_t),
                        ("job_mem", ctypes.c_size_t), ("peak_process_mem", ctypes.c_size_t), ("peak_job_mem", ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(proc._handle))):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)
        # Popen closes the initial thread handle. Resume through its process handle.
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        ntdll.NtResumeProcess.restype = ctypes.c_long
        if ntdll.NtResumeProcess(wintypes.HANDLE(int(proc._handle))) != 0:
            self.close()
            raise RuntimeError("Could not resume job-managed Codex process")

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def terminate_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def run_codex_once(project: Path, cfg: dict[str, Any]) -> RunResult:
    cfg = validate_config(cfg)
    env = codex_environment(cfg)
    try:
        auth_check(project, cfg, env)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return RunResult("auth", 1, error_text=str(exc))
    if interruptible_wait(project, 0):
        return RunResult("stopped", 0)
    steering, steering_ids, legacy = steering_snapshot(project)
    prompt = build_prompt(project, steering)
    cmd = executable_command(cfg) + ["-c", 'model_provider="openai"', "-c", 'forced_login_method="chatgpt"',
          "exec", "--json", "--sandbox", cfg["sandbox"], "--model", cfg["model"], "-"]
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW | 0x00000004} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(cmd, cwd=project, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    try:
        job = _WindowsJob(proc)
    except BaseException:
        proc.kill()
        proc.wait(timeout=5)
        raise
    stdout, stderr = _StreamTail(cfg["log_tail_bytes"], True), _StreamTail(cfg["log_tail_bytes"])
    readers = [threading.Thread(target=stdout.drain, args=(proc.stdout,), daemon=True),
               threading.Thread(target=stderr.drain, args=(proc.stderr,), daemon=True)]
    for thread in readers:
        thread.start()
    def write_prompt():
        try:
            proc.stdin.write(prompt.encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.stdin.close()
    writer = threading.Thread(target=write_prompt, daemon=True)
    writer.start()
    def stop_process():
        if os.name == "nt":
            job.close()
            proc.wait(timeout=5)
        else:
            terminate_tree(proc)
    began = time.monotonic()
    forced_kind = None
    try:
        while proc.poll() is None:
            if (project / AUTOPILOT_DIR / STOP_NOW_MARKER).exists():
                forced_kind = "stopped"
                stop_process()
                break
            if cfg["turn_timeout_seconds"] and time.monotonic() - began >= cfg["turn_timeout_seconds"]:
                forced_kind = "timeout"
                stop_process()
                break
            time.sleep(0.1)
    except BaseException:
        stop_process()
        raise
    finally:
        job.close()
        if os.name != "nt":
            terminate_tree(proc)
        for thread in readers:
            thread.join(timeout=2)
        if any(thread.is_alive() for thread in readers):
            # A grandchild inherited a pipe after its parent exited.
            terminate_tree(proc)
            for thread in readers:
                thread.join(timeout=2)
        writer.join(timeout=2)
    parsed = stdout.parsed
    error = (stderr.text() + ("\n" + json.dumps(parsed["errors"], ensure_ascii=False) if parsed["errors"] else "")).strip()[-8000:]
    kind = forced_kind or ("success" if proc.returncode == 0 and parsed["completed"] and not parsed["failed"] else classify_error(error))
    usage = parsed["usage"]
    return RunResult(kind, proc.returncode, parsed["thread_id"],
                     usage.get("input_tokens"), usage.get("cached_input_tokens"), usage.get("output_tokens"),
                     usage.get("reasoning_output_tokens"), error, stdout.text(), stderr.text(), steering_ids, legacy)


def log_run(project: Path, cfg: dict[str, Any], result: RunResult) -> Path:
    directory = project_paths(project)["base"] / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (utc_now().strftime("%Y%m%dT%H%M%S%f") + "-" + result.kind + ".log")
    body = json.dumps({k: v for k, v in asdict(result).items() if k not in ("stdout", "stderr", "legacy_steering")}, ensure_ascii=False)
    atomic_write(path, body + "\n=== STDOUT TAIL ===\n" + result.stdout + "\n=== STDERR TAIL ===\n" + result.stderr)
    for old in sorted(directory.glob("*.log"))[:-cfg["max_log_files"]]:
        old.unlink(missing_ok=True)
    return path


def update_state_from_result(state: SupervisorState, result: RunResult) -> None:
    state.attempted_turns += 1
    state.last_result, state.last_thread_id = result.kind, result.thread_id
    available = False
    for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"):
        value = getattr(result, key)
        if value is not None:
            available = True
            setattr(state, "total_" + key, (getattr(state, "total_" + key) or 0) + value)
    state.usage_observed_turns += int(available)
    state.usage_unavailable_turns += int(not available)
    state.last_error = result.error_text or None
    state.next_retry_at = None
    state.consecutive_unknown_errors = state.consecutive_unknown_errors + 1 if result.kind == "unknown" else 0
    state.consecutive_transient_errors = state.consecutive_transient_errors + 1 if result.kind == "transient" else 0
    field = {"success": "successful_turns", "quota": "quota_waits", "transient": "transient_errors", "unknown": "unknown_errors"}.get(result.kind)
    if field:
        setattr(state, field, getattr(state, field) + 1)


def set_marker(project: Path, marker: str, content: str = "") -> Path:
    if marker not in (STOP_MARKER, STOP_NOW_MARKER, BLOCKED_MARKER, COMPLETE_MARKER):
        raise ValueError("Unsupported marker")
    path = project_paths(project)["base"] / marker
    atomic_write(path, content or iso_now() + "\n")
    return path


def clear_marker(project: Path, marker: str) -> bool:
    path = project / AUTOPILOT_DIR / marker
    if path.exists():
        path.unlink()
        return True
    return False


class SupervisorLock:
    """Kernel lock, automatically released at process exit; never unlink its inode."""
    def __init__(self, path: Path, force: bool = False):
        self.path = path
        self.acquired = False
        self.handle = None
        if force:
            raise ValueError("Force-stealing a lock is unsupported; OS locks recover after crashes")

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b" ")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Supervisor already running; lock is held") from exc
        self.acquired = True

    def release(self) -> None:
        if self.handle is not None:
            if self.acquired:
                if os.name == "nt":
                    import msvcrt
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None
        self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


def supervisor_running(project: Path) -> bool:
    if not project_paths(project)["base"].exists():
        return False
    lock = SupervisorLock(project_paths(project)["lock"])
    try:
        lock.acquire()
    except RuntimeError:
        return True
    lock.release()
    return False


def get_status(project: Path) -> dict[str, Any]:
    p = project_paths(project)
    mode = json.loads(p["mode"].read_text(encoding="utf-8")) if p["mode"].exists() else {"mode": "cli"}
    return {"project": str(project.resolve()), "complete": p["complete"].exists(),
            "blocked": p["blocked"].exists(), "stopped": p["stop"].exists(),
            "running": supervisor_running(project), "mode": mode,
            "state": asdict(load_state(project))}


def interruptible_wait(project: Path, seconds: float, poll_seconds: float = 0.2) -> str | None:
    deadline = time.monotonic() + max(0, seconds)
    while True:
        for marker in (COMPLETE_MARKER, BLOCKED_MARKER, STOP_MARKER, STOP_NOW_MARKER):
            if (project / AUTOPILOT_DIR / marker).exists():
                return marker
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(max(0.05, poll_seconds), remaining))


def assert_cli_mode(project: Path) -> None:
    path = project_paths(project)["mode"]
    if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("mode") == "app":
        raise RuntimeError("This project is attached to Codex app mode. Detach app mode before starting CLI execution.")


def run_loop(project: Path, once: bool = False, force_lock: bool = False, ready_file: Path | None = None) -> int:
    project = project.resolve()
    p = project_paths(project)
    ensure_git_repo(project)
    with SupervisorLock(p["lock"], force=force_lock):
        assert_cli_mode(project)
        if not p["master"].exists():
            raise RuntimeError("Autopilot is not initialized. Run init --goal first.")
        cfg = load_config(project)
        # Validate version before launching work; every turn separately rechecks login.
        if not interruptible_wait(project, 0):
            validate_codex(project, cfg)
        state = load_state(project)  # Never read mutable state before obtaining ownership.
        state.started_at = state.started_at or iso_now()
        save_state(project, state)
        if ready_file:
            atomic_write(ready_file, json.dumps({"pid": os.getpid(), "ready": True}))
        began, turns = time.monotonic(), 0
        while True:
            marker = interruptible_wait(project, 0)
            if marker:
                print(f"{marker}: exiting.", flush=True)
                return 0
            if cfg["max_turns"] and turns >= cfg["max_turns"]:
                set_marker(project, STOP_MARKER, "Configured max_turns reached. Resume to continue.\n")
                return 0
            remaining = cfg["max_runtime_seconds"] - (time.monotonic() - began) if cfg["max_runtime_seconds"] else None
            if remaining is not None and remaining <= 0:
                set_marker(project, STOP_MARKER, "Configured max_runtime_seconds reached.\n")
                return 0
            if state.next_retry_at:
                retry_at = datetime.fromisoformat(state.next_retry_at)
                if retry_at.tzinfo is None:
                    raise ValueError("next_retry_at must include timezone")
                delay = max(0, retry_at.timestamp() - utc_now().timestamp())
                if delay:
                    if interruptible_wait(project, min(delay, remaining) if remaining is not None else delay):
                        return 0
                    if remaining is not None and delay >= remaining:
                        continue
                state.next_retry_at = None
                save_state(project, state)
            if state.last_result == "quota":
                from .quota import refresh_quota
                available = refresh_quota(project, cfg, state)
                save_state(project, state)
                if not available:
                    if once:
                        return 3
                    continue
            if cfg["max_runtime_seconds"] and time.monotonic() - began >= cfg["max_runtime_seconds"]:
                set_marker(project, STOP_MARKER, "Configured max_runtime_seconds reached during quota lookup.\n")
                return 0
            turn_cfg = dict(cfg)
            if remaining is not None:
                cap = max(1, int(cfg["max_runtime_seconds"] - (time.monotonic() - began)))
                turn_cfg["turn_timeout_seconds"] = min(cap, cfg["turn_timeout_seconds"]) if cfg["turn_timeout_seconds"] else cap
            result = run_codex_once(project, turn_cfg)
            turns += 1
            log = log_run(project, cfg, result)
            update_state_from_result(state, result)
            print(f"[{iso_now()}] {result.kind}; observed tokens(in/out)={result.input_tokens}/{result.output_tokens}; log={log}", flush=True)
            if result.kind == "success":
                archive_steering(project, result)
                delay = cfg["success_pause_seconds"]
            elif result.kind == "quota":
                from .quota import refresh_quota
                refresh_quota(project, cfg, state)
                # A contradictory available response immediately after rejection
                # must not produce a tight model retry loop.
                delay = max(1, cfg["quota_retry_seconds"])
            elif result.kind == "transient":
                delay = cfg["transient_retry_seconds"]
            elif result.kind == "unknown":
                delay = cfg["unknown_retry_seconds"]
            else:
                delay = 0
            if result.kind in ("auth", "timeout"):
                set_marker(project, BLOCKED_MARKER, f"{result.kind}: {result.error_text}\nReview and resume --blocked.\n")
            if state.consecutive_unknown_errors >= cfg["max_consecutive_unknown_errors"] or state.consecutive_transient_errors >= cfg["max_consecutive_transient_errors"]:
                set_marker(project, BLOCKED_MARKER, "Repeated execution errors. Inspect logs before resume --blocked.\n")
            if (delay or result.kind in ("quota", "transient", "unknown")) and not state.next_retry_at:
                state.next_retry_at = datetime.fromtimestamp(utc_now().timestamp() + max(1, delay), timezone.utc).isoformat()
            save_state(project, state)
            if once:
                return {"success": 0, "quota": 3, "auth": 4, "transient": 5, "unknown": 6, "stopped": 0, "timeout": 7}[result.kind]
            if result.kind == "stopped":
                return 0


def start_background(project: Path) -> dict[str, Any]:
    project = project.resolve()
    assert_cli_mode(project)
    p = project_paths(project)
    if not p["master"].exists():
        raise RuntimeError("Initialize this project first")
    if interruptible_wait(project, 0):
        raise RuntimeError("Project has a stop/completion/blocker marker; resolve it before start")
    # Startup is serialized independently; worker owns the execution lock.
    with SupervisorLock(p["base"] / "start.lock"):
        if supervisor_running(project):
            raise RuntimeError("Supervisor already running")
        load_config(project)
        ready = p["base"] / ("ready-" + uuid.uuid4().hex + ".json")
        env = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = package_root
        cmd = [sys.executable, "-m", "astra_supervisor.cli", "--project", str(project), "run", "--ready-file", str(ready)]
        kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        # A target repository must not shadow the installed supervisor package.
        proc = subprocess.Popen(cmd, cwd=package_root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        acknowledged = False
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if ready.exists():
                    info = json.loads(ready.read_text(encoding="utf-8"))
                    ready.unlink(missing_ok=True)
                    acknowledged = True
                    return info
                if proc.poll() is not None:
                    raise RuntimeError("Background supervisor failed during startup; run foreground for diagnostics")
                time.sleep(0.1)
            raise RuntimeError("Background startup timed out")
        finally:
            if not acknowledged:
                if proc.poll() is None:
                    terminate_tree(proc)
                ready.unlink(missing_ok=True)
