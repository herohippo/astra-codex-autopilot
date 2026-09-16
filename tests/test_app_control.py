import subprocess

import pytest

from astra_supervisor.app_control import control
from astra_supervisor.core import SupervisorLock, init_project, project_paths


@pytest.fixture
def project(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    init_project(tmp_path, "Native app project")
    return tmp_path


def test_app_lifecycle(project):
    claimed = control(project, "claim", "thread-a")
    assert claimed["may_work"] and not claimed["running"]
    control(project, "attach", "thread-a", "automation-1")
    assert control(project, "status", "")["binding"]["automation_id"] == "automation-1"
    assert not control(project, "pause", "thread-a")["may_work"]
    with pytest.raises(RuntimeError):
        control(project, "release", "thread-a")
    assert control(project, "release", "thread-a", automation_paused=True)["binding"]["mode"] == "cli"


def test_wrong_owner_rejected(project):
    control(project, "claim", "thread-a")
    for action in ("claim", "check", "pause", "release"):
        with pytest.raises(RuntimeError):
            control(project, action, "thread-b", automation_paused=True)


def test_cli_lock_blocks_claim(project):
    with SupervisorLock(project_paths(project)["lock"]):
        with pytest.raises(RuntimeError):
            control(project, "claim", "thread-a")


def test_complete_prevents_app_work(project):
    control(project, "claim", "thread-a")
    project_paths(project)["complete"].write_text("Validated", encoding="utf-8")
    assert not control(project, "check", "thread-a")["may_work"]


def test_cannot_replace_attached_heartbeat(project):
    control(project, "claim", "thread-a")
    control(project, "attach", "thread-a", "automation-1")
    control(project, "attach", "thread-a", "automation-1")
    with pytest.raises(RuntimeError):
        control(project, "attach", "thread-a", "automation-2")
