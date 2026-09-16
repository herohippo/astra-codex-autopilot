# Astra Autopilot

**Codex가 할당량 때문에 멈춰도, 저장한 프로젝트 상태를 읽고 다음 실행에서 이어서 작업하도록 돕는 도구입니다.**

앱 대화에서 시작하거나 터미널에서 직접 실행할 수 있습니다. 목표를 정하고 작업을 맡긴 뒤, 필요할 때 상태를 확인하거나 중지·재개하세요.

> OpenAI가 제공하거나 보증하는 공식 제품이 아닌 독립 오픈소스 도구입니다. 할당량을 늘리거나 제한을 우회하지 않습니다. **앱 모드는 호스트 자동화 기능에 의존**하며, **CLI 모드는 로컬 프로그램이 재시도를 관리**합니다. 완료나 정확한 충전 시각의 재개를 보장하지 않습니다.

## 어떤 모드를 쓰면 되나요?

| | Codex 앱 모드 | CLI 모드 |
|---|---|---|
| 시작 위치 | 현재 프로젝트의 앱 대화 | 터미널 또는 앱에서 CLI 작업 요청 |
| 실제 작업 위치 | 현재 앱 작업 | 별도의 `codex exec` 실행 |
| 다시 실행하는 주체 | 앱의 작업 연결 자동화(heartbeat) | 로컬 Python supervisor |
| 한도 소진 뒤 | 다음 실행 가능한 예약 시점에 체크포인트로 재개 | 오류를 감지하고 기본 30분 간격 재시도 |
| 중지 | 자동화 일시정지, 실행 중에는 앱 Stop | `stop` 또는 `stop --now` |
| 조건 | 로컬 프로젝트와 heartbeat 도구 제공 환경 | Python, Git, ChatGPT 로그인된 Codex CLI |

앱 모드는 현재 대화의 맥락을 사용할 수 있습니다. CLI 모드는 앱 대화 자체를 재개하지 않으므로, 시작 전에 목표와 현재 상태를 프로젝트 파일에 정리합니다. 한 프로젝트에는 한 모드를 사용하세요. 서로 다른 프로젝트도 같은 계정의 사용량을 공유할 수 있습니다.

## 1. 한 번만 설치하기

준비물: Python 3.10 이상, Git, Codex. CLI 모드는 Codex CLI 0.153 이상과 ChatGPT 로그인이 필요합니다. 사용할 모델은 계정에서 사용 가능해야 합니다. 기본값은 `gpt-6-astra`입니다.

### 앱 플러그인만 설치

터미널에서:

```powershell
codex plugin marketplace add herohippo/astra-codex-autopilot
codex plugin add astra-autopilot@astra-autopilot-marketplace
```

**설치 후 새 Codex 작업이나 CLI 세션을 여세요.** 앱에서 바로 보이지 않으면 앱을 다시 시작하세요. 이 플러그인은 실행 스크립트를 포함하므로 플러그인 사용만을 위해 별도 Python 패키지를 설치할 필요는 없습니다.

### CLI 명령어도 설치

```powershell
git clone https://github.com/herohippo/astra-codex-autopilot.git
cd astra-codex-autopilot
python -m pip install --user .
astra-autopilot --help
```

명령어를 찾지 못하면 `python -m astra_supervisor --help`를 사용하세요. macOS/Linux의 시스템 Python에서 설치가 거부되면 가상환경 또는 `pipx install .`을 사용하세요.

Windows에서 CLI 설치와 플러그인 등록을 한 번에 하려면 저장소 폴더에서 `./scripts/install.ps1`을 실행할 수 있습니다. 설치 스크립트는 자동 개발이나 로그인 시 실행을 시작하지 않습니다.

## 2-A. Codex 앱에서 사용하기

원하는 로컬 프로젝트를 열고 다음처럼 요청하세요. 플러그인 선택 메뉴에서 **Astra Autopilot**을 선택하거나 스킬을 명시할 수 있습니다.

```text
$astra-autopilot
앱 모드로 이 프로젝트의 MVP를 완료할 때까지 이어서 작업해줘.
목표: 사용자가 할 일을 추가하고 완료 표시할 수 있는 웹앱.
완료 기준: 추가·완료·삭제 기능, 새로고침 후 저장 유지, 관련 테스트 통과.
현재 대화의 결정사항을 체크포인트에 저장하고 자동 재실행을 설정해줘.
```

이후 같은 작업에서:

```text
자동 작업 상태와 남은 일을 알려줘.
자동 작업을 일시정지해줘.
아까 멈춘 자동 작업을 다시 시작해줘.
다음 작업부터 접근성 문제 수정을 우선해줘.
```

앱 모드는 이 작업에 연결된 자동화를 사용합니다. 해당 도구가 없는 환경에서는 앱 자동 재개를 설정할 수 없습니다. 이때 CLI 모드를 선택할 수 있지만, 앱 대화를 이어가는 것과는 구분됩니다. 앱 모드는 한도 복구 직후를 감지하는 서비스가 아니며, 예약 실패가 누적되면 호스트 자동화 상태를 확인해야 합니다.

## 2-B. CLI에서 사용하기

아래 `C:\my-project`를 **실제 프로젝트 경로**로 바꾸세요. PowerShell에서는 각 명령을 한 줄로 실행합니다.

```powershell
astra-autopilot --project "C:\my-project" init --goal "할 일 앱 MVP를 구현하고 추가·완료·삭제·저장 기능의 테스트를 통과시킨다."
astra-autopilot --project "C:\my-project" doctor
astra-autopilot --project "C:\my-project" once
astra-autopilot --project "C:\my-project" start
```

- `init`: 목표와 작업 기록을 만듭니다. 새 Git 저장소가 필요하면 `--init-git`을 추가합니다.
- `doctor`: 실행 환경과 로그인을 확인합니다. 모델을 호출하지 않습니다.
- `once`: 한 차례 실행해 확인합니다. 한도 오류 후 자동 재시도하지 않습니다.
- `start`: 터미널과 분리된 백그라운드 작업을 시작합니다.
- `run`: 터미널을 열어둔 채 같은 반복 작업을 실행합니다. `start`와 동시에 실행하지 마세요.

```powershell
astra-autopilot --project "C:\my-project" status
astra-autopilot --project "C:\my-project" steer "디자인 수정 전에 데이터 저장 문제를 먼저 해결해줘."
astra-autopilot --project "C:\my-project" stop
astra-autopilot --project "C:\my-project" resume --start
```

`stop`은 현재 차례를 마친 뒤 멈춥니다. **지금 실행을 끊으려면**:

```powershell
astra-autopilot --project "C:\my-project" stop --now
```

즉시 중지해도 이미 편집한 파일은 되돌아가지 않습니다. 재개할 때 현재 파일을 확인합니다. `BLOCKED` 상태라면 원인을 해결한 뒤 `resume --blocked --start`를 사용하세요. 완료 후 새 작업을 추가하려면 목표를 수정하고 `reset-complete --yes`를 실행한 뒤 시작하세요.

앱에서 CLI 모드를 요청하는 것도 가능합니다:

```text
$astra-autopilot 이 프로젝트를 CLI 백그라운드 모드로 이어서 작업해줘.
현재 목표와 진행 상황을 저장하고 시작한 뒤 중지 방법을 알려줘.
```

## 무엇을 저장하나요?

```text
프로젝트/
└─ .autopilot/
   ├─ MASTER_TASK.md   목표·완료 기준
   ├─ STATUS.md        완료한 일·검증·다음 단계
   ├─ TASKS.md         남은 작업
   ├─ config.json     CLI 모델·대기 간격·실행 제한
   ├─ mode.json       앱 작업과 자동화 연결(앱 모드)
   └─ logs/           로컬 실행 로그
```

기존 `AGENTS.md`는 덮어쓰지 않습니다. 새로 생성하는 `.autopilot/.gitignore`는 실행 기록을 기본적으로 Git에서 제외합니다. 목표와 로그에는 프로젝트 정보가 들어갈 수 있으므로 공유 전에 확인하세요. 이미 Git에 추적된 파일은 ignore 규칙만으로 제외되지 않습니다.

```mermaid
flowchart TD
    A[사용자가 목표와 완료 기준 지정] --> B{실행 모드}
    B -->|앱| C[현재 작업의 heartbeat]
    B -->|CLI| D[로컬 supervisor]
    C --> E[체크포인트와 현재 파일 확인]
    D --> E
    E --> F[작업 · 테스트 · 진행 상황 저장]
    F --> G{결과}
    G -->|진행 중| E
    G -->|할당량 부족| H[다음 실행 가능한 시점까지 대기]
    H --> B
    G -->|완료 · 사용자 중지 · 개입 필요| I[실행 중단]
```

## 실행 제한과 안전한 사용

CLI 설정은 `.autopilot/config.json`에 저장됩니다. `max_turns`, `max_runtime_seconds`, `turn_timeout_seconds`로 실행을 제한할 수 있습니다. 값 `0`은 해당 제한 없음이며, 실제 동작과 범위는 [운영 가이드](docs/OPERATIONS.md)를 확인하세요. 로그와 관측된 토큰 수는 계정 잔여 할당량과 다릅니다. 제공되지 않은 수치는 알 수 없음으로 표시합니다.

- ChatGPT 로그인 방식만 지원합니다. 매 실행 전에 확인하고, API 키로 자동 전환하거나 크레딧·리셋을 구매하지 않습니다. **기존 계정의 크레딧 사용 설정까지 통제하지는 않습니다.**
- 기본 sandbox는 `workspace-write`입니다. 승인이나 로그인, 중요한 결정이 필요하면 개입을 기다립니다.
- 컴퓨터가 꺼지거나 잠들면 실행할 수 없습니다. 앱 모드는 앱 스케줄러도 필요합니다. 재부팅 후 자동 시작은 기본 설치에 포함되지 않습니다.
- 완료는 에이전트가 저장된 기준을 검증한 후 표시합니다. 모든 결함이 없다는 보장은 아니므로 중요한 변경은 검토하세요.
- 앱에서 모드를 바꿀 때는 기존 자동화를 일시정지하고 진행 중 작업을 멈춘 뒤 전환하세요.

## 문서와 검증

- [운영·설정·문제 해결](docs/OPERATIONS.md)
- [대화 예시](docs/PROMPT_RECIPES.md)
- [구조와 검증 범위](docs/ARCHITECTURE.md)
- [보안 안내](SECURITY.md) · [변경 이력](CHANGELOG.md)

개발 테스트는 실제 할당량을 소진하지 않는 가짜 Codex 실행기로 진행합니다:

```powershell
python -m pip install -e . pytest
python -m pytest -q
```

공식 인터페이스 참고: [Codex 비대화형 실행](https://developers.openai.com/codex/noninteractive), [플러그인](https://developers.openai.com/codex/plugins).

MIT License. 원본 v0.1.0의 라이선스 고지를 유지합니다.
