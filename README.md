# Orchestra for Codex

**작업마다 필요한 에이전트 팀을 구성하고, 하위 작업의 모델과 추론 강도를 자동으로 선택하는 Codex 스킬입니다.**

Orchestra is a task-scoped Codex skill for native agent delegation, model and reasoning selection, review, and honest result reporting. It targets Codex in Ubuntu WSL and uses Python's standard library for local checks and records.

```text
$orchestra 5 이 프로젝트의 오류를 조사하고 수정한 뒤 결과를 검토해줘.
```

사용자가 선택한 총괄 모델과 추론 강도를 유지합니다. 총괄이 각 하위 작업의 성격을 판단해 적절한 모델과 추론 강도를 선택하고, 결과를 검토·통합합니다. 별도 상주 서비스나 모델 API 키, OMC·OMX는 필요하지 않습니다.

## 핵심 동작

- **5~20명 상한 설정**: 숫자는 총괄을 제외한 최대 동시 하위 에이전트 수입니다. 생략하면 5이며, 자문역·검토자도 포함합니다. 필요한 인원만 사용합니다.
- **작업별 자동 배정**: 명확성, 복잡성, 오류의 영향, 검증 가능성, 도구·자료 준비 상태를 함께 판단합니다.
- **총괄의 추론 강도가 상한**: 총괄보다 강한 모델을 자문역으로 선택할 수 있지만, 하위 작업의 추론 강도는 총괄의 설정을 넘지 않습니다.
- **검토와 기록**: 의존성·쓰기 범위·재시도를 관리하고 요청한 설정과 실제 관측값을 구분합니다.
- **명시적 호출**: `$orchestra`로 요청했을 때 사용합니다. 간단한 작업에는 불필요한 팀을 만들지 않습니다.

| 하위 작업 예시 | 기본 선택 기준 |
|---|---|
| 단순 추출, 파일 목록, 명확한 작은 수정 | 사용 가능한 Luna / Low 또는 Medium |
| 일반 구현, 여러 단계의 분석 | 사용 가능한 Sol / Medium 또는 High |
| 중요한 설계 판단, 어려운 결과 검토 | 사용 가능한 Astra / High, 총괄의 강도 상한 안에서 |

예를 들어 총괄이 Sol / High라면 Luna / Low 작업자, Sol / Medium 구현자, Astra / High 자문역을 조합할 수 있습니다. 총괄이 Astra / Low라면 모든 하위 작업도 Low 범위에서 배정합니다.

모델 이름은 이 스킬의 후보 정책입니다. 모든 계정·Codex 환경에서 해당 모델을 제공한다는 뜻은 아닙니다. **현재 모델 목록과 실제 에이전트 생성 도구가 모두 허용하는 조합만 사용합니다.** 자세한 기준은 [모델 선택 정책](orchestra/references/routing.md)에 있습니다.

## 설치

대상 환경은 **Ubuntu WSL**, **Python 3.11 이상**, 하위 에이전트별 모델·추론 강도 지정이 가능한 **Codex**입니다. 최초 검증 환경은 Codex CLI 0.157.1 / Python 3.12.3입니다. 다른 버전과 도구 환경에서는 [호환성 안내](orchestra/references/native-compatibility.md)를 먼저 확인하세요.

WSL 터미널에서 실행합니다.

```bash
git clone https://github.com/sel00000/codex-orchestra.git
cd codex-orchestra
python3 tools/install_orchestra.py
```

설치 위치는 `~/.agents/skills/orchestra/`입니다. 같은 이름의 스킬이 있으면 이웃 백업 폴더에 보존한 뒤 설치합니다. 기존 Codex 설정이나 다른 스킬은 수정하지 않습니다. 열린 세션에 새 스킬이 표시되지 않으면 새 Codex 세션에서 호출하세요.

ZIP만 만들려면 다음을 실행합니다.

```bash
python3 tools/install_orchestra.py --zip dist/orchestra.zip
```

ZIP에는 스킬의 10개 파일만 포함합니다. 테스트, 로컬 실행 DB, 캐시는 포함하지 않습니다.

## 사용 예시

```text
$orchestra 이 코드의 오류 원인을 찾고 수정 결과를 확인해줘.
$orchestra 8 이 CAD 자료의 파일 관계와 검토가 필요한 부분을 정리해줘.
$orchestra 10 이 연구 자료들의 근거를 대조하고 실험 계획 초안을 만들어줘.
```

현재 세션의 실제 에이전트 한도가 요청보다 작으면 필요한 실행 조건을 안내합니다. 스킬의 숫자 설정만으로 Codex 자체의 한도가 늘어나지는 않습니다. 새 세션을 준비하는 방법은 [사용 안내](docs/usage.ko.md)를 참고하세요.

## 검증과 현재 한계

로컬 정책·상태·명령·패키징 테스트 **58개**를 통과했습니다. 설치된 스킬에서 네이티브 하위 작업 두 건을 생성하고 코드 수정과 자료 검토 결과를 확인했습니다.

- **실제 5명·20명 동시 실행은 아직 검증하지 않았습니다.** 로컬 기록의 5/20 예약 경계 시험과 구분합니다.
- 생성 도구가 최종 유효 모델·추론 강도를 노출하지 않으면 실제값을 `unverified`로 남깁니다.
- 이 스킬은 운영 규칙과 로컬 검사로 관리합니다. Codex 런타임 전체의 강제 차단이나 악의적인 호출자 인증을 제공하지 않습니다.
- 종료를 확인할 수 없는 도구 환경에서는 산출물이 완성되어도 `CLEANUP_REQUIRED`를 보고합니다.
- CAD 파일 목록 정리는 실제 CAD 편집·물리 검증이 아니며, 자료 요약은 논문 원문 검증이나 실험 결과와 구분합니다.

재현 가능한 로컬 시험과 실제 모델 시험의 범위는 [검증 기록](docs/validation.md)에 정리했습니다.

## 개발·테스트

추가 Python 패키지 설치 없이 WSL/Linux에서 실행합니다. 이 시험은 실제 모델을 호출하지 않습니다.

```bash
python3 -m unittest discover -s tests -v
```

| 경로 | 내용 |
|---|---|
| [orchestra/SKILL.md](orchestra/SKILL.md) | Codex가 읽는 스킬 진입점 |
| `orchestra/references/` | 모델 선택, 작업 절차, 호환성, 보조 명령 |
| `orchestra/scripts/` | 정책 검사, 원자적 예약, 상태 기록, 보고 |
| `tools/install_orchestra.py` | 백업 설치 및 ZIP 생성 |
| `tests/` | 모델 호출 없는 회귀 시험 |
| `docs/` | 한국어 사용 안내와 검증 범위 |

작업 기록은 사용하는 프로젝트의 `.orchestra/<run-id>/`에 보존됩니다. 이 저장소에는 개인 실행 기록을 포함하지 않습니다.
