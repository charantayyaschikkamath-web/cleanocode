export type Provenance = 'REAL' | 'SIMULATED' | 'DERIVED' | 'UNKNOWN';
export type HealthState = 'HEALTHY' | 'DEGRADED' | 'UNAVAILABLE' | 'UNKNOWN';
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type EventStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | 'FALSE_ALARM';
export type ActionState =
  | 'PENDING_APPROVAL'
  | 'COMMAND_SENT'
  | 'ACKED'
  | 'VERIFYING'
  | 'VERIFIED_SUCCESS'
  | 'REJECTED'
  | 'COMMAND_FAILED'
  | 'ACK_TIMEOUT'
  | 'VERIFICATION_FAILED'
  | 'VERIFICATION_TIMEOUT';
export type ScenarioOutcome = 'VERIFIED_SUCCESS' | 'COMMAND_DROPPED' | 'ACKNOWLEDGED_IGNORED';
export type NavKey = 'overview' | 'twin' | 'events' | 'actions' | 'copilot' | 'whatif' | 'reports' | 'settings' | 'camera';

export interface MetricValue {
  value: number | null;
  unit: string;
  period?: string;
  provenance: Provenance;
  note?: string;
}

export interface KPISet {
  energy: MetricValue;
  water: MetricValue;
  waste: MetricValue;
  cost: MetricValue;
  co2: MetricValue;
  verifiedSavings: MetricValue;
}

export interface ResourceReading {
  id: string;
  resourceType: 'ENERGY' | 'WATER' | 'WASTE' | 'OCCUPANCY' | 'OTHER';
  value: number | string | null;
  unit: string;
  observedAt: string;
  ageSeconds: number | null;
  health: HealthState;
  provenance: Provenance;
  sourceName: string;
}

export interface EvidenceItem {
  id: string;
  label: string;
  detail: string;
  reading?: ResourceReading;
}

export interface CampusEvent {
  id: string;
  eventType: string;
  severity: Severity;
  status: EventStatus;
  title: string;
  summary: string;
  buildingId: string;
  buildingName: string;
  roomId?: string;
  roomName?: string;
  firstSeenAt: string;
  updatedAt: string;
  triggerRule: string;
  threshold: string;
  explanation: string;
  limitations: string[];
  evidence: EvidenceItem[];
  provenance: Provenance;
}

export interface ActionTransition {
  id: string;
  fromState: ActionState | null;
  toState: ActionState;
  at: string;
  actor: string;
  note?: string;
}

export interface CampusAction {
  id: string;
  eventId: string;
  eventTitle: string;
  buildingName: string;
  roomName?: string;
  state: ActionState;
  createdAt: string;
  updatedAt: string;
  proposedAction: string;
  actor?: string;
  outcome?: string;
  baselineValue?: number | null;
  observedValue?: number | null;
  requiredDropPercent?: number | null;
  observedDropPercent?: number | null;
  verificationWindowSeconds?: number | null;
  provenance: Provenance;
  transitions: ActionTransition[];
}

export interface BuildingSummary {
  id: string;
  name: string;
  shortName: string;
  state: 'NORMAL' | 'ATTENTION' | 'CRITICAL' | 'UNKNOWN';
  rooms: number | null;
  activeEvents: number | null;
  energyKwh: number | null;
  waterLitres: number | null;
  provenance: Provenance;
}

export interface ServiceHealth {
  state: HealthState;
  detail: string;
  checkedAt?: string;
}

export interface SystemHealth {
  backend: ServiceHealth;
  database: ServiceHealth;
  camera: ServiceHealth;
  sensorFeed: ServiceHealth;
  copilot: ServiceHealth;
  preflight: ServiceHealth;
  scenarioClock: { mode: 'REAL_TIME' | 'ACCELERATED' | 'UNKNOWN'; multiplier: number | null; detail: string };
  connection: 'CONNECTED' | 'RECONNECTING' | 'OFFLINE' | 'UNKNOWN';
}

export interface LedgerEntry {
  id: string;
  actionId: string;
  eventId: string;
  resourceType: string;
  quantity: number;
  unit: string;
  estimatedCost: number | null;
  estimatedCo2Kg: number | null;
  formula: string;
  assumptions: string[];
  observationPeriod: string;
  provenance: Provenance;
  status: 'VERIFIED_SIMULATED' | 'MEASURED' | 'PROJECTED';
  createdAt: string;
}

export interface DashboardOverview {
  generatedAt: string;
  kpis: KPISet;
  pulse: { value: number | null; label: string; formula: string; components: { label: string; value: number | null }[] };
  counts: { openEvents: number; actionsAwaitingApproval: number; verifiedActions: number; buildingsWithIssues: number };
  buildings: BuildingSummary[];
  recentEvents: CampusEvent[];
  priorityActions: CampusAction[];
  ledger: LedgerEntry[];
  health: SystemHealth;
}

export interface ScenarioRequest {
  scenario: string;
  buildingId?: string;
  roomId?: string;
  outcome?: ScenarioOutcome;
}

export interface ScenarioResponse {
  runId: string;
  scenario: string;
  message: string;
  createdEventIds: string[];
  actionId?: string;
  provenance: Provenance;
}

export interface CopilotResponse {
  answer: string;
  mode: 'LLM' | 'CACHED' | 'TEMPLATE';
  groundedIn: string[];
  suggestions?: string[];
  limitations?: string[];
  createdAt: string;
}

export interface WhatIfRequest {
  buildingId: string;
  roomId?: string;
  intervention: 'REDUCE_POWER' | 'WATER_REPAIR' | 'SCHEDULE_OPTIMIZATION';
  durationHours: number;
  reductionPercent: number;
}

export interface WhatIfResponse {
  baseline: number | null;
  projected: number | null;
  delta: number | null;
  unit: string;
  costDelta: number | null;
  co2DeltaKg: number | null;
  formula: string;
  assumptions: string[];
  provenance: Provenance;
  status: 'PROJECTED' | 'UNAVAILABLE';
}

export interface CampusSettings {
  tariffPerKwh: number | null;
  co2KgPerKwh: number | null;
  energyWasteWatts: number;
  waterNightFlowLitresPerMinute: number;
  persistenceMinutes: number;
  verificationDropPercent: number;
  verificationWindowSeconds: number;
  scenarioClockMultiplier: number;
  updatedAt?: string;
}

export interface ReportRecord {
  id: string;
  title: string;
  type: 'WEEKLY' | 'INCIDENT' | 'AUDIT';
  generatedAt: string;
  period: string;
  eventCount: number;
  verifiedActionCount: number;
  provenance: Provenance;
}

export interface ApiErrorShape {
  error?: { code?: string; message?: string; request_id?: string; details?: unknown };
  message?: string;
}
