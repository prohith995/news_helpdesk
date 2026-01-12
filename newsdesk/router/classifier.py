"""Query classifier - routes queries to appropriate workflows.

This module uses LLM for semantic classification only.
All control flow decisions are made by code based on the classification result.
"""

from dataclasses import dataclass
from typing import Optional

from ..schemas import Query, WorkflowType, AbstentionReason
from ..llm import LLMClient


@dataclass
class ClassificationResult:
    """Result of query classification."""
    workflow_type: WorkflowType
    confidence: float
    reasoning: str
    success: bool = True
    abstention_reason: Optional[AbstentionReason] = None
    abstention_details: Optional[str] = None


# Classification context explaining each workflow
CLASSIFICATION_CONTEXT = """
Workflow descriptions:

1. FRAMING_DIVERGENCE: Use when the user wants to understand how different news sources are covering/framing the same topic differently. Keywords: "how is X being framed", "different perspectives on", "media coverage of", "how are outlets covering", "narrative around".

2. CLAIM_CHECK: Use when the user wants to verify a specific factual claim. Keywords: "is it true that", "did X really", "verify that", "fact check", "is X accurate".

3. UNKNOWN: Use when the query doesn't clearly fit either workflow, or is not a news-related query.

Be strict: if the query is ambiguous or doesn't clearly match a workflow, classify as UNKNOWN.
"""


class QueryClassifier:
    """Classifies queries into workflow types using LLM."""

    WORKFLOW_CATEGORIES = ["FRAMING_DIVERGENCE", "CLAIM_CHECK", "UNKNOWN"]

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    def classify(self, query: Query) -> ClassificationResult:
        """Classify a query into a workflow type.

        Uses LLM for classification with retry logic.
        On failure, returns UNKNOWN with abstention reason.
        """
        response = self.llm.classify(
            text=query.raw_text,
            categories=self.WORKFLOW_CATEGORIES,
            context=CLASSIFICATION_CONTEXT,
        )

        if not response.success:
            return ClassificationResult(
                workflow_type=WorkflowType.UNKNOWN,
                confidence=0.0,
                reasoning="Classification failed",
                success=False,
                abstention_reason=AbstentionReason.LLM_OUTPUT_INVALID,
                abstention_details=f"LLM classification failed after retries: {response.error}",
            )

        data = response.parsed_data
        category = data.get("category", "UNKNOWN").upper()
        confidence = float(data.get("confidence", 0.0))
        reasoning = data.get("reasoning", "")

        # Validate category
        if category not in self.WORKFLOW_CATEGORIES:
            category = "UNKNOWN"

        # Map to enum
        workflow_map = {
            "FRAMING_DIVERGENCE": WorkflowType.FRAMING_DIVERGENCE,
            "CLAIM_CHECK": WorkflowType.CLAIM_CHECK,
            "UNKNOWN": WorkflowType.UNKNOWN,
        }
        workflow_type = workflow_map.get(category, WorkflowType.UNKNOWN)

        # If UNKNOWN, this is an abstention
        if workflow_type == WorkflowType.UNKNOWN:
            return ClassificationResult(
                workflow_type=workflow_type,
                confidence=confidence,
                reasoning=reasoning,
                success=False,
                abstention_reason=AbstentionReason.QUERY_AMBIGUOUS,
                abstention_details=f"Query does not clearly match any supported workflow. {reasoning}",
            )

        return ClassificationResult(
            workflow_type=workflow_type,
            confidence=confidence,
            reasoning=reasoning,
            success=True,
        )


def classify_query(query: Query, llm_client: LLMClient | None = None) -> ClassificationResult:
    """Convenience function to classify a query."""
    classifier = QueryClassifier(llm_client)
    return classifier.classify(query)
