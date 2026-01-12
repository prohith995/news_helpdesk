"""Currents API client.

Free tier: 600 requests/day
Docs: https://currentsapi.services/en/docs/
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


class CurrentsClient:
    """Client for Currents API."""

    BASE_URL = "https://api.currentsapi.services/v1"

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
        cache_key = hashlib.md5(f"currents:{query}".encode()).hexdigest()
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
        """Parse a raw Currents article into our Article model."""
        try:
            url = raw.get("url", "")
            if not url:
                return None

            # Currents uses a flat structure for source info
            source = SourceInfo(
                name=raw.get("author", "Unknown"),
                url=url,
            )

            published_str = raw.get("published")
            published_at = None
            if published_str:
                try:
                    # Currents uses format: "2024-01-15 10:30:00 +0000"
                    published_at = datetime.strptime(
                        published_str.replace(" +0000", ""),
                        "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    try:
                        published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass

            return Article(
                title=raw.get("title", ""),
                url=url,
                source=source,
                published_at=published_at,
                content=raw.get("description"),  # Currents puts content in description
                snippet=raw.get("description", "")[:200] if raw.get("description") else None,
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
        if not self.config.currents_key:
            return RetrievalResult(
                articles=[],
                sources_count=0,
                total_results=0,
                success=False,
                error="CURRENTS_KEY not configured.",
            )

        cache_path = self._get_cache_path(query)

        # Try cache first
        if use_cache:
            cached_data = self._load_from_cache(cache_path)
            if cached_data:
                articles = [self._parse_article(a) for a in cached_data.get("news", [])]
                articles = [a for a in articles if a is not None]
                unique_sources = set(a.source.name for a in articles)
                return RetrievalResult(
                    articles=articles[:self.config.max_articles_per_api],
                    sources_count=len(unique_sources),
                    total_results=len(articles),
                    success=True,
                    from_cache=True,
                )

        # Fetch from API
        try:
            response = self.http_client.get(
                f"{self.BASE_URL}/search",
                params={
                    "keywords": query,
                    "language": "en",
                    "apiKey": self.config.currents_key,
                },
            )

            if response.status_code == 401:
                return RetrievalResult(
                    articles=[],
                    sources_count=0,
                    total_results=0,
                    success=False,
                    error="Invalid Currents API key.",
                )

            if response.status_code == 429:
                return RetrievalResult(
                    articles=[],
                    sources_count=0,
                    total_results=0,
                    success=False,
                    error="Currents API rate limit exceeded.",
                )

            response.raise_for_status()
            data = response.json()

            # Check for API-level errors
            if data.get("status") == "error":
                return RetrievalResult(
                    articles=[],
                    sources_count=0,
                    total_results=0,
                    success=False,
                    error=f"Currents API error: {data.get('message', 'Unknown')}",
                )

            # Cache the response
            if use_cache:
                self._save_to_cache(cache_path, data)

            # Parse articles
            articles = [self._parse_article(a) for a in data.get("news", [])]
            articles = [a for a in articles if a is not None]
            unique_sources = set(a.source.name for a in articles)

            return RetrievalResult(
                articles=articles[:self.config.max_articles_per_api],
                sources_count=len(unique_sources),
                total_results=len(articles),
                success=True,
            )

        except httpx.HTTPStatusError as e:
            return RetrievalResult(
                articles=[],
                sources_count=0,
                total_results=0,
                success=False,
                error=f"Currents HTTP error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            return RetrievalResult(
                articles=[],
                sources_count=0,
                total_results=0,
                success=False,
                error=f"Currents request error: {str(e)}",
            )
