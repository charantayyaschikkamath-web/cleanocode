import { useState, type FormEvent } from 'react';
import { downloadUrl, requestJson } from './api';
import type { ActionPlan, CopilotAnswer, ReportArtifactMetadata, WeeklyReport } from './types';
import './copilot.css';

type WorkspaceTab = 'copilot' | 'reports';

function ModeTag({ mode }: { mode: string }) {
  return <span className={`ct-mode ct-mode-${mode.toLowerCase()}`}>Narrative mode: {mode}</span>;
}

function ErrorText({ children }: { children: string }) {
  return <p className="ct-error" role="alert">{children}</p>;
}

export function CopilotPanel() {
  const [tab, setTab] = useState<WorkspaceTab>('copilot');
  const [question, setQuestion] = useState('Why did this alert happen, and what evidence is still missing?');
  const [eventId, setEventId] = useState('');
  const [answer, setAnswer] = useState<CopilotAnswer | null>(null);
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [actionPlan, setActionPlan] = useState<ActionPlan | null>(null);
  const [savedReport, setSavedReport] = useState<ReportArtifactMetadata | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function ask(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await requestJson<CopilotAnswer>('/api/copilot/ask', {
        method: 'POST',
        body: JSON.stringify({ question: question.trim(), ...(eventId.trim() ? { event_id: eventId.trim() } : {}) }),
      });
      setAnswer(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Copilot request failed.');
    } finally {
      setBusy(false);
    }
  }

  async function createSavedReport(reportType: 'WEEKLY_SUSTAINABILITY' | 'ACTION_PLAN') {
    setBusy(true);
    setError('');
    try {
      const result = await requestJson<ReportArtifactMetadata>('/api/reports', {
        method: 'POST',
        body: JSON.stringify({ report_type: reportType, format: 'HTML' }),
      });
      setSavedReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not persist report artifacts.');
    } finally {
      setBusy(false);
    }
  }

  async function loadReports() {
    setBusy(true);
    setError('');
    try {
      const [nextReport, nextPlan] = await Promise.all([
        requestJson<WeeklyReport>('/api/copilot/reports/weekly'),
        requestJson<ActionPlan>('/api/copilot/reports/action-plan', { method: 'POST' }),
      ]);
      setReport(nextReport);
      setActionPlan(nextPlan);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load reports.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ct-workspace" aria-labelledby="ct-copilot-title">
      <header className="ct-workspace-head">
        <div>
          <p className="ct-eyebrow">ACCOUNT 07 / EXPLAINABILITY LAYER</p>
          <h2 id="ct-copilot-title">Sustainability Copilot</h2>
          <p>Evidence first. Backend-owned numbers. Human-approved decisions.</p>
        </div>
        <div className="ct-mode-legend" aria-label="Narrative modes">
          <span>LLM = provider response</span><span>CACHED = last good narrative</span><span>TEMPLATE = offline-safe</span>
        </div>
      </header>

      <div className="ct-tabs" role="tablist" aria-label="Copilot workspace">
        <button type="button" role="tab" aria-selected={tab === 'copilot'} className={tab === 'copilot' ? 'is-active' : ''} onClick={() => setTab('copilot')}>Ask Copilot</button>
        <button type="button" role="tab" aria-selected={tab === 'reports'} className={tab === 'reports' ? 'is-active' : ''} onClick={() => { setTab('reports'); if (!report) void loadReports(); }}>Reports & action plan</button>
      </div>

      {error && <ErrorText>{error}</ErrorText>}

      {tab === 'copilot' ? (
        <div className="ct-copilot-grid">
          <form className="ct-panel ct-ask-form" onSubmit={ask}>
            <div className="ct-panel-title"><span className="ct-step">01</span><div><h3>Ask about the evidence</h3><p>The model receives a bounded facts snapshot, not camera frames.</p></div></div>
            <label htmlFor="ct-event-id">Event ID <span>(optional)</span></label>
            <input id="ct-event-id" value={eventId} maxLength={120} onChange={(e) => setEventId(e.target.value)} placeholder="Paste an event ID to focus the answer" />
            <label htmlFor="ct-question">Question</label>
            <textarea id="ct-question" rows={4} maxLength={1200} value={question} onChange={(e) => setQuestion(e.target.value)} required />
            <button className="ct-primary" type="submit" disabled={busy || question.trim().length < 3}>{busy ? 'Working…' : 'Explain with evidence'} <span aria-hidden="true">↗</span></button>
            <p className="ct-footnote">Suggestions do not issue commands. Unknown or stale sensor states must stay unknown.</p>
          </form>

          <div className="ct-panel ct-answer-panel" aria-live="polite" aria-busy={busy}>
            <div className="ct-panel-title"><span className="ct-step">02</span><div><h3>Grounded response</h3><p>Explanation is separate from computed facts.</p></div></div>
            {!answer ? <div className="ct-empty"><span className="ct-empty-glyph" aria-hidden="true">◎</span><h4>Ready to investigate</h4><p>Ask a question to see source references, provenance, limitations and safe next steps.</p></div> : (
              <>
                <div className="ct-answer-meta"><ModeTag mode={answer.mode} /><span>Source status: <strong>{answer.grounding.source_status}</strong></span></div>
                <h4 className="ct-answer-summary">{answer.summary}</h4>
                <ol className="ct-answer-lines">{answer.lines.map((line, index) => <li key={`${index}-${line}`}>{line}</li>)}</ol>
                {answer.recommendations.length > 0 && <div className="ct-recommendations"><h4>Suggested next steps</h4>{answer.recommendations.map((item, index) => <article key={`${item.title}-${index}`} className="ct-recommendation"><h5>{item.title}</h5><p>{item.rationale}</p><p><strong>Next:</strong> {item.next_step}</p>{item.fact_refs.length > 0 && <p className="ct-ref-line">Evidence IDs: {item.fact_refs.join(', ')}</p>}</article>)}</div>}
                <div className="ct-origin-strip" aria-label="Facts provenance counts">
                  <div><strong>{answer.grounding.real_count}</strong><span>REAL records</span></div>
                  <div><strong>{answer.grounding.simulated_count}</strong><span>SIMULATED</span></div>
                  <div><strong>{answer.grounding.derived_count}</strong><span>DERIVED</span></div>
                  <div><strong>{answer.grounding.unknown_count}</strong><span>UNKNOWN</span></div>
                </div>
                {answer.fact_references.length > 0 && <details className="ct-details"><summary>Inspect source references ({answer.fact_references.length})</summary><ul>{answer.fact_references.map((ref) => <li key={`${ref.kind}-${ref.id}`}><code>{ref.id}</code> — {ref.label} <span className="ct-inline-provenance">{ref.provenance}</span></li>)}</ul></details>}
                <details className="ct-details"><summary>Assumptions & limitations</summary><ul>{Object.entries(answer.grounding.assumptions).map(([key, value]) => <li key={key}><strong>{key}:</strong> {value}</li>)}{answer.grounding.unavailable_inputs.map((item) => <li key={item}>Unavailable: {item}</li>)}{answer.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="ct-report-stack">
          <div className="ct-panel ct-report-heading"><div><p className="ct-eyebrow">REPORT CENTER</p><h3>Weekly sustainability report</h3><p>Exports include provenance, limitations and the source IDs supplied by the facts provider.</p></div><button type="button" className="ct-secondary" onClick={() => void loadReports()} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh report'}</button></div>
          <div className="ct-export-row" aria-label="Download weekly report">
            <a href={downloadUrl('/api/copilot/reports/weekly/export?format=json')} download>Download JSON</a>
            <a href={downloadUrl('/api/copilot/reports/weekly/export?format=csv')} download>Download CSV</a>
            <a href={downloadUrl('/api/copilot/reports/weekly/export?format=html')} download>Download HTML</a>
            <a href={downloadUrl('/api/copilot/reports/action-plan/export?format=csv')} download>Action plan CSV</a>
          </div>
          <div className="ct-saved-report-actions">
            <button type="button" className="ct-secondary" onClick={() => void createSavedReport('WEEKLY_SUSTAINABILITY')} disabled={busy}>Generate saved weekly report</button>
            <button type="button" className="ct-secondary" onClick={() => void createSavedReport('ACTION_PLAN')} disabled={busy}>Generate saved action-plan packet</button>
          </div>
          {savedReport && <div className="ct-panel ct-saved-report" aria-live="polite">
            <div className="ct-answer-meta"><span className="ct-mode">Format: {savedReport.format}</span><span>Saved report: <code>{savedReport.id}</code></span></div>
            <p>{savedReport.report_type.replace(/_/g, ' ')} · {new Date(savedReport.period_start).toLocaleDateString()} – {new Date(savedReport.period_end).toLocaleDateString()}</p>
            <p>Source IDs: {savedReport.source_event_ids.length} events · {savedReport.source_action_ids.length} actions · {savedReport.source_ledger_ids.length} ledger entries</p>
            <div className="ct-export-row" aria-label="Download persisted report formats">{savedReport.available_formats.map((format) => <a key={format} href={downloadUrl(`${savedReport.file_reference}?format=${format}`)} download>{format} artifact</a>)}</div>
            <details className="ct-details"><summary>Artifact assumptions and limitations</summary><ul>{Object.entries(savedReport.assumptions).map(([key, value]) => <li key={key}><strong>{key}:</strong> {value}</li>)}{savedReport.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
          </div>}
          {!report ? <div className="ct-panel ct-empty"><h4>No report loaded yet</h4><p>Select Refresh report to retrieve the current facts-based report from the backend.</p></div> : <>
            <div className="ct-metric-grid">
              <Metric label="Readings" value={report.metrics.reading_count} detail={`REAL ${report.metrics.readings_by_provenance.REAL ?? 0} · SIMULATED ${report.metrics.readings_by_provenance.SIMULATED ?? 0}`} />
              <Metric label="Open events" value={report.metrics.events_open} detail={`${report.metrics.events_total} events in period`} />
              <Metric label="Verified actions" value={report.metrics.actions_verified_success} detail={`${report.metrics.actions_failed_or_timed_out} failed / timed out`} />
              <Metric label="Verified simulated energy" value={report.metrics.verified_simulated.energy_kwh ?? 'UNAVAILABLE'} detail="kWh · not measured campus savings" />
            </div>
            <div className="ct-panel"><div className="ct-answer-meta"><ModeTag mode={report.mode} /><span>Period: {new Date(report.period_start).toLocaleDateString()} – {new Date(report.period_end).toLocaleDateString()}</span></div><h4>{report.summary}</h4><ul className="ct-answer-lines">{report.narrative_lines.map((line, index) => <li key={`${index}-${line}`}>{line}</li>)}</ul><h4>Verified vs simulated</h4><ul>{report.verified_vs_simulated.map((line) => <li key={line}>{line}</li>)}</ul><details className="ct-details"><summary>Assumptions, unavailable inputs and limitations</summary><ul>{Object.entries(report.assumptions).map(([key, value]) => <li key={key}><strong>{key}:</strong> {value}</li>)}{report.unavailable_inputs.map((item) => <li key={item}>Unavailable: {item}</li>)}{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details></div>
          </>}
          <div className="ct-panel"><div className="ct-report-heading"><div><p className="ct-eyebrow">OPERATOR QUEUE</p><h3>Prioritized action plan</h3><p>Priority comes from a deterministic severity map—not from the LLM.</p></div><button type="button" className="ct-secondary" onClick={() => void loadReports()} disabled={busy}>Refresh plan</button></div>
            {!actionPlan ? <p className="ct-empty-inline">Action plan has not been loaded.</p> : <><div className="ct-answer-meta"><ModeTag mode={actionPlan.mode} /><span>{actionPlan.items.length} open events in this plan</span></div><h4>{actionPlan.summary}</h4><ol className="ct-plan-list">{actionPlan.items.map((item) => <li key={item.event_id}><div className="ct-plan-head"><span className={`ct-priority ct-priority-${item.priority.toLowerCase()}`}>{item.priority}</span><strong>{item.event_type}</strong><code>{item.event_id}</code></div><p>{item.reason}</p><p><strong>Next:</strong> {item.proposed_next_step}</p><p className="ct-ref-line">{item.provenance} · Evidence: {item.evidence_ids.length ? item.evidence_ids.join(', ') : 'none supplied'}</p><div className="ct-plan-impact"><strong>Deterministic impact: {item.projected_impact.status}</strong><span>Energy: {item.projected_impact.energy_avoided_kwh ?? 'UNAVAILABLE'} kWh</span><span>Water: {item.projected_impact.water_avoided_liters ?? 'UNAVAILABLE'} L</span><span>Cost: {item.projected_impact.cost_avoided_amount ?? 'UNAVAILABLE'} {item.projected_impact.cost_currency ?? ''}</span><span>CO₂: {item.projected_impact.co2_avoided_kg ?? 'UNAVAILABLE'} kg</span>{item.projected_impact.source_ids.length > 0 && <small>Impact sources: {item.projected_impact.source_ids.join(', ')}</small>}{item.projected_impact.assumptions.map((assumption) => <small key={assumption}>{assumption}</small>)}</div></li>)}</ol></>}
          </div>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <article className="ct-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}
