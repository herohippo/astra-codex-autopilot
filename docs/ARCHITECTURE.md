# 구조와 검증 범위

## 경계

`plugins/astra-autopilot`은 manifest, skill, Python runtime을 포함하는 이동 가능한 플러그인입니다. 같은 Python 코드를 설치하면 `astra-autopilot`과 `astra-autopilot-app` 명령이 생깁니다. 런타임의 외부 Python 패키지 의존성은 없습니다. pytest는 개발 테스트용입니다.

네이티브 앱 adapter는 스킬 + `app_control.py` + 호스트 heartbeat입니다. 앱 내부 예약은 Python이 직접 제어하지 않고 호스트에 제공된 도구로 생성·갱신합니다. CLI adapter는 `core.py`가 실행하는 독립 프로세스입니다. 두 모드는 `.autopilot` 체크포인트를 공유하되, app 소유권이 있으면 CLI 실행을 거부합니다.

CLI supervisor는 프로세스가 살아 있는 동안 OS lock을 유지합니다. 앱 소유권은 task ID를 저장하는 협력 규칙입니다. 앱의 임의 편집이나 수동 shell 명령까지 강제로 차단하는 보안 경계가 아닙니다. 모드 전환 전 현재 작업과 자동화를 멈춰야 합니다.

## 재개와 완료

각 CLI 차례는 새 `codex exec --json` 실행입니다. 이전 세션 ID를 무조건 resume하는 대신, 목표·진행 상황·현재 파일을 읽습니다. 중간에 강제 종료된 차례의 변경은 파일에 남을 수 있으므로 다음 차례가 실제 상태를 확인합니다. 한도 판정은 실제 오류 이벤트/표준 오류에 근거하며 일반 도구 출력의 문구로 판정하지 않습니다. 오류 문구 변경으로 미분류 오류가 될 수 있습니다.

완료 마커는 에이전트가 명시된 기준과 검증 결과를 확인한 뒤 작성합니다. supervisor 자체는 임의 프로젝트의 정답을 판정하지 않습니다. 중요한 목표는 명확한 테스트와 사람의 검토를 함께 사용하세요.

## 검증 원칙

가짜 Codex 프로세스로 한도 오류 → 대기 → 성공, 중지/재개, 중복 실행, 새 지시 보존, 인증 변경, 프로세스 트리 종료를 검증합니다. 테스트에서는 실제 모델이나 외부 과금 API를 호출하지 않습니다. CI는 Windows와 Linux에서 실행하도록 구성합니다.

앱 helper의 소유권/중지/연결 검증과 실제 앱 스케줄러의 장시간 동작 검증은 별개입니다. 실제 한도 소진부터 복구까지는 계정·시간·호스트 조건에 의존하므로 모의 테스트 통과만으로 실사용 복구를 확인했다고 주장하지 않습니다. 각 릴리스의 실제 검증 결과는 CHANGELOG와 검증 보고서를 확인하세요.

공식 지원 인터페이스 확인: [비대화형 실행](https://developers.openai.com/codex/noninteractive), [플러그인](https://developers.openai.com/codex/plugins), [forced_login_method 설정](https://developers.openai.com/codex/config-reference).
