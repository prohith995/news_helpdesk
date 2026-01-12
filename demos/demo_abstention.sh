#!/bin/bash
# Demo: Abstention Scenario
# Shows how the system gracefully abstains when it cannot provide a reliable answer

echo "=== News Intelligence Desk - Abstention Demo ==="
echo ""
echo "This demo shows THREE scenarios that trigger abstention:"
echo ""

echo "--- Scenario 1: Non-news query ---"
echo "Query: What is the weather like today?"
python -m newsdesk "What is the weather like today?" 2>&1 | tail -15
echo ""

echo "--- Scenario 2: Unverifiable claim (mock data doesn't match) ---"
echo "Query: Is it true that OpenAI laid off 10,000 employees?"
python -m newsdesk "Is it true that OpenAI laid off 10,000 employees?" 2>&1 | tail -15
echo ""

echo "--- Scenario 3: Ambiguous query ---"
echo "Query: Tell me about technology"
python -m newsdesk "Tell me about technology" 2>&1 | tail -15
echo ""

echo "=== Abstention Demo Complete ==="
echo ""
echo "The system abstains rather than hallucinate when:"
echo "  - Query doesn't match any supported workflow"
echo "  - Insufficient evidence to verify a claim"
echo "  - Query is too ambiguous"
echo "  - Source diversity is too low"
