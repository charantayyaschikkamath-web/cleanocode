from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.copilot.config import CopilotSettings
from app.copilot.models import CopilotMode, FactsSnapshot, GroundedNarrative, Recommendation
from app.copilot.service import CopilotService, _validate_generated_narrative
from app.copilot.cache import LastGoodNarrativeCache
from app.copilot.service import _weekly_report_cache_key


@pytest.mark.asyncio
async def test_ask_uses_template_when_provider_is_not_configured(facts, template_service):
    answer = await template_service.ask("Why did the event happen?", facts, "event-energy-1")
    assert answer.mode == CopilotMode.TEMPLATE
    assert answer.grounding.simulated_count >= 1
    assert "likely_energy_waste" in answer.summary
    assert any(ref.id == "event-energy-1" for ref in answer.fact_references)
    assert answer.recommendations[0].fact_refs[0] == "event-energy-1"


@pytest.mark.asyncio
async def test_template_truncates_long_persisted_event_explanation(facts, template_service):
    facts.events[0].explanation = "A detailed source explanation that exceeds the compact narrative line limit. " * 10
    answer = await template_service.ask("Explain the event", facts, "event-energy-1")
    assert answer.mode == CopilotMode.TEMPLATE
    assert all(1 <= len(line) <= 240 for line in answer.lines)
    assert answer.lines[1].endswith("…")


@pytest.mark.asyncio
async def test_unknown_event_is_not_invented(facts, template_service):
    answer = await template_service.ask("Explain this event", facts, "does-not-exist")
    assert answer.mode == CopilotMode.TEMPLATE
    assert "could not find" in answer.summary.lower()
    assert "does-not-exist" not in [ref.id for ref in answer.fact_references]


def test_numeric_claim_in_llm_prose_is_rejected(facts):
    raw = {
        "summary": "This action saves 25 percent.",
        "lines": ["The baseline is healthy.", "The event has evidence.", "Check the action."],
        "recommendations": [],
    }
    with pytest.raises(ValueError):
        _validate_generated_narrative(raw, facts)


def test_unknown_fact_id_in_llm_recommendation_is_rejected(facts):
    raw = {
        "summary": "The evidence needs review.",
        "lines": ["Check source health.", "Inspect the rule.", "Use human approval."],
        "recommendations": [{
            "title": "Inspect the room",
            "rationale": "Evidence needs a manual check.",
            "next_step": "Compare the source before approving an action.",
            "fact_refs": ["fake-id"],
        }],
    }
    with pytest.raises(ValueError):
        _validate_generated_narrative(raw, facts)


@pytest.mark.asyncio
async def test_provider_response_validated_and_retried_once(monkeypatch, facts, tmp_path):
    settings = CopilotSettings(
        api_base_url="https://provider.example/v1", api_key="server-only", model="test-model",
        cache_path=str(tmp_path / "cache.json"),
    )
    service = CopilotService(settings=settings, cache=LastGoodNarrativeCache(settings.cache_path))
    calls = {"count": 0}

    async def fake_request(_settings, _operation, _facts_json, question=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return '{"summary":"Invented 20 percent","lines":["Bad 20", "No", "No"],"recommendations":[]}'
        return json.dumps({
            "summary": "The event needs review.",
            "lines": ["Check the linked reading.", "Confirm source freshness.", "Use human approval before action."],
            "recommendations": [{
                "title": "Inspect the evidence",
                "rationale": "The rule and reading should be reviewed together.",
                "next_step": "Confirm the current source and verify the result after action.",
                "fact_refs": ["event-energy-1", "reading-power-1"],
            }],
        })

    monkeypatch.setattr("app.copilot.service.request_narrative", fake_request)
    answer = await service.ask("Explain the event", facts, "event-energy-1")
    assert calls["count"] == 2
    assert answer.mode == CopilotMode.LLM
    assert answer.recommendations[0].fact_refs == ["event-energy-1", "reading-power-1"]


@pytest.mark.asyncio
async def test_report_fallback_uses_cache_and_keeps_metrics_current(facts, tmp_path):
    settings = CopilotSettings(
        api_base_url="https://provider.example/v1", api_key="server-only", model="test-model",
        cache_path=str(tmp_path / "cache.json"),
    )
    cache = LastGoodNarrativeCache(settings.cache_path)
    report_end = datetime.now(timezone.utc)
    report_start = report_end - timedelta(days=7)
    cache_key = _weekly_report_cache_key(facts, report_start, report_end, settings.max_context_records)
    cache.set(cache_key, GroundedNarrative(
        summary="The report separates observations and projections.",
        lines=["Check provenance before interpretation.", "Verified simulated outcomes are not measured outcomes.", "Missing factors remain unavailable."],
        recommendations=[],
    ).model_dump(mode="json"))
    service = CopilotService(settings=settings, cache=cache)

    async def fail_request(*_args, **_kwargs):
        raise RuntimeError("private provider details must not surface")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.copilot.service.request_narrative", fail_request)
    try:
        report = await service.weekly_report(facts, now=report_end, period_start=report_start)
    finally:
        monkeypatch.undo()

    assert report.mode == CopilotMode.CACHED
    assert report.cached_at is not None
    assert report.metrics.verified_simulated.energy_kwh is not None
    assert str(report.metrics.verified_simulated.energy_kwh) == "0.500000"
    # Failed and unverified entries are not included in the verified simulated total.
    assert report.metrics.verified_simulated.entries_count == 1
    assert report.metrics.projected_or_unverified.entries_count == 1
    assert any("cached" in item.lower() for item in report.limitations)


@pytest.mark.asyncio
async def test_missing_provider_returns_weekly_report_with_explicit_unavailable_values(facts, template_service):
    facts.energy_tariff_per_kwh = None
    facts.co2_factor_kg_per_kwh = None
    report = await template_service.weekly_report(facts)
    assert report.mode == CopilotMode.TEMPLATE
    assert report.period_end.tzinfo is not None
    assert report.metrics.reading_count == 1
    assert report.metrics.actions_failed_or_timed_out == 1
    assert "measured campus validation" in report.unavailable_inputs


@pytest.mark.asyncio
async def test_question_contact_details_are_redacted_before_provider_call(monkeypatch, facts, tmp_path):
    settings = CopilotSettings(
        api_base_url="https://provider.example/v1", api_key="server-only", model="test-model",
        cache_path=str(tmp_path / "cache.json"),
    )
    service = CopilotService(settings=settings, cache=LastGoodNarrativeCache(settings.cache_path))
    received = {}

    async def fake_request(_settings, _operation, facts_json, question=None):
        received["question"] = question
        received["facts_json"] = facts_json
        return json.dumps({
            "summary": "The event evidence needs review.",
            "lines": ["Check the rule evidence.", "Confirm source freshness.", "Use human review before intervention."],
            "recommendations": [],
        })

    monkeypatch.setattr("app.copilot.service.request_narrative", fake_request)
    answer = await service.ask("Why is the event open? Contact: chaitanya@example.com phone: +91 98765 43210", facts)
    assert answer.mode == CopilotMode.LLM
    assert "chaitanya@example.com" not in received["question"]
    assert "98765 43210" not in received["question"]
    assert "[REDACTED_CONTACT_FIELD]" in received["question"]
    assert "location" not in json.loads(received["facts_json"]).get("readings", [{}])[0]


@pytest.mark.asyncio
async def test_provider_failure_retries_once_then_uses_template_without_leaking_error(monkeypatch, facts, tmp_path):
    settings = CopilotSettings(
        api_base_url="https://provider.example/v1", api_key="server-only", model="test-model",
        cache_path=str(tmp_path / "cache.json"),
    )
    service = CopilotService(settings=settings, cache=LastGoodNarrativeCache(settings.cache_path))
    calls = {"count": 0}

    async def timeout(*_args, **_kwargs):
        calls["count"] += 1
        raise TimeoutError("secret provider response should not leak")

    monkeypatch.setattr("app.copilot.service.request_narrative", timeout)
    answer = await service.ask("Explain current event", facts)
    assert calls["count"] == 2
    assert answer.mode == CopilotMode.TEMPLATE
    assert "secret provider response" not in answer.summary


def test_mixed_currency_ledger_totals_are_unavailable_not_summed(facts):
    from app.copilot.reports import build_weekly_metrics
    from datetime import timedelta

    latest = facts.generated_at
    facts.ledger_entries[1].verification_status = "VERIFIED_SUCCESS"
    facts.ledger_entries[1].cost_currency = "USD"
    metrics = build_weekly_metrics(facts, latest - timedelta(days=7), latest + timedelta(seconds=1))
    assert metrics.verified_simulated.cost_amount is None
    assert metrics.verified_simulated.cost_currency is None


@pytest.mark.asyncio
async def test_weekly_report_narrative_uses_only_records_inside_requested_period(monkeypatch, facts, tmp_path):
    settings = CopilotSettings(
        api_base_url="https://provider.example/v1", api_key="server-only", model="test-model",
        cache_path=str(tmp_path / "cache.json"),
    )
    service = CopilotService(settings=settings, cache=LastGoodNarrativeCache(settings.cache_path))
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=14)
    current_event = facts.events[0]
    old_event = current_event.model_copy(update={
        "id": "event-old-outside-period", "first_seen_at": old_time,
        "last_updated_at": old_time, "evidence_ids": ["reading-old-outside-period"],
    })
    old_reading = facts.readings[0].model_copy(update={
        "id": "reading-old-outside-period", "observed_at": old_time,
        "room_id": "old-room", "location": "old-room",
    })
    scoped_test_facts = facts.model_copy(update={
        "events": [*facts.events, old_event],
        "readings": [*facts.readings, old_reading],
    })
    captured = {}

    async def fake_request(_settings, operation, facts_json, question=None):
        import json
        captured["operation"] = operation
        captured["context"] = json.loads(facts_json)
        return json.dumps({
            "summary": "The report separates current observations and projections.",
            "lines": ["Review the linked readings.", "Keep simulated outcomes distinct.", "Verify evidence before action."],
            "recommendations": [],
        })

    monkeypatch.setattr("app.copilot.service.request_narrative", fake_request)
    report = await service.weekly_report(scoped_test_facts, now=now, period_start=now - timedelta(days=7))

    assert report.metrics.events_total == 1
    assert captured["operation"] == "weekly_report"
    assert [event["id"] for event in captured["context"]["events"]] == ["event-energy-1"]
    assert [reading["id"] for reading in captured["context"]["readings"]] == ["reading-power-1"]

    # The cache signature is content-sensitive, so newly changed report facts get a new key.
    altered = scoped_test_facts.model_copy(update={"snapshot_id": "different-snapshot"})
    first_key = _weekly_report_cache_key(scoped_test_facts, now - timedelta(days=7), now, settings.max_context_records)
    second_key = _weekly_report_cache_key(altered, now - timedelta(days=7), now, settings.max_context_records)
    assert first_key == second_key  # bookkeeping ID alone must not defeat safe reuse
    modified_reading = scoped_test_facts.readings[0].model_copy(update={"value": scoped_test_facts.readings[0].value + 1})
    changed = scoped_test_facts.model_copy(update={"readings": [modified_reading, old_reading]})
    third_key = _weekly_report_cache_key(changed, now - timedelta(days=7), now, settings.max_context_records)
    assert third_key != first_key
