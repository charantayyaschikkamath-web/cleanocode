from __future__ import annotations

import csv
import io

from app.copilot.csv_safety import SpreadsheetSafeCSVWriter
from app.copilot.reports import report_csv
from app.copilot.formatters import action_plan_csv


def test_csv_writer_neutralizes_formula_like_text_but_keeps_numeric_cells_numeric():
    output = io.StringIO(newline="")
    writer = SpreadsheetSafeCSVWriter(output)
    writer.writerow(["plain", "=HYPERLINK(\"https://example.invalid\")", "  +SUM(A1:A3)", "\t=1+1", -12])
    row = next(csv.reader(io.StringIO(output.getvalue())))
    assert row == [
        "plain",
        "'=HYPERLINK(\"https://example.invalid\")",
        "'  +SUM(A1:A3)",
        "'\t=1+1",
        "-12",
    ]


def test_report_and_action_plan_csv_exports_use_safe_writer(facts, template_service):
    import asyncio

    unsafe_event = facts.events[0].model_copy(update={
        "event_type": "custom_event",
        "explanation": '=HYPERLINK("https://example.invalid", "click")',
    })
    unsafe_facts = facts.model_copy(update={"events": [unsafe_event]})
    weekly = asyncio.run(template_service.weekly_report(unsafe_facts))
    weekly_rows = list(csv.reader(io.StringIO(report_csv(weekly))))
    weekly_explanation = next(row[2] for row in weekly_rows if row[1] == "event-energy-1.explanation")
    assert weekly_explanation.startswith("'=")

    plan = asyncio.run(template_service.action_plan(unsafe_facts))
    plan_rows = list(csv.reader(io.StringIO(action_plan_csv(plan))))
    action_plan_reason = next(row[2] for row in plan_rows if row[1] == "event-energy-1.reason")
    assert action_plan_reason.startswith("'=")
