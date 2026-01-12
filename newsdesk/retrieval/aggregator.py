"""Multi-source news aggregator.

Combines results from NewsAPI, GNews, and Currents API for better
source diversity and higher request limits.
"""

from dataclasses import dataclass
from typing import Optional

from ..config import get_config, NewsConfig
from ..schemas import Article
from .client import NewsAPIClient, RetrievalResult
from .gnews import GNewsClient
from .currents import CurrentsClient
from .mock import get_mock_articles_framing, get_mock_articles_claim


@dataclass
class AggregatedResult:
    """Result from multi-source aggregation."""
    articles: list[Article]
    sources_count: int
    total_results: int
    success: bool
    apis_used: list[str]
    apis_failed: list[str]
    errors: list[str]
    from_cache: bool = False


class NewsAggregator:
    """Aggregates news from multiple APIs for better coverage."""

    def __init__(self, config: NewsConfig | None = None):
        self.config = config or get_config().news
        self._newsapi: NewsAPIClient | None = None
        self._gnews: GNewsClient | None = None
        self._currents: CurrentsClient | None = None

    @property
    def newsapi(self) -> NewsAPIClient:
        if self._newsapi is None:
            self._newsapi = NewsAPIClient(self.config)
        return self._newsapi

    @property
    def gnews(self) -> GNewsClient:
        if self._gnews is None:
            self._gnews = GNewsClient(self.config)
        return self._gnews

    @property
    def currents(self) -> CurrentsClient:
        if self._currents is None:
            self._currents = CurrentsClient(self.config)
        return self._currents

    def _deduplicate_articles(self, articles: list[Article]) -> list[Article]:
        """Remove duplicate articles based on URL."""
        seen_urls = set()
        unique = []
        for article in articles:
            # Normalize URL for comparison
            url = article.url.rstrip("/").lower()
            if url not in seen_urls:
                seen_urls.add(url)
                unique.append(article)
        return unique

    def search(self, query: str, use_cache: bool = True) -> AggregatedResult:
        """Search across all configured APIs and aggregate results.

        Args:
            query: Search query
            use_cache: Whether to use cached results

        Returns:
            AggregatedResult with combined articles from all sources
        """
        all_articles: list[Article] = []
        apis_used: list[str] = []
        apis_failed: list[str] = []
        errors: list[str] = []
        any_from_cache = False

        # Try NewsAPI
        if self.config.newsapi_key:
            result = self.newsapi.search(query, use_cache)
            if result.success:
                all_articles.extend(result.articles)
                apis_used.append("newsapi")
                if result.from_cache:
                    any_from_cache = True
            else:
                apis_failed.append("newsapi")
                if result.error:
                    errors.append(f"NewsAPI: {result.error}")

        # Try GNews
        if self.config.gnews_key:
            result = self.gnews.search(query, use_cache)
            if result.success:
                all_articles.extend(result.articles)
                apis_used.append("gnews")
                if result.from_cache:
                    any_from_cache = True
            else:
                apis_failed.append("gnews")
                if result.error:
                    errors.append(f"GNews: {result.error}")

        # Try Currents
        if self.config.currents_key:
            result = self.currents.search(query, use_cache)
            if result.success:
                all_articles.extend(result.articles)
                apis_used.append("currents")
                if result.from_cache:
                    any_from_cache = True
            else:
                apis_failed.append("currents")
                if result.error:
                    errors.append(f"Currents: {result.error}")

        # Check if any API succeeded
        if not apis_used:
            return AggregatedResult(
                articles=[],
                sources_count=0,
                total_results=0,
                success=False,
                apis_used=[],
                apis_failed=apis_failed,
                errors=errors if errors else ["No news APIs configured or all failed."],
            )

        # Deduplicate and limit
        unique_articles = self._deduplicate_articles(all_articles)
        limited_articles = unique_articles[:self.config.max_articles]
        unique_sources = set(a.source.name for a in limited_articles)

        return AggregatedResult(
            articles=limited_articles,
            sources_count=len(unique_sources),
            total_results=len(unique_articles),
            success=True,
            apis_used=apis_used,
            apis_failed=apis_failed,
            errors=errors,
            from_cache=any_from_cache,
        )


def search_news_multi(query: str, use_cache: bool = True) -> RetrievalResult:
    """Search for news using all available APIs.

    This is the main entry point for news retrieval. It automatically
    uses all configured APIs and falls back to mock data if none are available.

    Args:
        query: Search query
        use_cache: Whether to use cached results

    Returns:
        RetrievalResult with articles from combined sources
    """
    config = get_config().news

    # If no APIs configured, use mock data
    if not config.has_any_api_key:
        # Determine mock type based on query
        if any(kw in query.lower() for kw in ["true", "verify", "confirm", "claim", "did"]):
            articles = get_mock_articles_claim(query)
        else:
            articles = get_mock_articles_framing(query)

        unique_sources = set(a.source.name for a in articles)
        return RetrievalResult(
            articles=articles,
            sources_count=len(unique_sources),
            total_results=len(articles),
            success=True,
            from_cache=False,
        )

    # Use the aggregator
    aggregator = NewsAggregator(config)
    result = aggregator.search(query, use_cache)

    # Convert to RetrievalResult
    error_msg = None
    if not result.success:
        error_msg = "; ".join(result.errors) if result.errors else "All APIs failed."
    elif result.apis_failed:
        # Partial success - some APIs failed
        error_msg = f"Partial: {', '.join(result.apis_failed)} failed"

    return RetrievalResult(
        articles=result.articles,
        sources_count=result.sources_count,
        total_results=result.total_results,
        success=result.success,
        error=error_msg,
        from_cache=result.from_cache,
    )
