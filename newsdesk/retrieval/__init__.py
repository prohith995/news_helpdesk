"""News retrieval module - fetches articles from various sources."""

from .client import NewsAPIClient, RetrievalResult, search_news
from .gnews import GNewsClient
from .currents import CurrentsClient
from .aggregator import NewsAggregator, search_news_multi

__all__ = [
    "NewsAPIClient",
    "GNewsClient",
    "CurrentsClient",
    "NewsAggregator",
    "RetrievalResult",
    "search_news",
    "search_news_multi",
]
