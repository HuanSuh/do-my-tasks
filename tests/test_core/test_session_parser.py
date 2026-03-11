"""Tests for the JSONL session parser."""

import json

from do_my_tasks.core.session_parser import parse_session_file


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
