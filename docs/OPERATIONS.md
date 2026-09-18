# 운영과 문제 해결

## 모드 선택

앱 모드는 현재 작업에 붙는 heartbeat를 이용합니다. 설치된 스킬은 호스트의 자동화 도구를 찾아 설정하고 반환된 ID를 기록합니다. Python 앱 helper 자체는 스케줄러가 아닙니다. 앱 자동화 도구가 없으면 CLI 모드만 사용할 수 있습니다.

CLI 모드는 OS 프로세스로 실행되며 앱을 닫더라도 호스트 환경이 프로세스를 유지하고 컴퓨터가 깨어 있으면 동작할 수 있습니다. 모든 터미널·보안 환경에서 분리 실행이 보장되는 것은 아니므로 `start` 후 `status`를 확인하세요. 로그아웃/재부팅 후 자동 복구는 기본 제공 동작이 아닙니다.

## CLI 설정

작업을 중지한 뒤 `.autopilot/config.json`을 수정하고 다시 시작하세요.

| 설정 | 기본값 | 의미 |
|---|---:|---|
| model | gpt-6-astra | 계정에서 사용 가능한 모델 ID |
| sandbox | workspace-write | read-only도 가능. 권한 우회 모드는 거부 |
| quota_retry_seconds | 1800 | 초기화 시각 불명·조회 실패·오류와 조회 결과 불일치 시 정보만 재조회하는 간격(1~604800초) |
| quota_reset_margin_seconds | 60 | 공식 초기화 시각 이후 여유 시간(0~86400초) |
| quota_limit_id | codex | 조회할 할당량 버킷 ID. 모델명으로 추정하지 않으며 해당 버킷이 없으면 작업 보류 |
| transient_retry_seconds | 180 | 일시적인 연결/서버 오류 후 대기 |
| unknown_retry_seconds | 900 | 분류하지 못한 오류 후 대기 |
| success_pause_seconds | 30 | 성공한 차례 다음 실행까지 대기 |
| max_turns | 0 | 이번 supervisor 실행의 시도 횟수 상한; 0은 무제한 |
| max_runtime_seconds | 0 | 이번 실행의 시간 상한; 대기 포함, 정리 시간은 추가될 수 있음 |
| turn_timeout_seconds | 0 | 한 차례 Codex 실행의 시간 상한 |
| max_consecutive_unknown_errors | 8 | 연속 미분류 오류 상한 |
| max_consecutive_transient_errors | 8 | 연속 일시 오류 상한 |
| max_log_files | 20 | 실행 로그 보존 개수 |
| log_tail_bytes | 262144 | 각 출력 스트림에서 보존하는 마지막 바이트 수 |

시간·횟수 상한에 도달하면 멈춥니다. 재시작하면 해당 실행의 상한 계산도 다시 시작합니다. 재시도 예정 시각은 디스크에 남아 있으므로 프로세스를 다시 시작해도 남은 대기를 지킵니다. `once`도 저장된 대기 시각을 따를 수 있습니다. timeout은 즉시 무한 재시도하지 않고 확인이 필요한 상태로 처리합니다.

`auth_mode`는 `chatgpt`, `require_chatgpt_login`은 `true`, `extra_codex_args`는 빈 배열만 허용합니다. CLI 실행 파일을 지정하려면 `codex_executable`에 신뢰하는 실행 파일의 절대 경로를 넣으세요. 프로젝트 설정은 실행 권한을 가진 코드처럼 검토해야 합니다.

## 상태와 중지

`status`의 `running`은 CLI supervisor lock 점유 상태입니다. 앱 모드의 진행 상태는 앱 작업과 저장된 자동화 ID에서도 확인하세요. `next_retry_at`은 다음 확인 예정 시각입니다. `quota_reset_at`은 마지막 공식 응답의 소진된 창 중 가장 늦은 초기화 시각에 여유 시간을 더한 값입니다. `quota_check_at`은 조회 시각, `quota_wait_reason`은 `reset_time`, `metadata_unavailable`, `available`입니다. 이 값은 실시간 잔여 할당량 보장이 아닙니다.

할당량 오류 이후에는 사용 가능 상태가 확인될 때까지 `codex exec`를 실행하지 않습니다. 초기화 시각이 과거인데 계속 소진 상태이거나 응답이 불명확하면 정보만 재조회합니다. 조회는 20초 제한과 프로세스 정리를 적용하며 대기 중 STOP도 처리합니다. 앱 helper `check`도 이 확인을 수행합니다. 조회를 지원하지 않는 구형 CLI/인증 환경에서는 자동 작업이 보류되므로 Codex 업데이트와 로그인을 확인하세요.

업그레이드 전에 실행 중인 CLI worker를 중지하세요. v0.2.0의 `quota_retry_seconds`는 그대로 읽지만 이제 개발 작업 재시도 간격이 아니라 정보 재조회 간격입니다. 기존 앱 heartbeat의 저장된 프롬프트도 새 스킬 지침으로 업데이트해야 합니다. 플러그인 파일 업데이트만으로 이미 저장된 자동화 프롬프트는 바뀌지 않습니다.

- 정상 중지: `stop` → 현재 차례 종료 → `status`에서 running=false 확인.
- 즉시 중지: `stop --now` → 관리 중인 Codex 프로세스 트리 종료. 이미 저장한 파일은 남습니다.
- 다시 시작: `resume --start`.
- 로그인/결정 필요: BLOCKED 내용 확인 → 원인 해결 → `resume --blocked --start`.
- 완료 이후 추가 작업: 목표/기준 수정 → `reset-complete --yes` → `start`.

앱에서는 먼저 예약 자동화를 일시정지하고, 현재 실행 중인 차례는 앱의 Stop으로 중지하세요. `STOP` 파일만으로 이미 실행 중인 모든 앱 도구를 강제로 종료할 수는 없습니다. 다른 모드로 넘길 때는 진행 중인 편집이 끝났는지 확인합니다.

## 자주 생기는 문제

**명령어 없음:** 같은 Python으로 `python -m astra_supervisor --help` 실행. 플러그인은 자체 wrapper가 있어 패키지 명령어 PATH에 의존하지 않습니다.

**Codex 로그인 확인 실패:** `codex login`으로 ChatGPT 로그인을 완료한 뒤 `doctor`. 계정/모델 접근 권한은 이 도구가 제공하지 않습니다.

**플러그인이 안 보임:** 설치 결과 확인 후 새 작업/CLI 세션을 시작. 필요하면 앱 재시작. GitHub marketplace를 설치하는 것은 공식 공개 디렉터리 심사 통과와 다릅니다.

**앱 작업이 깨어나지 않음:** 실제 heartbeat가 생성됐는지, 활성 상태인지, 앱/컴퓨터가 실행 가능한 상태인지 확인. 한도/호스트 정책에 따라 실행이 실패하거나 늦어질 수 있습니다. 필요하면 앱 자동화를 멈추고 CLI 모드로 전환합니다.

**중복 실행 오류:** 기존 supervisor를 멈춘 뒤 재시도. OS lock은 프로세스 종료 때 풀립니다. lock 파일을 삭제하거나 force-lock으로 살아 있는 작업을 덮어쓰지 마세요.

**토큰 값이 null:** Codex가 해당 값을 제공하지 않았다는 뜻입니다. 수치는 제공된 실행만의 관측값이며 전체 과금/계정 잔여량이 아닙니다. CLI 프로브도 서비스 요청이며 할당량 밖의 무료 실행을 보장하지 않습니다.

## 업데이트와 제거

작업을 먼저 중지합니다. Git clone 설치는 `git pull --ff-only` 후 같은 Python으로 `python -m pip install --user .`를 실행합니다. marketplace 업데이트는 설치된 Codex의 `plugin marketplace --help`에 맞춰 수행하고 플러그인을 다시 설치한 뒤 새 세션을 여세요.

플러그인 제거: `codex plugin remove astra-autopilot@astra-autopilot-marketplace` (현재 CLI 도움말로 selector 확인). Python CLI 제거: `python -m pip uninstall astra-codex-autopilot`. **제거 전에 앱 heartbeat와 CLI worker를 중지하세요.** 플러그인 제거가 별도로 만든 자동화까지 제거하지는 않습니다. 프로젝트 결과물은 그대로 남습니다.

## 완료 후 예약 자동 삭제 (v0.4.0)

정상 완료 시 사용자가 별도로 예약을 삭제하거나 `finish` 명령을 실행할 필요는 없습니다. Codex가 아래 두 단계를 자동 수행합니다. 이미 허용된 완료 정리에 대해 추가 승인을 반복 요청하지 않습니다.

1. 완료 근거와 연결된 예약의 소유권을 확인하고, 호스트 `automation_update`의 지원되는 삭제 동작으로 정확한 ID만 삭제합니다. 현재 호스트에서는 `mode: delete`로 실제 삭제 성공을 확인했습니다.
2. 삭제 성공 응답을 확인한 뒤 helper `finish`로 완료 정리 기록을 남깁니다. 이 helper만 실행하는 것은 실제 예약 삭제가 아닙니다.

- 모든 완료 기준과 관련 검증을 충족하면 근거와 COMPLETE를 저장하고, 이 프로젝트에 연결된 예약만 호스트 도구로 삭제합니다.
- 실제 삭제 성공을 확인한 뒤 앱 helper `finish --automation-id ID --automation-deleted`로 연결 ID를 정리합니다. 소스·체크포인트·로그·완료 근거는 보존합니다. 이 명령 자체가 호스트 예약을 삭제하지는 않습니다.
- 삭제에 실패하거나 호스트가 삭제 기능을 제공하지 않으면 ID를 보존하고 예약을 일시정지할 수 있는 경우 정지한 뒤 사용자에게 미완료 정리를 알립니다. 삭제했다고 보고하지 않습니다.
- 사용자 중지(STOP), 진행 불가(BLOCKED)는 예약을 일시정지하고 보존합니다. 할당량 대기는 기존 초기화 시각 기반 정책을 유지합니다.
- CLI는 완료 시 프로세스가 종료되며 별도 앱 예약을 생성하지 않습니다. 다른 프로젝트의 예약은 삭제하지 않습니다.
- 완료 후 추가 개발은 새 요청으로 목표를 수정하고 완료 상태를 명시적으로 해제한 후 새 예약을 연결합니다. 단순 재개로 완료된 작업의 예약을 다시 만들지 않습니다.

업데이트 후 기존 예약에도 이 정책과 새 helper 경로를 적용해야 합니다. 플러그인 설치만으로 저장된 예약 프롬프트가 바뀌지는 않습니다.
