"""Claim Check Workflow.

Verifies factual claims by searching for evidence in news sources.
This workflow:
1. Extracts the specific claim from the user query
2. Searches for relevant articles
3. Uses LLM to extract supporting/contradicting evidence
4. Aggregates evidence and assesses claim veracity
5. Generates a verdict with citations and confidence

All control flow is deterministic; LLM is only used for extraction.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..config import get_config
from ..llm import LLMClient
from ..retrieval import search_news, RetrievalResult
from ..retrieval.mock import get_mock_articles_claim
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


class EvidenceType(Enum):
    """Type of evidence found."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    IRRELEVANT = "irrelevant"


class Verdict(Enum):
    """Claim verification verdict."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    MIXED = "mixed"
    UNVERIFIABLE = "unverifiable"


@dataclass
class Evidence:
    """Evidence extracted from an article."""
    article: Article
    evidence_type: EvidenceType
    relevant_text: str
    confidence: float  # How confident we are this is relevant


@dataclass
class ClaimCheckResult:
    """Result of claim verification."""
    claim: str
    verdict: Verdict
    evidence_for: list[Evidence]
    evidence_against: list[Evidence]
    summary: str


CLAIM_EXTRACTION_PROMPT = """Extract the specific factual claim to verify from this query.

Query: {query}

Respond with ONLY a JSON object:
{{
    "claim": "<the specific factual claim to verify>",
    "search_terms": ["<term1>", "<term2>", ...],
    "claim_type": "<numeric|event|statement|other>"
}}

Examples:
- "Is it true that Tesla recalled 2 million vehicles?" -> claim: "Tesla recalled 2 million vehicles"
- "Did OpenAI raise $10 billion from Microsoft?" -> claim: "OpenAI raised $10 billion from Microsoft"
"""


EVIDENCE_EXTRACTION_PROMPT = """Analyze if this article provides evidence for or against the claim.

Claim to verify: "{claim}"

Article from {source}:
Title: {title}
Content: {content}

Respond with ONLY a JSON object:
{{
    "evidence_type": "<supports|contradicts|neutral|irrelevant>",
    "relevant_text": "<direct quote or close paraphrase that is evidence>",
    "explanation": "<why this supports/contradicts the claim>",
    "confidence": <0.0 to 1.0>
}}

Guidelines:
- "supports" = article confirms the claim is true
- "contradicts" = article suggests the claim is false or different
- "neutral" = article discusses the topic but doesn't confirm or deny
- "irrelevant" = article is not about this claim
"""


VERDICT_PROMPT = """Based on the evidence, determine the verdict for this claim.

Claim: "{claim}"

Supporting evidence ({num_for}):
{evidence_for}

Contradicting evidence ({num_against}):
{evidence_against}

Respond with ONLY a JSON object:
{{
    "verdict": "<supported|contradicted|mixed|unverifiable>",
    "summary": "<2-3 sentence summary of findings>",
    "confidence": <0.0 to 1.0>
}}

Guidelines:
- "supported" = strong evidence confirms the claim
- "contradicted" = strong evidence refutes the claim
- "mixed" = evidence is conflicting or partial
- "unverifiable" = insufficient evidence to make determination
"""


class ClaimCheckWorkflow:
    """Workflow for verifying factual claims."""

    def __init__(self, llm_client: LLMClient | None = None, use_mock: bool = False):
        self.llm = llm_client or LLMClient()
        self.config = get_config()
        self.use_mock = use_mock or not self.config.news.newsapi_key

    def extract_claim(self, query: Query) -> tuple[str, list[str]] | None:
        """Extract the specific claim to verify from user query.

        Returns:
            Tuple of (claim, search_terms) or None if extraction fails
        """
        response = self.llm.call_with_schema(
            prompt=CLAIM_EXTRACTION_PROMPT.format(query=query.raw_text),
            system="You are an expert fact-checker who identifies specific verifiable claims.",
            expected_fields=["claim", "search_terms"],
        )

        if not response.success:
            return None

        data = response.parsed_data
        return data.get("claim", ""), data.get("search_terms", [])

    def fetch_articles(self, search_terms: list[str]) -> RetrievalResult:
        """Fetch articles relevant to the claim."""
        if self.use_mock:
            articles = get_mock_articles_claim(" ".join(search_terms))
            unique_sources = set(a.source.name for a in articles)
            return RetrievalResult(
                articles=articles,
                sources_count=len(unique_sources),
                total_results=len(articles),
                success=True,
            )

        # Search using the first few terms
        query = " ".join(search_terms[:3])
        return search_news(query)

    def extract_evidence(self, article: Article, claim: str) -> Evidence | None:
        """Extract evidence from an article regarding the claim."""
        content = article.content or article.snippet or ""
        if not content:
            return None

        response = self.llm.call_with_schema(
            prompt=EVIDENCE_EXTRACTION_PROMPT.format(
                claim=claim,
                source=article.source.name,
                title=article.title,
                content=content[:2000],
            ),
            system="You are an expert fact-checker who evaluates evidence objectively.",
            expected_fields=["evidence_type", "relevant_text", "confidence"],
        )

        if not response.success:
            return None

        data = response.parsed_data
        evidence_type_str = data.get("evidence_type", "irrelevant").lower()

        try:
            evidence_type = EvidenceType(evidence_type_str)
        except ValueError:
            evidence_type = EvidenceType.IRRELEVANT

        return Evidence(
            article=article,
            evidence_type=evidence_type,
            relevant_text=data.get("relevant_text", ""),
            confidence=float(data.get("confidence", 0.5)),
        )

    def determine_verdict(
        self,
        claim: str,
        evidence_for: list[Evidence],
        evidence_against: list[Evidence],
    ) -> tuple[Verdict, str, float] | None:
        """Determine the final verdict based on collected evidence."""
        # Format evidence for prompt
        for_text = "\n".join([
            f"- [{e.article.source.name}]: {e.relevant_text}"
            for e in evidence_for
        ]) or "None"

        against_text = "\n".join([
            f"- [{e.article.source.name}]: {e.relevant_text}"
            for e in evidence_against
        ]) or "None"

        response = self.llm.call_with_schema(
            prompt=VERDICT_PROMPT.format(
                claim=claim,
                num_for=len(evidence_for),
                num_against=len(evidence_against),
                evidence_for=for_text,
                evidence_against=against_text,
            ),
            system="You are an expert fact-checker who makes fair, evidence-based judgments.",
            expected_fields=["verdict", "summary", "confidence"],
        )

        if not response.success:
            return None

        data = response.parsed_data
        verdict_str = data.get("verdict", "unverifiable").lower()

        try:
            verdict = Verdict(verdict_str)
        except ValueError:
            verdict = Verdict.UNVERIFIABLE

        return verdict, data.get("summary", ""), float(data.get("confidence", 0.5))

    def run(self, query: Query, debug: bool = False) -> WorkflowResult:
        """Execute the claim check workflow.

        Args:
            query: The user query containing a claim
            debug: Whether to print debug info

        Returns:
            WorkflowResult with verification or abstention
        """
        start_time = time.time()

        # Step 1: Extract claim
        if debug:
            print("[DEBUG] Extracting claim from query...")

        claim_result = self.extract_claim(query)
        if not claim_result:
            return WorkflowResult(
                workflow_type=WorkflowType.CLAIM_CHECK,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=AbstentionReason.LLM_OUTPUT_INVALID,
                abstention_details="Failed to extract claim from query.",
                execution_time_seconds=time.time() - start_time,
            )

        claim, search_terms = claim_result
        if debug:
            print(f"[DEBUG] Claim: {claim}")
            print(f"[DEBUG] Search terms: {search_terms}")

        # Step 2: Fetch articles
        if debug:
            print("[DEBUG] Fetching articles...")

        retrieval = self.fetch_articles(search_terms)
        if not retrieval.success:
            return WorkflowResult(
                workflow_type=WorkflowType.CLAIM_CHECK,
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
                workflow_type=WorkflowType.CLAIM_CHECK,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=gate_result.abstention_reason,
                abstention_details=gate_result.details,
                articles_analyzed=len(retrieval.articles),
                sources_count=retrieval.sources_count,
                execution_time_seconds=time.time() - start_time,
            )

        # Step 4: Extract evidence from each article
        if debug:
            print("[DEBUG] Extracting evidence...")

        evidence_for: list[Evidence] = []
        evidence_against: list[Evidence] = []
        neutral_evidence: list[Evidence] = []

        for article in retrieval.articles:
            evidence = self.extract_evidence(article, claim)
            if evidence:
                if debug:
                    print(f"[DEBUG]   {evidence.article.source.name}: {evidence.evidence_type.value}")

                if evidence.evidence_type == EvidenceType.SUPPORTS:
                    evidence_for.append(evidence)
                elif evidence.evidence_type == EvidenceType.CONTRADICTS:
                    evidence_against.append(evidence)
                elif evidence.evidence_type == EvidenceType.NEUTRAL:
                    neutral_evidence.append(evidence)

        # Check if we have enough evidence
        total_relevant = len(evidence_for) + len(evidence_against)
        if total_relevant == 0:
            return WorkflowResult(
                workflow_type=WorkflowType.CLAIM_CHECK,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=AbstentionReason.CLAIM_NOT_VERIFIABLE,
                abstention_details=f"No relevant evidence found for claim: '{claim}'. "
                                  f"Found {len(neutral_evidence)} neutral mentions.",
                articles_analyzed=len(retrieval.articles),
                sources_count=retrieval.sources_count,
                execution_time_seconds=time.time() - start_time,
            )

        # Step 5: Determine verdict
        if debug:
            print("[DEBUG] Determining verdict...")

        verdict_result = self.determine_verdict(claim, evidence_for, evidence_against)
        if not verdict_result:
            return WorkflowResult(
                workflow_type=WorkflowType.CLAIM_CHECK,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=AbstentionReason.LLM_OUTPUT_INVALID,
                abstention_details="Failed to determine verdict from evidence.",
                articles_analyzed=len(retrieval.articles),
                sources_count=retrieval.sources_count,
                execution_time_seconds=time.time() - start_time,
            )

        verdict, summary, verdict_confidence = verdict_result

        if debug:
            print(f"[DEBUG] Verdict: {verdict.value} ({verdict_confidence:.0%})")

        # Step 6: Build citations (prioritize relevant evidence)
        all_evidence = evidence_for + evidence_against
        citations = [
            Citation(
                article=e.article,
                relevant_quote=e.relevant_text,
                relevance_score=e.confidence,
            )
            for e in sorted(all_evidence, key=lambda x: x.confidence, reverse=True)
        ]

        # Step 7: Calculate confidence
        source_factor = min(1.0, total_relevant / 4)  # Max out at 4 relevant sources
        agreement_factor = 1.0 if verdict != Verdict.MIXED else 0.7

        confidence_score = verdict_confidence * (source_factor * 0.5 + agreement_factor * 0.5)

        limiting_factors = []
        if total_relevant < 4:
            limiting_factors.append(f"Limited to {total_relevant} relevant sources")
        if verdict == Verdict.MIXED:
            limiting_factors.append("Evidence is conflicting")
        if self.use_mock:
            limiting_factors.append("Using mock data (no NewsAPI key)")
            confidence_score *= 0.5

        confidence = Confidence(
            score=min(1.0, confidence_score),
            reasoning=summary,
            limiting_factors=limiting_factors,
        )

        # Step 8: Build result data
        result_data = {
            "claim": claim,
            "verdict": verdict.value,
            "summary": summary,
            "evidence_for": [
                {
                    "source": e.article.source.name,
                    "quote": e.relevant_text,
                    "confidence": e.confidence,
                }
                for e in evidence_for
            ],
            "evidence_against": [
                {
                    "source": e.article.source.name,
                    "quote": e.relevant_text,
                    "confidence": e.confidence,
                }
                for e in evidence_against
            ],
            "sources_supporting": len(evidence_for),
            "sources_contradicting": len(evidence_against),
            "sources_neutral": len(neutral_evidence),
        }

        return WorkflowResult(
            workflow_type=WorkflowType.CLAIM_CHECK,
            query=query,
            success=True,
            data=result_data,
            citations=citations,
            confidence=confidence,
            articles_analyzed=len(retrieval.articles),
            sources_count=retrieval.sources_count,
            execution_time_seconds=time.time() - start_time,
        )


def run_claim_check(query: Query, debug: bool = False) -> WorkflowResult:
    """Convenience function to run the claim check workflow."""
    workflow = ClaimCheckWorkflow()
    return workflow.run(query, debug)
