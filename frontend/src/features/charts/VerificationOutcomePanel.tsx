import type { VerificationSummary } from './types';

interface VerificationOutcomePanelProps {
  verification?: VerificationSummary | null;
}

function outcomeLabel(outcome: string): string {
  switch (outcome) {
    case 'VERIFIED_SUCCESS': return 'Verified success';
    case 'VERIFICATION_FAILED': return 'Verification failed';
    case 'VERIFYING': return 'Verification in progress';
    case 'VERIFICATION_TIMEOUT': return 'Verification timed out';
    case 'UNKNOWN': return 'Outcome unknown';
    default: return outcome.replaceAll('_', ' ').toLowerCase();
  }
}

function fmt(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'Unavailable';
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(value)}${unit ? ` ${unit}` : ''}`;
}

function fmtWindow(start?: string | null, end?: string | null): string {
  if (!start && !end) return 'Verification window not supplied';
  const format = (value?: string | null) => {
    if (!value) return 'not supplied';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'invalid timestamp' : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  };
  return `${format(start)} → ${format(end)}`;
}

export function VerificationOutcomePanel({ verification }: VerificationOutcomePanelProps) {
  if (!verification) {
    return <section className="ct-verification-panel" aria-label="Action verification outcome">
      <div className="ct-verification-header"><div><p className="ct-chart-eyebrow">ACTION VERIFICATION</p><h3>Outcome unavailable</h3></div><span className="ct-result-status ct-result-status--unknown">Not supplied</span></div>
      <p className="ct-verification-note">No backend verification record was provided. This view will not infer success from a command or acknowledgement.</p>
    </section>;
  }

  const success = verification.outcome === 'VERIFIED_SUCCESS';
  const failed = ['VERIFICATION_FAILED', 'VERIFICATION_TIMEOUT'].includes(verification.outcome);
  const statusClass = success ? 'success' : failed ? 'failed' : 'unknown';
  return (
    <section className="ct-verification-panel" aria-label="Action verification outcome">
      <div className="ct-verification-header">
        <div><p className="ct-chart-eyebrow">ACTION VERIFICATION</p><h3>{outcomeLabel(verification.outcome)}</h3></div>
        <span className={`ct-result-status ct-result-status--${statusClass}`}>{success ? '✓ Verified' : failed ? '! Not verified' : '? Unconfirmed'}</span>
      </div>
      <div className="ct-verification-metrics">
        <div><span>Required drop</span><strong>{fmt(verification.requiredDrop, verification.unit)}</strong></div>
        <div><span>Observed drop</span><strong>{fmt(verification.observedDrop, verification.unit)}</strong></div>
      </div>
      <div className="ct-verification-meta"><span>Window</span><strong>{fmtWindow(verification.windowStart, verification.windowEnd)}</strong></div>
      <div className="ct-verification-meta"><span>Evidence provenance</span><strong>{verification.provenance || 'Not supplied'}</strong></div>
      <div className="ct-verification-meta"><span>Evidence sources</span><strong>{verification.sourceIds?.length ? verification.sourceIds.join(', ') : 'Not supplied'}</strong></div>
      {!success ? <p className="ct-verification-note">No verified savings should be recorded for this outcome. An acknowledgement is not proof that the resource change occurred.</p> : <p className="ct-verification-note">The backend marked this action as verified. Any ledger entry should reference this verification record and its evidence.</p>}
    </section>
  );
}
