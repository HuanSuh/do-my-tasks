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
  tasks     - 태스크 관리 (list/add/complete/update/delete/rollover)
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
| `/dmt tasks add "Fix bug" --priority high` | `poetry run dmt tasks add "Fix bug" --priority high` |
| `/dmt tasks add "Write tests" --priority medium` | `poetry run dmt tasks add "Write tests" --priority medium` |
| `/dmt tasks list` | `poetry run dmt tasks list` |
| `/dmt tasks list --status pending` | `poetry run dmt tasks list --status pending` |
| `/dmt tasks list --project myapp` | `poetry run dmt tasks list --project myapp` |
| `/dmt tasks complete T-0001` | `poetry run dmt tasks complete T-0001` |
| `/dmt tasks update T-0001 --priority high` | `poetry run dmt tasks update T-0001 --priority high` |
| `/dmt tasks update T-0001 --status in_progress` | `poetry run dmt tasks update T-0001 --status in_progress` |
| `/dmt tasks delete T-0002` | `poetry run dmt tasks delete T-0002` |
| `/dmt tasks rollover` | `poetry run dmt tasks rollover` |
| `/dmt tasks rollover --from-date 2026-03-10 --to-date 2026-03-11` | `poetry run dmt tasks rollover --from-date 2026-03-10 --to-date 2026-03-11` |
| `/dmt config discover` | `poetry run dmt config discover` |
| `/dmt config add myproject /path/to/project` | `poetry run dmt config add myproject /path/to/project` |
| `/dmt config remove myproject` | `poetry run dmt config remove myproject` |
| `/dmt config show` | `poetry run dmt config show` |
| `/dmt config list` | `poetry run dmt config list` |
| `/dmt collect --project myproject` | `poetry run dmt collect --project myproject` |
| `/dmt summary --date 2026-03-10` | `poetry run dmt summary --date 2026-03-10` |
| `/dmt --verbose collect` | `poetry run dmt --verbose collect` |

## 에러 처리

- 명령 실패 시 `--help` 플래그를 붙여 해당 서브커맨드의 도움말을 보여주기
- poetry가 설치되지 않은 경우 설치 안내
