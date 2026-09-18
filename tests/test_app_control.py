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


def test_completed_heartbeat_cleanup_is_confirmed_and_idempotent(project):
    control(project, "claim", "thread-a")
    control(project, "attach", "thread-a", "automation-1")
    project_paths(project)["complete"].write_text("Acceptance tests passed", encoding="utf-8")
    result = control(project, "check", "thread-a")
    assert result["cleanup_action"] == "delete_automation" and not result["may_work"]
    with pytest.raises(RuntimeError):
        control(project, "finish", "thread-a", "automation-1")
    assert control(project, "status", "")["binding"]["automation_id"] == "automation-1"
    for _ in range(2):
        result = control(project, "finish", "thread-a", "automation-1", automation_deleted=True)
        assert result["binding"]["automation_id"] is None
        assert result["binding"]["deleted_automation_id"] == "automation-1"
        assert result["cleanup_action"] is None and not result["may_work"]
    assert project_paths(project)["complete"].exists()
    assert project_paths(project)["master"].exists()
    with pytest.raises(RuntimeError):
        control(project, "attach", "thread-a", "automation-2")


@pytest.mark.parametrize("marker", ["STOP", "BLOCKED", "COMPLETE"])
def test_unfinished_or_empty_evidence_cannot_acknowledge_deletion(project, marker):
    control(project, "claim", "thread-a")
    control(project, "attach", "thread-a", "automation-1")
    (project / ".autopilot" / marker).touch()
    assert control(project, "check", "thread-a")["cleanup_action"] is None
    with pytest.raises(RuntimeError):
        control(project, "finish", "thread-a", "automation-1", automation_deleted=True)


def test_finish_rejects_wrong_owner_and_id(project):
    control(project, "claim", "thread-a")
    control(project, "attach", "thread-a", "automation-1")
    project_paths(project)["complete"].write_text("Tests passed", encoding="utf-8")
    for owner, identifier in [("thread-b", "automation-1"), ("thread-a", "unrelated")]:
        with pytest.raises(RuntimeError):
            control(project, "finish", owner, identifier, automation_deleted=True)
