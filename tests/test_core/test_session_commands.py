"""Tests for session.py helper functions (live/watch/clean support)."""

import json
from pathlib import Path

from do_my_tasks.cli.commands.session import (
    _char_width,
    _extract_user_text,
    _get_project_name,
    _get_session_state,
    _truncate_display,
)


# --- _get_project_name ---


class TestGetProjectName:
    def test_simple_path(self):
        assert _get_project_name("/Users/me/workspace/myapp") == "myapp"

    def test_worktree_path(self):
        cwd = "/Users/me/workspace/myapp/.claude/worktrees/feat-x"
        assert _get_project_name(cwd) == "myapp"

    def test_worktree_nested(self):
        cwd = "/Users/me/workspace/org/repo/.claude/worktrees/branch"
        assert _get_project_name(cwd) == "repo"

    def test_root_path(self):
        assert _get_project_name("/") == ""

    def test_trailing_slash(self):
        assert _get_project_name("/Users/me/myapp/") == "myapp"


# --- _char_width / _truncate_display ---


class TestDisplayWidth:
    def test_ascii_width(self):
        assert _char_width("a") == 1
        assert _char_width(" ") == 1

    def test_cjk_width(self):
        assert _char_width("한") == 2
        assert _char_width("中") == 2
        assert _char_width("あ") == 2

    def test_truncate_ascii(self):
        assert _truncate_display("hello world", 8) == "hello..."

    def test_truncate_no_need(self):
        assert _truncate_display("short", 10) == "short"

    def test_truncate_cjk(self):
        text = "한글테스트입니다"
        result = _truncate_display(text, 10)
        assert result.endswith("...")
        # Each Korean char = 2 cols, so max 3 chars + "..." (3) = 9 cols fits in 10
        assert len(result) <= 7  # 3 korean + "..."


# --- _extract_user_text ---


class TestExtractUserText:
    def test_plain_string(self):
        assert _extract_user_text("hello world") == "hello world"

    def test_multiline_returns_first(self):
        assert _extract_user_text("line1\nline2\nline3") == "line1"

    def test_leading_whitespace_stripped(self):
        assert _extract_user_text("\n  hello") == "hello"

    def test_empty_string(self):
        assert _extract_user_text("") is None

    def test_system_message_xml_tag(self):
        assert _extract_user_text("<system-reminder>test</system-reminder>") is None

    def test_system_message_continuation(self):
        text = "This session is being continued from a previous conversation"
        assert _extract_user_text(text) is None

    def test_tool_result_with_amend(self):
        content = [
            {
                "type": "tool_result",
                "content": (
                    "Some tool output\n"
                    "To tell you how to proceed, the user said:\n"
                    "fix the bug please"
                ),
            }
        ]
        assert _extract_user_text(content) == "fix the bug please"

    def test_tool_result_without_amend(self):
        content = [
            {
                "type": "tool_result",
                "content": "Just a tool result without user text",
            }
        ]
        assert _extract_user_text(content) is None

    def test_non_tool_result_list(self):
        content = [{"type": "text", "text": "hello"}]
        assert _extract_user_text(content) is None

    def test_none_content(self):
        assert _extract_user_text(None) is None

    def test_integer_content(self):
        assert _extract_user_text(42) is None


# --- _get_session_state ---


def _make_log(tmp_path: Path, entries: list[dict]) -> Path:
    """Write JSONL entries to a temp log file."""
    log = tmp_path / "session.jsonl"
    lines = [json.dumps(e) for e in entries]
    log.write_text("\n".join(lines) + "\n")
    return log


class TestGetSessionState:
    def test_empty_file(self, tmp_path):
        log = tmp_path / "empty.jsonl"
        log.write_text("")
        state = _get_session_state(log)
        assert state["status"] == "waiting"
        assert state["last_type"] is None

    def test_user_then_assistant_done(self, tmp_path):
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "fix the bug"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:01:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Done."}],
                    "stop_reason": "end_turn",
                },
            },
        ])
        state = _get_session_state(log)
        assert state["status"] == "idle"
        assert state["last_type"] == "assistant"
        assert state["last_user_msg"] == "fix the bug"

    def test_assistant_tool_use_permission(self, tmp_path):
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "deploy it"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:01:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Bash",
                         "input": {"command": "git push origin main"}},
                    ],
                    "stop_reason": "tool_use",
                },
            },
        ])
        state = _get_session_state(log)
        assert state["status"] == "permission"
        assert "Bash" in state["tools"]
        assert "git push origin" in state["commands_run"]

    def test_tool_approval_preserves_last_type(self, tmp_path):
        """Tool approval (empty user msg) should NOT reset last_type to 'user'."""
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "fix it"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:01:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Write",
                         "input": {"file_path": "/src/app.py", "content": "..."}},
                    ],
                    "stop_reason": "tool_use",
                },
            },
            # Tool approval — user entry with tool_result, no real text
            {
                "type": "user",
                "timestamp": "2026-03-10T09:02:00.000Z",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": ""},
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:02:30.000Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "File written."}],
                    "stop_reason": "end_turn",
                },
            },
        ])
        state = _get_session_state(log)
        assert state["status"] == "idle"
        assert state["last_type"] == "assistant"
        # last_user_msg should still be "fix it", not reset
        assert state["last_user_msg"] == "fix it"

    def test_files_modified_tracked(self, tmp_path):
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "update config"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:01:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Edit",
                         "input": {"file_path": "/config/settings.py",
                                   "old_string": "a", "new_string": "b"}},
                        {"type": "tool_use", "id": "t2", "name": "Write",
                         "input": {"file_path": "/src/new_file.py",
                                   "content": "..."}},
                    ],
                    "stop_reason": "end_turn",
                },
            },
        ])
        state = _get_session_state(log)
        assert "settings.py" in state["files_modified"]
        assert "new_file.py" in state["files_modified"]

    def test_meta_messages_ignored(self, tmp_path):
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "do work"},
            },
            {
                "type": "user",
                "timestamp": "2026-03-10T09:01:00.000Z",
                "message": {"role": "user", "content": "/help"},
                "isMeta": True,
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:02:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done"}],
                    "stop_reason": "end_turn",
                },
            },
        ])
        state = _get_session_state(log)
        assert state["last_user_msg"] == "do work"

    def test_system_injected_messages_filtered(self, tmp_path):
        """System-injected XML messages should not become last_user_msg."""
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "real request"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:01:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "working..."}],
                    "stop_reason": "end_turn",
                },
            },
            {
                "type": "user",
                "timestamp": "2026-03-10T09:02:00.000Z",
                "message": {
                    "role": "user",
                    "content": "<system-reminder>reminder text</system-reminder>",
                },
            },
        ])
        state = _get_session_state(log)
        # System message should be filtered; last_user_msg stays "real request"
        assert state["last_user_msg"] == "real request"

    def test_file_size_tracked(self, tmp_path):
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "hi"},
            },
        ])
        state = _get_session_state(log)
        assert state["file_size"] > 0

    def test_nonexistent_file(self, tmp_path):
        log = tmp_path / "nonexistent.jsonl"
        state = _get_session_state(log)
        assert state["file_size"] == 0
        assert state["status"] == "waiting"

    def test_new_user_msg_resets_tracking(self, tmp_path):
        """A new user message should reset tools, files, and commands."""
        log = _make_log(tmp_path, [
            {
                "type": "user",
                "timestamp": "2026-03-10T09:00:00.000Z",
                "message": {"role": "user", "content": "first task"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:01:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Write",
                         "input": {"file_path": "/old_file.py", "content": "..."}},
                    ],
                    "stop_reason": "end_turn",
                },
            },
            {
                "type": "user",
                "timestamp": "2026-03-10T09:05:00.000Z",
                "message": {"role": "user", "content": "second task"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-03-10T09:06:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t2", "name": "Read",
                         "input": {"file_path": "/new_file.py"}},
                    ],
                    "stop_reason": "end_turn",
                },
            },
        ])
        state = _get_session_state(log)
        assert state["last_user_msg"] == "second task"
        assert "Read" in state["tools"]
        assert "Write" not in state["tools"]
        assert "old_file.py" not in state["files_modified"]
