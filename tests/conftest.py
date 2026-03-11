"""Pytest fixtures for DMT tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from do_my_tasks.storage.database import init_db, reset_session_factory


@pytest.fixture
def db_session_factory():
    """Create an in-memory SQLite database for testing."""
    reset_session_factory()
    factory = init_db(":memory:")
    yield factory
    reset_session_factory()


@pytest.fixture
def sample_session_path():
    """Path to the sample session JSONL fixture."""
    return Path(__file__).parent / "fixtures" / "sample_session.jsonl"


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Create a temporary Git repository with sample commits."""
    import subprocess

    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir, capture_output=True,
    )

    # Create initial commit
    (repo_dir / "README.md").write_text("# Test Project")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initial commit"],
        cwd=repo_dir, capture_output=True,
    )

    # Create a feature commit
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        [
            "git", "commit", "-m",
            "feat: add main entry point\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
        ],
        cwd=repo_dir, capture_output=True,
    )

    # Create a fix commit
    (repo_dir / "src" / "main.py").write_text("def main():\n    print('hello world')\n")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: correct greeting message"],
        cwd=repo_dir, capture_output=True,
    )

    yield repo_dir


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir
