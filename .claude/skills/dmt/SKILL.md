---
name: dmt
description: DMT(Do My Tasks) CLI를 실행합니다. 일일 활동 수집, 요약 리포트, 태스크 관리, 오늘의 계획 등을 수행할 때 사용합니다.
argument-hint: "[collect|summary|plan|tasks|sessions|config] [options]"
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
  sessions  - 라이브 세션 조회 (live/watch/clean/--wide/--detail)
  config    - 프로젝트 설정 (discover/add/remove/show/list)
```

2. **요약/분석 요청** (summary, plan, sessions 요약, tasks list 등 데이터를 해석해야 하는 경우):
   - `poetry run dmt --json <command>` 로 실행하여 JSON 출력을 받는다
   - JSON을 파싱하여 사용자에게 읽기 쉬운 형태로 요약/분석하여 전달
   - 원시 JSON을 그대로 보여주지 말고, 핵심 정보를 추출하여 정리

3. **실행/액션 요청** (collect, tasks add/complete/update/delete, config add/remove 등):
   - `poetry run dmt $ARGUMENTS` 를 Bash로 실행
   - 실행 결과를 사용자에게 보여주기

4. 작업 디렉토리: !`pwd`

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
| `/dmt sessions` | `poetry run dmt sessions` |
| `/dmt sessions live` | `poetry run dmt sessions live` |
| `/dmt sessions --wide` | `poetry run dmt sessions --wide` |
| `/dmt sessions --detail` | `poetry run dmt sessions --detail` |
| `/dmt sessions -d` | `poetry run dmt sessions -d` |
| `/dmt sessions watch` | `poetry run dmt sessions watch` |
| `/dmt sessions watch --idle 15 --no-notify` | `poetry run dmt sessions watch --idle 15 --no-notify` |
| `/dmt sessions clean` | `poetry run dmt sessions clean` |
| `/dmt sessions clean --idle 30 --dry-run` | `poetry run dmt sessions clean --idle 30 --dry-run` |
| `/dmt sessions clean --force` | `poetry run dmt sessions clean --force` |
| `/dmt sessions clean 12345` | `poetry run dmt sessions clean 12345` |
| `/dmt sessions clean 12345 67890` | `poetry run dmt sessions clean 12345 67890` |
| `/dmt config discover` | `poetry run dmt config discover` |
| `/dmt config add myproject /path/to/project` | `poetry run dmt config add myproject /path/to/project` |
| `/dmt config remove myproject` | `poetry run dmt config remove myproject` |
| `/dmt config show` | `poetry run dmt config show` |
| `/dmt config list` | `poetry run dmt config list` |
| `/dmt collect --project myproject` | `poetry run dmt collect --project myproject` |
| `/dmt summary --date 2026-03-10` | `poetry run dmt summary --date 2026-03-10` |
| `/dmt --verbose collect` | `poetry run dmt --verbose collect` |

## 요약/분석 처리 가이드

### 일일 요약 (`summary`)
1. `poetry run dmt --json summary --no-save` 실행
2. JSON에서 projects 배열과 statistics를 파싱
3. 프로젝트별 커밋 수, 세션 수, 코드 변경량을 정리하여 전달
4. 전체 통계 (총 커밋, 파일 변경, 라인 추가/삭제) 요약

### 계획 조회 (`plan`)
1. `poetry run dmt --json plan` 실행
2. rolled_over, high_priority, follow_ups를 파싱
3. 우선순위별로 정리하여 오늘 해야 할 일 목록 전달

### 라이브 세션 요약 (`sessions`)
1. `poetry run dmt --json sessions --detail` 실행
2. sessions 배열에서 각 세션의 project, last_message, tools, time_ago 파싱
3. 세션별 작업 내용 요약:
   - 세션별 마지막 작업 내용, 사용 도구, 경과 시간
   - 작업 우선순위/중요도 판단 (활성도, 최근 업데이트 기준)
   - 현재 진행 중인 작업 vs 유휴 세션 구분

### 태스크 목록 (`tasks list`)
1. `poetry run dmt --json tasks list` 실행
2. tasks 배열에서 status, priority, project별로 그룹핑
3. 우선순위 높은 순으로 정리하여 전달

### 설정 조회 (`config show/list`)
1. `poetry run dmt --json config show` 또는 `--json config list` 실행
2. 프로젝트 목록, 경로, 상태를 파싱하여 전달

## JSON 출력 모드

`--json` 글로벌 옵션으로 모든 명령어 출력을 JSON으로 받을 수 있습니다.
(sessions watch, config discover 제외)

```
dmt --json collect
dmt --json summary --no-save
dmt --json plan
dmt --json tasks list
dmt --json sessions --detail
dmt --json config show
dmt --json config list
```

## 에러 처리

- 명령 실패 시 `--help` 플래그를 붙여 해당 서브커맨드의 도움말을 보여주기
- poetry가 설치되지 않은 경우 설치 안내
