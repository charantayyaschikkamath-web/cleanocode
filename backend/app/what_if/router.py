from __future__ import annotations

from fastapi import APIRouter, Depends

from ..copilot.facts import fact_references, get_facts_snapshot, grounding_from_facts
from ..copilot.models import FactsSnapshot
from ..copilot.router import get_copilot_service
from ..copilot.service import CopilotService
from .engine import build_single_request, calculate_comparison
from .models import WhatIfCompareRequest, WhatIfResponse, WhatIfRunRequest

router = APIRouter(prefix="/api/what-if", tags=["what-if"])


async def _execute(request: WhatIfCompareRequest, facts: FactsSnapshot, service: CopilotService) -> WhatIfResponse:
    estimates = calculate_comparison(request, facts)
    deterministic_result = {
        "room_id": request.room_id,
        "duration_hours": str(request.duration_hours),
        "comparisons": [estimate.model_dump(mode="json") for estimate in estimates],
        "result_type": "PROJECTED_NOT_VERIFIED",
    }
    narrative, mode, _cached_at = await service.explain_what_if(deterministic_result, facts)
    limitations = [
        "All impact values are deterministic projections based on the baseline, duration, intervention, and configured factors shown.",
        "This endpoint never executes a device command and never writes a savings-ledger entry.",
        "A healthy source reading is required for automatic baseline selection; a manual baseline is always labelled SIMULATED.",
    ]
    if any(result.status.value == "UNAVAILABLE" for result in estimates):
        limitations.append("One or more estimates are unavailable because a valid baseline or required input was not supplied.")
    if any(result.missing_inputs for result in estimates):
        limitations.append("Cost and carbon values may be unavailable when the corresponding factors have not been configured.")
    if facts.source_status != "HEALTHY":
        limitations.append(f"Facts source status is {facts.source_status}; this is not a live-campus validation.")
    return WhatIfResponse(
        mode=mode,
        summary=narrative.summary,
        explanation_lines=narrative.lines,
        comparisons=estimates,
        grounding=grounding_from_facts(facts),
        fact_references=fact_references(facts),
        recommendations=narrative.recommendations,
        limitations=limitations,
    )


@router.post("/run", response_model=WhatIfResponse)
async def run_what_if(
    request: WhatIfRunRequest,
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> WhatIfResponse:
    comparison = build_single_request(
        room_id=request.room_id,
        duration_hours=request.duration_hours,
        scenario_baseline_watts=request.scenario_baseline_watts,
        intervention_name=request.intervention_name,
        reduction_percent=request.reduction_percent,
    )
    return await _execute(comparison, facts, service)


@router.post("/compare", response_model=WhatIfResponse)
async def compare_what_if(
    request: WhatIfCompareRequest,
    facts: FactsSnapshot = Depends(get_facts_snapshot),
    service: CopilotService = Depends(get_copilot_service),
) -> WhatIfResponse:
    return await _execute(request, facts, service)
