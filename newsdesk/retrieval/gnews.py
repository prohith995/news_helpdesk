"""GNews.io API client.

Free tier: 100 requests/day
Docs: https://gnews.io/docs/v4
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from ..config import get_config, NewsConfig
from ..schemas import Article, SourceInfo
from .client import RetrievalResult


class GNewsClient:
    """Client for GNews.io API."""

    BASE_URL = "https://gnews.io/api/v4"

    def __init__(self, config: NewsConfig | None = None):
        self.config = config or get_config().news
        self._http_client: httpx.Client | None = None

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def _get_cache_path(self, query: str) -> Path:
        """Generate cache file path for a query."""
        cache_key = hashlib.md5(f"gnews:{query}".encode()).hexdigest()
        return self.config.cache_dir / f"{cache_key}.json"

    def _load_from_cache(self, cache_path: Path) -> dict | None:
        """Load cached response if valid."""
        if not cache_path.exists():
            return None

        try:
            with open(cache_path) as f:
                cached = json.load(f)

            cached_at = datetime.fromisoformat(cached.get("cached_at", ""))
            ttl = timedelta(hours=self.config.cache_ttl_hours)
            if datetime.now() - cached_at > ttl:
                return None

            return cached.get("data")
        except (json.JSONDecodeError, ValueError, KeyError):
            return None

    def _save_to_cache(self, cache_path: Path, data: dict):
        """Save response to cache."""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump({
                "cached_at": datetime.now().isoformat(),
                "data": data,
            }, f)

    def _parse_article(self, raw: dict) -> Article | None:
        """Parse a raw GNews article into our Article model."""
        try:
            source_data = raw.get("source", {})
            source_name = source_data.get("name", "Unknown")
            source_url = source_data.get("url", "")
            url = raw.get("url", "")

            if not url:
                return None

            source = SourceInfo(
                name=source_name,
                url=source_url or url,
            )

            published_str = raw.get("publishedAt")
            published_at = None
            if published_str:
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            return Article(
                title=raw.get("title", ""),
                url=url,
                source=source,
                published_at=published_at,
                content=raw.get("content"),
                snippet=raw.get("description"),
            )
        except (ValueError, KeyError):
            return None

    def search(self, query: str, use_cache: bool = True) -> RetrievalResult:
        """Search for news articles matching a query.

        Args:
            query: Search query
            use_cache: Whether to use cached results

        Returns:
            RetrievalResult with articles or error details
        """
        if not self.config.gnews_key:
            return RetrievalResult(
                articles=[],
                sources_count=0,
                total_results=0,
                success=False,
                error="GNEWS_KEY not configured.",
            )

        cache_path = self._get_cache_path(query)

        # Try cache first
        if use_cache:
            cached_data = self._load_from_cache(cache_path)
            if cached_data:
                articles = [self._parse_article(a) for a in cached_data.get("articles", [])]
                articles = [a for a in articles if a is not None]
                unique_sources = set(a.source.name for a in articles)
                return RetrievalResult(
                    articles=articles[:self.config.max_articles_per_api],
                    sources_count=len(unique_sources),
                    total_results=cached_data.get("totalArticles", len(articles)),
                    success=True,
                    from_cache=True,
                )

        # Fetch from API
        try:
            response = self.http_client.get(
                f"{self.BASE_URL}/search",
                params={
                    "q": query,
                    "lang": "en",
                    "max": self.config.max_articles_per_api,
                    "apikey": self.config.gnews_key,
                },
            )

            if response.status_code == 401:
                return RetrievalResult(
                    articles=[],
                    sources_count=0,
                    total_results=0,
                    success=False,
                    error="Invalid GNews API key.",
                )

            if response.status_code == 403:
                return RetrievalResult(
                    articles=[],
                    sources_count=0,
                    total_results=0,
                    success=False,
                    error="GNews API rate limit exceeded.",
                )

            response.raise_for_status()
            data = response.json()

            # Cache the response
            if use_cache:
                self._save_to_cache(cache_path, data)

            # Parse articles
            articles = [self._parse_article(a) for a in data.get("articles", [])]
            articles = [a for a in articles if a is not None]
            unique_sources = set(a.source.name for a in articles)

            return RetrievalResult(
                articles=articles[:self.config.max_articles_per_api],
                sources_count=len(unique_sources),
                total_results=data.get("totalArticles", len(articles)),
                success=True,
            )

        except httpx.HTTPStatusError as e:
            return RetrievalResult(
                articles=[],
                sources_count=0,
                total_results=0,
                success=False,
                error=f"GNews HTTP error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            return RetrievalResult(
                articles=[],
                sources_count=0,
                total_results=0,
                success=False,
                error=f"GNews request error: {str(e)}",
            )
