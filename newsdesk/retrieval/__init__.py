"""News retrieval module - fetches articles from various sources."""

from .client import NewsAPIClient, RetrievalResult, search_news

__all__ = ["NewsAPIClient", "RetrievalResult", "search_news"]
