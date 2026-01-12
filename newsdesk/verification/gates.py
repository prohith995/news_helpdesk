"""Verification gates for ensuring data quality.

These gates are explicit checkpoints that must pass before proceeding.
They implement the "fail-fast with abstention" pattern.
"""

from dataclasses import dataclass
from typing import Optional

from ..config import get_config, VerificationConfig
from ..schemas import Article, AbstentionReason


@dataclass
class GateResult:
    """Result of a verification gate check."""
    passed: bool
    reason: Optional[str] = None
    abstention_reason: Optional[AbstentionReason] = None
    details: Optional[str] = None

    # Metrics for transparency
    actual_value: Optional[float] = None
    threshold: Optional[float] = None


class SourceDiversityGate:
    """Verify that articles come from sufficiently diverse sources.

    This prevents analysis based on a single perspective or echo chamber.
    """

    def __init__(self, config: VerificationConfig | None = None):
        self.config = config or get_config().verification

    def check(self, articles: list[Article]) -> GateResult:
        """Check if articles meet source diversity requirements.

        Args:
            articles: List of articles to check

        Returns:
            GateResult indicating pass/fail with details
        """
        if not articles:
            return GateResult(
                passed=False,
                reason="No articles provided",
                abstention_reason=AbstentionReason.NO_RELEVANT_ARTICLES,
                details="Cannot verify source diversity with zero articles.",
                actual_value=0,
                threshold=self.config.min_source_diversity,
            )

        # Count unique sources
        unique_sources = set(a.source.name for a in articles)
        source_count = len(unique_sources)

        if source_count < self.config.min_source_diversity:
            return GateResult(
                passed=False,
                reason=f"Insufficient source diversity: {source_count} sources, need {self.config.min_source_diversity}",
                abstention_reason=AbstentionReason.LOW_SOURCE_DIVERSITY,
                details=f"Found articles from only {source_count} unique sources: {', '.join(sorted(unique_sources))}. "
                        f"Minimum required: {self.config.min_source_diversity}.",
                actual_value=source_count,
                threshold=self.config.min_source_diversity,
            )

        return GateResult(
            passed=True,
            reason=f"Source diversity check passed: {source_count} unique sources",
            actual_value=source_count,
            threshold=self.config.min_source_diversity,
        )


class MinimumArticlesGate:
    """Verify that we have enough articles for meaningful analysis."""

    def __init__(self, min_articles: int = 3):
        self.min_articles = min_articles

    def check(self, articles: list[Article]) -> GateResult:
        """Check if we have enough articles.

        Args:
            articles: List of articles to check

        Returns:
            GateResult indicating pass/fail
        """
        count = len(articles)

        if count < self.min_articles:
            return GateResult(
                passed=False,
                reason=f"Insufficient articles: {count}, need {self.min_articles}",
                abstention_reason=AbstentionReason.INSUFFICIENT_SOURCES,
                details=f"Only found {count} relevant articles. Need at least {self.min_articles} for meaningful analysis.",
                actual_value=count,
                threshold=self.min_articles,
            )

        return GateResult(
            passed=True,
            reason=f"Article count check passed: {count} articles",
            actual_value=count,
            threshold=self.min_articles,
        )


class ContentQualityGate:
    """Verify that articles have sufficient content for analysis."""

    def __init__(self, min_content_length: int = 100):
        self.min_content_length = min_content_length

    def check(self, articles: list[Article]) -> GateResult:
        """Check if articles have meaningful content.

        Args:
            articles: List of articles to check

        Returns:
            GateResult with count of articles with sufficient content
        """
        articles_with_content = [
            a for a in articles
            if (a.content and len(a.content) >= self.min_content_length)
               or (a.snippet and len(a.snippet) >= self.min_content_length // 2)
        ]

        count = len(articles_with_content)
        total = len(articles)

        if count < 3:  # Need at least 3 articles with content
            return GateResult(
                passed=False,
                reason=f"Insufficient content: only {count}/{total} articles have meaningful content",
                abstention_reason=AbstentionReason.INSUFFICIENT_SOURCES,
                details=f"Only {count} articles have enough text content for analysis.",
                actual_value=count,
                threshold=3,
            )

        return GateResult(
            passed=True,
            reason=f"Content quality check passed: {count}/{total} articles have sufficient content",
            actual_value=count,
            threshold=3,
        )


def run_retrieval_gates(articles: list[Article]) -> GateResult:
    """Run all retrieval-related verification gates.

    Returns the first failing gate result, or a pass result if all pass.
    """
    gates = [
        MinimumArticlesGate(),
        SourceDiversityGate(),
        # ContentQualityGate(),  # Optional: can be too strict for some queries
    ]

    for gate in gates:
        result = gate.check(articles)
        if not result.passed:
            return result

    return GateResult(
        passed=True,
        reason="All retrieval gates passed",
    )
