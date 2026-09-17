import json
import time
from datetime import datetime, timezone

import pytest

from astra_supervisor.quota import quota_decision, read_limits
from astra_supervisor.core import (DEFAULT_CONFIG, RunResult, SupervisorState,
    init_project, load_state, run_loop, save_state, project_paths)
from astra_supervisor.app_control import control


def payload(primary=100, reset=2000, secondary=None):
    return {"rateLimits": {"primary": {"usedPercent": primary, "resetsAt": reset}, "secondary": secondary}}


def test_latest_exhausted_reset():
    assert quota_decision(payload(100, 2000, {"usedPercent": 100, "resetsAt": 4000}), 1000) == ("wait", 4060)
    assert quota_decision(payload(100, 2000, {"usedPercent": 1, "resetsAt": 4000}), 1000) == ("wait", 2060)


@pytest.mark.parametrize("value", [None, {}, {"rateLimits": None}, payload(100, None),
    payload(100, 100), payload(True), payload(float('nan')), payload(100, float('inf')),
    payload(10**400), payload(100, 10**400),
    {"rateLimits": {"primary": {"usedPercent": 5}, "secondary": {}}},
    {"rateLimits": {"primary": {"usedPercent": 5}, "rateLimitReachedType": "other"}}])
def test_unknown_is_not_permission_to_execute(value):
    assert quota_decision(value, 1000) == ("unknown", None)


def test_named_bucket_is_authoritative():
    value = payload(0)
    value['rateLimitsByLimitId'] = {'codex': payload()['rateLimits'], 'other': payload(100, 9000)['rateLimits']}
    assert quota_decision(value, 1000) == ('wait', 2060)
    assert quota_decision(value, 1000, 'absent') == ('unknown', None)
    assert quota_decision(value, 1000, 'other') == ('wait', 9060)


def fake_server(tmp_path, hang=False):
    server = tmp_path / 'server.py'
    server.write_text('''import sys,json,time
for line in sys.stdin:
 m=json.loads(line)
 if m['method']=='initialize':
  print(json.dumps({'id':1,'result':{}}),flush=True)
 elif m['method']=='initialized':
  pass
 elif m['method']=='account/rateLimits/read':
''' + ("  time.sleep(60)\n" if hang else "  print(json.dumps({'id':2,'result':{'rateLimits':{'primary':{'usedPercent':3}}}}),flush=True)\n"), encoding='utf-8')
    return {**DEFAULT_CONFIG, 'codex_executable': str(server)}


def test_documented_rpc_without_model_turn(tmp_path):
    assert read_limits(tmp_path, fake_server(tmp_path))['rateLimits']['primary']['usedPercent'] == 3


def test_rpc_timeout_is_bounded(tmp_path):
    began = time.monotonic()
    with pytest.raises(RuntimeError, match='timed out'):
        read_limits(tmp_path, fake_server(tmp_path, hang=True), timeout=.3)
    assert time.monotonic() - began < 5


def test_rpc_stop_cancels_wait(tmp_path):
    (tmp_path / '.autopilot').mkdir()
    (tmp_path / '.autopilot/STOP').touch()
    with pytest.raises(RuntimeError, match='cancelled'):
        read_limits(tmp_path, fake_server(tmp_path, hang=True))


def test_quota_config_bounds():
    from astra_supervisor.core import validate_config
    for key, value in [('quota_retry_seconds', 0), ('quota_reset_margin_seconds', 10**400)]:
        with pytest.raises(ValueError):
            validate_config({key: value})


def test_runtime_expiring_during_metadata_does_not_launch(tmp_path, monkeypatch):
    init_project(tmp_path, 'test', init_git=True)
    project_paths(tmp_path)['config'].write_text(json.dumps({'max_runtime_seconds': 10}), encoding='utf-8')
    save_state(tmp_path, SupervisorState(last_result='quota'))
    monkeypatch.setattr('astra_supervisor.core.validate_codex', lambda *a: None)
    clock = [0]
    monkeypatch.setattr('astra_supervisor.core.time.monotonic', lambda: clock[0])
    def read(*args):
        clock[0] = 11
        return payload(0)
    monkeypatch.setattr('astra_supervisor.quota.read_limits', read)
    monkeypatch.setattr('astra_supervisor.core.run_codex_once', lambda *a: pytest.fail('expired'))
    assert run_loop(tmp_path) == 0
    assert project_paths(tmp_path)['stop'].exists()


def test_quota_schedule_persisted_and_not_fixed_interval(tmp_path, monkeypatch):
    init_project(tmp_path, 'test', init_git=True)
    monkeypatch.setattr('astra_supervisor.core.validate_codex', lambda *a: None)
    monkeypatch.setattr('astra_supervisor.core.run_codex_once', lambda *a: RunResult('quota', 1))
    reset = int(time.time()) + 7200
    monkeypatch.setattr('astra_supervisor.quota.read_limits', lambda *a: payload(100, reset))
    assert run_loop(tmp_path, once=True) == 3
    state = load_state(tmp_path)
    assert datetime.fromisoformat(state.next_retry_at).timestamp() == reset + 60
    assert state.quota_wait_reason == 'reset_time'


def test_unknown_metadata_does_not_call_model_after_restart(tmp_path, monkeypatch):
    init_project(tmp_path, 'test', init_git=True)
    save_state(tmp_path, SupervisorState(last_result='quota'))
    monkeypatch.setattr('astra_supervisor.core.validate_codex', lambda *a: None)
    monkeypatch.setattr('astra_supervisor.quota.read_limits', lambda *a: {})
    monkeypatch.setattr('astra_supervisor.core.run_codex_once', lambda *a: pytest.fail('must not execute model'))
    assert run_loop(tmp_path, once=True) == 3
    assert load_state(tmp_path).quota_wait_reason == 'metadata_unavailable'


def test_app_wait_and_recovery(tmp_path, monkeypatch):
    init_project(tmp_path, 'test', init_git=True)
    control(tmp_path, 'claim', 'owner')
    monkeypatch.setattr('astra_supervisor.quota.read_limits', lambda *a: payload(100, time.time() + 7200))
    result = control(tmp_path, 'check', 'owner')
    assert not result['may_work'] and result['next_check_at']
    monkeypatch.setattr('astra_supervisor.quota.read_limits', lambda *a: pytest.fail('no polling before reset'))
    assert not control(tmp_path, 'check', 'owner')['may_work']
    state = load_state(tmp_path)
    state.next_retry_at = datetime.fromtimestamp(1, timezone.utc).isoformat()
    save_state(tmp_path, state)
    monkeypatch.setattr('astra_supervisor.quota.read_limits', lambda *a: payload(10))
    assert control(tmp_path, 'check', 'owner')['may_work']


def test_app_metadata_failure_and_stop(tmp_path, monkeypatch):
    init_project(tmp_path, 'test', init_git=True)
    control(tmp_path, 'claim', 'owner')
    monkeypatch.setattr('astra_supervisor.quota.read_limits', lambda *a: {})
    assert not control(tmp_path, 'check', 'owner')['may_work']
    project_paths(tmp_path)['stop'].touch()
    monkeypatch.setattr('astra_supervisor.quota.read_limits', lambda *a: pytest.fail('stopped'))
    assert not control(tmp_path, 'check', 'owner')['may_work']
