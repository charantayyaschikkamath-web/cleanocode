from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from .facts import get_facts_snapshot
from .formatters import action_plan_csv, action_plan_html, count_provenance
from .models import (
    ActionPlan,
    CopilotAnswer,
    CopilotAskRequest,
    CopilotMode,
    CopilotQueryRequest,
    CopilotQueryResponse,
    CopilotQueryRecommendation,
    FactsSnapshot,
    ReportArtifactMetadata,
    ReportCreateRequest,
    ReportFormat,
    WeeklyReport,
)
from .report_store import ReportNotFoundError, ReportStore, new_report_id, utc_period
from .reports import report_csv, report_html
from .service import CopilotService

router = APIRouter(prefix="/api/copilot", tags=["copilot"])
reports_router = APIRouter(prefix="/api/reports", tags=["reports"])


@lru_cache(maxsize=1)
def get_copilot_service() -> CopilotService:
    return CopilotService()


@lru_cache(maxsize=1)
def get_report_store() -> ReportStore:
    return ReportStore()


def _scope_facts(facts: FactsSnapshot, event_ids: list[str]) -> tuple[FactsSnapshot, list[str]]:
    """Limit the supplied facts snapshot to user-selected events and linked evidence."""
    if not event_ids:
        return facts, []
    requested = list(dict.fromkeys(event_ids))
    by_id = {event.id: event for event in facts.events}
    selected = [by_id[event_id] for event_id in requested if event_id in by_id]
    missing = [event_id for event_id in requested if event_id not in by_id]
    evidence_ids = {event.id for event in selected}
    rooms = set()
    for event in selected:
        evidence_ids.update(event.evidence_ids)
        if event.room_id:
            rooms.add(event.room_id)
    related_actions = [action for action in facts.actions if action.event_id in evidence_ids]
    related_action_ids = {action.id for action in related_actions}
    evidence_ids.update(related_action_ids)
    for action in related_actions:
        evidence_ids.update(action.evidence_ids)
    readings = [
        reading for reading in facts.readings
        if reading.id in evidence_ids or (reading.room_id and reading.room_id in rooms)
    ]
    ledger_entries = [
        entry for entry in facts.ledger_entries
        if entry.action_id in related_action_ids or bool(set(entry.source_ids) & evidence_ids)
    ]
    scoped = facts.model_copy(update={
        "events": selected,
        "readings": readings,
        "actions": related_actions,
        "ledger_entries": ledger_entries,
    })
    return scoped, missing


def _report_sources(facts: FactsSnapshot, start, end, report_type: str, action_plan: ActionPlan | None = None) -> tuple[list[str], list[str], list[str]]:
    if report_type == "ACTION_PLAN" and action_plan is not None:
        event_ids = [item.event_id for item in action_plan.items]
        relevant_events = {event.id for event in facts.events if event.id in event_ids}
        action_ids = [action.id for action in facts.actions if action.event_id in relevant_events]
        ledger_ids = [entry.id for entry in facts.ledger_entries if entry.action_id in set(action_ids)]
        return event_ids, action_ids, ledger_ids

    def in_period(value):
        return value is not None and value.tzinfo is not None and start <= value.astimezone(start.tzinfo) < end
    event_ids = [e.id for e in facts.events if in_period(e.first_seen_at) or in_period(e.last_updated_at)]
    action_ids = [a.id for a in facts.actions if in_period(a.requested_at) or in_period(a.updated_at)]
    ledger_ids = [l.id for l in facts.ledger_entries if in_period(l.created_at)]
    return event_ids, action_ids, ledger_ids


def _records_for_metadata(facts: FactsSnapshot, start, end, report_type: str, action_plan: ActionPlan | None = None) -> list:
    def in_period(value):
        return value is not None and value.tzinfo is not None and start <= value.astimezone(start.tzinfo) < end

    if report_type == "WEEKLY_SUSTAINABILITY":
        return [
            *[item for item in facts.readings if in_period(item.observed_at)],
            *[item for item in facts.events if in_period(item.first_seen_at) or in_period(item.last_updated_at)],
            *[item for item in facts.actions if in_period(item.requested_at) or in_period(item.updated_at)],
            *[item for item in facts.ledger_entries if in_period(item.created_at)],
        ]

    event_ids = {item.event_id for item in action_plan.items} if action_plan else set()
    selected_events = [event for event in facts.events if event.id in event_ids]
    actions = [action for action in facts.actions if action.event_id in event_ids]
    related_ids = {event.id for event in selected_events}
    related_rooms = {event.room_id for event in selected_events if event.room_id}
    for event in selected_events:
        related_ids.update(event.evidence_ids)
    for action in actions:
        related_ids.update([action.id, *action.evidence_ids])
    readings = [reading for reading in facts.readings if reading.id in related_ids or (reading.room_id and reading.room_id in related_rooms)]
    action_ids = {action.id for action in actions}
    ledgers = [entry for entry in facts.ledger_entries if entry.action_id in action_ids or bool(set(entry.source_ids) & related_ids)]
    return [*readings, *selected_events, *actions, *ledgers]


async def _build_report_artifacts(
    request: ReportCreateRequest,
    facts: FactsSnapshot,
    service: CopilotService,
    store: ReportStore,
) -> ReportArtifactMetadata:
    period_start, period_end = utc_period(request.period_start, request.period_end)
    report_id = new_report_id()
    action_plan: ActionPlan | None = None
    if request.report_type == "WEEKLY_SUSTAINABILITY":
        weekly = await service.weekly_report(facts, now=period_end, period_start=period_start)
        # The externally addressable artifact ID is the canonical report ID everywhere.
        weekly.report_id = report_id
        artifacts = {
            ReportFormat.JSON: weekly.model_dump_json(indent=2),
            ReportFormat.CSV: report_csv(weekly),
            ReportFormat.HTML: report_html(weekly),
        }
        assumptions = dict(weekly.assumptions)
        limitations = list(weekly.limitations)
        limitations.extend(weekly.verified_vs_simulated)
        created_at = weekly.generated_at
    else:
        action_plan = await service.action_plan(facts)
        artifacts = {
            ReportFormat.JSON: action_plan.model_dump_json(indent=2),
            ReportFormat.CSV: action_plan_csv(action_plan),
            ReportFormat.HTML: action_plan_html(action_plan),
        }
        assumptions = dict(action_plan.assumptions)
        assumptions["report_semantics"] = "Action plan is a current-snapshot view of open events, not historical event counts over the selected interval."
        limitations = list(action_plan.limitations)
        created_at = action_plan.generated_at

    source_event_ids, source_action_ids, source_ledger_ids = _report_sources(
        facts, period_start, period_end, request.report_type, action_plan
    )
    metadata = ReportArtifactMetadata(
        id=report_id,
        format=request.format,
        created_at=created_at,
        period_start=period_start,
        period_end=period_end,
        source_event_ids=source_event_ids,
        source_action_ids=source_action_ids,
        source_ledger_ids=source_ledger_ids,
        provenance_summary=count_provenance(_records_for_metadata(facts, period_start, period_end, request.report_type, action_plan)),
        assumptions=assumptions,
        limitations=limitations,
        file_reference=f"/api/reports/{report_id}/download",
        available_formats=[ReportFormat.JSON, ReportFormat.CSV, ReportFormat.HTML],
        report_type=request.report_type,
    )
    try:
        return store.create(metadata, artifacts)
    except FileExistsError:
        # A new random ID is normally unique. Treat an exceptional collision as a safe failure.
        raise HTTPException(status_code=500, detail="Could not allocate report artifact")
    except OSError:
        raise HTTPException(status_code=500, detail="Could not persist report artifact")


@router.post("/ask", response_model=CopilotAnswer)
async def ask_copilot(
    request: CopilotAskRequest,
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> CopilotAnswer:
    return await service.ask(request.question, facts, request.event_id)


@router.post("/query", response_model=CopilotQueryResponse)
async def query_copilot(
    request: CopilotQueryRequest,
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> CopilotQueryResponse:
    scoped_facts, missing_event_ids = _scope_facts(facts, request.event_ids)
    answer = await service.ask(
        request.question,
        scoped_facts,
        request.event_ids[0] if len(request.event_ids) == 1 and not missing_event_ids else None,
        force_template=request.request_mode == "TEMPLATE",
    )
    source_ids: set[str] = set()
    if request.event_ids:
        for event in scoped_facts.events:
            source_ids.update([event.id, *event.evidence_ids])
        for reading in scoped_facts.readings:
            source_ids.add(reading.id)
        for action in scoped_facts.actions:
            source_ids.update([action.id, *action.evidence_ids])
        for entry in scoped_facts.ledger_entries:
            source_ids.update([entry.id, *entry.source_ids])
    else:
        source_ids.update(ref.id for ref in answer.fact_references)
    known_ids = scoped_facts.fact_ids
    source_ids = {source_id for source_id in source_ids if source_id in known_ids}
    for recommendation in answer.recommendations:
        source_ids.update(ref for ref in recommendation.fact_refs if ref in known_ids)

    warnings = list(answer.limitations)
    if request.facts_version and request.facts_version != facts.snapshot_id:
        warnings.append(f"Requested facts version {request.facts_version} differs from current snapshot {facts.snapshot_id}; current facts were used.")
    if missing_event_ids:
        warnings.append("Unknown event IDs were not used: " + ", ".join(missing_event_ids))
    if not scoped_facts.events and request.event_ids:
        warnings.append("No requested event matched the current facts snapshot. No event evidence was inferred.")
    if facts.source_status != "HEALTHY":
        warnings.append("The source status is not HEALTHY; data completeness is not established.")
    if request.request_mode == "LLM" and answer.mode != CopilotMode.LLM:
        warnings.append(f"LLM mode was requested but unavailable; response fell back to {answer.mode.value}.")
    recommendations = [
        CopilotQueryRecommendation(label=item.title, action_type="REVIEW_EVIDENCE", requires_approval=False)
        for item in answer.recommendations
    ]
    return CopilotQueryResponse(
        answer="\n".join([answer.summary, *answer.lines]),
        mode=answer.mode,
        facts_version=facts.snapshot_id,
        source_ids=sorted(source_ids),
        recommendations=recommendations,
        warnings=list(dict.fromkeys(warnings)),
        generated_at=answer.generated_at,
    )


@router.get("/reports/weekly", response_model=WeeklyReport)
async def get_weekly_report(
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> WeeklyReport:
    return await service.weekly_report(facts)


@router.get("/reports/weekly/export")
async def export_weekly_report(
    format: Literal["json", "csv", "html"] = Query(default="json"),
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> Response:
    report = await service.weekly_report(facts)
    filename = "campustwin-weekly-report"
    if format == "csv":
        return Response(
            content=report_csv(report),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )
    if format == "html":
        return Response(
            content=report_html(report),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.html"'},
        )
    return JSONResponse(
        content=report.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
    )


@router.post("/reports/action-plan", response_model=ActionPlan)
async def get_action_plan(
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> ActionPlan:
    return await service.action_plan(facts)


@router.get("/reports/action-plan/export")
async def export_action_plan(
    format: Literal["json", "csv", "html"] = Query(default="json"),
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> Response:
    plan = await service.action_plan(facts)
    filename = "campustwin-action-plan"
    if format == "json":
        return JSONResponse(
            content=plan.model_dump(mode="json"),
            headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
        )
    content = action_plan_csv(plan) if format == "csv" else action_plan_html(plan)
    media_type = "text/csv; charset=utf-8" if format == "csv" else "text/html; charset=utf-8"
    suffix = "csv" if format == "csv" else "html"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}.{suffix}"'})


@reports_router.post("", response_model=ReportArtifactMetadata, status_code=201)
async def create_report(
    request: ReportCreateRequest,
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
    store: ReportStore = Depends(get_report_store),
) -> ReportArtifactMetadata:
    try:
        return await _build_report_artifacts(request, facts, service, store)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@reports_router.get("/{report_id}", response_model=ReportArtifactMetadata)
def get_report_metadata(report_id: str, store: ReportStore = Depends(get_report_store)) -> ReportArtifactMetadata:
    try:
        return store.get_metadata(report_id)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report was not found") from exc


@reports_router.get("/{report_id}/download")
def download_report(
    report_id: str,
    format: ReportFormat = Query(default=ReportFormat.HTML),
    store: ReportStore = Depends(get_report_store),
) -> Response:
    try:
        content, media_type, filename = store.get_artifact(report_id, format)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report was not found or requested format is unavailable") from exc
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
