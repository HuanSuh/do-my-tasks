"""Tests for the priority scoring engine."""

from datetime import UTC, datetime

from do_my_tasks.intelligence.priority_analyzer import PriorityAnalyzer
from do_my_tasks.models.commit import GitCommitData
from do_my_tasks.models.task import TaskPriority


def _make_commit(**kwargs) -> GitCommitData:
    defaults = {
        "sha": "abc1234",
        "project_path": "/test",
        "project_name": "test",
        "author": "test",
        "timestamp": datetime(2026, 3, 10, tzinfo=UTC),
        "message": "chore: update deps",
        "branch": "main",
        "files_changed": ["src/main.py"],
        "additions": 50,
        "deletions": 10,
        "commit_type": "chore",
    }
    defaults.update(kwargs)
    return GitCommitData(**defaults)


def test_high_priority_keywords():
    """Test that high-priority keywords score HIGH."""
    analyzer = PriorityAnalyzer()
    commit = _make_commit(
        message="fix: critical security vulnerability",
        additions=600,
        files_changed=["core/auth.py"],
    )
    result = analyzer.score_commit(commit)
    assert result.priority == TaskPriority.HIGH
    assert result.score > 7.5


def test_low_priority_docs():
    """Test that docs changes score LOW."""
    analyzer = PriorityAnalyzer()
    commit = _make_commit(
        message="docs: update README",
        additions=10,
        deletions=5,
        files_changed=["docs/README.md"],
        commit_type="docs",
    )
    result = analyzer.score_commit(commit)
    assert result.priority == TaskPriority.LOW


def test_medium_priority_normal():
    """Test that normal changes get MEDIUM."""
    analyzer = PriorityAnalyzer()
    commit = _make_commit(
        message="feat: add user profile page",
        additions=150,
        deletions=20,
        files_changed=["src/pages/profile.py"],
    )
    result = analyzer.score_commit(commit)
    assert result.priority in (TaskPriority.MEDIUM, TaskPriority.HIGH)


def test_temporal_signal():
    """Test that multiple edits boost score."""
    analyzer = PriorityAnalyzer()
    commit = _make_commit(additions=150)
    result_no = analyzer.score_commit(commit, {"multiple_edits_today": False})
    result_yes = analyzer.score_commit(commit, {"multiple_edits_today": True})
    assert result_yes.score >= result_no.score


def test_score_explanation():
    """Test that explanation is generated."""
    analyzer = PriorityAnalyzer()
    commit = _make_commit(
        message="fix: urgent production bug",
        additions=600,
        files_changed=["core/config.py"],
    )
    result = analyzer.score_commit(commit, {"multiple_edits_today": True})
    assert "keyword" in result.explanation.lower() or "HIGH" in result.explanation


def test_score_commits_batch():
    """Test batch scoring with temporal context."""
    analyzer = PriorityAnalyzer()
    commits = [
        _make_commit(sha="aaa", files_changed=["src/main.py"]),
        _make_commit(sha="bbb", files_changed=["src/main.py"]),  # same file
    ]
    results = analyzer.score_commits(commits)
    assert len(results) == 2
    # Both should have temporal signal since same file edited multiple times
    assert all(r.signals["temporal"] >= 7 for r in results)
