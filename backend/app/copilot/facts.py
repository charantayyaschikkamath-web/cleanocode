from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .privacy import redact_sensitive_text
from .models import (
    ActionFact,
    EventFact,
    FactsGrounding,
    FactsSnapshot,
    FactReference,
    LedgerFact,
    Provenance,
    ReadingFact,
)


def get_facts_snapshot() -> FactsSnapshot:
    """Default integration seam; Account 9 must override it with a persisted-data adapter.

    An unconfigured seam returns an honest empty snapshot rather than fabricated demo values.
    """
    return FactsSnapshot(
        source_status="NOT_CONFIGURED",
        assumptions={"data_source": "No persisted facts provider has been registered."},
        unavailable_inputs=["persisted campus readings", "persisted events", "action history", "impact ledger"],
    )


def grounding_from_facts(facts: FactsSnapshot) -> FactsGrounding:
    records: list[Any] = [*facts.readings, *facts.events, *facts.actions, *facts.ledger_entries]
    counts = {p.value: 0 for p in Provenance}
    for record in records:
        provenance = getattr(record, "provenance", Provenance.UNKNOWN)
        counts[provenance.value] = counts.get(provenance.value, 0) + 1
    return FactsGrounding(
        real_count=counts[Provenance.REAL.value],
        simulated_count=counts[Provenance.SIMULATED.value],
        derived_count=counts[Provenance.DERIVED.value],
        unknown_count=counts[Provenance.UNKNOWN.value],
        source_status=facts.source_status,
        assumptions={redact_sensitive_text(key, 100) or "assumption": redact_sensitive_text(value, 500) or "" for key, value in facts.assumptions.items()},
        unavailable_inputs=[redact_sensitive_text(value, 240) or "UNAVAILABLE" for value in facts.unavailable_inputs],
    )


def fact_references(facts: FactsSnapshot) -> list[FactReference]:
    refs: list[FactReference] = []
    refs.extend(FactReference(id=r.id, kind="reading", label=f"{redact_sensitive_text(r.resource_type, 80) or 'resource'} reading", provenance=r.provenance) for r in facts.readings)
    refs.extend(FactReference(id=e.id, kind="event", label=redact_sensitive_text(e.event_type, 100) or "event", provenance=e.provenance) for e in facts.events)
    refs.extend(FactReference(id=a.id, kind="action", label=f"Action {a.status}", provenance=a.provenance) for a in facts.actions)
    refs.extend(FactReference(id=l.id, kind="ledger", label=f"Ledger {l.verification_status}", provenance=l.provenance) for l in facts.ledger_entries)
    known = {r.id for r in refs}
    for event in facts.events:
        for evidence_id in event.evidence_ids:
            if evidence_id not in known:
                refs.append(FactReference(id=evidence_id, kind="evidence", label="Linked event evidence", provenance=event.provenance))
                known.add(evidence_id)
    for action in facts.actions:
        for evidence_id in action.evidence_ids:
            if evidence_id not in known:
                refs.append(FactReference(id=evidence_id, kind="evidence", label="Linked action evidence", provenance=action.provenance))
                known.add(evidence_id)
    for ledger in facts.ledger_entries:
        for evidence_id in ledger.source_ids:
            if evidence_id not in known:
                refs.append(FactReference(id=evidence_id, kind="evidence", label="Linked ledger source", provenance=ledger.provenance))
                known.add(evidence_id)
    return refs


def facts_context(facts: FactsSnapshot, max_records: int = 40, event_id: str | None = None) -> dict[str, Any]:
    """Create a bounded, privacy-minimised context for the LLM.

    Raw camera/video frames and user identity are not representable in FactsSnapshot.
    Textual source fields are explicitly framed as untrusted data in the provider prompt.
    """
    readings = sorted(facts.readings, key=lambda r: r.observed_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:max_records]
    events = sorted(facts.events, key=lambda e: e.last_updated_at or e.first_seen_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if event_id:
        events = [e for e in events if e.id == event_id]
    events = events[:max_records]
    actions = sorted(facts.actions, key=lambda a: a.updated_at or a.requested_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:max_records]
    ledgers = sorted(facts.ledger_entries, key=lambda l: l.created_at, reverse=True)[:max_records]
    return {
        "snapshot_id": facts.snapshot_id,
        "generated_at": facts.generated_at.isoformat(),
        "source_status": facts.source_status,
        "readings": [
            {
                "id": r.id,
                "resource_type": redact_sensitive_text(r.resource_type, 80),
                "reading_type": redact_sensitive_text(r.reading_type, 80),
                "value": str(r.value) if r.value is not None else None,
                "unit": r.unit,
                "observed_at": r.observed_at.isoformat() if r.observed_at else None,
                "provenance": r.provenance.value,
                "source_health": r.source_health.value,
                "freshness_seconds": r.freshness_seconds,
                "building_id": r.building_id,
                "room_id": r.room_id,
            }
            for r in readings
        ],
        "events": [
            {
                "id": e.id,
                "event_type": redact_sensitive_text(e.event_type, 100) or "unknown",
                "severity": e.severity,
                "status": e.status,
                "building_id": e.building_id,
                "room_id": e.room_id,
                "first_seen_at": e.first_seen_at.isoformat() if e.first_seen_at else None,
                "last_updated_at": e.last_updated_at.isoformat() if e.last_updated_at else None,
                "trigger_rule": redact_sensitive_text(e.trigger_rule, 300),
                "explanation": redact_sensitive_text(e.explanation, 1200),
                "evidence_ids": e.evidence_ids,
                "provenance": e.provenance.value,
                "projected_impact": {
                    **e.projected_impact.model_dump(mode="json"),
                    "assumptions": [redact_sensitive_text(value, 500) or "" for value in e.projected_impact.assumptions],
                },
            }
            for e in events
        ],
        "actions": [
            {
                "id": a.id,
                "event_id": a.event_id,
                "status": a.status,
                "requested_at": a.requested_at.isoformat() if a.requested_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                "verification_summary": redact_sensitive_text(a.verification_summary, 600),
                "evidence_ids": a.evidence_ids,
                "provenance": a.provenance.value,
            }
            for a in actions
        ],
        "ledger_entries": [
            {
                "id": l.id,
                "action_id": l.action_id,
                "created_at": l.created_at.isoformat(),
                "verification_status": l.verification_status,
                "provenance": l.provenance.value,
                "energy_kwh": str(l.energy_kwh) if l.energy_kwh is not None else None,
                "water_liters": str(l.water_liters) if l.water_liters is not None else None,
                "cost_amount": str(l.cost_amount) if l.cost_amount is not None else None,
                "cost_currency": l.cost_currency,
                "co2_kg": str(l.co2_kg) if l.co2_kg is not None else None,
                "source_ids": l.source_ids,
                "calculation_version": l.calculation_version,
            }
            for l in ledgers
        ],
        "configured_factors": {
            "energy_tariff_per_kwh": str(facts.energy_tariff_per_kwh) if facts.energy_tariff_per_kwh is not None else None,
            "energy_tariff_currency": facts.energy_tariff_currency,
            "co2_factor_kg_per_kwh": str(facts.co2_factor_kg_per_kwh) if facts.co2_factor_kg_per_kwh is not None else None,
            "water_tariff_per_m3": str(facts.water_tariff_per_m3) if facts.water_tariff_per_m3 is not None else None,
            "water_tariff_currency": facts.water_tariff_currency,
        },
        "assumptions": {redact_sensitive_text(k, 100) or "assumption": redact_sensitive_text(v, 500) or "" for k, v in facts.assumptions.items()},
        "unavailable_inputs": [redact_sensitive_text(value, 240) or "UNAVAILABLE" for value in facts.unavailable_inputs],
        "truncated": {
            "readings": max(0, len(facts.readings) - len(readings)),
            "events": max(0, len(facts.events) - len(events)),
            "actions": max(0, len(facts.actions) - len(actions)),
            "ledger_entries": max(0, len(facts.ledger_entries) - len(ledgers)),
        },
    }
