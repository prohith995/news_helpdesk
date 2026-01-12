"""LLM client with typed schema validation and retry logic.

This module wraps the Anthropic API and enforces typed outputs.
Invalid outputs trigger one retry, then abstention.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, TypeVar, Type

from anthropic import Anthropic

from ..config import get_config, LLMConfig


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    raw_text: str
    parsed_data: dict | None = None
    success: bool = False
    error: str | None = None
    retries_used: int = 0


T = TypeVar("T")


class LLMClient:
    """LLM client with schema validation and retry logic."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or get_config().llm
        self._client: Anthropic | None = None

    @property
    def client(self) -> Anthropic:
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            self._client = Anthropic(api_key=self.config.api_key)
        return self._client

    def extract_json(self, text: str) -> dict | None:
        """Extract JSON from LLM response text.

        Handles:
        - Raw JSON
        - JSON in markdown code blocks
        - JSON with trailing text
        """
        # Try to find JSON in code blocks first
        code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
        matches = re.findall(code_block_pattern, text)
        if matches:
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

        # Try to parse the entire response as JSON
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        brace_pattern = r"\{[\s\S]*\}"
        matches = re.findall(brace_pattern, text)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        return None

    def call_with_schema(
        self,
        prompt: str,
        system: str,
        expected_fields: list[str],
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Call LLM and validate response against expected fields.

        Args:
            prompt: The user prompt
            system: System prompt
            expected_fields: List of required field names in response
            temperature: Sampling temperature (0.0 for deterministic)

        Returns:
            LLMResponse with success=True if valid, or error details
        """
        retries = 0
        last_error = None

        while retries <= self.config.max_retries:
            try:
                response = self.client.messages.create(
                    model=self.config.model,
                    max_tokens=1024,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )

                raw_text = response.content[0].text
                parsed = self.extract_json(raw_text)

                if parsed is None:
                    last_error = "Failed to parse JSON from response"
                    retries += 1
                    continue

                # Validate expected fields
                missing = [f for f in expected_fields if f not in parsed]
                if missing:
                    last_error = f"Missing required fields: {missing}"
                    retries += 1
                    continue

                # Success
                return LLMResponse(
                    raw_text=raw_text,
                    parsed_data=parsed,
                    success=True,
                    retries_used=retries,
                )

            except Exception as e:
                last_error = str(e)
                retries += 1

        # All retries exhausted
        return LLMResponse(
            raw_text="",
            parsed_data=None,
            success=False,
            error=last_error,
            retries_used=retries,
        )

    def classify(
        self,
        text: str,
        categories: list[str],
        context: str = "",
    ) -> LLMResponse:
        """Classify text into one of the given categories.

        Args:
            text: Text to classify
            categories: List of valid category names
            context: Additional context for classification

        Returns:
            LLMResponse with parsed_data containing 'category' and 'confidence'
        """
        system = f"""You are a text classifier. Classify the input into exactly one of these categories: {', '.join(categories)}.

{context}

Respond with ONLY a JSON object in this exact format:
{{
    "category": "<one of the categories>",
    "confidence": <0.0 to 1.0>,
    "reasoning": "<brief explanation>"
}}"""

        prompt = f"Classify this text:\n\n{text}"

        return self.call_with_schema(
            prompt=prompt,
            system=system,
            expected_fields=["category", "confidence", "reasoning"],
        )
