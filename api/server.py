"""
Vipin Lab API — FastAPI backend for the Web UI.

Endpoints:
  POST /api/discover          → SSE stream of discovery progress + results
  POST /api/extend            → SSE stream
  POST /api/transfer          → SSE stream
  POST /api/pipeline/{id}     → SSE stream of pipeline progress
  POST /api/resume/{id}       → SSE stream
  GET  /api/ideas             → list all ideas
  GET  /api/sessions          → list recent sessions
  GET  /api/sessions/{id}     → get session detail
  GET  /api/ideas/{id}        → get idea detail
  GET  /api/health            → health check
"""
from __future__ import annotations
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from lab.core.config import LabConfig
from lab.core.orchestrator import LabOrchestrator
from lab.core.progress import set_reporter, ProgressReporter, ProgressEvent

app = FastAPI(title="Vipin Lab API", version="1.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_config = LabConfig()
_orchestrator: LabOrchestrator | None = None


def get_orchestrator() -> LabOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LabOrchestrator(_config)
    return _orchestrator


# ── SSE helpers ───────────────────────────────────────────────────────────────

def sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def sse_progress(phase: str, step: str, detail: str = "") -> str:
    return sse("progress", {"phase": phase, "step": step, "detail": detail,
                             "ts": datetime.utcnow().isoformat()})


def sse_error(msg: str) -> str:
    return sse("error", {"message": msg})


def sse_done(data: dict) -> str:
    return sse("done", data)


def _session_to_dict(session) -> dict:
    """Serialize a LabSession to JSON-safe dict."""
    return {
        "id": session.id,
        "mode": session.mode,
        "domain": session.domain,
        "created_at": session.created_at,
        "phenomena": [
            {"id": p.id, "description": p.description, "severity": p.severity,
             "evidence": p.evidence[:3], "potential_causes": p.potential_causes[:3]}
            for p in session.phenomena
        ],
        "analogies": [
            {"source_domain": a.source_domain, "target_domain": a.target_domain,
             "source_problem": a.source_problem, "target_problem": a.target_problem,
             "structural_similarity": a.structural_similarity,
             "confidence": a.confidence}
            for a in session.analogies
        ],
        "ideas": [
            {
                "id": i.id, "title": i.title, "domain": i.domain,
                "origin": i.origin.value, "status": i.status.value,
                "phenomenon": i.phenomenon, "hypothesis": i.hypothesis,
                "proposed_method": i.proposed_method,
                "expected_contribution": i.expected_contribution,
                "novelty_score": i.novelty_score,
                "feasibility_score": i.feasibility_score,
                "workspace_dir": i.workspace_dir,
                "kill_survived": i.kill_argument.survived if i.kill_argument else None,
                "kill_argument": i.kill_argument.argument[:300] if i.kill_argument else None,
                "kill_rebuttal": i.kill_argument.rebuttal[:300] if i.kill_argument else None,
            }
            for i in session.ideas
        ],
        "audit_trail": session.audit_trail,
    }


# ── Request models ────────────────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    domain: str
    use_beam: bool = True


class ExtendRequest(BaseModel):
    domain: str
    method: str
    results: str = ""
    limitations: str = ""
    n: int = 3


class TransferRequest(BaseModel):
    source_domain: str
    target_domain: str


# ── Streaming endpoints ───────────────────────────────────────────────────────

@app.post("/api/discover")
async def discover(req: DiscoverRequest):
    async def stream() -> AsyncGenerator[str, None]:
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()

        reporter = ProgressReporter(verbose=True)
        reporter._callbacks = [lambda e: events.put_nowait(e)]
        set_reporter(reporter)

        yield sse_progress("start", f"Scanning {req.domain} for phenomena")

        async def run():
            try:
                orch = get_orchestrator()
                session = await orch.discover(req.domain, use_beam=req.use_beam)
                await events.put(None)  # sentinel
                return session
            except Exception as e:
                await events.put(None)
                raise e

        task = asyncio.create_task(run())

        # Stream progress events while task runs
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=0.5)
                if event is None:
                    break
                yield sse_progress(event.phase, event.step, event.detail)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # SSE keepalive

        try:
            session = await task
            yield sse_done(_session_to_dict(session))
        except Exception as e:
            yield sse_error(str(e))

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/extend")
async def extend(req: ExtendRequest):
    async def stream() -> AsyncGenerator[str, None]:
        yield sse_progress("start", f"Generating extension ideas for {req.domain}")
        try:
            orch = get_orchestrator()
            session = await orch.extend(
                req.domain, req.method, req.results, req.limitations, req.n
            )
            yield sse_done(_session_to_dict(session))
        except Exception as e:
            yield sse_error(str(e))

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.post("/api/transfer")
async def transfer(req: TransferRequest):
    async def stream() -> AsyncGenerator[str, None]:
        yield sse_progress("start", f"Finding analogies: {req.source_domain} → {req.target_domain}")
        try:
            orch = get_orchestrator()
            session = await orch.transfer(req.source_domain, req.target_domain)
            yield sse_done(_session_to_dict(session))
        except Exception as e:
            yield sse_error(str(e))

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.post("/api/pipeline/{idea_id}")
async def run_pipeline(idea_id: str):
    async def stream() -> AsyncGenerator[str, None]:
        orch = get_orchestrator()
        idea = orch.workspace.load_idea(idea_id)
        if not idea:
            yield sse_error(f"Idea not found: {idea_id}")
            return

        stage = orch.workspace.get_pipeline_stage(idea)
        yield sse_progress("pipeline", f"Starting from stage: {stage}",
                           f"idea: {idea.title[:60]}")

        if stage == "bridge_done":
            yield sse_error("Waiting for experiments. Place results in experiments/results/ then resume.")
            return

        try:
            result_idea, paper = await orch.run_pipeline(idea)
            result = {
                "idea": {
                    "id": result_idea.id, "title": result_idea.title,
                    "status": result_idea.status.value,
                },
                "paper": {
                    "title": paper.title,
                    "abstract": paper.abstract,
                    "review_scores": paper.review_scores,
                    "claim_audit_passed": paper.claim_audit_passed,
                } if paper else None,
            }
            yield sse_done(result)
        except Exception as e:
            yield sse_error(str(e))

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.post("/api/resume/{idea_id}")
async def resume_pipeline(idea_id: str):
    async def stream() -> AsyncGenerator[str, None]:
        yield sse_progress("resume", f"Resuming pipeline: {idea_id}")
        try:
            orch = get_orchestrator()
            idea, paper = await orch.resume_pipeline(idea_id)
            if idea is None:
                yield sse_error(f"Idea not found: {idea_id}")
                return
            yield sse_done({
                "idea": {"id": idea.id, "title": idea.title, "status": idea.status.value},
                "paper": {"title": paper.title, "abstract": paper.abstract} if paper else None,
            })
        except Exception as e:
            yield sse_error(str(e))

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


# ── Read endpoints ────────────────────────────────────────────────────────────

@app.get("/api/ideas")
async def list_ideas(domain: str = "", status: str = ""):
    orch = get_orchestrator()
    ideas = orch.workspace.list_ideas(status_filter=status or None)
    if domain:
        ideas = [i for i in ideas if domain.lower() in i.get("domain", "").lower()]
    return ideas


@app.get("/api/ideas/{idea_id}")
async def get_idea(idea_id: str):
    orch = get_orchestrator()
    idea = orch.workspace.load_idea(idea_id)
    if not idea:
        raise HTTPException(404, f"Idea not found: {idea_id}")
    plan = orch.workspace.load_plan(idea)
    paper = orch.workspace.load_paper(idea)
    return {
        "id": idea.id, "title": idea.title, "domain": idea.domain,
        "origin": idea.origin.value, "status": idea.status.value,
        "phenomenon": idea.phenomenon, "hypothesis": idea.hypothesis,
        "proposed_method": idea.proposed_method,
        "expected_contribution": idea.expected_contribution,
        "novelty_score": idea.novelty_score,
        "feasibility_score": idea.feasibility_score,
        "workspace_dir": idea.workspace_dir,
        "stage": orch.workspace.get_pipeline_stage(idea),
        "kill_argument": {
            "argument": idea.kill_argument.argument,
            "rebuttal": idea.kill_argument.rebuttal,
            "survived": idea.kill_argument.survived,
            "closest_prior_work": idea.kill_argument.closest_prior_work,
        } if idea.kill_argument else None,
        "plan": {
            "blocks": len(plan.blocks),
            "approved": plan.approved,
            "audit_scores": plan.audit_scores,
            "milestone_gates": plan.milestone_gates,
        } if plan else None,
        "paper": {
            "title": paper.title,
            "abstract": paper.abstract,
            "review_scores": paper.review_scores,
            "claim_audit_passed": paper.claim_audit_passed,
        } if paper else None,
    }


@app.get("/api/sessions")
async def list_sessions():
    workspace = Path(_config.workspace_root)
    sessions = []
    for f in sorted(workspace.glob("*/session.json"), reverse=True)[:50]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": d.get("id"), "mode": d.get("mode"),
                "domain": d.get("domain"), "created_at": d.get("created_at"),
                "ideas_count": len(d.get("ideas", [])),
                "surviving": sum(1 for i in d.get("ideas", []) if i.get("kill_survived")),
            })
        except Exception:
            pass
    return sessions


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    workspace = Path(_config.workspace_root)
    matches = list(workspace.glob(f"{session_id}*/session.json"))
    if not matches:
        raise HTTPException(404, f"Session not found: {session_id}")
    return json.loads(matches[0].read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "1.3.0",
        "anthropic_key": bool(_config.anthropic_key),
        "workspace": str(Path(_config.workspace_root).absolute()),
    }
