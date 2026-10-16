from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ScenarioType = Literal[
    "EMPTY_ROOM_HIGH_POWER",
    "NIGHT_WATER_FLOW",
    "BIN_OVERFLOW",
    "INEFFICIENT_ROOM_USE",
    "NORMAL_OPERATION",
    "SENSOR_MISSING",
    "SENSOR_STALE",
    "COMMAND_DROPPED",
    "ACKNOWLEDGED_IGNORED",
    "VERIFIED_RESPONSE",
]
OutcomeMode = Literal["SUCCESS", "DROP_COMMAND", "ACK_IGNORE", "NOT_APPLICABLE"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DetectionThresholds(StrictModel):
    """Transparent demo defaults; production thresholds must be campus-configured."""

    min_power_w: float = Field(default=500.0, gt=0, le=100_000)
    energy_persistence_seconds: float = Field(default=300.0, gt=0, le=86_400)
    water_flow_lpm: float = Field(default=2.0, gt=0, le=10_000)
    water_persistence_seconds: float = Field(default=300.0, gt=0, le=86_400)
    bin_overflow_percent: float = Field(default=90.0, ge=0, le=100)
    bin_persistence_seconds: float = Field(default=300.0, gt=0, le=86_400)
    low_occupancy_ratio: float = Field(default=0.2, ge=0, le=1)
    required_drop_percent: float = Field(default=30.0, gt=0, le=100)
    verification_window_seconds: float = Field(default=300.0, gt=0, le=86_400)

    @field_validator("min_power_w", "energy_persistence_seconds", "water_flow_lpm", "water_persistence_seconds", "bin_overflow_percent", "bin_persistence_seconds", "low_occupancy_ratio", "required_drop_percent", "verification_window_seconds")
    @classmethod
    def finite_values(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("threshold values must be finite")
        return value


class ScenarioRunRequest(StrictModel):
    scenario_type: ScenarioType
    building_id: str = Field(min_length=1, max_length=36)
    room_id: str | None = Field(default=None, min_length=1, max_length=36)
    outcome_mode: OutcomeMode = "NOT_APPLICABLE"
    duration_virtual_seconds: int = Field(default=900, ge=1, le=86_400)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    thresholds: DetectionThresholds = Field(default_factory=DetectionThresholds)

    @model_validator(mode="after")
    def check_outcome_compatibility(self):
        mode = self.outcome_mode
        scenario = self.scenario_type
        allowed = {
            "EMPTY_ROOM_HIGH_POWER": {"NOT_APPLICABLE", "SUCCESS", "DROP_COMMAND", "ACK_IGNORE"},
            "COMMAND_DROPPED": {"NOT_APPLICABLE", "DROP_COMMAND"},
            "ACKNOWLEDGED_IGNORED": {"NOT_APPLICABLE", "ACK_IGNORE"},
            "VERIFIED_RESPONSE": {"NOT_APPLICABLE", "SUCCESS"},
        }
        compatible = allowed.get(scenario, {"NOT_APPLICABLE"})
        if mode not in compatible:
            raise ValueError(f"outcome_mode {mode} is not valid for scenario_type {scenario}")
        return self


class ScenarioRunOut(BaseModel):
    scenario_run_id: str
    status: str
    scenario_type: str
    provenance: str = "SIMULATED"
    virtual_clock_multiplier: float
    reading_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    ledger_entry_ids: list[str] = Field(default_factory=list)
    started_at: str
    completed_at: str
    warnings: list[str] = Field(default_factory=list)
    detection_summary: list[dict[str, Any]] = Field(default_factory=list)


class ActionProposalRequest(StrictModel):
    event_id: str = Field(min_length=1, max_length=36)
    action_type: Literal["SIMULATED_REDUCE_POWER"] = "SIMULATED_REDUCE_POWER"
    idempotency_key: str = Field(min_length=1, max_length=160)
    actor: str = Field(default="system_recommendation", min_length=1, max_length=120)
    outcome_mode: Literal["SUCCESS", "DROP_COMMAND", "ACK_IGNORE"] = "SUCCESS"
    required_drop_percent: float = Field(default=30.0, gt=0, le=100)
    verification_window_seconds: int = Field(default=300, ge=1, le=86_400)


class ActionRejectRequest(StrictModel):
    actor: str = Field(default="operator", min_length=1, max_length=120)
    reason: str = Field(min_length=3, max_length=1000)


class EventEvaluateRequest(StrictModel):
    building_id: str = Field(min_length=1, max_length=36)
    room_id: str | None = Field(default=None, max_length=36)
    reading_ids: list[str] | None = Field(default=None, max_length=500)
    thresholds: DetectionThresholds = Field(default_factory=DetectionThresholds)


class EventFeedbackRequest(StrictModel):
    label: Literal["CONFIRMED", "FALSE_POSITIVE", "NEEDS_INSPECTION"]
    reason: str | None = Field(default=None, max_length=3000)
    actor: str = Field(default="operator", min_length=1, max_length=120)


class DemoResetRequest(StrictModel):
    confirm: bool
    actor: str = Field(default="operator", min_length=1, max_length=120)
    reason: str = Field(default="Reset active demo incidents", min_length=3, max_length=1000)


class VerificationSummary(BaseModel):
    id: str | None = None
    result: str | None = None
    baseline_snapshot: dict[str, Any] | None = None
    post_action_snapshot: dict[str, Any] | None = None
    required_change: dict[str, Any] | None = None
    observed_change: dict[str, Any] | None = None
    evidence_reading_ids: list[str] = Field(default_factory=list)
    verification_window_start: str | None = None
    verification_window_end: str | None = None
