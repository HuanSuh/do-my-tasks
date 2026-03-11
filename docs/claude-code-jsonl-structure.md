# Claude Code JSONL 세션 로그 구조

`~/.claude/projects/**/` 하위에 저장되는 JSONL 파일은 Claude Code 대화 세션의 메시지 로그입니다.
각 줄(line)이 하나의 JSON 객체입니다.

## 파일 종류

| 파일명 패턴 | 설명 |
|---|---|
| `{uuid}.jsonl` | 메인 세션 대화 로그 |
| `agent-{id}.jsonl` | 서브에이전트 대화 로그 |
| `{uuid}/subagents/agent-{id}.jsonl` | 세션 하위 서브에이전트 로그 |

## 메시지 타입

### 1. User 메시지 (`type: "user"`)

```json
{
  "parentUuid": null,
  "isSidechain": true,
  "userType": "external",
  "cwd": "/Users/huansuh/Documents/workspace/howmuch",
  "sessionId": "511c0051-9609-4686-98bf-303668a09b53",
  "version": "2.0.76",
  "gitBranch": "",
  "agentId": "a020d6c",
  "type": "user",
  "message": { "role": "user", "content": "Warmup" },
  "uuid": "92111f4d-248e-4698-89c7-dcff928db2a5",
  "timestamp": "2026-02-13T02:57:18.816Z"
}
```

### 2. Assistant 메시지 (`type: "assistant"`)

```json
{
  "parentUuid": "92111f4d-248e-4698-89c7-dcff928db2a5",
  "isSidechain": true,
  "userType": "external",
  "cwd": "/Users/huansuh/Documents/workspace/howmuch",
  "sessionId": "511c0051-9609-4686-98bf-303668a09b53",
  "version": "2.0.76",
  "gitBranch": "",
  "agentId": "a020d6c",
  "message": {
    "model": "claude-haiku-4-5-20251001",
    "id": "msg_01EYppa8ZiH1swkJZYRT6Jjb",
    "type": "message",
    "role": "assistant",
    "content": [{ "type": "text", "text": "I'm ready to help! ..." }],
    "stop_reason": null,
    "usage": {
      "input_tokens": 736,
      "cache_creation_input_tokens": 0,
      "cache_read_input_tokens": 0,
      "output_tokens": 143,
      "service_tier": "standard"
    }
  },
  "requestId": "req_011CY5KN1ACXfoihKmjHbhHs",
  "type": "assistant",
  "uuid": "951a5e26-22c9-4527-95b0-6f83b86585f6",
  "timestamp": "2026-02-13T02:57:23.959Z"
}
```

### 3. 파일 히스토리 스냅샷 (`type: "file-history-snapshot"`)

```json
{
  "type": "file-history-snapshot",
  "messageId": "dd238786-7743-44e3-8712-7f6e3cfebb3e",
  "snapshot": {
    "messageId": "dd238786-7743-44e3-8712-7f6e3cfebb3e",
    "trackedFileBackups": {},
    "timestamp": "2026-03-05T05:09:09.002Z"
  },
  "isSnapshotUpdate": false
}
```

### 4. 커맨드/메타 메시지 (slash commands)

`isMeta: true`로 표시되며, 내부 커맨드 실행 결과를 담습니다.

```json
{
  "type": "user",
  "isMeta": true,
  "message": {
    "role": "user",
    "content": "<command-name>/login</command-name>\n<command-message>login</command-message>\n<command-args></command-args>"
  }
}
```

커맨드 실행 결과:

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": "<local-command-stdout>Login successful</local-command-stdout>"
  }
}
```

## 주요 필드 요약

| 필드 | 설명 |
|---|---|
| `parentUuid` | 이전 메시지 UUID (대화 트리 구성, 첫 메시지는 `null`) |
| `uuid` | 현재 메시지의 고유 ID |
| `isSidechain` | 사이드체인(서브에이전트) 대화 여부 |
| `sessionId` | 세션 ID (메인 JSONL 파일명과 동일) |
| `agentId` | 서브에이전트 ID (에이전트 JSONL에만 존재) |
| `type` | `user`, `assistant`, `file-history-snapshot` |
| `userType` | `external` (사용자 입력) |
| `cwd` | 작업 디렉토리 경로 |
| `version` | Claude Code CLI 버전 |
| `gitBranch` | 현재 git 브랜치 |
| `isMeta` | 시스템/커맨드 메시지 여부 (`true`일 때) |
| `message.model` | 사용된 모델 (assistant 메시지에만) |
| `message.usage` | 토큰 사용량 (assistant 메시지에만) |
| `requestId` | API 요청 ID (assistant 메시지에만) |
| `timestamp` | ISO 8601 형식 타임스탬프 |
