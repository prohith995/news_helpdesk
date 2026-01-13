"""FastAPI application with SSE for real-time status updates."""

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..config import get_config, reset_config
from ..schemas import Query, Report, WorkflowType
from ..router import classify_query
from ..retrieval import search_news_multi
from ..verification import run_retrieval_gates
from ..workflows.framing import FramingDivergenceWorkflow
from ..workflows.claim_check import ClaimCheckWorkflow
from ..storage import HistoryStore, HistoryEntry, get_history_store


# Store for active analysis jobs
jobs: dict[str, dict] = {}


class AnalysisRequest(BaseModel):
    query: str


class AnalysisStatus(BaseModel):
    job_id: str
    status: str
    step: str
    progress: int  # 0-100
    message: str
    result: dict | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan handler."""
    reset_config()  # Ensure fresh config
    yield
    jobs.clear()


app = FastAPI(
    title="News Intelligence Desk",
    description="Deterministic news analysis with real-time status updates",
    lifespan=lifespan,
)

# Serve static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main UI."""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content="<h1>News Intelligence Desk</h1><p>Static files not found.</p>")


@app.post("/api/analyze")
async def start_analysis(request: AnalysisRequest):
    """Start a new analysis job."""
    job_id = str(uuid.uuid4())[:8]

    jobs[job_id] = {
        "status": "pending",
        "step": "queued",
        "progress": 0,
        "message": "Analysis queued",
        "query": request.query,
        "result": None,
        "created_at": datetime.now().isoformat(),
    }

    # Start background task
    asyncio.create_task(run_analysis(job_id, request.query))

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Get current status of a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/api/stream/{job_id}")
async def stream_status(job_id: str):
    """Stream status updates via SSE."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator() -> AsyncGenerator[dict, None]:
        last_status = None
        while True:
            if job_id not in jobs:
                break

            current = jobs[job_id]

            # Send update if status changed
            if current != last_status:
                last_status = current.copy()
                yield {
                    "event": "status",
                    "data": json.dumps(current),
                }

            # Stop if completed or failed
            if current["status"] in ("completed", "failed", "abstained"):
                break

            await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())


def update_job(job_id: str, step: str, progress: int, message: str, status: str = "running"):
    """Update job status."""
    if job_id in jobs:
        jobs[job_id].update({
            "status": status,
            "step": step,
            "progress": progress,
            "message": message,
        })


async def run_analysis(job_id: str, query_text: str):
    """Run the analysis pipeline with status updates."""
    try:
        start_time = time.time()

        # Step 1: Parse query
        update_job(job_id, "parsing", 5, "Parsing query...")
        await asyncio.sleep(0.1)  # Allow SSE to catch up

        try:
            query = Query(raw_text=query_text)
        except ValueError as e:
            update_job(job_id, "error", 0, str(e), status="failed")
            return

        # Step 2: Classify query
        update_job(job_id, "classifying", 15, "Classifying query type...")
        await asyncio.sleep(0.1)

        classification = await asyncio.to_thread(classify_query, query)

        if not classification.success:
            jobs[job_id]["result"] = {
                "success": False,
                "abstained": True,
                "reason": classification.abstention_reason.value if classification.abstention_reason else "unknown",
                "details": classification.abstention_details,
                "workflow": "unknown",
            }
            update_job(job_id, "abstained", 100, classification.abstention_details or "Query not supported", status="abstained")
            return

        workflow_type = classification.workflow_type
        update_job(job_id, "classified", 20, f"Detected: {workflow_type.value.replace('_', ' ').title()}")
        await asyncio.sleep(0.1)

        # Step 3: Fetch articles
        update_job(job_id, "fetching", 30, "Searching news sources...")
        await asyncio.sleep(0.1)

        # Extract topic/claim first
        if workflow_type == WorkflowType.FRAMING_DIVERGENCE:
            workflow = FramingDivergenceWorkflow()
            topic_result = await asyncio.to_thread(workflow.extract_topic, query)
            if not topic_result:
                update_job(job_id, "error", 0, "Failed to extract topic", status="failed")
                return
            topic, _ = topic_result
            search_query = topic
        else:
            workflow = ClaimCheckWorkflow()
            claim_result = await asyncio.to_thread(workflow.extract_claim, query)
            if not claim_result:
                update_job(job_id, "error", 0, "Failed to extract claim", status="failed")
                return
            claim, search_terms = claim_result
            search_query = " ".join(search_terms[:3])

        update_job(job_id, "fetching", 40, f"Searching for: {search_query[:50]}...")
        await asyncio.sleep(0.1)

        retrieval = await asyncio.to_thread(search_news_multi, search_query)

        if not retrieval.success:
            update_job(job_id, "error", 0, retrieval.error or "Failed to fetch articles", status="failed")
            return

        update_job(job_id, "fetched", 50, f"Found {len(retrieval.articles)} articles from {retrieval.sources_count} sources")
        await asyncio.sleep(0.1)

        # Step 4: Verification gate
        update_job(job_id, "verifying", 55, "Checking source diversity...")
        await asyncio.sleep(0.1)

        gate_result = run_retrieval_gates(retrieval.articles)
        if not gate_result.passed:
            jobs[job_id]["result"] = {
                "success": False,
                "abstained": True,
                "reason": gate_result.abstention_reason.value if gate_result.abstention_reason else "verification_failed",
                "details": gate_result.details,
                "workflow": workflow_type.value,
            }
            update_job(job_id, "abstained", 100, gate_result.details or "Verification failed", status="abstained")
            return

        # Step 5: Run workflow
        update_job(job_id, "analyzing", 60, "Extracting insights from articles...")
        await asyncio.sleep(0.1)

        if workflow_type == WorkflowType.FRAMING_DIVERGENCE:
            update_job(job_id, "analyzing", 70, "Analyzing framing across sources...")
            result = await asyncio.to_thread(workflow.run, query, False)
        else:
            update_job(job_id, "analyzing", 70, "Evaluating evidence for claim...")
            result = await asyncio.to_thread(workflow.run, query, False)

        update_job(job_id, "analyzing", 85, "Generating report...")
        await asyncio.sleep(0.1)

        # Step 6: Generate report
        report = Report(result=result)

        execution_time = time.time() - start_time

        jobs[job_id]["result"] = {
            "success": result.success,
            "abstained": result.abstained,
            "workflow": workflow_type.value,
            "json": report.to_json(),
            "markdown": report.to_markdown(),
            "execution_time": round(execution_time, 1),
        }

        if result.abstained:
            update_job(job_id, "abstained", 100, result.abstention_details or "Analysis abstained", status="abstained")
        else:
            update_job(job_id, "completed", 100, f"Analysis complete in {execution_time:.1f}s", status="completed")

        # Save to history
        save_to_history(job_id, query_text, jobs[job_id]["result"])

    except Exception as e:
        update_job(job_id, "error", 0, str(e), status="failed")


@app.get("/api/config")
async def get_api_config():
    """Get current API configuration status."""
    config = get_config()
    return {
        "apis_configured": config.news.available_apis,
        "has_any_api": config.news.has_any_api_key,
    }


# History endpoints
@app.get("/api/history")
async def list_history(limit: int = 20, offset: int = 0):
    """List recent analysis history."""
    store = get_history_store()
    entries = store.list(limit=limit, offset=offset)
    return {"entries": entries, "total": len(store.list(limit=100))}


@app.get("/api/history/{entry_id}")
async def get_history_entry(entry_id: str):
    """Get a specific history entry."""
    store = get_history_store()
    entry = store.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    return {
        "id": entry.id,
        "query": entry.query,
        "workflow": entry.workflow,
        "status": entry.status,
        "summary": entry.summary,
        "created_at": entry.created_at,
        "execution_time": entry.execution_time,
        "result": entry.result,
    }


@app.delete("/api/history/{entry_id}")
async def delete_history_entry(entry_id: str):
    """Delete a history entry."""
    store = get_history_store()
    if store.delete(entry_id):
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="History entry not found")


@app.delete("/api/history")
async def clear_history():
    """Clear all history."""
    store = get_history_store()
    count = store.clear()
    return {"deleted": count}


def save_to_history(job_id: str, query: str, result: dict):
    """Save a completed analysis to history."""
    store = get_history_store()

    # Extract summary based on workflow type
    workflow = result.get("workflow", "unknown")
    if result.get("abstained"):
        summary = result.get("details", "Analysis abstained")
    elif workflow == "framing_divergence":
        json_data = result.get("json", {})
        if isinstance(json_data, str):
            import json as json_module
            try:
                json_data = json_module.loads(json_data)
            except:
                json_data = {}
        data = json_data.get("data", {})
        clusters = data.get("clusters", [])
        summary = f"Found {len(clusters)} distinct framing perspectives"
    elif workflow == "claim_check":
        json_data = result.get("json", {})
        if isinstance(json_data, str):
            import json as json_module
            try:
                json_data = json_module.loads(json_data)
            except:
                json_data = {}
        data = json_data.get("data", {})
        verdict = data.get("verdict", "unknown")
        summary = f"Verdict: {verdict.replace('_', ' ').title()}"
    else:
        summary = "Analysis complete"

    entry = HistoryEntry(
        id=job_id,
        query=query,
        workflow=workflow,
        status=result.get("status", "completed") if result.get("abstained") else "completed",
        summary=summary,
        created_at=datetime.now().isoformat(),
        execution_time=result.get("execution_time", 0),
        result=result,
    )

    store.save(entry)
