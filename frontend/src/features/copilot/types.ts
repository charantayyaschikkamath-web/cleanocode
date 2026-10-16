export type Provenance = 'REAL' | 'SIMULATED' | 'DERIVED' | 'UNKNOWN';
export type CopilotMode = 'LLM' | 'CACHED' | 'TEMPLATE';

export interface ProjectedImpact {
  status: 'PROJECTED' | 'UNAVAILABLE';
  energy_avoided_kwh?: string | number | null;
  water_avoided_liters?: string | number | null;
  cost_avoided_amount?: string | number | null;
  cost_currency?: string | null;
  co2_avoided_kg?: string | number | null;
  source_ids: string[];
  assumptions: string[];
}

export interface CopilotQueryResponse {
  answer: string;
  mode: CopilotMode;
  facts_version: string;
  source_ids: string[];
  recommendations: Array<{ label: string; action_type: string; requires_approval: boolean }>;
  warnings: string[];
  generated_at: string;
}

export interface ReportArtifactMetadata {
  id: string;
  format: 'HTML' | 'CSV' | 'JSON';
  created_at: string;
  period_start: string;
  period_end: string;
  source_event_ids: string[];
  source_action_ids: string[];
  source_ledger_ids: string[];
  provenance_summary: Record<string, number>;
  assumptions: Record<string, string>;
  limitations: string[];
  file_reference: string;
  available_formats: Array<'HTML' | 'CSV' | 'JSON'>;
  report_type: 'WEEKLY_SUSTAINABILITY' | 'ACTION_PLAN';
}

export interface FactReference {
  id: string;
  kind: 'reading' | 'event' | 'action' | 'ledger' | 'evidence';
  label: string;
  provenance: Provenance;
}

export interface Recommendation {
  title: string;
  rationale: string;
  next_step: string;
  fact_refs: string[];
}

export interface CopilotAnswer {
  mode: CopilotMode;
  generated_at: string;
  cached_at?: string | null;
  summary: string;
  lines: string[];
  recommendations: Recommendation[];
  fact_references: FactReference[];
  grounding: {
    real_count: number;
    simulated_count: number;
    derived_count: number;
    unknown_count: number;
    source_status: string;
    assumptions: Record<string, string>;
    unavailable_inputs: string[];
  };
  limitations: string[];
}

export interface ImpactTotals {
  energy_kwh?: string | number | null;
  water_liters?: string | number | null;
  cost_amount?: string | number | null;
  cost_currency?: string | null;
  co2_kg?: string | number | null;
  entries_count: number;
  missing_value_count: number;
}

export interface WeeklyReport {
  report_id: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  mode: CopilotMode;
  cached_at?: string | null;
  summary: string;
  narrative_lines: string[];
  readings: Array<{
    id: string;
    resource_type: string;
    reading_type?: string | null;
    value?: string | number | null;
    unit?: string | null;
    observed_at?: string | null;
    provenance: Provenance;
    source_health: string;
    freshness_seconds?: number | null;
    building_id?: string | null;
    room_id?: string | null;
  }>;
  events: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
  ledger_entries: Array<Record<string, unknown>>;
  metrics: {
    reading_count: number;
    readings_by_provenance: Record<string, number>;
    events_total: number;
    events_open: number;
    events_by_severity: Record<string, number>;
    actions_total: number;
    actions_verified_success: number;
    actions_failed_or_timed_out: number;
    verified_measured: ImpactTotals;
    measured_unverified: ImpactTotals;
    verified_simulated: ImpactTotals;
    projected_or_unverified: ImpactTotals;
  };
  verified_vs_simulated: string[];
  recommendations: Recommendation[];
  assumptions: Record<string, string>;
  unavailable_inputs: string[];
  evidence_ids: string[];
  limitations: string[];
}

export interface ActionPlan {
  generated_at: string;
  mode: CopilotMode;
  cached_at?: string | null;
  summary: string;
  narrative_lines: string[];
  items: Array<{
    event_id: string;
    event_type: string;
    priority: 'P1' | 'P2' | 'P3' | 'REVIEW';
    reason: string;
    proposed_next_step: string;
    evidence_ids: string[];
    provenance: Provenance;
    projected_impact: ProjectedImpact;
  }>;
  assumptions: Record<string, string>;
  unavailable_inputs: string[];
  limitations: string[];
}
