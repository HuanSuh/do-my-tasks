"""CLI smoke tests using typer.testing.CliRunner."""

from typer.testing import CliRunner

from do_my_tasks.cli.main import app

runner = CliRunner()


def test_help():
    """Test that --help works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "DMT" in result.output or "dmt" in result.output


def test_version():
    """Test that --version works."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_collect_help():
    """Test collect --help."""
    result = runner.invoke(app, ["collect", "--help"])
    assert result.exit_code == 0
    assert "collect" in result.output.lower() or "Collect" in result.output


def test_summary_help():
    """Test summary --help."""
    result = runner.invoke(app, ["summary", "--help"])
    assert result.exit_code == 0


def test_tasks_help():
    """Test tasks --help."""
    result = runner.invoke(app, ["tasks", "--help"])
    assert result.exit_code == 0


def test_config_help():
    """Test config --help."""
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0


def test_plan_help():
    """Test plan --help."""
    result = runner.invoke(app, ["plan", "--help"])
    assert result.exit_code == 0
