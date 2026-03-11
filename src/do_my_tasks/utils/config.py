"""Configuration management: TOML-based config for projects and settings."""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Configuration for a single tracked project."""

    name: str
    path: str
    main_branch: str = "main"


class ScoringConfig(BaseModel):
    """Priority scoring configuration."""

    keyword_weight: float = 0.4
    volume_weight: float = 0.3
    file_criticality_weight: float = 0.2
    temporal_weight: float = 0.1
    high_threshold: float = 7.5
    medium_threshold: float = 4.0
    high_lines_threshold: int = 500
    medium_lines_threshold: int = 100
    high_keywords: list[str] = Field(
        default_factory=lambda: [
            "urgent", "critical", "bug", "fix", "hotfix", "breaking", "security"
        ]
    )
    low_keywords: list[str] = Field(
        default_factory=lambda: ["docs", "style", "chore", "typo", "refactor"]
    )
    critical_file_patterns: list[str] = Field(
        default_factory=lambda: [
            "core/", "config", "requirements", ".env", "auth", "schema", "migration"
        ]
    )
    low_file_patterns: list[str] = Field(
        default_factory=lambda: ["test", "docs/", ".md", "README"]
    )


class DMTConfig(BaseModel):
    """Top-level DMT configuration."""

    projects: list[ProjectConfig] = Field(default_factory=list)
    claude_projects_dir: str = str(Path.home() / ".claude" / "projects")
    reports_dir: str = str(Path.home() / "dmt-reports")
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)


def get_config_path() -> Path:
    """Get the config file path."""
    config_dir = Path.home() / ".config" / "do_my_tasks"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.toml"


def load_config() -> DMTConfig:
    """Load config from TOML file, creating default if not exists."""
    config_path = get_config_path()
    if not config_path.exists():
        config = DMTConfig()
        save_config(config)
        return config

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    projects = [ProjectConfig(**p) for p in data.get("projects", [])]
    scoring_data = data.get("scoring", {})
    scoring = ScoringConfig(**scoring_data) if scoring_data else ScoringConfig()

    return DMTConfig(
        projects=projects,
        claude_projects_dir=data.get(
            "claude_projects_dir", str(Path.home() / ".claude" / "projects")
        ),
        reports_dir=data.get("reports_dir", str(Path.home() / "dmt-reports")),
        scoring=scoring,
    )


def save_config(config: DMTConfig) -> None:
    """Save config to TOML file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {
        "claude_projects_dir": config.claude_projects_dir,
        "reports_dir": config.reports_dir,
        "projects": [p.model_dump() for p in config.projects],
        "scoring": config.scoring.model_dump(),
    }

    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)


def discover_projects(claude_projects_dir: str | None = None) -> list[ProjectConfig]:
    """Discover projects from ~/.claude/projects/ directory.

    Claude Code stores projects in directories whose names encode the filesystem path
    by replacing '/' with '-'. We resolve ambiguity by checking filesystem existence.
    """
    if claude_projects_dir is None:
        claude_projects_dir = str(Path.home() / ".claude" / "projects")

    claude_dir = Path(claude_projects_dir)
    if not claude_dir.exists():
        return []

    discovered: list[ProjectConfig] = []
    for entry in sorted(claude_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        # Try to decode the directory name to a real filesystem path
        resolved_path = _decode_project_path(name)
        if resolved_path:
            project_name = Path(resolved_path).name
            discovered.append(ProjectConfig(name=project_name, path=resolved_path))
    return discovered


def _decode_project_path(encoded_name: str) -> str | None:
    """Decode a Claude projects directory name to an actual filesystem path.

    The encoding replaces '/' with '-'. We resolve ambiguity by checking
    which decoded path actually exists on the filesystem.
    """
    # The encoded name starts with '-' representing the root '/'
    # e.g., '-Users-huansuh-Documents-workspace-do_my_tasks'
    # → '/Users/huansuh/Documents/workspace/do_my_tasks'
    if not encoded_name.startswith("-"):
        return None

    parts = encoded_name.split("-")
    # Remove the leading empty string from the first '-'
    parts = parts[1:]

    # Try to reconstruct the path by testing different split points
    # The challenge: directory names can contain hyphens
    return _find_valid_path(parts, "/")


def _find_valid_path(parts: list[str], prefix: str) -> str | None:
    """Recursively find a valid filesystem path from encoded parts."""
    if not parts:
        if Path(prefix).exists():
            return prefix
        return None

    # Try increasingly long combinations of parts joined with '-'
    for i in range(1, len(parts) + 1):
        segment = "-".join(parts[:i])
        candidate = f"{prefix}/{segment}" if prefix != "/" else f"/{segment}"

        if Path(candidate).exists():
            if i == len(parts):
                return candidate
            result = _find_valid_path(parts[i:], candidate)
            if result:
                return result

    return None
