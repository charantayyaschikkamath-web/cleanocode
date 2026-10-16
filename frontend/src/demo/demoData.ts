import type { CampusAction, CampusEvent, DashboardOverview, LedgerEntry, SystemHealth } from '../types';

const now = '2026-10-15T16:45:00.000Z';
const sim = 'SIMULATED' as const;
const metric = (value: number | null, unit: string, note = 'Synthetic demo data') => ({ value, unit, period: 'Today', provenance: sim, note });

export const demoEvents: CampusEvent[] = [
  {
    id: 'EVT-DEMO-1042', eventType: 'likely_energy_waste', severity: 'HIGH', status: 'OPEN',
    title: 'Power draw while room appears unoccupied',
    summary: 'Power stayed above the configured threshold while the room occupancy signal indicated empty.',
    buildingId: 'b-library', buildingName: 'Learning Commons', roomId: 'LC-204', roomName: 'Seminar Room 204',
    firstSeenAt: '2026-10-15T16:23:00.000Z', updatedAt: now,
    triggerRule: 'likely_energy_waste', threshold: 'Power > 850 W for 10 minutes while occupancy = EMPTY',
    explanation: 'The configured rule matched sustained power readings and the supplied occupancy state over the persistence window.',
    limitations: ['Occupancy is simulated in this walkthrough.', 'This is a rule-based alert, not a trained prediction.', 'No physical device has been controlled.'],
    provenance: sim,
    evidence: [
      { id: 'RD-DEMO-91', label: 'Power reading', detail: 'Above configured threshold', reading: { id: 'RD-DEMO-91', resourceType: 'ENERGY', value: 1120, unit: 'W', observedAt: now, ageSeconds: 12, health: 'HEALTHY', provenance: sim, sourceName: 'Scenario energy meter' } },
      { id: 'RD-DEMO-92', label: 'Occupancy signal', detail: 'Room marked empty by demo scenario', reading: { id: 'RD-DEMO-92', resourceType: 'OCCUPANCY', value: 'EMPTY', unit: 'state', observedAt: now, ageSeconds: 8, health: 'HEALTHY', provenance: sim, sourceName: 'Manual scenario control' } },
      { id: 'RULE-DEMO-3', label: 'Persistence rule', detail: 'Condition held for 12 minutes; configured minimum is 10 minutes.' },
    ],
  },
  {
    id: 'EVT-DEMO-1041', eventType: 'likely_water_anomaly', severity: 'MEDIUM', status: 'OPEN',
    title: 'Low-use water flow continued overnight',
    summary: 'Flow remained above the demo threshold during the configured night window.',
    buildingId: 'b-hostel', buildingName: 'North Residence', roomId: 'NR-W1', roomName: 'Ground-floor washroom',
    firstSeenAt: '2026-10-15T02:14:00.000Z', updatedAt: '2026-10-15T02:32:00.000Z',
    triggerRule: 'likely_water_anomaly', threshold: 'Flow > 1.5 L/min during the low-use window for 15 minutes',
    explanation: 'A simulated flow signal crossed the configured low-use threshold for the full persistence interval.',
    limitations: ['Flow values are synthetic.', 'Inspect fixtures before dispatching maintenance.'], provenance: sim,
    evidence: [{ id: 'RD-DEMO-88', label: 'Flow reading', detail: 'Sustained flow in low-use window', reading: { id: 'RD-DEMO-88', resourceType: 'WATER', value: 2.1, unit: 'L/min', observedAt: '2026-10-15T02:32:00.000Z', ageSeconds: 86000, health: 'HEALTHY', provenance: sim, sourceName: 'Scenario water meter' } }],
  },
  {
    id: 'EVT-DEMO-1039', eventType: 'sensor_unavailable', severity: 'LOW', status: 'ACKNOWLEDGED',
    title: 'Occupancy evidence is stale', summary: 'The current room state cannot be determined because the last frame is too old.',
    buildingId: 'b-engineering', buildingName: 'Engineering Block', roomId: 'EB-118', roomName: 'Project Lab 118',
    firstSeenAt: '2026-10-15T15:40:00.000Z', updatedAt: '2026-10-15T15:42:00.000Z',
    triggerRule: 'sensor_unavailable', threshold: 'No fresh frame within configured freshness interval',
    explanation: 'The safe result is UNKNOWN. The system does not infer that the room is empty.',
    limitations: ['Camera is unavailable in this local preview.', 'No occupancy-based action should be approved from this evidence.'], provenance: sim,
    evidence: [{ id: 'CAM-DEMO-11', label: 'Camera health', detail: 'Frame is stale; occupancy status is UNKNOWN.' }],
  },
];

export const demoActions: CampusAction[] = [
  {
    id: 'ACT-DEMO-501', eventId: 'EVT-DEMO-1042', eventTitle: 'Power draw while room appears unoccupied', buildingName: 'Learning Commons', roomName: 'Seminar Room 204',
    state: 'PENDING_APPROVAL', createdAt: '2026-10-15T16:31:00.000Z', updatedAt: '2026-10-15T16:31:00.000Z',
    proposedAction: 'Request a simulated reduction in room power, then verify against the stored baseline.', baselineValue: 1120, observedValue: null,
    requiredDropPercent: 25, observedDropPercent: null, verificationWindowSeconds: 120, provenance: sim,
    transitions: [{ id: 'TR-DEMO-1', fromState: null, toState: 'PENDING_APPROVAL', at: '2026-10-15T16:31:00.000Z', actor: 'RULE_ENGINE', note: 'Proposed from event EVT-DEMO-1042.' }],
  },
  {
    id: 'ACT-DEMO-499', eventId: 'EVT-DEMO-1041', eventTitle: 'Low-use water flow continued overnight', buildingName: 'North Residence', roomName: 'Ground-floor washroom',
    state: 'VERIFICATION_FAILED', createdAt: '2026-10-15T03:00:00.000Z', updatedAt: '2026-10-15T03:04:00.000Z',
    proposedAction: 'Inspect the washroom supply and verify whether flow returns to baseline.', baselineValue: 2.1, observedValue: 2.0,
    requiredDropPercent: 30, observedDropPercent: 4.8, verificationWindowSeconds: 120, provenance: sim,
    transitions: [
      { id: 'TR-DEMO-2', fromState: null, toState: 'PENDING_APPROVAL', at: '2026-10-15T03:00:00.000Z', actor: 'RULE_ENGINE' },
      { id: 'TR-DEMO-3', fromState: 'PENDING_APPROVAL', toState: 'COMMAND_SENT', at: '2026-10-15T03:00:20.000Z', actor: 'DEMO_OPERATOR' },
      { id: 'TR-DEMO-4', fromState: 'COMMAND_SENT', toState: 'ACKED', at: '2026-10-15T03:00:30.000Z', actor: 'SIMULATOR' },
      { id: 'TR-DEMO-5', fromState: 'ACKED', toState: 'VERIFICATION_FAILED', at: '2026-10-15T03:04:00.000Z', actor: 'VERIFIER', note: 'Observed change did not meet the required threshold.' },
    ],
  },
];

const health: SystemHealth = {
  backend: { state: 'UNAVAILABLE', detail: 'Backend is not connected in local simulation' },
  database: { state: 'UNKNOWN', detail: 'No backend database is connected in local simulation' },
  camera: { state: 'UNAVAILABLE', detail: 'No camera inference is running in this local simulation' },
  sensorFeed: { state: 'DEGRADED', detail: 'All displayed readings are synthetic demo values' },
  copilot: { state: 'HEALTHY', detail: 'Deterministic template mode' },
  preflight: { state: 'UNKNOWN', detail: 'Backend preflight is not running in local simulation' },
  scenarioClock: { mode: 'ACCELERATED', multiplier: 30, detail: 'Local preview clock; not a physical clock' },
  connection: 'UNKNOWN',
};

export function createDemoOverview(events: CampusEvent[] = demoEvents, actions: CampusAction[] = demoActions, ledgerEntries: LedgerEntry[] = []): DashboardOverview {
  return {
    generatedAt: now,
    kpis: {
      energy: metric(684.2, 'kWh'), water: metric(14280, 'L'), waste: metric(63, '% capacity'), cost: metric(null, 'INR', 'Tariff unavailable in this preview'),
      co2: metric(null, 'kg CO₂e', 'Emission factor unavailable in this preview'), verifiedSavings: metric(ledgerEntries.reduce((sum, item) => sum + item.quantity, 0), 'kWh'),
    },
    pulse: { value: 78, label: 'Campus Pulse · illustrative', formula: '0.4 × service coverage + 0.3 × event response + 0.3 × data freshness (demo weights)', components: [{ label: 'Service coverage', value: 84 }, { label: 'Response', value: 72 }, { label: 'Data freshness', value: 69 }] },
    counts: {
      openEvents: events.filter((e) => e.status === 'OPEN').length,
      actionsAwaitingApproval: actions.filter((a) => a.state === 'PENDING_APPROVAL').length,
      verifiedActions: actions.filter((a) => a.state === 'VERIFIED_SUCCESS').length,
      buildingsWithIssues: new Set(events.filter((event) => event.status === 'OPEN').map((event) => event.buildingId)).size,
    },
    buildings: [
      { id: 'b-library', name: 'Learning Commons', shortName: 'LC', state: 'ATTENTION' as const, rooms: 24, activeEvents: 0, energyKwh: 188.4, waterLitres: null, provenance: sim },
      { id: 'b-engineering', name: 'Engineering Block', shortName: 'EB', state: 'UNKNOWN' as const, rooms: 32, activeEvents: 0, energyKwh: 245.1, waterLitres: null, provenance: sim },
      { id: 'b-hostel', name: 'North Residence', shortName: 'NR', state: 'CRITICAL' as const, rooms: 58, activeEvents: 0, energyKwh: 250.7, waterLitres: 14280, provenance: sim },
      { id: 'b-admin', name: 'Administration', shortName: 'AD', state: 'NORMAL' as const, rooms: 16, activeEvents: 0, energyKwh: null, waterLitres: null, provenance: sim },
    ].map((building) => {
      const linked = events.filter((event) => event.buildingId === building.id && event.status !== 'RESOLVED' && event.status !== 'FALSE_ALARM');
      const open = linked.filter((event) => event.status === 'OPEN');
      const hasUnknown = linked.some((event) => event.eventType === 'sensor_unavailable' || event.eventType === 'evidence_insufficient');
      const severe = open.some((event) => event.severity === 'CRITICAL') ? 'CRITICAL' as const : open.some((event) => event.severity === 'HIGH') ? 'ATTENTION' as const : open.length ? 'ATTENTION' as const : hasUnknown ? 'UNKNOWN' as const : 'NORMAL' as const;
      return { ...building, state: severe, activeEvents: open.length };
    }),
    recentEvents: events, priorityActions: actions, ledger: ledgerEntries, health,
  };
}

export const demoCopilot = (question: string) => ({
  answer: `This is a local template response, not an LLM result. Based on the synthetic records currently loaded, ${question.toLowerCase().includes('priorit') ? 'start with the high-severity Learning Commons event because it has sustained power evidence and a pending human review.' : 'the Learning Commons event triggered because the simulated power reading (1,120 W) remained above the configured 850 W threshold while the simulated occupancy state was EMPTY for 12 minutes. Verify the source and room state before acting.'} No physical device was controlled, and no real-world savings are established.`,
  mode: 'TEMPLATE' as const,
  groundedIn: ['EVT-DEMO-1042', 'RD-DEMO-91', 'RD-DEMO-92', 'RULE-DEMO-3'],
  suggestions: ['Check source health and evidence freshness.', 'Approve only after reviewing the event evidence.', 'Treat impact as simulated until independently verified with real measurements.'],
  limitations: ['Synthetic demo data only', 'No live campus connection', 'No measured savings'],
  createdAt: new Date().toISOString(),
});
