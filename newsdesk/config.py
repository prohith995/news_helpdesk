"""Configuration management for News Intelligence Desk."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "anthropic"  # or "openai"
    model: str = "claude-sonnet-4-20250514"
    max_retries: int = 1
    timeout_seconds: int = 30

    # API key from environment
    @property
    def api_key(self) -> str:
        if self.provider == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY", "")
        else:
            key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError(f"Missing API key for {self.provider}. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")
        return key


@dataclass
class NewsConfig:
    """News retrieval configuration."""
    # NewsAPI.org - free tier allows 100 requests/day
    newsapi_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))

    # Minimum sources required for analysis
    min_sources: int = 3

    # Maximum articles to fetch per query
    max_articles: int = 20

    # Cache settings
    cache_dir: Path = field(default_factory=lambda: Path("./cache"))
    cache_ttl_hours: int = 1


@dataclass
class VerificationConfig:
    """Verification gate thresholds."""
    # Source diversity: require articles from at least N different sources
    min_source_diversity: int = 3

    # Clustering stability: minimum agreement between runs
    clustering_stability_threshold: float = 0.7

    # Minimum confidence to not abstain
    min_confidence_threshold: float = 0.3


@dataclass
class Config:
    """Main application configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)

    # Output settings
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    # Debug mode
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "").lower() == "true")

    def __post_init__(self):
        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.news.cache_dir.mkdir(parents=True, exist_ok=True)


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config():
    """Reset config (useful for testing)."""
    global _config
    _config = None
