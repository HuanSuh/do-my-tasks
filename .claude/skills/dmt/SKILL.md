---
name: dmt
description: DMT(Do My Tasks) CLI를 실행합니다. 일일 활동 수집, 요약 리포트, 태스크 관리, 오늘의 계획 등을 수행할 때 사용합니다.
argument-hint: "[collect|summary|plan|tasks|config] [options]"
disable-model-invocation: true
allowed-tools: Bash, Read
---

# DMT - Do My Tasks 실행

DMT CLI 명령어를 실행합니다.

## 인자 파싱

사용자 입력: `$ARGUMENTS`

## 실행 규칙

1. 인자가 비어있으면 아래 메뉴를 표시하고 사용자에게 선택을 요청:

```
DMT 명령어:
  collect   - 오늘의 활동 데이터 수집
  summary   - 일일 리포트 생성
  plan      - 오늘의 TODO 계획
  tasks     - 태스크 관리 (list/add/complete/update/delete)
  config    - 프로젝트 설정 (discover/add/remove/show/list)
```

2. 인자가 있으면 `poetry run dmt $ARGUMENTS` 를 Bash로 실행
   - 작업 디렉토리: !`pwd`

3. 실행 결과를 사용자에게 보여주기

## 자주 쓰는 조합 예시

| 호출 | 실행되는 명령 |
|------|-------------|
| `/dmt collect` | `poetry run dmt collect` |
| `/dmt collect --date 2026-03-10` | `poetry run dmt collect --date 2026-03-10` |
| `/dmt summary` | `poetry run dmt summary` |
| `/dmt summary --save` | `poetry run dmt summary --save` |
| `/dmt plan` | `poetry run dmt plan` |
| `/dmt plan --save` | `poetry run dmt plan --save` |
| `/dmt tasks list` | `poetry run dmt tasks list` |
| `/dmt tasks add "Fix bug" --priority high` | `poetry run dmt tasks add "Fix bug" --priority high` |
| `/dmt tasks complete T-0001` | `poetry run dmt tasks complete T-0001` |
| `/dmt config discover` | `poetry run dmt config discover` |
| `/dmt config show` | `poetry run dmt config show` |

## 에러 처리

- 명령 실패 시 `--help` 플래그를 붙여 해당 서브커맨드의 도움말을 보여주기
- poetry가 설치되지 않은 경우 설치 안내
