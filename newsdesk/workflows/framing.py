"""Framing Divergence Workflow.

Analyzes how different news sources frame the same topic differently.
This workflow:
1. Extracts the topic from the user query
2. Fetches articles from multiple sources
3. Uses LLM to extract framing/stance from each source
4. Clusters similar framings
5. Generates a divergence report with citations

All control flow is deterministic; LLM is only used for extraction.
"""

import time
from dataclasses import dataclass
from typing import Optional

from ..config import get_config
from ..llm import LLMClient, LLMResponse
from ..retrieval import search_news, RetrievalResult
from ..retrieval.mock import get_mock_articles_framing
from ..schemas import (
    Query,
    Article,
    Citation,
    Confidence,
    WorkflowResult,
    WorkflowType,
    AbstentionReason,
)
from ..verification import run_retrieval_gates


@dataclass
class SourceFraming:
    """Extracted framing from a single source."""
    source_name: str
    stance: str  # e.g., "supportive", "critical", "neutral"
    key_frame: str  # The main framing/narrative
    supporting_quote: str
    article: Article


@dataclass
class FramingCluster:
    """A cluster of similar framings."""
    label: str  # e.g., "Pro-regulation", "Industry-friendly"
    sources: list[str]
    common_themes: list[str]
    representative_quote: str


TOPIC_EXTRACTION_PROMPT = """Extract the main topic from this query for news search.

Query: {query}

Respond with ONLY a JSON object:
{{
    "topic": "<concise search topic, 2-5 words>",
    "keywords": ["<keyword1>", "<keyword2>", ...]
}}"""


FRAMING_EXTRACTION_PROMPT = """Analyze how this news article frames the topic "{topic}".

Article from {source}:
Title: {title}
Content: {content}

Respond with ONLY a JSON object:
{{
    "stance": "<supportive|critical|neutral|mixed>",
    "key_frame": "<one sentence describing the main narrative/angle>",
    "supporting_quote": "<a direct quote or close paraphrase that exemplifies the framing>",
    "confidence": <0.0 to 1.0>
}}"""


CLUSTERING_PROMPT = """Group these source framings into 2-4 clusters based on similarity.

Framings:
{framings_text}

Respond with ONLY a JSON object:
{{
    "clusters": [
        {{
            "label": "<descriptive label for this perspective>",
            "sources": ["<source1>", "<source2>"],
            "common_themes": ["<theme1>", "<theme2>"],
            "representative_quote": "<quote that best represents this cluster>"
        }}
    ],
    "divergence_summary": "<2-3 sentences describing the key differences between clusters>"
}}"""


class FramingDivergenceWorkflow:
    """Workflow for analyzing framing divergence across sources."""

    def __init__(self, llm_client: LLMClient | None = None, use_mock: bool = False):
        self.llm = llm_client or LLMClient()
        self.config = get_config()
        self.use_mock = use_mock or not self.config.news.newsapi_key

    def extract_topic(self, query: Query) -> tuple[str, list[str]] | None:
        """Extract the searchable topic from a user query.

        Returns:
            Tuple of (topic, keywords) or None if extraction fails
        """
        response = self.llm.call_with_schema(
            prompt=TOPIC_EXTRACTION_PROMPT.format(query=query.raw_text),
            system="You are a helpful assistant that extracts search topics from queries.",
            expected_fields=["topic", "keywords"],
        )

        if not response.success:
            return None

        data = response.parsed_data
        return data.get("topic", ""), data.get("keywords", [])

    def fetch_articles(self, topic: str) -> RetrievalResult:
        """Fetch articles for the topic."""
        if self.use_mock:
            articles = get_mock_articles_framing(topic)
            unique_sources = set(a.source.name for a in articles)
            return RetrievalResult(
                articles=articles,
                sources_count=len(unique_sources),
                total_results=len(articles),
                success=True,
            )

        return search_news(topic)

    def extract_framing(self, article: Article, topic: str) -> SourceFraming | None:
        """Extract framing from a single article using LLM."""
        content = article.content or article.snippet or ""
        if not content:
            return None

        response = self.llm.call_with_schema(
            prompt=FRAMING_EXTRACTION_PROMPT.format(
                topic=topic,
                source=article.source.name,
                title=article.title,
                content=content[:2000],  # Limit content length
            ),
            system="You are an expert media analyst who identifies framing and bias in news coverage.",
            expected_fields=["stance", "key_frame", "supporting_quote", "confidence"],
        )

        if not response.success:
            return None

        data = response.parsed_data
        return SourceFraming(
            source_name=article.source.name,
            stance=data.get("stance", "neutral"),
            key_frame=data.get("key_frame", ""),
            supporting_quote=data.get("supporting_quote", ""),
            article=article,
        )

    def cluster_framings(self, framings: list[SourceFraming]) -> tuple[list[FramingCluster], str] | None:
        """Cluster similar framings and identify divergence."""
        if len(framings) < 2:
            return None

        # Prepare framings text for LLM
        framings_text = "\n".join([
            f"- {f.source_name}: [{f.stance}] {f.key_frame}"
            for f in framings
        ])

        response = self.llm.call_with_schema(
            prompt=CLUSTERING_PROMPT.format(framings_text=framings_text),
            system="You are an expert at identifying patterns and grouping similar perspectives.",
            expected_fields=["clusters", "divergence_summary"],
        )

        if not response.success:
            return None

        data = response.parsed_data
        clusters = []
        for c in data.get("clusters", []):
            clusters.append(FramingCluster(
                label=c.get("label", "Unknown"),
                sources=c.get("sources", []),
                common_themes=c.get("common_themes", []),
                representative_quote=c.get("representative_quote", ""),
            ))

        return clusters, data.get("divergence_summary", "")

    def run(self, query: Query, debug: bool = False) -> WorkflowResult:
        """Execute the framing divergence workflow.

        Args:
            query: The user query
            debug: Whether to print debug info

        Returns:
            WorkflowResult with analysis or abstention
        """
        start_time = time.time()

        # Step 1: Extract topic
        if debug:
            print("[DEBUG] Extracting topic from query...")

        topic_result = self.extract_topic(query)
        if not topic_result:
            return WorkflowResult(
                workflow_type=WorkflowType.FRAMING_DIVERGENCE,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=AbstentionReason.LLM_OUTPUT_INVALID,
                abstention_details="Failed to extract topic from query.",
                execution_time_seconds=time.time() - start_time,
            )

        topic, keywords = topic_result
        if debug:
            print(f"[DEBUG] Topic: {topic}, Keywords: {keywords}")

        # Step 2: Fetch articles
        if debug:
            print("[DEBUG] Fetching articles...")

        retrieval = self.fetch_articles(topic)
        if not retrieval.success:
            return WorkflowResult(
                workflow_type=WorkflowType.FRAMING_DIVERGENCE,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=AbstentionReason.NO_RELEVANT_ARTICLES,
                abstention_details=retrieval.error or "Failed to fetch articles.",
                execution_time_seconds=time.time() - start_time,
            )

        if debug:
            print(f"[DEBUG] Found {len(retrieval.articles)} articles from {retrieval.sources_count} sources")

        # Step 3: Verification gate
        gate_result = run_retrieval_gates(retrieval.articles)
        if not gate_result.passed:
            return WorkflowResult(
                workflow_type=WorkflowType.FRAMING_DIVERGENCE,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=gate_result.abstention_reason,
                abstention_details=gate_result.details,
                articles_analyzed=len(retrieval.articles),
                sources_count=retrieval.sources_count,
                execution_time_seconds=time.time() - start_time,
            )

        # Step 4: Extract framing from each article
        if debug:
            print("[DEBUG] Extracting framings...")

        framings: list[SourceFraming] = []
        for article in retrieval.articles:
            framing = self.extract_framing(article, topic)
            if framing:
                framings.append(framing)
                if debug:
                    print(f"[DEBUG]   {framing.source_name}: {framing.stance}")

        if len(framings) < 2:
            return WorkflowResult(
                workflow_type=WorkflowType.FRAMING_DIVERGENCE,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=AbstentionReason.INSUFFICIENT_SOURCES,
                abstention_details=f"Only extracted framings from {len(framings)} sources. Need at least 2.",
                articles_analyzed=len(retrieval.articles),
                sources_count=retrieval.sources_count,
                execution_time_seconds=time.time() - start_time,
            )

        # Step 5: Cluster framings
        if debug:
            print("[DEBUG] Clustering framings...")

        cluster_result = self.cluster_framings(framings)
        if not cluster_result:
            return WorkflowResult(
                workflow_type=WorkflowType.FRAMING_DIVERGENCE,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=AbstentionReason.CLUSTERING_UNSTABLE,
                abstention_details="Failed to cluster framings into coherent groups.",
                articles_analyzed=len(retrieval.articles),
                sources_count=retrieval.sources_count,
                execution_time_seconds=time.time() - start_time,
            )

        clusters, divergence_summary = cluster_result

        # Step 6: Build citations
        citations = [
            Citation(
                article=f.article,
                relevant_quote=f.supporting_quote,
                relevance_score=0.8,  # Could be refined based on framing confidence
            )
            for f in framings
        ]

        # Step 7: Calculate confidence
        # Higher confidence with more sources and clearer clustering
        source_factor = min(1.0, len(framings) / 5)  # Max out at 5 sources
        cluster_factor = 1.0 if len(clusters) >= 2 else 0.7  # Penalize if only 1 cluster
        confidence_score = (source_factor * 0.6 + cluster_factor * 0.4)

        limiting_factors = []
        if len(framings) < 5:
            limiting_factors.append(f"Limited to {len(framings)} sources")
        if self.use_mock:
            limiting_factors.append("Using mock data (no NewsAPI key)")
            confidence_score *= 0.5  # Reduce confidence for mock data

        confidence = Confidence(
            score=confidence_score,
            reasoning=f"Analysis based on {len(framings)} sources across {len(clusters)} distinct perspectives.",
            limiting_factors=limiting_factors,
        )

        # Step 8: Build result data
        result_data = {
            "topic": topic,
            "framings": [
                {
                    "source": f.source_name,
                    "stance": f.stance,
                    "key_frame": f.key_frame,
                }
                for f in framings
            ],
            "clusters": [
                {
                    "label": c.label,
                    "sources": c.sources,
                    "common_themes": c.common_themes,
                }
                for c in clusters
            ],
            "divergence_summary": divergence_summary,
        }

        return WorkflowResult(
            workflow_type=WorkflowType.FRAMING_DIVERGENCE,
            query=query,
            success=True,
            data=result_data,
            citations=citations,
            confidence=confidence,
            articles_analyzed=len(retrieval.articles),
            sources_count=retrieval.sources_count,
            execution_time_seconds=time.time() - start_time,
        )


def run_framing_divergence(query: Query, debug: bool = False) -> WorkflowResult:
    """Convenience function to run the framing divergence workflow."""
    workflow = FramingDivergenceWorkflow()
    return workflow.run(query, debug)
