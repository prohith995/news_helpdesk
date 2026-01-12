"""Core data models for News Intelligence Desk.

All LLM outputs must conform to typed schemas. Invalid outputs trigger
retry once, then abstention with clear reason.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class WorkflowType(Enum):
    """Supported analysis workflows."""
    FRAMING_DIVERGENCE = "framing_divergence"
    CLAIM_CHECK = "claim_check"
    UNKNOWN = "unknown"


class AbstentionReason(Enum):
    """Explicit reasons why the system chose not to provide an answer."""
    INSUFFICIENT_SOURCES = "insufficient_sources"
    LOW_SOURCE_DIVERSITY = "low_source_diversity"
    CLUSTERING_UNSTABLE = "clustering_unstable"
    LLM_OUTPUT_INVALID = "llm_output_invalid"
    NO_RELEVANT_ARTICLES = "no_relevant_articles"
    CLAIM_NOT_VERIFIABLE = "claim_not_verifiable"
    QUERY_AMBIGUOUS = "query_ambiguous"
    RATE_LIMITED = "rate_limited"


@dataclass
class Query:
    """User input query."""
    raw_text: str
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self.raw_text = self.raw_text.strip()
        if not self.raw_text:
            raise ValueError("Query cannot be empty")


@dataclass
class SourceInfo:
    """Metadata about a news source."""
    name: str
    url: str
    bias_label: Optional[str] = None  # e.g., "left", "center", "right"
    reliability_score: Optional[float] = None  # 0.0 to 1.0


@dataclass
class Article:
    """A retrieved news article."""
    title: str
    url: str
    source: SourceInfo
    published_at: Optional[datetime] = None
    content: Optional[str] = None
    snippet: Optional[str] = None

    def __post_init__(self):
        if not self.title:
            raise ValueError("Article must have a title")
        if not self.url:
            raise ValueError("Article must have a URL")


@dataclass
class Citation:
    """A citation linking a claim to its source."""
    article: Article
    relevant_quote: str
    relevance_score: float  # 0.0 to 1.0

    def to_markdown(self) -> str:
        """Format citation for markdown output."""
        return f'"{self.relevant_quote}" — [{self.article.source.name}]({self.article.url})'


@dataclass
class Confidence:
    """Confidence assessment for a result."""
    score: float  # 0.0 to 1.0
    reasoning: str
    limiting_factors: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Confidence score must be 0.0-1.0, got {self.score}")

    @property
    def level(self) -> str:
        """Human-readable confidence level."""
        if self.score >= 0.8:
            return "high"
        elif self.score >= 0.5:
            return "medium"
        elif self.score >= 0.3:
            return "low"
        return "very_low"


@dataclass
class WorkflowResult:
    """Result from a workflow execution."""
    workflow_type: WorkflowType
    query: Query
    success: bool

    # Populated on success
    data: Optional[dict] = None
    citations: list[Citation] = field(default_factory=list)
    confidence: Optional[Confidence] = None

    # Populated on abstention
    abstained: bool = False
    abstention_reason: Optional[AbstentionReason] = None
    abstention_details: Optional[str] = None

    # Metadata
    articles_analyzed: int = 0
    sources_count: int = 0
    execution_time_seconds: float = 0.0

    def __post_init__(self):
        if self.success and self.abstained:
            raise ValueError("Result cannot be both successful and abstained")
        if not self.success and not self.abstained:
            raise ValueError("Failed result must have abstention reason")


@dataclass
class Report:
    """Final output report combining structured data and human-readable summary."""
    result: WorkflowResult
    generated_at: datetime = field(default_factory=datetime.now)

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "query": self.result.query.raw_text,
            "workflow": self.result.workflow_type.value,
            "success": self.result.success,
            "abstained": self.result.abstained,
            "abstention_reason": self.result.abstention_reason.value if self.result.abstention_reason else None,
            "abstention_details": self.result.abstention_details,
            "confidence": {
                "score": self.result.confidence.score,
                "level": self.result.confidence.level,
                "reasoning": self.result.confidence.reasoning,
                "limiting_factors": self.result.confidence.limiting_factors,
            } if self.result.confidence else None,
            "data": self.result.data,
            "citations": [
                {
                    "source": c.article.source.name,
                    "url": c.article.url,
                    "quote": c.relevant_quote,
                    "relevance": c.relevance_score,
                }
                for c in self.result.citations
            ],
            "metadata": {
                "articles_analyzed": self.result.articles_analyzed,
                "sources_count": self.result.sources_count,
                "execution_time_seconds": self.result.execution_time_seconds,
                "generated_at": self.generated_at.isoformat(),
            },
        }

    def to_markdown(self) -> str:
        """Generate human-readable markdown report."""
        lines = [
            f"# News Intelligence Report",
            f"",
            f"**Query:** {self.result.query.raw_text}",
            f"**Workflow:** {self.result.workflow_type.value}",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
        ]

        if self.result.abstained:
            lines.extend([
                "## ⚠️ Analysis Abstained",
                f"",
                f"**Reason:** {self.result.abstention_reason.value if self.result.abstention_reason else 'Unknown'}",
                f"",
                f"{self.result.abstention_details or 'No additional details.'}",
            ])
        else:
            # Confidence section
            if self.result.confidence:
                conf = self.result.confidence
                lines.extend([
                    f"## Confidence: {conf.level.upper()} ({conf.score:.0%})",
                    f"",
                    f"{conf.reasoning}",
                    f"",
                ])
                if conf.limiting_factors:
                    lines.append("**Limiting factors:**")
                    for factor in conf.limiting_factors:
                        lines.append(f"- {factor}")
                    lines.append("")

            # Data section (workflow-specific)
            if self.result.data:
                lines.extend([
                    "## Analysis",
                    "",
                ])
                # This will be customized per workflow
                lines.append("_(See structured output for details)_")
                lines.append("")

            # Citations
            if self.result.citations:
                lines.extend([
                    "## Sources Cited",
                    "",
                ])
                for i, citation in enumerate(self.result.citations, 1):
                    lines.append(f"{i}. {citation.to_markdown()}")
                lines.append("")

        # Metadata footer
        lines.extend([
            "---",
            f"*Analyzed {self.result.articles_analyzed} articles from {self.result.sources_count} sources in {self.result.execution_time_seconds:.1f}s*",
        ])

        return "\n".join(lines)
