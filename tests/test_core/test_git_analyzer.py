"""Tests for the Git commit analyzer."""

from datetime import date

from do_my_tasks.core.git_analyzer import _parse_commit_type, analyze_project


def test_parse_conventional_commit_types():
    """Test parsing conventional commit types from messages."""
    assert _parse_commit_type("feat: add login") == "feat"
    assert _parse_commit_type("fix: resolve crash") == "fix"
    assert _parse_commit_type("docs: update README") == "docs"
    assert _parse_commit_type("chore: bump deps") == "chore"
    assert _parse_commit_type("refactor(auth): simplify logic") == "refactor"
    assert _parse_commit_type("random message") == "other"
    assert _parse_commit_type("feat!: breaking change") == "feat"


def test_analyze_project_with_git_repo(tmp_git_repo):
    """Test analyzing a real git repository."""
    today = date.today().isoformat()
    commits = analyze_project(
        str(tmp_git_repo), "test_repo", today
    )
    # Commits were made today
    assert len(commits) >= 2  # initial + feat + fix

    # Check commit types
    types = {c.commit_type for c in commits}
    assert "feat" in types
    assert "fix" in types


def test_analyze_nonexistent_path():
    """Test graceful handling of nonexistent path."""
    commits = analyze_project("/nonexistent/path", "fake", "2026-03-10")
    assert commits == []


def test_analyze_non_git_dir(tmp_path):
    """Test graceful handling of non-git directory."""
    commits = analyze_project(str(tmp_path), "nongit", "2026-03-10")
    assert commits == []


def test_ai_assisted_detection(tmp_git_repo):
    """Test detection of AI-assisted commits via Co-Authored-By."""
    today = date.today().isoformat()
    commits = analyze_project(str(tmp_git_repo), "test_repo", today)
    ai_commits = [c for c in commits if c.is_ai_assisted]
    assert len(ai_commits) >= 1  # The feat commit has Co-Authored-By: Claude
