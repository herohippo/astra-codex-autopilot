import json
from pathlib import Path

from astra_supervisor.core import (
    classify_error,
    codex_environment,
    init_project,
    parse_jsonl,
    parse_version,
    project_paths,
    run_codex_once,
    validate_codex,
)


def test_parse_version():
    assert parse_version("codex-cli 0.153.1") == (0, 153, 1)


def test_classify_quota():
    samples = [
        "Usage limit reached. Try again after reset.",
        "Weekly limit exceeded",
        "429 too many requests",
        "Five-hour allowance exhausted",
    ]
    assert all(classify_error(x) == "quota" for x in samples)


def test_classify_auth_and_transient():
    assert classify_error("401 unauthorized") == "auth"
    assert classify_error("503 service unavailable") == "transient"


def test_parse_jsonl_completed():
    stream = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "abc"}),
            json.dumps({"type": "turn.started"}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 4,
                        "output_tokens": 3,
                        "reasoning_output_tokens": 2,
                    },
                }
            ),
        ]
    )
    parsed = parse_jsonl(stream)
    assert parsed["completed"] is True
    assert parsed["thread_id"] == "abc"
    assert parsed["usage"]["output_tokens"] == 3


def test_init_project(tmp_path: Path):
    # Make a minimal git repo without relying on git config/user identity.
    import subprocess

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    created = init_project(tmp_path, "Build a test thing")
    paths = project_paths(tmp_path)
    assert paths["master"].exists()
    assert paths["policy"].exists()
    assert "Build a test thing" in paths["master"].read_text(encoding="utf-8")
    assert (tmp_path / "AGENTS.md").exists()
    assert created


def _write_fake_codex(path: Path, mode: str = "success") -> Path:
    script = path / "fake_codex.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args=sys.argv[1:]\n"
        "if args == ['--version']:\n"
        "    print('codex-cli 0.153.1'); raise SystemExit(0)\n"
        "if args[-2:] == ['login', 'status']:\n"
        "    print('Logged in using ChatGPT'); raise SystemExit(0)\n"
        f"mode={mode!r}\n"
        "if mode == 'success':\n"
        "    print(json.dumps({'type':'thread.started','thread_id':'thread-test'}))\n"
        "    print(json.dumps({'type':'turn.completed','usage':{'input_tokens':11,'cached_input_tokens':5,'output_tokens':7,'reasoning_output_tokens':2}}))\n"
        "    raise SystemExit(0)\n"
        "if mode == 'quota':\n"
        "    print(json.dumps({'type':'turn.failed','error':{'message':'Usage limit reached; try again after reset'}}))\n"
        "    print('Usage limit reached; try again after reset', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
        "raise SystemExit(9)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_codex_environment_strips_api_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-leak")
    monkeypatch.setenv("CODEX_API_KEY", "should-not-leak")
    env = codex_environment({"auth_mode": "chatgpt"})
    assert "OPENAI_API_KEY" not in env
    assert "CODEX_API_KEY" not in env


def test_validate_codex_requires_chatgpt_login(tmp_path: Path):
    fake = _write_fake_codex(tmp_path)
    cfg = {
        "codex_executable": str(fake),
        "model": "gpt-6-astra",
        "minimum_astra_codex_version": "0.153.0",
        "auth_mode": "chatgpt",
        "require_chatgpt_login": True,
    }
    assert validate_codex(tmp_path, cfg) == "codex-cli 0.153.1"


def test_run_codex_once_success(tmp_path: Path):
    import subprocess
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    init_project(tmp_path, "Test autonomous work")
    fake = _write_fake_codex(tmp_path, "success")
    cfg = {
        "codex_executable": str(fake),
        "sandbox": "workspace-write",
        "model": "gpt-6-astra",
        "auth_mode": "chatgpt",
        "extra_codex_args": [],
    }
    result = run_codex_once(tmp_path, cfg)
    assert result.kind == "success"
    assert result.thread_id == "thread-test"
    assert result.input_tokens == 11
    assert result.output_tokens == 7


def test_run_codex_once_detects_quota(tmp_path: Path):
    import subprocess
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    init_project(tmp_path, "Test quota retry")
    fake = _write_fake_codex(tmp_path, "quota")
    cfg = {
        "codex_executable": str(fake),
        "sandbox": "workspace-write",
        "model": "gpt-6-astra",
        "auth_mode": "chatgpt",
        "extra_codex_args": [],
    }
    result = run_codex_once(tmp_path, cfg)
    assert result.kind == "quota"
    assert result.returncode == 1


def test_init_force_preserves_existing_agents(tmp_path: Path):
    import subprocess
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Existing project rules\nDo not overwrite me.\n", encoding="utf-8")
    init_project(tmp_path, "New goal", force=True)
    assert agents.read_text(encoding="utf-8") == "# Existing project rules\nDo not overwrite me.\n"
    assert project_paths(tmp_path)["policy"].exists()
