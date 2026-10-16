from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from .cache import LastGoodNarrativeCache
from .config import CopilotSettings
from .facts import fact_references, facts_context, grounding_from_facts
from .models import (
    ActionFact,
    ActionPlan,
    ActionPlanItem,
    CopilotAnswer,
    CopilotMode,
    FactsSnapshot,
    GroundedNarrative,
    Provenance,
    Recommendation,
    ReportActionSummary,
    ReportReadingSummary,
    ReportEventSummary,
    ReportLedgerSummary,
    WeeklyReport,
)
from .privacy import redact_sensitive_text
from .provider import ProviderError, parse_narrative_json, request_narrative
from .reports import action_plan_items, build_weekly_metrics


# Numeric language is disallowed in LLM prose so it cannot introduce free-form metrics,
# percentages, prices, confidence values or unverified counts. Numeric fields are backend-owned.
_FORBIDDEN_LLM_TEXT = re.compile(
    r"(?:[0-9]|[%$€₹]|https?://|\bdoi\s*:\s*|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|hundred|thousand|million|first|second|third)\b)",
    re.IGNORECASE,
)


def _context_fact_ids(context: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for group in ("readings", "events", "actions", "ledger_entries"):
        for record in context.get(group, []):
            if not isinstance(record, dict):
                continue
            if isinstance(record.get("id"), str):
                ids.add(record["id"])
            for field in ("evidence_ids", "source_ids"):
                values = record.get(field, [])
                if isinstance(values, list):
                    ids.update(value for value in values if isinstance(value, str))
            impact = record.get("projected_impact")
            if isinstance(impact, dict) and isinstance(impact.get("source_ids"), list):
                ids.update(value for value in impact["source_ids"] if isinstance(value, str))
    derived = context.get("derived_context", {})
    if isinstance(derived, dict):
        for item in derived.get("action_plan_items", []) if isinstance(derived.get("action_plan_items", []), list) else []:
            if isinstance(item, dict):
                if isinstance(item.get("event_id"), str):
                    ids.add(item["event_id"])
                for value in item.get("evidence_ids", []) if isinstance(item.get("evidence_ids", []), list) else []:
                    if isinstance(value, str):
                        ids.add(value)
                impact = item.get("projected_impact")
                if isinstance(impact, dict):
                    ids.update(value for value in impact.get("source_ids", []) if isinstance(value, str))
    return ids


def _validate_generated_narrative(raw: dict[str, Any], facts: FactsSnapshot, allowed_ids: set[str] | None = None) -> GroundedNarrative:
    narrative = GroundedNarrative.model_validate(raw)
    allowed_ids = allowed_ids if allowed_ids is not None else facts.fact_ids
    all_text = [narrative.summary, *narrative.lines]
    for rec in narrative.recommendations:
        all_text.extend([rec.title, rec.rationale, rec.next_step])
        unknown_refs = set(rec.fact_refs) - allowed_ids
        if unknown_refs:
            raise ValueError("LLM output referenced unknown fact IDs")
    if any(_FORBIDDEN_LLM_TEXT.search(part) for part in all_text):
        raise ValueError("LLM prose included a numeric claim or citation")
    return narrative


def _short_text(value: str | None, maximum: int = 180) -> str:
    """Normalize untrusted persisted prose before putting it into a bounded UI line."""
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) <= maximum:
        return cleaned
    return cleaned[: maximum - 1].rstrip() + "…"


def _event_recommendation(event) -> Recommendation:
    kind = event.event_type.lower()
    if "energy" in kind or "power" in kind:
        title = "Check room state and power evidence"
        rationale = "The alert suggests likely energy waste, but the supplied evidence and occupancy state should be inspected."
        next_step = "Review source freshness and threshold details, then request a human-approved action and verify the post-action reading."
    elif "water" in kind or "flow" in kind or "leak" in kind:
        title = "Validate the water-flow pattern"
        rationale = "A persistent flow pattern may indicate an anomaly, but it does not by itself prove a leak."
        next_step = "Compare the meter trend with the expected low-use period and arrange an inspection if the signal persists."
    elif "sensor" in kind or "evidence" in kind:
        title = "Restore evidence health"
        rationale = "Missing or unhealthy evidence cannot establish either a normal state or a confirmed incident."
        next_step = "Inspect connectivity and freshness, then reassess the event only after suitable evidence returns."
    elif "bin" in kind or "waste" in kind:
        title = "Confirm the bin state"
        rationale = "The event may describe a waste overflow, but detector or manual evidence needs confirmation."
        next_step = "Ask an operator to confirm the physical state before dispatching a collection."
    else:
        title = "Review the linked evidence"
        rationale = event.explanation or "The event needs evidence-led review before intervention."
        next_step = "Inspect the trigger rule and source records, then choose a human-approved next step."
    return Recommendation(
        title=title,
        rationale=redact_sensitive_text(rationale, 260) or "Review the supplied evidence.",
        next_step=next_step,
        fact_refs=[event.id, *event.evidence_ids],
    )


def _template_narrative(operation: str, facts: FactsSnapshot, event_id: str | None = None, extra: dict[str, Any] | None = None, question: str | None = None) -> GroundedNarrative:
    relevant_events = [e for e in facts.events if not event_id or e.id == event_id]
    if operation == "ask":
        if event_id and not relevant_events:
            return GroundedNarrative(
                summary="I could not find that event in the current facts snapshot, so I will not infer its state.",
                lines=[
                    f"Facts source status: {facts.source_status}.",
                    "No event with that identifier was supplied by the persisted facts provider.",
                    "Refresh the event list or inspect the source records before acting.",
                ],
                recommendations=[Recommendation(
                    title="Refresh event evidence",
                    rationale="The requested event is not present in the current snapshot.",
                    next_step="Reload persisted events and retry with the exact event identifier.",
                    fact_refs=[],
                )],
            )
        lowered = (question or "").casefold()
        if not event_id and any(term in lowered for term in ("priorit", "which issue", "open issue", "what should we fix", "highest impact")):
            items = action_plan_items(facts)
            by_id = {event.id: event for event in facts.events}
            top = items[:3]
            if top:
                ranked = "; ".join(f"{item.priority}: {item.event_type} ({item.event_id})" for item in top)
                refs = sorted({item.event_id for item in top})
                recommendations = [_event_recommendation(by_id[item.event_id]) for item in top if item.event_id in by_id]
                return GroundedNarrative(
                    summary="The backend priority mapping is based on the event severity field and current open status; it is not a learned ranking score.",
                    lines=[f"Highest-priority open items from the supplied facts: {ranked}.", "Treat severity as an ordering aid, not as proof of impact or a substitute for evidence quality.", "Review source freshness and event evidence before asking an operator to approve an intervention."],
                    recommendations=recommendations[:4],
                )
            return GroundedNarrative(
                summary="There are no open events in the supplied facts snapshot to prioritize.",
                lines=["An empty event list does not prove every source is healthy.", f"Facts source status is {facts.source_status}.", "Review unavailable and stale evidence before concluding no work is needed."],
                recommendations=[Recommendation(title="Check system health", rationale="Unknown inputs should not be interpreted as normal operation.", next_step="Review source freshness and preflight status.", fact_refs=[])],
            )
        if not event_id and any(term in lowered for term in ("what evidence", "missing evidence", "evidence is missing", "unknown", "stale sensor")):
            selected = relevant_events[0] if relevant_events else None
            unhealthy = [r for r in facts.readings if r.source_health.value != "HEALTHY"]
            if selected:
                known_evidence = ", ".join(selected.evidence_ids) if selected.evidence_ids else "none supplied"
                missing_detail = "; ".join(f"{r.id} ({r.source_health.value})" for r in unhealthy[:8]) or "no unhealthy reading was listed in this snapshot"
                return GroundedNarrative(
                    summary=f"Evidence review for {selected.event_type}: the event links to {known_evidence}.",
                    lines=[f"Rule: {selected.trigger_rule or 'UNAVAILABLE'}.", f"Reading-health review: {missing_detail}.", "Missing evidence must remain unknown; it is not evidence that the room is empty or the resource is normal."],
                    recommendations=[_event_recommendation(selected)],
                )
            return GroundedNarrative(
                summary=f"The facts provider supplied {len(unhealthy)} readings not marked HEALTHY.",
                lines=[f"Source status: {facts.source_status}.", f"Unavailable inputs: {', '.join(facts.unavailable_inputs) if facts.unavailable_inputs else 'none explicitly listed'}.", "Inspect event-linked source IDs and freshness before making an operational claim."],
                recommendations=[Recommendation(title="Restore evidence health", rationale="Stale or unknown signals cannot establish normal operation.", next_step="Restore affected feeds and reassess only when suitable evidence is available.", fact_refs=[r.id for r in unhealthy[:8]])],
            )
        if not event_id and any(term in lowered for term in ("verified vs simulated", "verified or simulated", "simulated vs", "verified savings", "what is verified")):
            records = [*facts.readings, *facts.events, *facts.actions, *facts.ledger_entries]
            by_origin = {p.value: sum(1 for record in records if record.provenance == p) for p in Provenance}
            verified_actions = sum(1 for action in facts.actions if action.status.upper() == "VERIFIED_SUCCESS")
            failed_actions = sum(1 for action in facts.actions if action.status.upper() in {"COMMAND_FAILED", "ACK_TIMEOUT", "VERIFICATION_FAILED", "VERIFICATION_TIMEOUT", "REJECTED"})
            verified_simulated = sum(1 for entry in facts.ledger_entries if entry.provenance == Provenance.SIMULATED and entry.verification_status.upper() == "VERIFIED_SUCCESS")
            return GroundedNarrative(
                summary="Verified simulated outcomes and measured real data are tracked separately; an acknowledgement alone is not a verified outcome.",
                lines=[f"Record provenance counts: REAL {by_origin['REAL']}, SIMULATED {by_origin['SIMULATED']}, DERIVED {by_origin['DERIVED']}, UNKNOWN {by_origin['UNKNOWN']}.", f"Action states: VERIFIED_SUCCESS {verified_actions}; failed or timed-out states {failed_actions}.", f"Verified simulated ledger entries: {verified_simulated}; these are simulator outcomes, not measured campus savings."],
                recommendations=[Recommendation(title="Inspect the impact ledger", rationale="Each ledger entry should show its action, source IDs, calculation inputs and verification state.", next_step="Compare the ledger record with the append-only action history and linked post-action readings.", fact_refs=[entry.id for entry in facts.ledger_entries[:8]])],
            )
        if not event_id and any(term in lowered for term in ("what if", "what-if", "reduce power", "two hours", "intervention")):
            return GroundedNarrative(
                summary="Use the What-If Arena for a numeric projection; this chat response will not invent a baseline or calculate impact in free-form prose.",
                lines=["Choose a room and duration, then select a reduction scenario.", "The backend will calculate energy and will leave cost or carbon unavailable if the configured factors are missing.", "Every what-if result is PROJECTED_NOT_VERIFIED until the separate action workflow confirms an outcome."],
                recommendations=[Recommendation(title="Run a what-if scenario", rationale="A deterministic baseline and explicit intervention assumptions are needed for a defensible projection.", next_step="Open Campus What-If Arena, select the room and duration, and compare interventions before deciding.", fact_refs=[])],
            )
        if relevant_events:
            event = relevant_events[0]
            evidence_text = _short_text(", ".join(event.evidence_ids), 90) if event.evidence_ids else "no evidence IDs were supplied"
            detail = _short_text(event.explanation or "No rule explanation was supplied by the facts provider.", 105)
            trigger_rule = _short_text(event.trigger_rule or "UNAVAILABLE", 150)
            return GroundedNarrative(
                summary=f"{event.event_type} is recorded as {event.status} with {event.severity} severity; the source label is {event.provenance.value}.",
                lines=[
                    f"Trigger rule: {trigger_rule}.",
                    f"Evidence references: {evidence_text}; explanation: {detail}",
                    "This is an event interpretation, not proof of a physical fault or a verified outcome.",
                ],
                recommendations=[_event_recommendation(event)],
            )
        return GroundedNarrative(
            summary=f"The current snapshot contains {len(facts.readings)} readings, {len(facts.events)} events, and {len(facts.actions)} actions; source status is {facts.source_status}.",
            lines=[
                "Numeric metrics are assembled separately from stored facts, not generated by the language model.",
                f"Available provenance counts: REAL {sum(1 for x in [*facts.readings, *facts.events, *facts.actions, *facts.ledger_entries] if x.provenance == Provenance.REAL)}, SIMULATED {sum(1 for x in [*facts.readings, *facts.events, *facts.actions, *facts.ledger_entries] if x.provenance == Provenance.SIMULATED)}, DERIVED {sum(1 for x in [*facts.readings, *facts.events, *facts.actions, *facts.ledger_entries] if x.provenance == Provenance.DERIVED)}, UNKNOWN {sum(1 for x in [*facts.readings, *facts.events, *facts.actions, *facts.ledger_entries] if x.provenance == Provenance.UNKNOWN)}.",
                "No live-campus or verified-savings claim is made unless supported by linked evidence and action status.",
            ],
            recommendations=[Recommendation(
                title="Connect the persisted facts provider",
                rationale="The copilot can only explain records supplied by the backend facts adapter.",
                next_step="Register the Account Two facts service and retry the question with a current snapshot.",
                fact_refs=[],
            )],
        )

    if operation == "weekly_report":
        return GroundedNarrative(
            summary="This report separates available observations, scenario data, calculated estimates, and unknown inputs.",
            lines=[
                "Use provenance and observation freshness to judge how much confidence the evidence deserves.",
                "A successful simulated verification is not the same as independently measured campus savings.",
                "Missing tariffs, emission factors, readings, or source health remain unavailable rather than being replaced with zero.",
            ],
            recommendations=[Recommendation(
                title="Review evidence before reporting impact",
                rationale="Impact claims should be traceable to source records and the calculation assumptions used.",
                next_step="Inspect the linked events, actions, ledger entries, and any unavailable-input warnings.",
                fact_refs=[],
            )],
        )

    if operation == "action_plan":
        items = (extra or {}).get("action_plan_items", [])
        if not items:
            lines = [
                "No open events were supplied by the current facts snapshot.",
                "This does not imply that every campus resource is healthy if data are missing or stale.",
                "Keep sensor-health and unavailable-evidence states visible during review.",
            ]
            summary = "There are no open events in the supplied facts snapshot to convert into a prioritized action plan."
            recs = [Recommendation(
                title="Check system health",
                rationale="An empty event list is not proof that sensors and source feeds are healthy.",
                next_step="Review the preflight and source-freshness indicators before concluding that no work is needed.",
                fact_refs=[],
            )]
        else:
            lines = [
                "The backend orders open events by the explicit severity-to-priority mapping.",
                "Each item is a suggested operator step; no device action is issued by the copilot.",
                "Confirm evidence freshness and require independent verification before recording impact.",
            ]
            summary = "The action plan is ordered by a transparent backend rule; the language model only explains the plan."
            recs = [_event_recommendation(e) for e in relevant_events[:4]] if relevant_events else []
        return GroundedNarrative(summary=summary, lines=lines, recommendations=recs[:4])

    if operation.startswith("what_if"):
        return GroundedNarrative(
            summary="This what-if result is a projection computed by deterministic backend formulas, not verified savings.",
            lines=[
                "The estimate depends on the baseline, duration, and intervention assumptions shown with the result.",
                "Cost and carbon projections are omitted when their configured factors are unavailable.",
                "Compare the projected outcome with post-action sensor readings before describing any result as verified.",
            ],
            recommendations=[Recommendation(
                title="Verify against post-action readings",
                rationale="A scenario estimate predicts a possible outcome and does not establish that a real action worked.",
                next_step="Store a pre-action baseline, request human approval, and compare fresh post-action readings against the configured threshold.",
                fact_refs=[],
            )],
        )

    return GroundedNarrative(
        summary="The service is operating in deterministic template mode.",
        lines=[
            "Backend calculations remain authoritative for numeric facts.",
            "Available data origins and assumptions are attached to the response.",
            "Review unknown and simulated values before making operational claims.",
        ],
        recommendations=[],
    )


def _in_report_window(value: datetime | None, start: datetime, end: datetime) -> bool:
    return value is not None and value.tzinfo is not None and start <= value.astimezone(timezone.utc) < end


def _weekly_report_cache_key(facts: FactsSnapshot, start: datetime, end: datetime, max_records: int) -> str:
    """Cache prose only for the same period and same scoped evidence content."""
    context = facts_context(facts, max_records)
    # Snapshot timestamps change on refresh even when the report inputs do not. Exclude
    # those bookkeeping fields, but retain all bounded records, assumptions, factors and
    # truncation counts so a changed input cannot silently reuse an unrelated narrative.
    context.pop("snapshot_id", None)
    context.pop("generated_at", None)
    payload = {
        "period_start": start.astimezone(timezone.utc).isoformat(),
        "period_end": end.astimezone(timezone.utc).isoformat(),
        "context": context,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"weekly_report:{digest}"


class CopilotService:
    def __init__(self, settings: CopilotSettings | None = None, cache: LastGoodNarrativeCache | None = None):
        self.settings = settings or CopilotSettings.from_env()
        self.cache = cache or LastGoodNarrativeCache(self.settings.cache_path)

    async def _get_narrative(
        self,
        operation: str,
        facts: FactsSnapshot,
        *,
        question: str | None = None,
        event_id: str | None = None,
        extra: dict[str, Any] | None = None,
        cache_key: str | None = None,
        force_template: bool = False,
    ) -> tuple[GroundedNarrative, CopilotMode, datetime | None]:
        context = facts_context(facts, self.settings.max_context_records, event_id)
        if extra:
            # Only module-owned deterministic data is added; never include request headers,
            # arbitrary app state, camera frames, or credentials.
            context["derived_context"] = extra
        allowed_ids = _context_fact_ids(context)
        if force_template:
            return _template_narrative(operation, facts, event_id, extra, question), CopilotMode.TEMPLATE, None
        if self.settings.provider_configured:
            context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
            for _attempt in range(2):
                try:
                    safe_question = redact_sensitive_text(question, 1200) if question else None
                    content = await request_narrative(self.settings, operation, context_json, question=safe_question)
                    raw = parse_narrative_json(content)
                    narrative = _validate_generated_narrative(raw, facts, allowed_ids)
                    if cache_key:
                        self.cache.set(cache_key, narrative.model_dump(mode="json"))
                    return narrative, CopilotMode.LLM, None
                except Exception:
                    # Retry once. Do not log the question, facts, key, provider body, or exception.
                    # Provider adapters are pluggable, so unexpected client errors must also degrade safely.
                    continue

        if cache_key:
            cached = self.cache.get(cache_key)
            if cached:
                try:
                    narrative = GroundedNarrative.model_validate(cached["narrative"])
                    # IDs in cached prose may refer to facts no longer present. Drop invalid refs.
                    known = allowed_ids
                    for recommendation in narrative.recommendations:
                        recommendation.fact_refs = [ref for ref in recommendation.fact_refs if ref in known]
                    stamp = datetime.fromisoformat(cached["created_at"])
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=timezone.utc)
                    return narrative, CopilotMode.CACHED, stamp
                except (ValidationError, ValueError, TypeError):
                    pass

        return _template_narrative(operation, facts, event_id, extra, question), CopilotMode.TEMPLATE, None

    async def ask(self, question: str, facts: FactsSnapshot, event_id: str | None = None, force_template: bool = False) -> CopilotAnswer:
        narrative, mode, cached_at = await self._get_narrative("ask", facts, question=question, event_id=event_id, force_template=force_template)
        limitations = [
            "Language-model text is an interpretation; numeric facts come from backend records.",
            "Recommendations do not execute actions and require operator review.",
        ]
        if facts.source_status != "HEALTHY":
            limitations.append(f"Facts source status is {facts.source_status}; live data completeness has not been established.")
        return CopilotAnswer(
            mode=mode,
            cached_at=cached_at,
            summary=narrative.summary,
            lines=narrative.lines,
            recommendations=narrative.recommendations,
            fact_references=fact_references(facts),
            grounding=grounding_from_facts(facts),
            limitations=limitations,
        )

    async def weekly_report(
        self,
        facts: FactsSnapshot,
        now: datetime | None = None,
        period_start: datetime | None = None,
    ) -> WeeklyReport:
        end = now or datetime.now(timezone.utc)
        if end.tzinfo is None:
            raise ValueError("report time must be timezone-aware")
        end = end.astimezone(timezone.utc)
        if period_start is None:
            start = end - timedelta(days=7)
        else:
            if period_start.tzinfo is None:
                raise ValueError("period_start must be timezone-aware")
            start = period_start.astimezone(timezone.utc)
            if start >= end:
                raise ValueError("period_start must be earlier than period_end")
        metrics = build_weekly_metrics(facts, start, end)
        readings_in_period = [r for r in facts.readings if _in_report_window(r.observed_at, start, end)]
        events_in_period = [e for e in facts.events if _in_report_window(e.first_seen_at, start, end) or _in_report_window(e.last_updated_at, start, end)]
        actions_in_period = [a for a in facts.actions if _in_report_window(a.requested_at, start, end) or _in_report_window(a.updated_at, start, end)]
        ledger_in_period = [l for l in facts.ledger_entries if _in_report_window(l.created_at, start, end)]
        report_facts = facts.model_copy(update={
            "readings": readings_in_period,
            "events": events_in_period,
            "actions": actions_in_period,
            "ledger_entries": ledger_in_period,
        })
        report_readings = [ReportReadingSummary(
            id=reading.id, resource_type=redact_sensitive_text(reading.resource_type, 80) or "resource",
            reading_type=redact_sensitive_text(reading.reading_type, 80), value=reading.value, unit=reading.unit,
            observed_at=reading.observed_at, provenance=reading.provenance, source_health=reading.source_health,
            freshness_seconds=reading.freshness_seconds, building_id=reading.building_id, room_id=reading.room_id,
        ) for reading in readings_in_period]
        report_events = [ReportEventSummary(
            id=e.id, event_type=redact_sensitive_text(e.event_type, 100) or "unknown", severity=e.severity, status=e.status,
            building_id=e.building_id, room_id=e.room_id, first_seen_at=e.first_seen_at,
            last_updated_at=e.last_updated_at, trigger_rule=redact_sensitive_text(e.trigger_rule, 300),
            explanation=redact_sensitive_text(e.explanation, 1200), evidence_ids=e.evidence_ids,
            provenance=e.provenance, projected_impact=e.projected_impact.model_copy(update={
                "assumptions": [redact_sensitive_text(value, 500) or "" for value in e.projected_impact.assumptions]
            }),
        ) for e in events_in_period]
        report_actions = [ReportActionSummary(
            id=a.id, event_id=a.event_id, status=a.status, requested_at=a.requested_at,
            updated_at=a.updated_at, verification_summary=redact_sensitive_text(a.verification_summary, 600),
            evidence_ids=a.evidence_ids, provenance=a.provenance,
        ) for a in actions_in_period]
        report_ledger = [ReportLedgerSummary.model_validate(l.model_dump()) for l in ledger_in_period]
        evidence_ids = sorted({
            identifier
            for event in events_in_period
            for identifier in [event.id, *event.evidence_ids]
        } | {
            source_id
            for ledger in ledger_in_period
            for source_id in [ledger.id, *ledger.source_ids]
        })[:250]
        cache_key = _weekly_report_cache_key(report_facts, start, end, self.settings.max_context_records)
        narrative, mode, cached_at = await self._get_narrative("weekly_report", report_facts, cache_key=cache_key)
        trust_lines = [
            "Verified measured totals are restricted to REAL ledger entries marked VERIFIED_SUCCESS.",
            "Verified simulated totals indicate that a simulated workflow passed verification; they are not measured campus savings.",
            "Projected, unverified, and missing-factor values are not treated as verified impact.",
        ]
        limitations = [
            "This report describes only the records returned by the configured facts provider.",
            "LLM/CACHED/TEMPLATE identifies the source of narrative text, not the origin of numeric metrics.",
        ]
        if mode == CopilotMode.CACHED and cached_at:
            limitations.append("Narrative text is cached from an earlier successful provider call; review it against the current metrics and evidence IDs.")
        if facts.source_status != "HEALTHY":
            limitations.append(f"Facts source status is {facts.source_status}; this is not a complete live-campus measurement report.")
        if metrics.reading_count == 0:
            limitations.append("No readings were provided for this reporting window; resource totals may be unavailable.")
        report_unavailable_inputs = [redact_sensitive_text(value, 240) or "UNAVAILABLE" for value in facts.unavailable_inputs]
        reporting_currencies = {entry.cost_currency for entry in ledger_in_period if entry.cost_amount is not None and entry.cost_currency}
        missing_cost_currency = any(entry.cost_amount is not None and not entry.cost_currency for entry in ledger_in_period)
        if len(reporting_currencies) > 1 or missing_cost_currency:
            report_unavailable_inputs.append("Aggregated cost total is UNAVAILABLE because relevant ledger cost entries have mixed or missing currencies.")
        return WeeklyReport(
            report_id=f"weekly-{end.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}",
            generated_at=datetime.now(timezone.utc),
            period_start=start,
            period_end=end,
            mode=mode,
            cached_at=cached_at,
            summary=narrative.summary,
            narrative_lines=narrative.lines,
            metrics=metrics,
            readings=report_readings,
            events=report_events,
            actions=report_actions,
            ledger_entries=report_ledger,
            verified_vs_simulated=trust_lines,
            recommendations=narrative.recommendations,
            assumptions={redact_sensitive_text(key, 100) or "assumption": redact_sensitive_text(value, 500) or "" for key, value in facts.assumptions.items()},
            unavailable_inputs=list(dict.fromkeys(report_unavailable_inputs)),
            evidence_ids=evidence_ids,
            limitations=limitations,
        )

    async def action_plan(self, facts: FactsSnapshot) -> ActionPlan:
        items = action_plan_items(facts)
        items_payload = [item.model_dump(mode="json") for item in items]
        narrative, mode, cached_at = await self._get_narrative(
            "action_plan", facts, extra={"action_plan_items": items_payload}, cache_key="action_plan"
        )
        limitations = [
            "The backend priority mapping orders events by severity; the LLM does not assign scores or reorder items.",
            "Items are recommendations only. Any real-world command requires separate human approval and action verification.",
        ]
        if facts.source_status != "HEALTHY":
            limitations.append(f"Facts source status is {facts.source_status}; check preflight and data freshness.")
        return ActionPlan(
            mode=mode,
            cached_at=cached_at,
            summary=narrative.summary,
            narrative_lines=narrative.lines,
            items=items,
            assumptions={redact_sensitive_text(key, 100) or "assumption": redact_sensitive_text(value, 500) or "" for key, value in facts.assumptions.items()},
            unavailable_inputs=[redact_sensitive_text(value, 240) or "UNAVAILABLE" for value in facts.unavailable_inputs],
            limitations=limitations,
        )

    async def explain_what_if(self, result: dict[str, Any], facts: FactsSnapshot) -> tuple[GroundedNarrative, CopilotMode, datetime | None]:
        return await self._get_narrative(
            "what_if_explanation",
            facts,
            extra={"deterministic_what_if_result": result},
        )
