from __future__ import annotations

import io
from html import escape
from typing import Any

from .models import ActionPlan, ProjectedImpact
from .csv_safety import SpreadsheetSafeCSVWriter


def action_plan_csv(plan: ActionPlan) -> str:
    output = io.StringIO(newline="")
    writer = SpreadsheetSafeCSVWriter(output)
    writer.writerow(["section", "key", "value", "unit", "provenance", "source_ids"])
    writer.writerow(["report", "summary", plan.summary, "", plan.mode.value, ""])
    writer.writerow(["report", "generated_at", plan.generated_at.isoformat(), "", "DERIVED", ""])
    writer.writerow(["report", "narrative_mode", plan.mode.value, "", plan.mode.value, ""])
    for index, line in enumerate(plan.narrative_lines, start=1):
        writer.writerow(["narrative", f"line_{index}", line, "", plan.mode.value, ""])
    for item in plan.items:
        refs = ";".join(dict.fromkeys([item.event_id, *item.evidence_ids]))
        prefix = item.event_id
        writer.writerow(["event", f"{prefix}.priority", item.priority, "", item.provenance.value, refs])
        writer.writerow(["event", f"{prefix}.event_type", item.event_type, "", item.provenance.value, refs])
        writer.writerow(["event", f"{prefix}.reason", item.reason, "", item.provenance.value, refs])
        writer.writerow(["event", f"{prefix}.proposed_next_step", item.proposed_next_step, "", item.provenance.value, refs])
        impact = item.projected_impact
        writer.writerow(["impact", f"{prefix}.impact_status", impact.status, "", "DERIVED" if impact.status == "PROJECTED" else "UNKNOWN", ";".join(impact.source_ids)])
        writer.writerow(["impact", f"{prefix}.energy_avoided_kwh", impact.energy_avoided_kwh if impact.energy_avoided_kwh is not None else "UNAVAILABLE", "kWh", "DERIVED" if impact.energy_avoided_kwh is not None else "UNKNOWN", ";".join(impact.source_ids)])
        writer.writerow(["impact", f"{prefix}.water_avoided_liters", impact.water_avoided_liters if impact.water_avoided_liters is not None else "UNAVAILABLE", "L", "DERIVED" if impact.water_avoided_liters is not None else "UNKNOWN", ";".join(impact.source_ids)])
        writer.writerow(["impact", f"{prefix}.cost_avoided_amount", impact.cost_avoided_amount if impact.cost_avoided_amount is not None else "UNAVAILABLE", impact.cost_currency or "currency", "DERIVED" if impact.cost_avoided_amount is not None else "UNKNOWN", ";".join(impact.source_ids)])
        writer.writerow(["impact", f"{prefix}.co2_avoided_kg", impact.co2_avoided_kg if impact.co2_avoided_kg is not None else "UNAVAILABLE", "kg CO₂e", "DERIVED" if impact.co2_avoided_kg is not None else "UNKNOWN", ";".join(impact.source_ids)])
        for index, assumption in enumerate(impact.assumptions, start=1):
            writer.writerow(["impact_assumption", f"{prefix}.assumption_{index}", assumption, "", "DERIVED", ";".join(impact.source_ids)])
    for key, value in plan.assumptions.items():
        writer.writerow(["assumption", key, value, "", "DERIVED", ""])
    for value in plan.unavailable_inputs:
        writer.writerow(["unavailable", value, "UNAVAILABLE", "", "UNKNOWN", ""])
    for index, value in enumerate(plan.limitations, start=1):
        writer.writerow(["limitation", f"limitation_{index}", value, "", "DERIVED", ""])
    return output.getvalue()


def action_plan_html(plan: ActionPlan) -> str:
    rows: list[str] = []
    for item in plan.items:
        impact = item.projected_impact
        energy = str(impact.energy_avoided_kwh) + " kWh" if impact.energy_avoided_kwh is not None else "UNAVAILABLE"
        water = str(impact.water_avoided_liters) + " L" if impact.water_avoided_liters is not None else "UNAVAILABLE"
        cost = (f"{impact.cost_currency or ''} {impact.cost_avoided_amount}".strip()
                if impact.cost_avoided_amount is not None else "UNAVAILABLE")
        co2 = str(impact.co2_avoided_kg) + " kg CO₂e" if impact.co2_avoided_kg is not None else "UNAVAILABLE"
        rows.append(
            "<tr>"
            f"<td>{escape(item.event_id)}</td><td>{escape(item.priority)}</td>"
            f"<td>{escape(item.event_type)}</td><td>{escape(item.reason)}</td>"
            f"<td>{escape(item.proposed_next_step)}</td><td>{escape(item.provenance.value)}</td>"
            f"<td>{escape(impact.status)}</td><td>{escape(energy)}</td><td>{escape(water)}</td>"
            f"<td>{escape(cost)}</td><td>{escape(co2)}</td>"
            f"<td>{escape('; '.join(impact.source_ids) or 'UNAVAILABLE')}</td>"
            f"<td>{escape('; '.join(impact.assumptions) or 'No assumptions supplied')}</td></tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="13">No open events in the supplied facts snapshot.</td></tr>')
    assumptions = "".join(f"<li><strong>{escape(k)}:</strong> {escape(v)}</li>" for k, v in plan.assumptions.items())
    unavailable = "".join(f"<li>{escape(v)}</li>" for v in plan.unavailable_inputs) or "<li>None reported</li>"
    limitations = "".join(f"<li>{escape(v)}</li>" for v in plan.limitations) or "<li>None supplied</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CampusTwin AI Action Plan</title><style>body{{font:16px system-ui;max-width:1300px;margin:2rem auto;padding:0 1rem;line-height:1.5}}table{{border-collapse:collapse;width:100%;font-size:.9rem}}th,td{{text-align:left;padding:.6rem;border-bottom:1px solid #8888;vertical-align:top}}section{{margin-top:2rem}}.tag{{border:1px solid #8888;border-radius:999px;padding:.15rem .5rem}}</style></head><body><span class="tag">{escape(plan.mode.value)} narrative</span><h1>CampusTwin AI operator action plan</h1><p>{escape(plan.summary)}</p><ul>{''.join(f'<li>{escape(line)}</li>' for line in plan.narrative_lines)}</ul><p>Priority is assigned by the deterministic severity mapping. Projections are not verified results.</p><table><thead><tr><th>Event</th><th>Priority</th><th>Type</th><th>Why</th><th>Next step</th><th>Provenance</th><th>Impact status</th><th>Energy</th><th>Water</th><th>Cost</th><th>CO₂</th><th>Source IDs</th><th>Assumptions</th></tr></thead><tbody>{''.join(rows)}</tbody></table><section><h2>Assumptions</h2><ul>{assumptions or '<li>No assumptions supplied</li>'}</ul></section><section><h2>Unavailable inputs</h2><ul>{unavailable}</ul></section><section><h2>Limitations</h2><ul>{limitations}</ul></section><footer>Numeric impact fields are supplied by deterministic backend facts. UNAVAILABLE is not zero.</footer></body></html>"""


def count_provenance(records: list[Any]) -> dict[str, int]:
    result = {name: 0 for name in ("REAL", "SIMULATED", "DERIVED", "UNKNOWN")}
    for record in records:
        key = getattr(getattr(record, "provenance", None), "value", "UNKNOWN")
        result[key if key in result else "UNKNOWN"] += 1
    return result
