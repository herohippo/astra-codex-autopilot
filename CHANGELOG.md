# Changelog

## 0.4.0 문서·실동작 확인 (2026-09-18)

- 현재 Codex 앱에서 PAUSED 임시 예약의 생성·직접 삭제를 실행하고 삭제 성공 응답 확인.
- 완료 후 수동 삭제가 필요 없으며 Codex가 삭제와 결과 기록을 처리한다는 설명을 명확화.
- 실제 호스트 검증과 자동 테스트, 미검증 범위를 구분. 기존 개발 예약과 런타임 코드는 변경하지 않음.

## 0.4.0

- 앱 모드 완료 후 예약을 일시정지하는 대신 해당 예약만 삭제하도록 변경.
- 완료 근거/소유자/예약 ID 확인과 삭제 확인 후 finish 기록, 재시도 안전성 추가.
- 삭제 실패 시 ID 보존 및 일시정지, STOP/BLOCKED와 할당량 대기는 기존 정책 유지.
- README, 운영/구조/대화 예시, 두 스킬 사본과 저장 프롬프트 지침 일치.

## 0.3.0

- 한도 오류 후 고정 간격 모델 재시도를 공식 App Server 초기화 시각 기반 대기로 변경.
- 소진된 창 중 가장 늦은 초기화 시각 + 기본 60초 여유, 재개 직전 재확인, 재시작 후 대기 복원.
- 초기화 시각 불명·조회 실패 시 모델 작업을 보류하고 정보만 재조회.
- 앱 helper도 할당량 확인을 수행하고 `next_check_at`을 반환. 앱 예약 호출 조정은 호스트 지원에 의존.
- 조회 시간/출력 제한, 중지 처리, 비정상 응답 및 실행 시간 제한 회귀 테스트 추가.

## 0.2.0

- Separate native Codex app heartbeat workflow from standalone CLI execution.
- Native app ownership, saved automation binding, pause and mode handoff helpers.
- Detached CLI start with readiness check; graceful and immediate process-tree stop.
- OS-held project lock; crash recovery without force-stealing live work.
- Durable retry times and per-turn ChatGPT login checks; restrict unsafe config overrides.
- Immutable steering queue prevents losing instructions added during a turn.
- Bounded output tails/log retention and optional runtime/turn limits.
- Private runtime ignore rules; nullable usage when Codex does not report it.
- Korean quickstart with app and CLI examples; Windows/Linux test workflow.
- Removed unverified v0.1 login-autostart scripts; install does not modify OS scheduling.

Validation uses fake Codex subprocesses without consuming actual model allowance. App coordination tests do not establish a real quota-exhaustion/reset recovery cycle. See the release verification report for executed checks.

## 0.1.0

Original reference implementation: CLI checkpoint loop, quota retry, plugin scaffold.
