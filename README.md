# DMT - Do My Tasks

Intelligent daily activity tracker & task manager for Claude Code power users.

Claude Code 세션 로그와 Git 커밋을 자동 수집하고, 태스크 관리와 우선순위 분석을 제공하는 CLI 도구.

## Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/) (패키지 매니저)
- Git (커밋 분석용)

## Installation

```bash
# 저장소 클론
git clone <repo-url>
cd do_my_tasks

# 의존성 설치
poetry install

# 설치 확인
poetry run dmt --version
```

Poetry shell을 활성화하면 `poetry run` 없이 직접 실행 가능:

```bash
poetry shell
dmt --version
```

## Initial Setup

### 1. 프로젝트 자동 탐색

Claude Code 프로젝트 디렉토리(`~/.claude/projects/`, `~/.claude-profiles/*/projects/`)에서 자동으로 프로젝트를 탐색:

```bash
dmt config discover
```

### 2. 프로젝트 수동 등록

```bash
dmt config add myproject /path/to/project
```

### 3. 현재 설정 확인

```bash
dmt config show
dmt config list   # 등록된 프로젝트 목록만
```

### 4. 프로젝트 제거

```bash
dmt config remove myproject
```

설정 파일 위치: `~/.config/do_my_tasks/config.toml`

## Daily Workflow

### Morning - 오늘의 계획 확인

```bash
dmt plan
```

전날 미완료 태스크(rollover), 고우선순위 항목, 자동 감지된 후속 작업을 종합해서 오늘의 TODO를 생성합니다.

```bash
dmt plan --save    # TODO 항목을 태스크로 DB에 저장
```

### During the day - 활동 데이터 수집

```bash
dmt collect                          # 오늘 날짜 기준 수집
dmt collect --date 2026-03-10        # 특정 날짜 수집
dmt collect --project myproject      # 특정 프로젝트만 수집
```

수집 대상:
- Claude Code 세션 로그 (메시지 수, 도구 사용, 토큰 사용량)
- Git 커밋 (additions/deletions, conventional commit 타입 파싱)

세션 로그 탐색 경로:
- `~/.claude/projects/` (기본)
- `~/.claude-profiles/*/projects/` (프로필 사용 시)
- 워크트리 세션도 자동 감지 (`--claude-worktrees-*` 디렉토리)

### Evening - 일일 리포트 생성

```bash
dmt summary                          # 터미널에 출력
dmt summary --save                   # 마크다운 파일로 저장
dmt summary --date 2026-03-10        # 특정 날짜 리포트
```

리포트에 포함되는 정보:
- 프로젝트별 커밋/세션 요약
- 태스크 진행 현황
- 코드 변경 통계 (lines added/deleted, files changed)
- 토큰 사용량
- 활동 시간

## Live Sessions

현재 실행 중인 Claude Code 세션을 조회:

```bash
dmt sessions                # 라이브 세션 목록
dmt sessions live           # 동일
dmt sessions --wide         # 전체 로그 경로 표시
dmt sessions --detail       # 각 세션의 마지막 메시지 & 도구 사용 표시
dmt sessions -d             # --detail 단축
```

PID, 프로젝트명, 시작 시각, 마지막 업데이트, 로그 파일 경로를 보여줍니다.
`--detail` 모드에서는 각 세션의 마지막 유저 메시지, 사용된 도구, 경과 시간을 추가로 표시합니다.

### Watch Mode

세션을 실시간 모니터링하고, 작업 완료 후 idle 상태가 되면 다음 태스크를 알림으로 전달:

```bash
dmt sessions watch                        # 기본 (10초 폴링, 30초 idle 감지)
dmt sessions watch --interval 5 --idle 15 # 커스텀 간격
dmt sessions watch --project myapp        # 특정 프로젝트만 감시
dmt sessions watch --no-notify            # OS 알림 끄기
```

idle 감지 시 표시 내용:
- ✅ 완료 — 요청 내용, 수정 파일, 실행 명령어 요약 + 다음 태스크
- ⏸️ 권한 필요 — 승인 대기 중인 도구 표시
- macOS 알림 (Glass 사운드)

Watch 로그는 `~/.dmt/logs/dmt_watch_log_{timestamp}.log`에 자동 저장됩니다.
5일 이상 된 로그는 watch 시작 시 자동 삭제됩니다.

### Clean (유휴 세션 정리)

오래된 유휴 세션을 찾아서 하나씩 확인 후 종료:

```bash
dmt sessions clean                # 60분 이상 idle 세션 정리 (y/N/a 선택)
dmt sessions clean --idle 30      # 30분 기준
dmt sessions clean --dry-run      # 종료 없이 대상만 확인
dmt sessions clean --force        # 확인 없이 전부 종료
dmt sessions clean 12345          # 특정 PID 직접 종료
dmt sessions clean 12345 67890    # 여러 PID 한번에 종료
```

각 세션별로 프로젝트, idle 시간, 마지막 메시지를 보여주고:
- **y** — 이 세션 kill
- **N** (기본) — skip
- **a** — 나머지 전부 kill

## Task Management

```bash
# 태스크 추가
dmt tasks add "Fix login bug" --priority high --project myapp
dmt tasks add "Write tests" --priority medium

# 태스크 목록
dmt tasks list
dmt tasks list --status pending
dmt tasks list --project myapp

# 태스크 완료
dmt tasks complete T-0001

# 태스크 수정
dmt tasks update T-0001 --priority high
dmt tasks update T-0001 --status in_progress

# 태스크 삭제
dmt tasks delete T-0002

# 태스크 롤오버 (미완료 → 다음 날로 이월)
dmt tasks rollover
dmt tasks rollover --from-date 2026-03-10 --to-date 2026-03-11
```

태스크 ID는 `T-0001` 형식이며, `dmt tasks list`에서 확인할 수 있습니다.

## Global Options

```bash
dmt --verbose collect    # 디버그 로그 출력
dmt --json tasks list    # JSON 형태로 출력 (sessions watch, config discover 제외)
dmt --version            # 버전 확인
dmt --help               # 도움말
```

모든 하위 명령어도 `--help` 지원:

```bash
dmt collect --help
dmt tasks --help
dmt tasks add --help
```

## Priority Scoring

태스크와 커밋에 대해 4가지 신호를 기반으로 우선순위를 자동 계산:

| Signal | Weight | Description |
|--------|--------|-------------|
| Keyword | 40% | 커밋 메시지의 키워드 (fix, bug, security 등) |
| Volume | 30% | 코드 변경량 (additions + deletions) |
| File Criticality | 20% | 변경된 파일의 중요도 (config, auth 등) |
| Temporal | 10% | 최근 변경일수록 높은 점수 |

점수 기준: >7.5 = **HIGH**, >4.0 = MEDIUM, ≤4.0 = LOW

## Data Storage

- **DB**: `~/.config/do_my_tasks/data.db` (SQLite)
- **Config**: `~/.config/do_my_tasks/config.toml`
- **Reports**: `~/.config/do_my_tasks/reports/YYYY-MM-DD.md`
- **Watch Logs**: `~/.dmt/logs/dmt_watch_log_{timestamp}.log` (5일 보관)

환경변수 `DMT_DB_PATH`로 DB 경로 변경 가능.

## Claude Code Session Logs

DMT는 Claude Code의 JSONL 세션 로그를 파싱합니다. 로그 파일 위치:

```
~/.claude/projects/<encoded-path>/*.jsonl           # 기본 세션
~/.claude/projects/<encoded-path>--claude-worktrees-<name>/*.jsonl  # 워크트리 세션
~/.claude-profiles/<profile>/projects/<encoded-path>/*.jsonl        # 프로필 세션
```

인코딩 규칙: 프로젝트 경로의 `/`가 `-`로 변환됨.
예: `/Users/me/workspace/myapp` → `-Users-me-workspace-myapp`

현재 실행 중인 Claude 세션 확인:

```bash
# 라이브 세션 프로세스 확인
ps aux | grep "[c]laude" | grep -v Helper

# 각 세션의 작업 디렉토리 확인
lsof -a -p <PID> -d cwd
```

## Development

```bash
# 테스트 실행
poetry run pytest

# 린트
poetry run ruff check src/ tests/

# 타입 체크
poetry run mypy src/
```

## Project Structure

```
src/do_my_tasks/
├── cli/                  # Typer CLI
│   ├── main.py
│   └── commands/         # collect, summary, plan, task, config
├── core/                 # 핵심 로직
│   ├── collector.py      # 일일 수집 오케스트레이션
│   ├── session_parser.py # JSONL 세션 파서
│   ├── git_analyzer.py   # Git 커밋 분석
│   └── task_manager.py   # 태스크 CRUD
├── intelligence/         # 분석 엔진
│   ├── summarizer.py     # 일일 요약 생성
│   ├── priority_analyzer.py  # 우선순위 점수
│   └── todo_generator.py # TODO 생성
├── models/               # Pydantic 도메인 모델
├── reporting/            # Jinja2 리포트 생성
├── storage/              # SQLAlchemy ORM + Repository
└── utils/                # 설정, 로깅
```
