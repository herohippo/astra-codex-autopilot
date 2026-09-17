import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from astra_supervisor.core import (DEFAULT_CONFIG, SupervisorLock, SupervisorState, RunResult,
    add_steering, archive_steering, build_prompt, init_project, load_state, parse_jsonl,
    project_paths, run_codex_once, run_loop, save_state, set_marker, start_background,
    update_state_from_result, validate_config, get_status)


def setup_project(path, body=""):
    init_project(path, "Build a tested MVP", init_git=True)
    fake = path / "fake.py"
    fake.write_text('''import sys,json,time,subprocess,os
from pathlib import Path
args=sys.argv[1:]
if args == ['--version']:
 print('codex-cli 0.153.1'); sys.exit()
if args[-2:] == ['login','status']:
 print('Logged in using ChatGPT'); sys.exit()
prompt=sys.stdin.read()
Path('received.txt').write_text(prompt)
''' + body, encoding="utf-8")
    cfg = {**DEFAULT_CONFIG, "codex_executable": str(fake), "success_pause_seconds": 0,
           "quota_retry_seconds": 1, "transient_retry_seconds": 1, "unknown_retry_seconds": 1}
    project_paths(path)["config"].write_text(json.dumps(cfg), encoding="utf-8")
    return cfg


def wait_for(path, timeout=8):
    end = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < end:
        time.sleep(.05)
    assert path.exists()


def test_malformed_json_and_usage():
    parsed = parse_jsonl('null\n[]\n42\n{"type":"turn.completed","usage":{"input_tokens":"bad","output_tokens":5}}\n')
    assert parsed["completed"] and parsed["usage"] == {"output_tokens": 5}
    state = SupervisorState()
    update_state_from_result(state, RunResult("quota", 1))
    assert state.total_input_tokens is None
    assert state.usage_unavailable_turns == 1


@pytest.mark.parametrize("change", [{"sandbox":"danger-full-access"}, {"auth_mode":"api"},
    {"require_chatgpt_login":False}, {"extra_codex_args":["--yolo"]}, {"max_turns":-1}, {"log_dir":"../other"}])
def test_unsafe_config_rejected(change):
    with pytest.raises(ValueError):
        validate_config(change)


def test_lock_cannot_steal_and_recovers(tmp_path):
    path = tmp_path / "lock"
    with SupervisorLock(path):
        with pytest.raises(RuntimeError):
            SupervisorLock(path).acquire()
        with pytest.raises(ValueError):
            SupervisorLock(path, force=True)
    with SupervisorLock(path):
        pass


def test_quota_then_success_and_complete(tmp_path, monkeypatch):
    monkeypatch.setattr("astra_supervisor.quota.read_limits", lambda *args: {"rateLimits": {"primary": {"usedPercent": 0}}})
    setup_project(tmp_path, '''count=Path('count')
n=int(count.read_text()) if count.exists() else 0
count.write_text(str(n+1))
if n == 0:
 print(json.dumps({'type':'turn.failed','error':{'message':'Usage limit reached'}})); sys.exit(1)
Path('.autopilot/COMPLETE').write_text('Tests passed')
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':8,'output_tokens':3}}))
''')
    assert run_loop(tmp_path) == 0
    state = load_state(tmp_path)
    assert state.quota_waits == 1 and state.successful_turns == 1
    assert state.usage_unavailable_turns == 1 and state.total_input_tokens == 8


def test_agent_text_cannot_trigger_quota_retry(tmp_path):
    cfg = setup_project(tmp_path, "print(json.dumps({'type':'item.completed','item':{'text':'Usage limit reached'}})); sys.exit(1)\n")
    assert run_codex_once(tmp_path, cfg).kind == "unknown"


def test_steering_arriving_during_turn_is_not_consumed(tmp_path):
    cfg = setup_project(tmp_path, "Path('active').touch(); time.sleep(.5); print(json.dumps({'type':'turn.completed'}))\n")
    add_steering(tmp_path, "first instruction")
    results = []
    thread = threading.Thread(target=lambda: results.append(run_codex_once(tmp_path, cfg)))
    thread.start()
    wait_for(tmp_path / "active")
    add_steering(tmp_path, "second instruction")
    thread.join(10)
    assert not thread.is_alive()
    archive_steering(tmp_path, results[0])
    prompt = build_prompt(tmp_path)
    assert "second instruction" in prompt and "first instruction" not in prompt
    assert "first instruction" in (tmp_path / "received.txt").read_text()


def test_stop_now_terminates_active_turn(tmp_path):
    cfg = setup_project(tmp_path, "Path('active').touch(); time.sleep(60)\n")
    results = []
    thread = threading.Thread(target=lambda: results.append(run_codex_once(tmp_path, cfg)))
    thread.start()
    wait_for(tmp_path / "active")
    set_marker(tmp_path, "STOP_NOW")
    thread.join(8)
    assert not thread.is_alive() and results[0].kind == "stopped"


def test_runtime_timeout(tmp_path):
    cfg = setup_project(tmp_path, "time.sleep(60)\n")
    cfg["turn_timeout_seconds"] = 1
    assert run_codex_once(tmp_path, cfg).kind == "timeout"


def test_persistent_wait_does_not_launch_on_restart(tmp_path):
    from datetime import datetime, timezone
    setup_project(tmp_path, "print(json.dumps({'type':'turn.completed'}))\n")
    state = SupervisorState(next_retry_at=datetime.fromtimestamp(time.time()+60, timezone.utc).isoformat())
    save_state(tmp_path, state)
    thread = threading.Thread(target=lambda: run_loop(tmp_path))
    thread.start()
    time.sleep(.4)
    set_marker(tmp_path, "STOP")
    thread.join(4)
    assert not thread.is_alive() and not (tmp_path / "received.txt").exists()
    assert load_state(tmp_path).next_retry_at == state.next_retry_at


def test_detached_start_duplicate_and_stop(tmp_path):
    setup_project(tmp_path, "Path('active').touch(); time.sleep(60)\n")
    info = start_background(tmp_path)
    assert info["ready"]
    try:
        wait_for(tmp_path / "active")
        with pytest.raises(RuntimeError, match="already running"):
            start_background(tmp_path)
    finally:
        set_marker(tmp_path, "STOP")
        set_marker(tmp_path, "STOP_NOW")
    end = time.monotonic() + 8
    while get_status(tmp_path)["running"] and time.monotonic() < end:
        time.sleep(.1)
    assert not get_status(tmp_path)["running"]


def test_app_mode_blocks_cli(tmp_path):
    setup_project(tmp_path)
    project_paths(tmp_path)["mode"].write_text('{"mode":"app"}')
    with pytest.raises(RuntimeError, match="app mode"):
        run_loop(tmp_path, once=True)
    with pytest.raises(RuntimeError, match="app mode"):
        start_background(tmp_path)
    with pytest.raises(RuntimeError, match="app mode"):
        init_project(tmp_path, "new", force=True)


def test_bounded_output_and_stdin_long_prompt(tmp_path):
    cfg = setup_project(tmp_path, "print('x'*1000000); print(json.dumps({'type':'turn.completed'}))\n")
    cfg["log_tail_bytes"] = 4096
    project_paths(tmp_path)["prompt"].write_text('long prompt ' * 10000)
    result = run_codex_once(tmp_path, cfg)
    assert result.kind == "success" and len(result.stdout.encode()) <= 4096
    assert (tmp_path / "received.txt").stat().st_size > 100000


def test_auth_rechecked_before_each_turn(tmp_path):
    cfg = setup_project(tmp_path, "print(json.dumps({'type':'turn.completed'}))\n")
    fake = Path(cfg["codex_executable"])
    fake.write_text(fake.read_text().replace("print('Logged in using ChatGPT'); sys.exit()", "print('Logged in using API key'); sys.exit()"))
    assert run_codex_once(tmp_path, cfg).kind == "auth"
    assert not (tmp_path / "received.txt").exists()


def test_private_files_ignored(tmp_path):
    setup_project(tmp_path)
    result = subprocess.run(['git','-C',str(tmp_path),'check-ignore','.autopilot/MASTER_TASK.md'],capture_output=True)
    assert result.returncode == 0

def test_stop_now_kills_descendant(tmp_path):
    cfg = setup_project(tmp_path, '''child = subprocess.Popen([sys.executable, '-c', "import time; from pathlib import Path; Path('child-active').touch(); time.sleep(2); Path('child-survived').touch(); time.sleep(30)"])
Path('active').touch()
time.sleep(60)
''')
    results = []
    thread = threading.Thread(target=lambda: results.append(run_codex_once(tmp_path, cfg)))
    thread.start()
    wait_for(tmp_path / "child-active")
    set_marker(tmp_path, "STOP_NOW")
    thread.join(8)
    time.sleep(2.1)
    assert not thread.is_alive() and results[0].kind == "stopped"
    assert not (tmp_path / "child-survived").exists()


def test_graceful_stop_finishes_current_turn(tmp_path):
    setup_project(tmp_path, "Path('active').touch(); time.sleep(.4); Path('finished').touch(); print(json.dumps({'type':'turn.completed'}))\n")
    thread = threading.Thread(target=lambda: run_loop(tmp_path))
    thread.start()
    wait_for(tmp_path / "active")
    set_marker(tmp_path, "STOP")
    thread.join(6)
    assert not thread.is_alive() and (tmp_path / "finished").exists()
    assert load_state(tmp_path).successful_turns == 1


def test_turn_cap(tmp_path):
    cfg = setup_project(tmp_path, "print(json.dumps({'type':'turn.completed'}))\n")
    cfg["max_turns"] = 2
    project_paths(tmp_path)["config"].write_text(json.dumps(cfg))
    assert run_loop(tmp_path) == 0
    assert load_state(tmp_path).successful_turns == 2
    assert project_paths(tmp_path)["stop"].exists()


def test_detached_uses_trusted_supervisor_package(tmp_path):
    setup_project(tmp_path, "Path('.autopilot/COMPLETE').touch(); print(json.dumps({'type':'turn.completed'}))\n")
    shadow = tmp_path / "astra_supervisor"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise RuntimeError('shadow supervisor imported')\n")
    info = start_background(tmp_path)
    assert info["ready"]
    wait_for(project_paths(tmp_path)["complete"])


def test_interrupted_start_cleans_worker(tmp_path, monkeypatch):
    import astra_supervisor.core as core
    setup_project(tmp_path)
    class Child:
        pid = 999999
        alive = True
        def poll(self):
            return None if self.alive else 1
    child = Child()
    monkeypatch.setattr(core.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(core.time, "sleep", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(core, "terminate_tree", lambda proc: setattr(proc, "alive", False))
    with pytest.raises(KeyboardInterrupt):
        start_background(tmp_path)
    assert not child.alive
    assert not list(project_paths(tmp_path)["base"].glob("ready-*.json"))


def test_stop_before_turn_does_not_spawn_model(tmp_path):
    cfg = setup_project(tmp_path, "Path('unexpected-model-run').touch()\n")
    set_marker(tmp_path, "STOP_NOW")
    assert run_codex_once(tmp_path, cfg).kind == "stopped"
    assert not (tmp_path / "unexpected-model-run").exists()
