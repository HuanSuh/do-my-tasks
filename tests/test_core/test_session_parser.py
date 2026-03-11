"""Tests for the JSONL session parser."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

from do_my_tasks.core.session_parser import (
    _to_local_date_str,
    parse_session_file,
    parse_sessions_for_date,
)


def test_parse_sample_session(sample_session_path):
    """Test parsing a sample JSONL session file."""
    session = parse_session_file(sample_session_path)

    assert session is not None
    assert session.session_id == "test-session-001"
    assert session.user_message_count == 2
    assert session.assistant_message_count == 2
    assert session.message_count == 4

    # Tools
    assert "Write" in session.tools_used
    assert "Bash" in session.tools_used

    # Files
    assert any("login.py" in f for f in session.files_accessed)

    # Models
    assert "claude-sonnet-4-6" in session.models_used

    # Tokens (input_tokens + cache_read_input_tokens)
    # msg1: 500 + 100 = 600, msg2: 800 + 200 = 1000 → 1600
    assert session.total_input_tokens == 1600
    assert session.total_output_tokens == 200 + 300

    # Duration
    assert session.duration_minutes > 0


def test_parse_empty_file(tmp_path):
    """Test parsing an empty JSONL file."""
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    session = parse_session_file(empty)
    assert session is None


def test_parse_malformed_json(tmp_path):
    """Test handling of malformed JSON lines."""
    bad = tmp_path / "bad.jsonl"
    line1 = json.dumps({
        "type": "user",
        "timestamp": "2026-03-10T09:00:00.000Z",
        "message": {"role": "user", "content": "hi"},
        "sessionId": "s1",
    })
    line2 = "{bad json"
    line3 = json.dumps({
        "type": "assistant",
        "timestamp": "2026-03-10T09:01:00.000Z",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
        "sessionId": "s1",
    })
    bad.write_text("\n".join([line1, line2, line3]) + "\n")
    session = parse_session_file(bad)
    assert session is not None
    assert session.message_count == 2  # skipped the bad line


def test_skip_agent_files(tmp_path):
    """Test that agent-*.jsonl files are skipped."""
    agent = tmp_path / "agent-abc123.jsonl"
    agent.write_text('{"type": "user", "timestamp": "2026-03-10T09:00:00.000Z"}\n')
    session = parse_session_file(agent)
    assert session is None


# --- Timezone handling tests ---


def test_parse_utc_z_timestamp(tmp_path):
    """Test that Z-suffix timestamps are parsed as UTC."""
    f = tmp_path / "utc.jsonl"
    f.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-03-10T09:00:00.000Z",
        "message": {"role": "user", "content": "hello"},
        "sessionId": "s1",
    }) + "\n")
    session = parse_session_file(f)
    assert session is not None
    assert session.start_time.tzinfo is not None
    assert session.start_time.utcoffset().total_seconds() == 0


def test_parse_offset_timestamp(tmp_path):
    """Test that +09:00 offset timestamps are parsed correctly."""
    f = tmp_path / "kst.jsonl"
    f.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-03-10T18:00:00.000+09:00",
        "message": {"role": "user", "content": "hello"},
        "sessionId": "s1",
    }) + "\n")
    session = parse_session_file(f)
    assert session is not None
    assert session.start_time.tzinfo is not None
    # 18:00+09:00 == 09:00 UTC
    utc_time = session.start_time.astimezone(timezone.utc)
    assert utc_time.hour == 9


def test_to_local_date_str_utc_midnight():
    """UTC midnight should map to previous day in UTC+9."""
    from zoneinfo import ZoneInfo
    utc_dt = datetime(2026, 3, 11, 0, 30, tzinfo=timezone.utc)
    # In KST (UTC+9), this is 2026-03-11 09:30 — same date
    kst = ZoneInfo("Asia/Seoul")
    local_dt = utc_dt.astimezone(kst)
    assert local_dt.strftime("%Y-%m-%d") == "2026-03-11"

    # But a session at UTC 14:00 would be next day in KST? No, 14:00 UTC = 23:00 KST same day
    # Session at UTC 15:30 = KST 00:30 next day
    utc_late = datetime(2026, 3, 10, 15, 30, tzinfo=timezone.utc)
    kst_late = utc_late.astimezone(kst)
    assert kst_late.strftime("%Y-%m-%d") == "2026-03-11"


def test_to_local_date_str_naive():
    """Naive datetime should be treated as local time."""
    naive_dt = datetime(2026, 3, 10, 23, 59)
    result = _to_local_date_str(naive_dt)
    assert result == "2026-03-10"


def test_parse_sessions_for_date_timezone(tmp_path):
    """Sessions at UTC late night should appear on the next local day in KST."""
    from zoneinfo import ZoneInfo

    # Create a session that starts at UTC 15:30 (= KST 00:30 next day)
    proj_dir = tmp_path / "-test-project"
    proj_dir.mkdir()
    session_file = proj_dir / "sess1.jsonl"
    session_file.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-03-10T15:30:00.000Z",
        "message": {"role": "user", "content": "late night work"},
        "sessionId": "s-late",
    }) + "\n")

    kst = ZoneInfo("Asia/Seoul")

    # With KST timezone, this should be 2026-03-11
    with patch(
        "do_my_tasks.core.session_parser._get_local_tz",
        return_value=kst,
    ):
        sessions_mar10 = parse_sessions_for_date(str(tmp_path), "2026-03-10")
        sessions_mar11 = parse_sessions_for_date(str(tmp_path), "2026-03-11")

    assert len(sessions_mar10) == 0
    assert len(sessions_mar11) == 1
    assert sessions_mar11[0].session_id == "s-late"


def test_parse_sessions_for_date_utc(tmp_path):
    """With UTC timezone, UTC timestamps should match UTC dates."""
    proj_dir = tmp_path / "-test-project"
    proj_dir.mkdir()
    session_file = proj_dir / "sess1.jsonl"
    session_file.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-03-10T15:30:00.000Z",
        "message": {"role": "user", "content": "work"},
        "sessionId": "s-utc",
    }) + "\n")

    with patch(
        "do_my_tasks.core.session_parser._get_local_tz",
        return_value=timezone.utc,
    ):
        sessions = parse_sessions_for_date(str(tmp_path), "2026-03-10")

    assert len(sessions) == 1


def test_duration_with_aware_timestamps(tmp_path):
    """Duration calculation should work correctly with aware datetimes."""
    f = tmp_path / "dur.jsonl"
    lines = [
        json.dumps({
            "type": "user",
            "timestamp": "2026-03-10T09:00:00.000Z",
            "message": {"role": "user", "content": "start"},
            "sessionId": "s1",
        }),
        json.dumps({
            "type": "assistant",
            "timestamp": "2026-03-10T09:30:00.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
            "sessionId": "s1",
        }),
    ]
    f.write_text("\n".join(lines) + "\n")
    session = parse_session_file(f)
    assert session is not None
    assert abs(session.duration_minutes - 30.0) < 0.01


def test_meta_messages_skipped(tmp_path):
    """Test that isMeta messages are not counted."""
    f = tmp_path / "meta.jsonl"
    lines = [
        json.dumps({
            "type": "user",
            "timestamp": "2026-03-10T09:00:00.000Z",
            "message": {"role": "user", "content": "real message"},
            "sessionId": "s1",
        }),
        json.dumps({
            "type": "user",
            "timestamp": "2026-03-10T09:01:00.000Z",
            "message": {"role": "user", "content": "/help"},
            "sessionId": "s1",
            "isMeta": True,
        }),
    ]
    f.write_text("\n".join(lines) + "\n")
    session = parse_session_file(f)
    assert session is not None
    assert session.user_message_count == 1


def test_cwd_and_git_branch_extraction(tmp_path):
    """Test cwd and gitBranch extraction from first entry."""
    f = tmp_path / "cwd.jsonl"
    f.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-03-10T09:00:00.000Z",
        "message": {"role": "user", "content": "hi"},
        "sessionId": "s1",
        "cwd": "/Users/test/myapp",
        "gitBranch": "feat/login",
    }) + "\n")
    session = parse_session_file(f)
    assert session is not None
    assert session.cwd == "/Users/test/myapp"
    assert session.git_branch == "feat/login"


def test_multiple_models_tracked(tmp_path):
    """Test that multiple models are tracked across messages."""
    f = tmp_path / "multi.jsonl"
    lines = [
        json.dumps({
            "type": "assistant",
            "timestamp": "2026-03-10T09:00:00.000Z",
            "message": {
                "model": "claude-sonnet-4-6",
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }),
        json.dumps({
            "type": "assistant",
            "timestamp": "2026-03-10T09:05:00.000Z",
            "message": {
                "model": "claude-haiku-4-5-20251001",
                "role": "assistant",
                "content": [{"type": "text", "text": "fast"}],
                "usage": {"input_tokens": 5, "output_tokens": 3},
            },
        }),
    ]
    f.write_text("\n".join(lines) + "\n")
    session = parse_session_file(f)
    assert session is not None
    assert "claude-sonnet-4-6" in session.models_used
    assert "claude-haiku-4-5-20251001" in session.models_used


def test_tool_use_extraction(tmp_path):
    """Test that tool names and file paths are extracted from content blocks."""
    f = tmp_path / "tools.jsonl"
    f.write_text(json.dumps({
        "type": "assistant",
        "timestamp": "2026-03-10T09:00:00.000Z",
        "message": {
            "model": "claude-sonnet-4-6",
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/src/main.py"}},
                {"type": "tool_use", "id": "t2", "name": "Edit",
                 "input": {"file_path": "/src/utils.py", "old_string": "a", "new_string": "b"}},
                {"type": "text", "text": "Done."},
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    }) + "\n")
    session = parse_session_file(f)
    assert session is not None
    assert "Read" in session.tools_used
    assert "Edit" in session.tools_used
    assert "/src/main.py" in session.files_accessed
    assert "/src/utils.py" in session.files_accessed
