"""Configuration management for News Intelligence Desk."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_env_file():
    """Load .env file if it exists."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


# Load .env on module import
_load_env_file()


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "anthropic"  # or "openai"
    model: str = "claude-sonnet-4-20250514"
    max_retries: int = 1
    timeout_seconds: int = 30

    # Mock mode for testing without API
    mock_mode: bool = field(default_factory=lambda: os.getenv("NEWSDESK_MOCK", "").lower() == "true")

    # API key from environment
    @property
    def api_key(self) -> str:
        if self.mock_mode:
            return "mock-api-key"
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
    # API Keys - all three free tiers combined = 800 requests/day
    newsapi_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))      # 100/day
    gnews_key: str = field(default_factory=lambda: os.getenv("GNEWS_KEY", ""))          # 100/day
    currents_key: str = field(default_factory=lambda: os.getenv("CURRENTS_KEY", ""))    # 600/day

    # Minimum sources required for analysis
    min_sources: int = 3

    # Maximum articles to fetch per query (per API)
    max_articles_per_api: int = 10

    # Maximum total articles after combining APIs
    max_articles: int = 20

    # Cache settings
    cache_dir: Path = field(default_factory=lambda: Path("./cache"))
    cache_ttl_hours: int = 1

    @property
    def has_any_api_key(self) -> bool:
        """Check if at least one news API is configured."""
        return bool(self.newsapi_key or self.gnews_key or self.currents_key)

    @property
    def available_apis(self) -> list[str]:
        """List of configured APIs."""
        apis = []
        if self.newsapi_key:
            apis.append("newsapi")
        if self.gnews_key:
            apis.append("gnews")
        if self.currents_key:
            apis.append("currents")
        return apis


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
