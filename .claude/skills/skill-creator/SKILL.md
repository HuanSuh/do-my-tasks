---
name: skill-creator
description: 새로운 Claude Code 스킬을 생성합니다. 스킬 생성, 슬래시 커맨드 만들기를 요청할 때 사용합니다.
argument-hint: "[스킬 설명]"
disable-model-invocation: true
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Skill Creator

사용자 요청: $ARGUMENTS

## 스킬이란?

스킬은 Claude Code에서 `/command` 형태로 호출할 수 있는 확장 기능입니다.
프롬프트 기반으로 동작하며, Claude가 자동으로 호출하거나 사용자가 수동으로 호출할 수 있습니다.

## 생성 절차

### 1단계: 요구사항 분석

사용자의 요청을 분석하여 다음을 결정합니다:

- **스킬 이름**: 영문 소문자 + 하이픈, 최대 64자
- **스킬 유형**:
  - `task`: 사용자가 수동으로 호출하는 작업 (disable-model-invocation: true)
  - `reference`: Claude가 자동으로 참조하는 지식 (user-invocable: false)
  - `hybrid`: 둘 다 가능 (기본값)
- **실행 컨텍스트**:
  - `inline`: 메인 대화에서 실행 (기본값)
  - `fork`: 서브에이전트에서 격리 실행 (context: fork)
- **필요한 도구**: Read, Write, Edit, Bash, Grep, Glob, Agent 등

### 2단계: 디렉토리 생성

```
.claude/skills/{skill-name}/
├── SKILL.md          # 필수: 메인 스킬 파일
├── reference.md      # 선택: 상세 문서
├── examples.md       # 선택: 사용 예시
└── scripts/          # 선택: 헬퍼 스크립트
    └── helper.sh
```

- 프로젝트 스코프: `.claude/skills/` (이 프로젝트에서만)
- 사용자 스코프: `~/.claude/skills/` (모든 프로젝트에서)

### 3단계: SKILL.md 작성

**필수 Frontmatter 필드:**

```yaml
---
name: skill-name                    # 필수: /command 이름
description: 스킬 설명               # 강력 권장: Claude 자동 호출 기준
argument-hint: "[arg1] [arg2]"      # 선택: 자동완성 힌트
disable-model-invocation: true      # 선택: 수동 전용 (기본 false)
user-invocable: true                # 선택: /메뉴 표시 (기본 true)
allowed-tools: Read, Grep           # 선택: 허용 도구 제한
model: sonnet                       # 선택: sonnet, opus, haiku, inherit
context: fork                       # 선택: 서브에이전트 실행
agent: Explore                      # 선택: 서브에이전트 유형
---
```

**사용 가능한 변수:**

| 변수 | 설명 |
|------|------|
| `$ARGUMENTS` | 전달된 모든 인자 |
| `$0`, `$1`, `$2` | 개별 인자 (인덱스) |
| `${CLAUDE_SESSION_ID}` | 현재 세션 ID |
| `${CLAUDE_SKILL_DIR}` | SKILL.md가 있는 디렉토리 |

**동적 컨텍스트 주입 (커맨드 실행):**
```markdown
현재 브랜치: !`git branch --show-current`
변경된 파일: !`git diff --name-only`
```

### 4단계: 본문 작성 가이드라인

1. **목적을 명확히**: 첫 줄에 이 스킬이 무엇을 하는지 기술
2. **단계별 절차**: 번호 목록으로 실행 흐름 정의
3. **출력 형식**: 결과물 포맷을 명시
4. **도구 활용**: 어떤 도구를 어떻게 사용할지 가이드
5. **예시 포함**: 입력/출력 예시 제공

### 5단계: 검증

- [ ] SKILL.md의 frontmatter가 `---`로 올바르게 감싸져 있는가?
- [ ] name 필드가 디렉토리명과 일치하는가?
- [ ] description이 Claude가 자동 호출 판단에 충분한가?
- [ ] 필요한 도구가 allowed-tools에 포함되어 있는가?
- [ ] $ARGUMENTS 등 변수가 올바르게 사용되었는가?

## 생성 후 안내

스킬 생성 완료 시 사용자에게 안내:

```
스킬이 생성되었습니다.

📂 위치: .claude/skills/{name}/SKILL.md
🔧 호출: /{name} [인자]
📝 편집: 위 파일을 수정하여 동작을 변경할 수 있습니다.

⚠️ 새 세션에서 바로 사용 가능합니다. 현재 세션에서는 재시작이 필요할 수 있습니다.
```

## 참고: 스킬 vs 훅 vs 에이전트

| 구분 | 스킬 | 훅 | 에이전트 |
|------|------|------|----------|
| 호출 | 수동 또는 Claude 자동 | 이벤트 자동 발동 | Claude 자동 위임 |
| 컨텍스트 | 메인 대화 (또는 fork) | 없음 (결정적 실행) | 격리된 컨텍스트 |
| 유연성 | 높음 (프롬프트 기반) | 낮음 (조건 기반) | 높음 (독립 실행) |
| 적합 | 워크플로우, 참조, 지침 | 포매팅, 검증, 알림 | 복잡 분석, 대규모 작업 |
