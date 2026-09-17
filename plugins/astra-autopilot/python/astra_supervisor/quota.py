"""Read documented Codex quota metadata without starting a model turn."""
from __future__ import annotations

import json
import math
import os
import queue
import subprocess
import threading
import time


def read_limits(project, cfg, timeout=20):
    from .core import executable_command, codex_environment, _WindowsJob, terminate_tree
    command = executable_command(cfg) + ["-c", 'model_provider="openai"',
               "-c", 'forced_login_method="chatgpt"', "app-server"]
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | 0x4} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(command, cwd=project, env=codex_environment(cfg),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, **flags)
    job = None
    messages = queue.Queue(maxsize=16)
    finished = threading.Event()
    def reader():
        try:
            while not finished.is_set():
                line = proc.stdout.readline(1024 * 1024 + 1)
                if not line:
                    return
                if len(line) > 1024 * 1024:
                    return
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(message, dict) and message.get("id") in (1, 2):
                    try:
                        messages.put_nowait(message)
                    except queue.Full:
                        return
        finally:
            proc.stdout.close()
    worker = threading.Thread(target=reader, daemon=True)
    try:
        job = _WindowsJob(proc)
        worker.start()
        deadline = time.monotonic() + timeout
        def send(message):
            proc.stdin.write((json.dumps(message) + "\n").encode())
            proc.stdin.flush()
        def response(identifier):
            while time.monotonic() < deadline:
                if any((project / ".autopilot" / name).exists() for name in ("STOP", "STOP_NOW", "COMPLETE", "BLOCKED")):
                    raise RuntimeError("Quota lookup cancelled")
                try:
                    message = messages.get(timeout=min(.1, max(.001, deadline - time.monotonic())))
                except queue.Empty:
                    if proc.poll() is not None:
                        raise RuntimeError("Quota service exited")
                    continue
                if message.get("id") == identifier:
                    if "error" in message or not isinstance(message.get("result"), dict):
                        raise RuntimeError("Quota service rejected request")
                    return message["result"]
            raise RuntimeError("Quota lookup timed out")
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "astra_autopilot", "version": "0.3.0"}}})
        response(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "account/rateLimits/read"})
        return response(2)
    finally:
        finished.set()
        if job is not None:
            job.close()
        if os.name != "nt":
            terminate_tree(proc)
        elif proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        proc.stdin.close()
        if worker.ident is not None:
            worker.join(timeout=2)
        else:
            proc.stdout.close()


def quota_decision(payload, now, bucket="codex", margin=60):
    """Return (ready/wait/unknown, UTC epoch or None). Never guess a bucket."""
    if not isinstance(payload, dict):
        return "unknown", None
    buckets = payload.get("rateLimitsByLimitId")
    limits = buckets.get(bucket) if isinstance(buckets, dict) else payload.get("rateLimits")
    if not isinstance(limits, dict) or limits.get("limitId") not in (None, bucket):
        return "unknown", None
    observed, resets, uncertain = False, [], False
    for key in ("primary", "secondary"):
        window = limits.get(key)
        if window is None:
            continue
        if not isinstance(window, dict):
            uncertain = True
            continue
        used = window.get("usedPercent")
        if type(used) not in (int, float) or not 0 <= used <= 1000000 or not math.isfinite(used):
            uncertain = True
            continue
        observed = True
        if used >= 100:
            reset = window.get("resetsAt")
            if type(reset) not in (int, float) or not now < reset < 253402214400 or not math.isfinite(reset):
                uncertain = True
            else:
                resets.append(reset + margin)
    if resets:
        return "wait", max(resets)
    if observed and not uncertain and not limits.get("rateLimitReachedType"):
        return "ready", None
    return "unknown", None


def refresh_quota(project, cfg, state):
    from .core import utc_now
    from datetime import datetime, timezone
    now = utc_now().timestamp()
    try:
        decision, reset = quota_decision(read_limits(project, cfg), now,
                                        cfg["quota_limit_id"], cfg["quota_reset_margin_seconds"])
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        decision, reset = "unknown", None
    state.quota_check_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
    state.quota_wait_reason = {"ready": "available", "wait": "reset_time", "unknown": "metadata_unavailable"}[decision]
    state.quota_reset_at = datetime.fromtimestamp(reset, timezone.utc).isoformat() if reset else None
    state.next_retry_at = state.quota_reset_at if decision == "wait" else (
        None if decision == "ready" else datetime.fromtimestamp(now + max(1, cfg["quota_retry_seconds"]), timezone.utc).isoformat())
    return decision == "ready"
