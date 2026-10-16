import type { ReactNode } from 'react';
import type { ActionState, EventStatus, HealthState, Provenance, Severity } from '../types';

const toneByStatus: Record<string, string> = {
  HEALTHY: 'tone-good', NORMAL: 'tone-good', VERIFIED_SUCCESS: 'tone-good', RESOLVED: 'tone-good', MEASURED: 'tone-good',
  DEGRADED: 'tone-warn', ATTENTION: 'tone-warn', HIGH: 'tone-warn', MEDIUM: 'tone-warn', ACKNOWLEDGED: 'tone-warn',
  CRITICAL: 'tone-danger', COMMAND_FAILED: 'tone-danger', ACK_TIMEOUT: 'tone-danger', VERIFICATION_FAILED: 'tone-danger', VERIFICATION_TIMEOUT: 'tone-danger', FALSE_ALARM: 'tone-danger',
  UNAVAILABLE: 'tone-muted', UNKNOWN: 'tone-muted', PENDING_APPROVAL: 'tone-warn', COMMAND_SENT: 'tone-info', ACKED: 'tone-info', VERIFYING: 'tone-info',
  SIMULATED: 'tone-sim', REAL: 'tone-good', DERIVED: 'tone-info', PROJECTED: 'tone-info', VERIFIED_SIMULATED: 'tone-sim', OPEN: 'tone-warn', REJECTED: 'tone-muted',
};

const pretty: Record<string, string> = {
  PENDING_APPROVAL: 'Pending approval', COMMAND_SENT: 'Command sent', ACKED: 'Acknowledged', VERIFYING: 'Verifying', VERIFIED_SUCCESS: 'Verified success',
  COMMAND_FAILED: 'Command failed', ACK_TIMEOUT: 'Ack timeout', VERIFICATION_FAILED: 'Verification failed', VERIFICATION_TIMEOUT: 'Verification timeout',
  FALSE_ALARM: 'False alarm', UNAVAILABLE: 'Unavailable', UNKNOWN: 'Unknown', DEGRADED: 'Degraded', VERIFIED_SIMULATED: 'Verified · simulated',
};

export function StatusPill({ value, children, icon }: { value?: string; children?: ReactNode; icon?: ReactNode }) {
  const raw = value || '';
  const tone = toneByStatus[raw] || 'tone-muted';
  return <span className={`status-pill ${tone}`}>{icon}{children ?? pretty[raw] ?? raw.toLowerCase().replaceAll('_', ' ')}</span>;
}

export function ProvenanceTag({ value }: { value: Provenance }) {
  return <StatusPill value={value} />;
}

export function SeverityTag({ value }: { value: Severity }) {
  return <StatusPill value={value} />;
}

export function HealthTag({ value }: { value: HealthState }) {
  return <StatusPill value={value} />;
}

export function EventStatusTag({ value }: { value: EventStatus }) {
  return <StatusPill value={value} />;
}

export function ActionStatusTag({ value }: { value: ActionState }) {
  return <StatusPill value={value} />;
}
