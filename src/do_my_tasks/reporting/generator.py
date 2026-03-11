"""Report generator: renders DailySummary into markdown using Jinja2."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from do_my_tasks.models.report import DailySummary
from do_my_tasks.utils.config import DMTConfig


class ReportGenerator:
    """Generates markdown reports from DailySummary data."""

    def __init__(self, config: DMTConfig):
        self.config = config
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, summary: DailySummary) -> str:
        """Render a daily summary to markdown.

        Pass model objects directly (not model_dump) so Jinja2 can access
        attributes like task.status.value and commit.sha[:7].
        """
        template = self.env.get_template("daily.md.j2")
        return template.render(
            date=summary.date,
            summary_text=summary.summary_text,
            projects=summary.projects,
            rolled_over_tasks=summary.rolled_over_tasks,
            high_priority_items=summary.high_priority_items,
            total_sessions=summary.total_sessions,
            total_commits=summary.total_commits,
            total_files_changed=summary.total_files_changed,
            total_additions=summary.total_additions,
            total_deletions=summary.total_deletions,
            total_active_minutes=summary.total_active_minutes,
            total_input_tokens=summary.total_input_tokens,
            total_output_tokens=summary.total_output_tokens,
        )

    def save(self, summary: DailySummary, rendered: str) -> Path:
        """Save rendered report to file."""
        reports_dir = Path(self.config.reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"{summary.date}.md"
        report_path.write_text(rendered, encoding="utf-8")
        return report_path
