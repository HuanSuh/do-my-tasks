"""Shared output mode state for CLI commands."""

_json_mode = False


def set_json_mode(enabled: bool) -> None:
    """Set JSON output mode."""
    global _json_mode
    _json_mode = enabled


def is_json_mode() -> bool:
    """Check if JSON output mode is enabled."""
    return _json_mode
