"""Multi-signal priority scoring engine.

4 signals with configurable weights:
- Keyword analysis (40%): high/low keywords in commit messages
- Volume (30%): lines changed
- File criticality (20%): critical vs low-priority file patterns
- Temporal urgency (10%): multiple edits to same files
"""

from __future__ import annotations

from dataclasses import dataclass, field

from do_my_tasks.models.commit import GitCommitData
from do_my_tasks.models.task import TaskPriority
from do_my_tasks.utils.config import ScoringConfig


@dataclass
class PriorityResult:
    """Result of priority scoring with explanation."""

    score: float
    priority: TaskPriority
    signals: dict[str, float] = field(default_factory=dict)
    explanation: str = ""


class PriorityAnalyzer:
    """Multi-signal priority scoring engine."""

    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or ScoringConfig()

    def score_commit(
        self,
        commit: GitCommitData,
        context: dict | None = None,
    ) -> PriorityResult:
        """Score a single commit's priority."""
        context = context or {}

        keyword_score = self._keyword_score(commit.message)
        volume_score = self._volume_score(commit.total_changes)
        file_score = self._file_criticality_score(commit.files_changed)
        temporal_score = self._temporal_score(context)

        final_score = (
            keyword_score * self.config.keyword_weight
            + volume_score * self.config.volume_weight
            + file_score * self.config.file_criticality_weight
            + temporal_score * self.config.temporal_weight
        )

        priority = self._score_to_priority(final_score)

        signals = {
            "keyword": keyword_score,
            "volume": volume_score,
            "file_criticality": file_score,
            "temporal": temporal_score,
        }

        explanation = self._build_explanation(signals, final_score, priority)

        return PriorityResult(
            score=round(final_score, 2),
            priority=priority,
            signals=signals,
            explanation=explanation,
        )

    def score_commits(
        self,
        commits: list[GitCommitData],
    ) -> list[PriorityResult]:
        """Score multiple commits with temporal context."""
        # Build context: track files edited multiple times
        file_edit_counts: dict[str, int] = {}
        for commit in commits:
            for f in commit.files_changed:
                file_edit_counts[f] = file_edit_counts.get(f, 0) + 1

        multiple_edits = any(c > 1 for c in file_edit_counts.values())
        context = {"multiple_edits_today": multiple_edits}

        return [self.score_commit(c, context) for c in commits]

    def _keyword_score(self, message: str) -> float:
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in self.config.high_keywords):
            return 10.0
        if any(kw in msg_lower for kw in self.config.low_keywords):
            return 3.0
        return 5.0

    def _volume_score(self, total_changes: int) -> float:
        if total_changes > self.config.high_lines_threshold:
            return 10.0
        if total_changes > self.config.medium_lines_threshold:
            return 7.0
        return 3.0

    def _file_criticality_score(self, files: list[str]) -> float:
        if any(
            p in f
            for f in files
            for p in self.config.critical_file_patterns
        ):
            return 10.0
        if any(
            p in f
            for f in files
            for p in self.config.low_file_patterns
        ):
            return 3.0
        return 5.0

    def _temporal_score(self, context: dict) -> float:
        if context.get("multiple_edits_today", False):
            return 8.0
        return 5.0

    def _score_to_priority(self, score: float) -> TaskPriority:
        if score > self.config.high_threshold:
            return TaskPriority.HIGH
        if score > self.config.medium_threshold:
            return TaskPriority.MEDIUM
        return TaskPriority.LOW

    def _build_explanation(
        self,
        signals: dict[str, float],
        final_score: float,
        priority: TaskPriority,
    ) -> str:
        parts = []
        if signals["keyword"] >= 8:
            parts.append("high-priority keywords detected")
        if signals["volume"] >= 8:
            parts.append("large change volume")
        if signals["file_criticality"] >= 8:
            parts.append("critical files modified")
        if signals["temporal"] >= 7:
            parts.append("multiple edits today")

        if not parts:
            parts.append("routine change")

        return f"{priority.value.upper()} (score={final_score:.1f}): {', '.join(parts)}"
