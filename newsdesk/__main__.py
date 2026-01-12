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


def run_pipeline(query: Query, workflow_override: str | None = None) -> WorkflowResult:
    """Execute the full analysis pipeline.

    This is the main orchestration function. LLM is used for:
    - Query classification (router)
    - Framing extraction
    - Claim parsing

    All control flow decisions are made by this code, not the LLM.
    """
    start_time = time.time()

    # TODO Phase 2: Implement router
    # For now, return a placeholder result
    workflow_type = WorkflowType.UNKNOWN
    if workflow_override == "framing":
        workflow_type = WorkflowType.FRAMING_DIVERGENCE
    elif workflow_override == "claim":
        workflow_type = WorkflowType.CLAIM_CHECK

    # Placeholder: abstain because not implemented yet
    result = WorkflowResult(
        workflow_type=workflow_type,
        query=query,
        success=False,
        abstained=True,
        abstention_reason=AbstentionReason.QUERY_AMBIGUOUS,
        abstention_details="Pipeline not yet implemented. Phase 1 skeleton only.",
        execution_time_seconds=time.time() - start_time,
    )

    return result


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
    result = run_pipeline(query, workflow_override)

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
