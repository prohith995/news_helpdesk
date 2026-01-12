#!/bin/bash
# Demo: Claim Check Workflow
# Verifies a factual claim by analyzing evidence from multiple sources

echo "=== News Intelligence Desk - Claim Check Demo ==="
echo ""
echo "Query: Did the company confirm 10,000 layoffs in a restructuring?"
echo ""

python -m newsdesk "Did the company confirm 10,000 layoffs in a restructuring?"

echo ""
echo "=== Demo Complete ==="
echo "See output/output.json for structured data"
echo "See output/report.md for formatted report"
