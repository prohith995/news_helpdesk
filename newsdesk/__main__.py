"""CLI entrypoint for News Intelligence Desk.

Usage:
    python -m newsdesk "How is the AI regulation debate being framed differently?"
    python -m newsdesk "Is it true that X company laid off 10,000 employees?"
"""

import argparse
import json
import sys
import time
from pathlib import Path

from .config import get_config
from .schemas import Query, Report, WorkflowResult, WorkflowType, AbstentionReason, Confidence
from .router import classify_query
from .workflows import run_framing_divergence


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="newsdesk",
        description="News Intelligence Desk - Deterministic news analysis workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Framing Divergence:
    python -m newsdesk "How is the AI regulation debate being framed?"

  Claim Check:
    python -m newsdesk "Is it true that Tesla recalled 2 million vehicles?"

Output:
  Results are written to ./output/output.json and ./output/report.md
        """,
    )

    parser.add_argument(
        "query",
        type=str,
        help="The news query to analyze",
    )

    parser.add_argument(
        "--workflow",
        "-w",
        type=str,
        choices=["auto", "framing", "claim"],
        default="auto",
        help="Force a specific workflow (default: auto-detect)",
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Output directory (default: ./output)",
    )

    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug output",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )

    return parser


def run_pipeline(query: Query, workflow_override: str | None = None, debug: bool = False) -> WorkflowResult:
    """Execute the full analysis pipeline.

    This is the main orchestration function. LLM is used for:
    - Query classification (router)
    - Framing extraction
    - Claim parsing

    All control flow decisions are made by this code, not the LLM.
    """
    start_time = time.time()

    # Step 1: Classify query (or use override)
    if workflow_override == "framing":
        workflow_type = WorkflowType.FRAMING_DIVERGENCE
        classification_reasoning = "Workflow manually set to framing"
    elif workflow_override == "claim":
        workflow_type = WorkflowType.CLAIM_CHECK
        classification_reasoning = "Workflow manually set to claim"
    else:
        # Use LLM-based classification
        if debug:
            print("[DEBUG] Classifying query...")

        classification = classify_query(query)

        if debug:
            print(f"[DEBUG] Classification: {classification.workflow_type.value}")
            print(f"[DEBUG] Confidence: {classification.confidence:.2f}")
            print(f"[DEBUG] Reasoning: {classification.reasoning}")

        if not classification.success:
            # Classification failed or query is ambiguous - abstain
            return WorkflowResult(
                workflow_type=classification.workflow_type,
                query=query,
                success=False,
                abstained=True,
                abstention_reason=classification.abstention_reason,
                abstention_details=classification.abstention_details,
                execution_time_seconds=time.time() - start_time,
            )

        workflow_type = classification.workflow_type
        classification_reasoning = classification.reasoning

    # Step 2: Execute the appropriate workflow
    if workflow_type == WorkflowType.FRAMING_DIVERGENCE:
        if debug:
            print("[DEBUG] Running Framing Divergence workflow...")
        return run_framing_divergence(query, debug)

    elif workflow_type == WorkflowType.CLAIM_CHECK:
        # TODO Phase 5: Implement claim check workflow
        return WorkflowResult(
            workflow_type=workflow_type,
            query=query,
            success=False,
            abstained=True,
            abstention_reason=AbstentionReason.NO_RELEVANT_ARTICLES,
            abstention_details=f"Claim Check workflow not yet implemented.",
            execution_time_seconds=time.time() - start_time,
        )

    else:
        return WorkflowResult(
            workflow_type=workflow_type,
            query=query,
            success=False,
            abstained=True,
            abstention_reason=AbstentionReason.QUERY_AMBIGUOUS,
            abstention_details=f"Unknown workflow type: {workflow_type.value}",
            execution_time_seconds=time.time() - start_time,
        )


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Initialize config
    config = get_config()
    if args.debug:
        config.debug = True
    if args.output_dir:
        config.output_dir = args.output_dir
        config.output_dir.mkdir(parents=True, exist_ok=True)

    # Parse query
    try:
        query = Query(raw_text=args.query)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if config.debug:
        print(f"[DEBUG] Query: {query.raw_text}")
        print(f"[DEBUG] Workflow override: {args.workflow}")

    if args.dry_run:
        print(f"Would analyze: {query.raw_text}")
        print(f"Workflow: {args.workflow}")
        sys.exit(0)

    # Run pipeline
    print(f"Analyzing: {query.raw_text}")
    print("-" * 50)

    workflow_override = None if args.workflow == "auto" else args.workflow
    result = run_pipeline(query, workflow_override, debug=config.debug)

    # Generate report
    report = Report(result=result)

    # Write outputs
    output_json_path = config.output_dir / "output.json"
    output_md_path = config.output_dir / "report.md"

    with open(output_json_path, "w") as f:
        json.dump(report.to_json(), f, indent=2)

    with open(output_md_path, "w") as f:
        f.write(report.to_markdown())

    # Print summary to console
    print(report.to_markdown())
    print()
    print(f"Output written to: {output_json_path}")
    print(f"Report written to: {output_md_path}")

    # Exit with appropriate code
    if result.abstained:
        sys.exit(2)  # Abstention
    elif not result.success:
        sys.exit(1)  # Failure
    else:
        sys.exit(0)  # Success


if __name__ == "__main__":
    main()
