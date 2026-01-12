#!/bin/bash
# Demo: Framing Divergence Workflow
# Shows how different sources frame the same topic

echo "=== News Intelligence Desk - Framing Divergence Demo ==="
echo ""
echo "Query: How is the AI regulation debate being framed by different outlets?"
echo ""

python -m newsdesk "How is the AI regulation debate being framed by different outlets?"

echo ""
echo "=== Demo Complete ==="
echo "See output/output.json for structured data"
echo "See output/report.md for formatted report"
