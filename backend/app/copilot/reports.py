from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html import escape

from .privacy import redact_sensitive_text
from .csv_safety import SpreadsheetSafeCSVWriter
from .models import (
    ActionFact,
    ActionPlanItem,
    EventFact,
    FactsSnapshot,
    ImpactTotals,
    Provenance,
    WeeklyReportMetrics,
)

OPEN_STATUSES = {"OPEN", "PENDING", "NEW", "ACKNOWLEDGED", "INVESTIGATING", "IN_PROGRESS"}
FAILED_ACTION_STATES = {
    "COMMAND_FAILED", "ACK_TIMEOUT", "VERIFICATION_FAILED", "VERIFICATION_TIMEOUT",
    "REJECTED", "FAILED", "TIMED_OUT",
}
VERIFIED_STATE = "VERIFIED_SUCCESS"


def _in_window(value: datetime | None, start: datetime, end: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        return False
    return start <= value.astimezone(timezone.utc) < end


def _sum_known(entries: list, field: str, currency: str | None = None) -> tuple[Decimal | None, int]:
    known = [getattr(entry, field) for entry in entries if getattr(entry, field) is not None]
    total = sum(known, Decimal("0")) if known else None
    missing = sum(1 for entry in entries if getattr(entry, field) is None)
    return total, missing


def _impact_totals(entries: list) -> ImpactTotals:
    energy, energy_missing = _sum_known(entries, "energy_kwh")
    water, water_missing = _sum_known(entries, "water_liters")
    cost, cost_missing = _sum_known(entries, "cost_amount")
    co2, co2_missing = _sum_known(entries, "co2_kg")
    currencies = {entry.cost_currency for entry in entries if entry.cost_currency}
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    if len(currencies) > 1:
        # Never combine amounts that use different currencies into a misleading total.
        cost = None
    # Missing means every value on an entry is absent; per-metric missing fields are
    # represented by unavailable_inputs and the raw entries included in the report.
    all_missing = sum(
        1 for entry in entries
        if all(getattr(entry, name) is None for name in ("energy_kwh", "water_liters", "cost_amount", "co2_kg"))
    )
    return ImpactTotals(
        energy_kwh=energy,
        water_liters=water,
        cost_amount=cost,
        cost_currency=currency,
        co2_kg=co2,
        entries_count=len(entries),
        missing_value_count=all_missing,
    )


def build_weekly_metrics(facts: FactsSnapshot, period_start: datetime, period_end: datetime) -> WeeklyReportMetrics:
    readings = [r for r in facts.readings if _in_window(r.observed_at, period_start, period_end)]
    events = [
        e for e in facts.events
        if _in_window(e.first_seen_at, period_start, period_end) or _in_window(e.last_updated_at, period_start, period_end)
    ]
    actions = [
        a for a in facts.actions
        if _in_window(a.requested_at, period_start, period_end) or _in_window(a.updated_at, period_start, period_end)
    ]
    entries = [l for l in facts.ledger_entries if _in_window(l.created_at, period_start, period_end)]

    by_provenance = {p.value: 0 for p in Provenance}
    for reading in readings:
        by_provenance[reading.provenance.value] += 1

    by_severity: dict[str, int] = {}
    for event in events:
        level = event.severity.strip().lower() or "unknown"
        by_severity[level] = by_severity.get(level, 0) + 1

    verified_measured = [
        e for e in entries
        if e.provenance == Provenance.REAL and e.verification_status.upper() == VERIFIED_STATE
    ]
    verified_simulated = [
        e for e in entries
        if e.provenance == Provenance.SIMULATED and e.verification_status.upper() == VERIFIED_STATE
    ]
    measured_unverified = [
        e for e in entries
        if e.provenance == Provenance.REAL and e.verification_status.upper() != VERIFIED_STATE
    ]
    projected_or_unverified = [
        e for e in entries
        if e not in verified_measured and e not in verified_simulated and e not in measured_unverified
    ]

    return WeeklyReportMetrics(
        reading_count=len(readings),
        readings_by_provenance=by_provenance,
        events_total=len(events),
        events_open=sum(1 for event in events if event.status.upper() in OPEN_STATUSES),
        events_by_severity=by_severity,
        actions_total=len(actions),
        actions_verified_success=sum(1 for action in actions if action.status.upper() == VERIFIED_STATE),
        actions_failed_or_timed_out=sum(1 for action in actions if action.status.upper() in FAILED_ACTION_STATES),
        verified_measured=_impact_totals(verified_measured),
        measured_unverified=_impact_totals(measured_unverified),
        verified_simulated=_impact_totals(verified_simulated),
        projected_or_unverified=_impact_totals(projected_or_unverified),
    )


def _severity_priority(event: EventFact) -> str:
    severity = event.severity.strip().lower()
    if severity in {"critical", "high", "urgent"}:
        return "P1"
    if severity in {"medium", "moderate"}:
        return "P2"
    if severity in {"low", "info", "informational"}:
        return "P3"
    return "REVIEW"


def _open_event(event: EventFact) -> bool:
    return event.status.upper() in OPEN_STATUSES


def action_plan_items(facts: FactsSnapshot) -> list[ActionPlanItem]:
    items: list[ActionPlanItem] = []
    for event in sorted(
        (e for e in facts.events if _open_event(e)),
        key=lambda e: (
            {"P1": 0, "P2": 1, "P3": 2, "REVIEW": 3}[_severity_priority(e)],
            -(e.last_updated_at or e.first_seen_at or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
            e.id,
        ),
    ):
        event_type = event.event_type.lower()
        if "energy" in event_type or "power" in event_type:
            reason = "The event suggests possible energy waste; the event evidence and occupancy state need review."
            step = "Review the room state and baseline reading, then request a human-approved intervention and independently verify post-action readings."
        elif "water" in event_type or "flow" in event_type or "leak" in event_type:
            reason = "The event suggests a possible water-flow anomaly; a sensor pattern alone does not confirm a leak."
            step = "Inspect the meter trend and physical context, then route a maintenance inspection if the evidence remains consistent."
        elif "bin" in event_type or "waste" in event_type:
            reason = "The event indicates a possible waste-bin issue; detector or manual evidence may need confirmation."
            step = "Confirm the bin state with an operator inspection before dispatching collection."
        elif "room" in event_type or "occup" in event_type:
            reason = "Room-use efficiency depends on occupancy, schedule and resource signals agreeing."
            step = "Check the schedule and source freshness before changing room assignment or building controls."
        elif "sensor" in event_type or "evidence" in event_type or event_type == "unknown":
            reason = "Evidence health is insufficient to treat the room or resource as normal or abnormal."
            step = "Restore or inspect the sensor feed and leave the event unresolved until evidence is adequate."
        else:
            reason = redact_sensitive_text(event.explanation, 260) or "The event needs an evidence-led review before any intervention."
            step = "Inspect the linked evidence and rule threshold, then select a human-approved next action."
        items.append(ActionPlanItem(
            event_id=event.id,
            event_type=redact_sensitive_text(event.event_type, 100) or "unknown",
            priority=_severity_priority(event),
            reason=reason,
            proposed_next_step=step,
            evidence_ids=event.evidence_ids,
            provenance=event.provenance,
            projected_impact=event.projected_impact.model_copy(update={
                "assumptions": [redact_sensitive_text(value, 500) or "" for value in event.projected_impact.assumptions]
            }),
        ))
    return items


def report_csv(report) -> str:
    output = io.StringIO(newline="")
    writer = SpreadsheetSafeCSVWriter(output)
    writer.writerow(["section", "key", "value", "unit", "provenance", "source_ids"])
    writer.writerow(["report", "report_id", report.report_id, "", report.mode.value, ""])
    writer.writerow(["report", "period_start", report.period_start.isoformat(), "", "DERIVED", ""])
    writer.writerow(["report", "period_end", report.period_end.isoformat(), "", "DERIVED", ""])
    metric_units = {
        "reading_count": "readings", "events_total": "events", "events_open": "events",
        "actions_total": "actions", "actions_verified_success": "actions",
        "actions_failed_or_timed_out": "actions", "energy_kwh": "kWh",
        "water_liters": "L", "cost_amount": "configured currency", "co2_kg": "kg CO₂e",
    }
    metrics_payload = report.metrics.model_dump(mode="json")
    for key, value in metrics_payload.items():
        if isinstance(value, dict):
            unit_currency = value.get("cost_currency") or "configured currency"
            for subkey, subvalue in value.items():
                unit = unit_currency if subkey == "cost_amount" else metric_units.get(subkey, "")
                writer.writerow(["metric", f"{key}.{subkey}", subvalue if subvalue is not None else "UNAVAILABLE", unit, "DERIVED", ""])
        else:
            writer.writerow(["metric", key, value if value is not None else "UNAVAILABLE", metric_units.get(key, ""), "DERIVED", ""])
    for index, line in enumerate(report.verified_vs_simulated, start=1):
        writer.writerow(["trust", f"verified_vs_simulated_{index}", line, "", report.mode.value, ""])
    for reading in report.readings:
        refs = reading.id
        for field, value, unit in (
            ("resource_type", reading.resource_type, ""), ("reading_type", reading.reading_type, ""),
            ("value", reading.value, reading.unit or ""), ("observed_at", reading.observed_at.isoformat() if reading.observed_at else None, ""),
            ("source_health", reading.source_health.value, ""), ("freshness_seconds", reading.freshness_seconds, "seconds"),
            ("building_id", reading.building_id, ""), ("room_id", reading.room_id, ""),
        ):
            writer.writerow(["reading", f"{reading.id}.{field}", value if value is not None else "UNAVAILABLE", unit, reading.provenance.value, refs])
    for event in report.events:
        refs = ";".join(dict.fromkeys([event.id, *event.evidence_ids]))
        for field, value in (("event_type", event.event_type), ("severity", event.severity), ("status", event.status),
                             ("building_id", event.building_id), ("room_id", event.room_id),
                             ("trigger_rule", event.trigger_rule), ("explanation", event.explanation)):
            writer.writerow(["event", f"{event.id}.{field}", value if value is not None else "UNAVAILABLE", "", event.provenance.value, refs])
        writer.writerow(["event", f"{event.id}.first_seen_at", event.first_seen_at.isoformat() if event.first_seen_at else "UNAVAILABLE", "", "DERIVED", refs])
        writer.writerow(["event", f"{event.id}.evidence_ids", ";".join(event.evidence_ids) or "UNAVAILABLE", "", event.provenance.value, refs])
    for action in report.actions:
        refs = ";".join(dict.fromkeys([action.id, *action.evidence_ids]))
        for field, value in (("event_id", action.event_id), ("status", action.status), ("verification_summary", action.verification_summary)):
            writer.writerow(["action", f"{action.id}.{field}", value if value is not None else "UNAVAILABLE", "", action.provenance.value, refs])
        writer.writerow(["action", f"{action.id}.requested_at", action.requested_at.isoformat() if action.requested_at else "UNAVAILABLE", "", "DERIVED", refs])
    for entry in report.ledger_entries:
        refs = ";".join(dict.fromkeys([entry.id, *entry.source_ids]))
        writer.writerow(["ledger", f"{entry.id}.verification_status", entry.verification_status, "", entry.provenance.value, refs])
        writer.writerow(["ledger", f"{entry.id}.energy_kwh", entry.energy_kwh if entry.energy_kwh is not None else "UNAVAILABLE", "kWh", entry.provenance.value, refs])
        writer.writerow(["ledger", f"{entry.id}.water_liters", entry.water_liters if entry.water_liters is not None else "UNAVAILABLE", "L", entry.provenance.value, refs])
        writer.writerow(["ledger", f"{entry.id}.cost_amount", entry.cost_amount if entry.cost_amount is not None else "UNAVAILABLE", entry.cost_currency or "configured currency", entry.provenance.value, refs])
        writer.writerow(["ledger", f"{entry.id}.co2_kg", entry.co2_kg if entry.co2_kg is not None else "UNAVAILABLE", "kg CO₂e", entry.provenance.value, refs])
        writer.writerow(["ledger", f"{entry.id}.calculation_version", entry.calculation_version or "UNAVAILABLE", "", "DERIVED", refs])
    for key, value in report.assumptions.items():
        writer.writerow(["assumption", key, value, "", "DERIVED", ""])
    for key in report.unavailable_inputs:
        writer.writerow(["unavailable", key, "UNAVAILABLE", "", "UNKNOWN", ""])
    for source_id in report.evidence_ids:
        writer.writerow(["evidence", "source_id", source_id, "", "UNKNOWN", source_id])
    return output.getvalue()


def report_html(report) -> str:
    m = report.metrics
    metric_rows = [
        ("Sensor readings in period", m.reading_count, "records"),
        ("Events in period", m.events_total, "events"),
        ("Open events", m.events_open, "events"),
        ("Actions in period", m.actions_total, "actions"),
        ("Verified successful actions", m.actions_verified_success, "actions"),
        ("Failed or timed-out actions", m.actions_failed_or_timed_out, "actions"),
    ]
    def total_rows(label: str, totals: ImpactTotals) -> list[tuple[str, object, str]]:
        return [
            (f"{label}: energy", totals.energy_kwh if totals.energy_kwh is not None else "UNAVAILABLE", "kWh"),
            (f"{label}: water", totals.water_liters if totals.water_liters is not None else "UNAVAILABLE", "L"),
            (f"{label}: cost", totals.cost_amount if totals.cost_amount is not None else "UNAVAILABLE", totals.cost_currency or "currency"),
            (f"{label}: carbon estimate", totals.co2_kg if totals.co2_kg is not None else "UNAVAILABLE", "kg CO₂e"),
        ]
    metric_rows.extend(total_rows("Verified measured", m.verified_measured))
    metric_rows.extend(total_rows("Verified simulated", m.verified_simulated))
    metric_rows.extend(total_rows("Measured but unverified", m.measured_unverified))
    metric_rows.extend(total_rows("Projected or unverified", m.projected_or_unverified))
    rows = "\n".join(
        f"<tr><th scope=\"row\">{escape(str(label))}</th><td>{escape(str(value))}</td><td>{escape(str(unit))}</td></tr>"
        for label, value, unit in metric_rows
    )
    trust = "\n".join(f"<li>{escape(line)}</li>" for line in report.verified_vs_simulated)
    recommendations = "\n".join(
        f"<li><strong>{escape(rec.title)}</strong> — {escape(rec.rationale)} Next step: {escape(rec.next_step)}</li>"
        for rec in report.recommendations
    ) or "<li>No recommendations were generated from the available facts.</li>"
    limitations = "\n".join(f"<li>{escape(line)}</li>" for line in report.limitations)
    assumptions = "\n".join(f"<li><strong>{escape(key)}:</strong> {escape(value)}</li>" for key, value in report.assumptions.items())
    unavailable = "\n".join(f"<li>{escape(value)}</li>" for value in report.unavailable_inputs) or "<li>None reported by the facts provider.</li>"
    reading_rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(value if value is not None else 'UNAVAILABLE'))}</td>" for value in (
            item.id, item.resource_type, item.reading_type, item.value, item.unit,
            item.observed_at.isoformat() if item.observed_at else None, item.provenance.value,
            item.source_health.value, item.freshness_seconds, item.building_id, item.room_id,
        )) + "</tr>" for item in report.readings
    ) or "<tr><td colspan=\"11\">No sensor readings were supplied for this period.</td></tr>"
    incident_rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(value if value is not None else 'UNAVAILABLE'))}</td>" for value in (
            item.id, item.event_type, item.severity, item.status, item.building_id, item.room_id,
            item.first_seen_at.isoformat() if item.first_seen_at else None, item.trigger_rule, item.explanation,
            item.provenance.value, "; ".join(item.evidence_ids) or "UNAVAILABLE",
        )) + "</tr>" for item in report.events
    ) or "<tr><td colspan=\"11\">No incidents were supplied for this period.</td></tr>"
    action_rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(value if value is not None else 'UNAVAILABLE'))}</td>" for value in (
            item.id, item.event_id, item.status, item.requested_at.isoformat() if item.requested_at else None,
            item.verification_summary, item.provenance.value, "; ".join(item.evidence_ids) or "UNAVAILABLE",
        )) + "</tr>" for item in report.actions
    ) or "<tr><td colspan=\"7\">No action records were supplied for this period.</td></tr>"
    ledger_rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(value if value is not None else 'UNAVAILABLE'))}</td>" for value in (
            item.id, item.action_id, item.verification_status, item.provenance.value,
            item.energy_kwh, item.water_liters,
            f"{item.cost_currency or 'configured currency'} {item.cost_amount}" if item.cost_amount is not None else None,
            item.co2_kg, item.calculation_version, "; ".join(item.source_ids) or "UNAVAILABLE",
        )) + "</tr>" for item in report.ledger_entries
    ) or "<tr><td colspan=\"10\">No ledger entries were supplied for this period.</td></tr>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CampusTwin AI Weekly Sustainability Report</title>
<style>
:root{{color-scheme:light dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif}}
body{{max-width:1000px;margin:0 auto;padding:2rem;line-height:1.55}}
header{{border-bottom:1px solid #8886;padding-bottom:1rem;margin-bottom:1.5rem}}
small,.muted{{opacity:.8}}table{{width:100%;border-collapse:collapse;margin:1rem 0}}th,td{{padding:.65rem;border-bottom:1px solid #8885;text-align:left}}th{{font-weight:650}}
li{{margin:.45rem 0}}.tag{{display:inline-block;border:1px solid #8888;padding:.15rem .5rem;border-radius:99px}}
@media(max-width:600px){{body{{padding:1rem}}th,td{{padding:.4rem}}}}
</style></head><body>
<header><span class="tag">{escape(report.mode.value)} narrative</span><h1>Weekly sustainability report</h1>
<p>{escape(report.summary)}</p><p class="muted">Period: {escape(report.period_start.isoformat())} to {escape(report.period_end.isoformat())}<br>
Generated: {escape(report.generated_at.isoformat())} · Report ID: {escape(report.report_id)}</p></header>
<section><h2>Overview</h2><ul>{''.join(f'<li>{escape(line)}</li>' for line in report.narrative_lines)}</ul></section>
<section><h2>Deterministic metrics</h2><p>All totals below are assembled from the supplied facts. UNAVAILABLE means the necessary input was not provided; it is not zero.</p>
<table><thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">Unit</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>Sensor evidence register</h2><p>Reading values and observation times are supplied by the facts provider. Freshness and source health are shown separately.</p><table><thead><tr><th scope="col">Reading ID</th><th scope="col">Resource</th><th scope="col">Reading type</th><th scope="col">Value</th><th scope="col">Unit</th><th scope="col">Observed at</th><th scope="col">Provenance</th><th scope="col">Source health</th><th scope="col">Age (seconds)</th><th scope="col">Building</th><th scope="col">Room</th></tr></thead><tbody>{reading_rows}</tbody></table></section>
<section><h2>Incident register</h2><p>Events shown here are records supplied by the facts provider for the selected reporting period.</p><table><thead><tr><th scope="col">Event ID</th><th scope="col">Type</th><th scope="col">Severity</th><th scope="col">Status</th><th scope="col">Building</th><th scope="col">Room</th><th scope="col">First seen</th><th scope="col">Trigger rule</th><th scope="col">Explanation</th><th scope="col">Provenance</th><th scope="col">Evidence IDs</th></tr></thead><tbody>{incident_rows}</tbody></table></section>
<section><h2>Action and failure history</h2><p>Command acknowledgement is not equivalent to verification. Failure and timeout statuses remain visible.</p><table><thead><tr><th scope="col">Action ID</th><th scope="col">Event ID</th><th scope="col">Status</th><th scope="col">Requested at</th><th scope="col">Verification summary</th><th scope="col">Provenance</th><th scope="col">Evidence IDs</th></tr></thead><tbody>{action_rows}</tbody></table></section>
<section><h2>Impact ledger records</h2><p>Amounts remain UNAVAILABLE when the source record lacks the value. The unit column in CSV distinguishes kWh, litres, configured currency and kg CO₂e.</p><table><thead><tr><th scope="col">Ledger ID</th><th scope="col">Action ID</th><th scope="col">Verification</th><th scope="col">Provenance</th><th scope="col">Energy (kWh)</th><th scope="col">Water (L)</th><th scope="col">Cost</th><th scope="col">CO₂e (kg)</th><th scope="col">Calculation version</th><th scope="col">Source IDs</th></tr></thead><tbody>{ledger_rows}</tbody></table></section>
<section><h2>Verified vs simulated</h2><ul>{trust}</ul></section>
<section><h2>Suggested next steps</h2><ul>{recommendations}</ul></section>
<section><h2>Assumptions</h2><ul>{assumptions or '<li>No assumptions were supplied.</li>'}</ul></section>
<section><h2>Unavailable inputs</h2><ul>{unavailable}</ul></section>
<section><h2>Limitations</h2><ul>{limitations or '<li>None supplied by the report service.</li>'}</ul></section>
<footer><small>CampusTwin AI · This report is not proof of real-world savings or live-campus validation unless its provenance and verification fields explicitly support that claim.</small></footer>
</body></html>"""
