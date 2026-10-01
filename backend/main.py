"""HAP backend v0.3 — FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from agent import AgentError, AnalystAgent
from agent.report_opinion import OpinionError, ReportOpinionService
from agent.run_workflow import AgentRunService, RunWorkflowError
from agent.service import AnalystService
from agent.schemas import CheckpointAnswer, ChatRequest, ChatResponse, FeedbackRequest, ToolCallSummary
from hap_auth import AuthConfigError, auth_enabled, is_production, validate_auth_configuration
from hap_auth.http import AuthGateMiddleware, auth_health_fields, register_auth_routes
from models.analysis import CreateAnalysisRequest, CreateAnalysisResponse
from models.new_company import LeaseRateReviewRequest, RdUsefulLifeOverrideRequest
from models.api_responses import (
    AnalysisDetailResponse,
    AnalysisSummaryResponse,
    build_detail_response,
    build_summary_response,
    load_engine_result_dict,
    load_final_report_dict,
)
from models.workbook_schema import WorkbookSummary
from pipeline.orchestrator import PipelineError, PipelineOrchestrator
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.answer_cache import AnswerCache
from services.budget_service import BudgetService
from services.feedback_service import FeedbackError, FeedbackService
from services.lessons_service import LessonError, LessonsService
from services.file_service import FileService, FileUploadError
from services.output_service import OutputService
from services.recommendation_conflict import recommendation_conflict
from services.workbook_service import WorkbookService
from settings import cors_allow_credentials, cors_allow_origins, storage_is_writable


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if auth_enabled():
        validate_auth_configuration()
    origins = cors_allow_origins()
    if is_production() and "*" in origins:
        raise AuthConfigError("Wildcard CORS is not allowed in production.")
    if auth_enabled() and not cors_allow_credentials():
        raise AuthConfigError("Credentialed sessions require explicit CORS origins (not *).")
    yield


app = FastAPI(
    title="HAP Backend",
    description="Houda's Analyst Platform API",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(AuthGateMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)
register_auth_routes(app)

analysis_service = AnalysisService()
file_service = FileService()
workbook_service = WorkbookService()
output_service = OutputService()
budget_service = BudgetService()
feedback_service = FeedbackService()
lessons_service = LessonsService(feedback=feedback_service)
analyst_agent = AnalystAgent(
    analysis_service=analysis_service,
    output_service=output_service,
    budget_service=budget_service,
    lessons_service=lessons_service,
)
answer_cache = AnswerCache()
analyst_service = AnalystService(
    analysis_service=analysis_service,
    output_service=output_service,
    agent=analyst_agent,
    budget=budget_service,
    cache=answer_cache,
    lessons=lessons_service,
)
pipeline_orchestrator = PipelineOrchestrator(
    analysis_service=analysis_service,
    file_service=file_service,
    output_service=output_service,
)
report_opinion_service = ReportOpinionService(
    agent=analyst_agent, analysis_service=analysis_service, output_service=output_service
)
agent_run_service = AgentRunService(
    analysis_service=analysis_service,
    output_service=output_service,
    pipeline=pipeline_orchestrator,
    feedback_service=feedback_service,
    agent=analyst_agent,
)


@app.get("/health")
@app.get("/healthz")
def health() -> JSONResponse:
    """Liveness/readiness for hosts (Render health check)."""
    writable = storage_is_writable()
    payload = {
        "status": "ok" if writable else "degraded",
        "service": "HAP backend",
        "version": "0.3.0",
        "storage_ok": writable,
        **auth_health_fields(),
    }
    return JSONResponse(payload, status_code=200 if writable else 503)


@app.post("/analysis/create", response_model=CreateAnalysisResponse)
def create_analysis(request: CreateAnalysisRequest) -> CreateAnalysisResponse:
    """Create a new analysis and persist its metadata."""
    analysis = analysis_service.create(request)
    return CreateAnalysisResponse(analysis_id=analysis.analysis_id, status="created")


@app.post("/analysis/{analysis_id}/upload")
async def upload_analysis_files(
    analysis_id: str,
    prefilled_workbook: UploadFile = File(...),
    previous_workbook: UploadFile | None = File(None),
    custom_run_filter: UploadFile | None = File(None),
) -> dict:
    """Upload workbook files for an existing analysis."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        updated = await file_service.handle_uploads(
            analysis,
            prefilled_workbook=prefilled_workbook,
            previous_workbook=previous_workbook,
            custom_run_filter=custom_run_filter,
        )
        analysis_service.save(updated)
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return updated.to_dict()


@app.get("/analyses", response_model=list[AnalysisSummaryResponse])
def list_analyses() -> list[AnalysisSummaryResponse]:
    """Return summary DTOs for all analyses (no full engine artifacts)."""
    items: list[AnalysisSummaryResponse] = []
    for analysis in analysis_service.list_all():
        engine_result = load_engine_result_dict(output_service, analysis)
        items.append(build_summary_response(analysis, engine_result, load_final_report_dict(output_service, analysis)))
    return items


@app.get("/analysis/{analysis_id}/recommendation-conflict")
def get_recommendation_conflict(analysis_id: str) -> dict:
    """Headline = final (workbook-based) report; flags disagreement with the SEC-based engine."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _read(name: str):
        try:
            return output_service.read_json(analysis_id, name)
        except Exception:  # noqa: BLE001 - missing report just means "not available"
            return None

    return recommendation_conflict(_read("final_recommendation_report.json"), _read("analysis_engine_result.json"))


@app.get("/analysis/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis(analysis_id: str) -> AnalysisDetailResponse:
    """Return detail metadata DTO. Engine JSON is available via outputs API."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    engine_result = load_engine_result_dict(output_service, analysis)
    return build_detail_response(analysis, engine_result, load_final_report_dict(output_service, analysis))


@app.post("/analysis/{analysis_id}/run")
def run_analysis_pipeline(analysis_id: str, background_tasks: BackgroundTasks) -> dict:
    """Start the HAP backend pipeline for an uploaded analysis."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        pipeline_orchestrator.assert_ready_for_pipeline(analysis)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(pipeline_orchestrator.run, analysis_id)
    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "message": "Pipeline started. Poll GET /analysis/{id} for progress.",
    }


@app.post("/analysis/{analysis_id}/agent/run")
def start_agent_run(analysis_id: str, background_tasks: BackgroundTasks, with_take: bool = False) -> dict:
    """Run the pipeline, then stop at checkpoints for your feedback. with_take adds a paid, labeled 'my take'."""
    try:
        state = agent_run_service.start(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    background_tasks.add_task(agent_run_service.run, analysis_id, with_take)
    return state


@app.get("/analysis/{analysis_id}/agent")
def get_agent_run(analysis_id: str, refresh: bool = True) -> dict:
    """Run state with its checkpoints. refresh=true opens the next checkpoint if the pipeline reached one."""
    try:
        analysis_service.get(analysis_id)
        state = agent_run_service.advance(analysis_id) if refresh and agent_run_service.state(analysis_id)["phase"] not in {"not_started", "stopped", "done"} else agent_run_service.state(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return state


@app.get("/analysis/{analysis_id}/agent/dossier")
def get_agent_dossier(analysis_id: str) -> dict:
    try:
        analysis_service.get(analysis_id)
        return output_service.read_json(analysis_id, "agent_dossier.json")
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="No dossier yet.") from exc


@app.post("/analysis/{analysis_id}/agent/checkpoints/{checkpoint_id}")
def answer_agent_checkpoint(analysis_id: str, checkpoint_id: str, request: CheckpointAnswer) -> dict:
    """One-click answer: approve, revise or stop. Recorded as feedback."""
    try:
        return agent_run_service.answer(analysis_id, checkpoint_id, request.decision, request.note)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/analysis/{analysis_id}/report/opinion")
def generate_report_opinion(analysis_id: str) -> dict:
    """Write the analyst opinions (fundamentals, and valuation if strong) into the Word report. Uses the paid model."""
    try:
        return report_opinion_service.generate(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OpinionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/analysis/{analysis_id}/report/opinion")
def get_report_opinion(analysis_id: str) -> dict:
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    saved = report_opinion_service.saved(analysis_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="No opinion generated yet.")
    return saved


@app.post("/analysis/{analysis_id}/agent/continue")
def continue_agent_run(analysis_id: str, background_tasks: BackgroundTasks, with_take: bool = False) -> dict:
    """After you resolved a review gate: carry on to the next checkpoint."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(agent_run_service.advance, analysis_id, with_take)
    return {"analysis_id": analysis_id, "message": "Continuing; poll GET /analysis/{id}/agent."}


@app.get("/analysis/{analysis_id}/analyst-review")
def get_analyst_review(analysis_id: str) -> dict:
    """Return pending New Company lease-rate review and R&D useful-life decision."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload: dict = {"analysis_id": analysis_id}
    for name, key in (
        ("lease_rate_review.json", "lease_rate_review"),
        ("rd_useful_life_decision.json", "rd_useful_life_decision"),
        ("new_company_run_state.json", "run_state"),
    ):
        try:
            payload[key] = output_service.read_json(analysis_id, name)
        except FileNotFoundError:
            payload[key] = None
    return payload


@app.post("/analysis/{analysis_id}/analyst-review/lease-rate")
def review_lease_rate(analysis_id: str, request: LeaseRateReviewRequest) -> dict:
    """Approve, correct, or request more evidence for the estimated lease discount rate."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.action not in {"approve", "correct", "request_more_evidence"}:
        raise HTTPException(status_code=400, detail="action must be approve, correct, or request_more_evidence")
    if request.action == "correct" and request.rate is None:
        raise HTTPException(status_code=400, detail="correct requires a rate")
    proposed = _peek_json(analysis_id, "lease_rate_review.json").get("proposed_rate")
    try:
        updated = pipeline_orchestrator.finalize_new_company_review(
            analysis,
            action=request.action,
            rate=request.rate,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_review_feedback(
        analysis,
        target="lease_rate",
        action=request.action,
        agent_value=proposed,
        analyst_value=request.rate if request.action == "correct" else proposed,
        reason=request.reason,
    )
    return updated.to_dict()


@app.post("/analysis/{analysis_id}/analyst-review/rd-useful-life")
def override_rd_useful_life(analysis_id: str, request: RdUsefulLifeOverrideRequest) -> dict:
    """Override the agent-selected R&D useful life and recalculate dependents."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.useful_life < 1 or request.useful_life > 10:
        raise HTTPException(status_code=400, detail="useful_life must be in 1–10")
    selected = _peek_json(analysis_id, "rd_useful_life_decision.json").get("selected_useful_life")
    try:
        updated = pipeline_orchestrator.finalize_new_company_review(
            analysis,
            action="approve",
            reason=request.reason,
            rd_life=request.useful_life,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_review_feedback(
        analysis,
        target="rd_useful_life",
        action="approve" if selected == request.useful_life else "correct",
        agent_value=selected,
        analyst_value=request.useful_life,
        reason=request.reason,
    )
    return updated.to_dict()


@app.post("/analysis/{analysis_id}/chat", response_model=ChatResponse)
def chat_with_analyst(analysis_id: str, request: ChatRequest) -> ChatResponse:
    """Ask the HAP Analyst about one analysis.

    ``mode=auto`` (default) answers from built-in logic or a remembered answer for free and
    never makes a paid call; if it cannot, ``needs_claude`` is true and the UI offers an explicit
    "Ask Claude" (``mode=claude``). The agent is read-only and never changes workbooks, scores
    or review decisions. Paid answers require ANTHROPIC_API_KEY and count against the monthly cap.
    """
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        result = analyst_service.answer(analysis_id, [m.model_dump() for m in request.messages], mode=request.mode)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ChatResponse(
        reply=result.reply,
        tool_calls=[ToolCallSummary(name=c.name, input=getattr(c, "input", {}) or {}, ok=getattr(c, "ok", True)) for c in result.tool_calls if hasattr(c, "name")],
        iterations=result.iterations,
        stop_reason=result.stop_reason,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        budget=result.budget,
        source=result.source,
        intent=result.intent,
        needs_claude=result.needs_claude,
        estimated_cost_usd=result.estimated_cost_usd,
    )


class LessonDecision(BaseModel):
    text: str | None = Field(default=None, max_length=1200)
    note: str | None = Field(default=None, max_length=500)


@app.get("/lessons")
def list_lessons(status: str | None = None) -> dict:
    """The lessons library: proposed, approved, rejected and retired lessons."""
    try:
        return {"items": lessons_service.list(status=status)}
    except LessonError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/lessons/propose")
def propose_lessons() -> dict:
    """Look for repeated corrections in the feedback and propose lessons (free, no AI call).

    Proposals do nothing until you approve them.
    """
    created = lessons_service.propose_from_feedback()
    return {"created": created, "count": len(created)}


def _lesson_action(action, lesson_id: str, **kwargs) -> dict:
    try:
        return action(lesson_id, **kwargs)
    except LessonError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.post("/lessons/{lesson_id}/approve")
def approve_lesson(lesson_id: str, body: LessonDecision | None = None) -> dict:
    """Approve a lesson (optionally editing its wording). Approved lessons guide the analyst chat."""
    body = body or LessonDecision()
    return _lesson_action(lessons_service.approve, lesson_id, text=body.text, note=body.note)


@app.post("/lessons/{lesson_id}/reject")
def reject_lesson(lesson_id: str, body: LessonDecision | None = None) -> dict:
    body = body or LessonDecision()
    return _lesson_action(lessons_service.reject, lesson_id, note=body.note)


@app.post("/lessons/{lesson_id}/retire")
def retire_lesson(lesson_id: str, body: LessonDecision | None = None) -> dict:
    body = body or LessonDecision()
    return _lesson_action(lessons_service.retire, lesson_id, note=body.note)


@app.get("/budget")
def get_budget() -> dict:
    """Claude API spend this month versus the hard monthly cap."""
    return budget_service.status()


@app.post("/analysis/{analysis_id}/feedback")
def submit_feedback(analysis_id: str, request: FeedbackRequest) -> dict:
    """Record analyst feedback (approve / correct / reject / thumbs / comment) on an agent output."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.target == "chat_answer" and request.action == "thumbs_down":
        question = (request.context or {}).get("question")
        if isinstance(question, str) and question.strip():
            try:
                answer_cache.invalidate(analysis_id, question)  # a disliked answer must not be served again
            except Exception:  # noqa: BLE001
                pass
    try:
        return feedback_service.add(
            analysis_id=analysis_id,
            target=request.target,
            action=request.action,
            agent_value=request.agent_value,
            analyst_value=request.analyst_value,
            reason=request.reason,
            context=request.context,
            ticker=analysis.ticker,
            analysis_type=analysis.analysis_type,
        )
    except FeedbackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/analysis/{analysis_id}/feedback")
def list_feedback(analysis_id: str, limit: int = 100) -> dict:
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"analysis_id": analysis_id, "items": feedback_service.list(analysis_id=analysis_id, limit=limit)}


@app.get("/feedback/summary")
def feedback_summary() -> dict:
    """How often the analyst approves versus corrects each kind of agent decision."""
    return feedback_service.summary()


def _record_review_feedback(analysis, *, target: str, action: str, agent_value, analyst_value, reason) -> None:
    """Log a review-gate decision as feedback. Never allowed to break the review itself."""
    try:
        feedback_service.add(
            analysis_id=analysis.analysis_id,
            target=target,
            action=action,
            agent_value=agent_value,
            analyst_value=analyst_value,
            reason=reason,
            ticker=analysis.ticker,
            analysis_type=analysis.analysis_type,
            source="review_gate",
        )
    except Exception:  # noqa: BLE001 - feedback logging is best effort
        pass


def _peek_json(analysis_id: str, filename: str) -> dict:
    try:
        return output_service.read_json(analysis_id, filename)
    except (FileNotFoundError, ValueError):
        return {}


@app.post("/analysis/{analysis_id}/read-workbook", response_model=WorkbookSummary)
def read_workbook(analysis_id: str) -> WorkbookSummary:
    """Inspect the prefilled workbook without modifying it."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        workbook_path = file_service.get_prefilled_workbook_path(analysis)
        original_filename = analysis.files.prefilled_workbook.filename  # type: ignore[union-attr]
        return workbook_service.read_summary(workbook_path, original_filename)
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/analysis/{analysis_id}/outputs")
def list_output_artifacts(analysis_id: str) -> dict:
    """List downloadable pipeline output artifacts for an analysis."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "analysis_id": analysis_id,
        "artifacts": output_service.list_artifacts(analysis_id),
    }


@app.get("/analysis/{analysis_id}/outputs/{artifact_name}")
def download_output_artifact(analysis_id: str, artifact_name: str) -> FileResponse:
    """Download a pipeline output artifact."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Prevent path traversal into sec_cache or parent directories.
    if "/" in artifact_name or "\\" in artifact_name or artifact_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid artifact name.")

    path = output_service.artifact_path(analysis_id, artifact_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_name}' not found.")

    return FileResponse(
        path=path,
        filename=artifact_name,
        media_type=_media_type_for(path),
    )


@app.get("/analysis/{analysis_id}/provenance/{cell_ref:path}")
def get_cell_provenance(analysis_id: str, cell_ref: str) -> dict:
    """
    Return explainability metadata for one workbook cell.

    Example: /analysis/{id}/provenance/Income%20Statement!B5
    """
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    provenance_path = output_service.artifact_path(analysis_id, "provenance_report.json")
    if not provenance_path.exists():
        raise HTTPException(status_code=404, detail="Provenance report not available yet.")

    import json

    with provenance_path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    normalized_ref = cell_ref.replace("%21", "!")
    for entry in report.get("entries", []):
        if entry.get("cell_ref") == normalized_ref:
            return entry

    raise HTTPException(status_code=404, detail=f"No provenance found for '{normalized_ref}'.")


def _media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".csv":
        return "text/csv"
    return "application/octet-stream"
