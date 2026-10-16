import { useState, type FormEvent } from 'react';
import { requestJson } from '../copilot/api';
import type { CopilotMode, Provenance } from '../copilot/types';
import './what-if.css';

type Estimate = {
  name: string;
  reduction_percent: string | number;
  status: 'CALCULATED' | 'UNAVAILABLE';
  room_id: string;
  duration_hours: string | number;
  baseline_power_watts?: string | number | null;
  baseline_provenance: Provenance;
  baseline_source_id?: string | null;
  baseline_energy_kwh?: string | number | null;
  projected_avoided_energy_kwh?: string | number | null;
  projected_remaining_energy_kwh?: string | number | null;
  projected_cost_avoided?: string | number | null;
  cost_currency?: string | null;
  projected_co2_avoided_kg?: string | number | null;
  energy_tariff_per_kwh?: string | number | null;
  co2_factor_kg_per_kwh?: string | number | null;
  assumptions: string[];
  missing_inputs: string[];
  source_ids: string[];
  impact_status: 'PROJECTED_NOT_VERIFIED';
};

type WhatIfResponse = {
  generated_at: string;
  mode: CopilotMode;
  summary: string;
  explanation_lines: string[];
  comparisons: Estimate[];
  grounding: { source_status: string; real_count: number; simulated_count: number; derived_count: number; unknown_count: number; assumptions: Record<string, string>; unavailable_inputs: string[] };
  fact_references: Array<{ id: string; kind: string; label: string; provenance: Provenance }>;
  recommendations: Array<{ title: string; rationale: string; next_step: string; fact_refs: string[] }>;
  limitations: string[];
};

type InterventionDraft = { name: string; reductionPercent: string };
const STARTER_INTERVENTIONS: InterventionDraft[] = [
  { name: 'Conservative adjustment', reductionPercent: '10' },
  { name: 'Moderate adjustment', reductionPercent: '25' },
  { name: 'Aggressive adjustment', reductionPercent: '40' },
];

function shown(value: string | number | null | undefined, unit = ''): string {
  if (value === null || value === undefined || value === '') return 'UNAVAILABLE';
  return `${value}${unit ? ` ${unit}` : ''}`;
}

function ProvenanceTag({ value }: { value: string }) {
  return <span className="ctwf-tag">{value}</span>;
}

export function WhatIfArena() {
  const [roomId, setRoomId] = useState('');
  const [durationHours, setDurationHours] = useState('2');
  const [manualBaseline, setManualBaseline] = useState('');
  const [interventions, setInterventions] = useState<InterventionDraft[]>(STARTER_INTERVENTIONS);
  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function updateIntervention(index: number, key: keyof InterventionDraft, value: string) {
    setInterventions((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  }

  async function compare(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = {
        room_id: roomId.trim(),
        duration_hours: Number(durationHours),
        ...(manualBaseline.trim() ? { scenario_baseline_watts: Number(manualBaseline) } : {}),
        interventions: interventions.map((item) => ({ name: item.name.trim(), reduction_percent: Number(item.reductionPercent) })),
      };
      const next = await requestJson<WhatIfResponse>('/api/what-if/compare', { method: 'POST', body: JSON.stringify(body) });
      setResult(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scenario comparison failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ctwf-root" aria-labelledby="ctwf-title">
      <header className="ctwf-head">
        <div><p className="ctwf-eyebrow">SCENARIO LAB / DETERMINISTIC IMPACT</p><h2 id="ctwf-title">Campus What‑If Arena</h2><p>Compare interventions against one baseline. Numeric outputs come from backend formulas—not the language model.</p></div>
        <div className="ctwf-stamp"><strong>PROJECTED</strong><span>not verified savings</span></div>
      </header>

      {error && <p className="ctwf-error" role="alert">{error}</p>}

      <div className="ctwf-layout">
        <form className="ctwf-panel ctwf-form" onSubmit={compare}>
          <div className="ctwf-section-title"><span>01</span><div><h3>Define the baseline</h3><p>Room and duration apply to every comparison.</p></div></div>
          <label htmlFor="ctwf-room">Room ID</label>
          <input id="ctwf-room" value={roomId} onChange={(e) => setRoomId(e.target.value)} required maxLength={120} placeholder="e.g. building-room identifier" />
          <label htmlFor="ctwf-duration">Duration (hours)</label>
          <input id="ctwf-duration" type="number" min="0.001" max="168" step="0.25" required value={durationHours} onChange={(e) => setDurationHours(e.target.value)} />
          <label htmlFor="ctwf-baseline">Manual baseline power (watts) <span>optional</span></label>
          <input id="ctwf-baseline" type="number" min="0.001" max="100000000" step="any" value={manualBaseline} onChange={(e) => setManualBaseline(e.target.value)} placeholder="Leave blank to use a healthy room reading" />
          <p className="ctwf-assumption-note">A manual baseline is always labelled <strong>SIMULATED</strong>. Leave it blank to use the latest healthy room reading from the facts provider.</p>
          <div className="ctwf-section-title ctwf-intervention-title"><span>02</span><div><h3>Compare interventions</h3><p>Use the same baseline and time window.</p></div></div>
          {interventions.map((item, index) => <div className="ctwf-intervention" key={index}>
            <label htmlFor={`ctwf-name-${index}`}>Option {index + 1} name</label>
            <input id={`ctwf-name-${index}`} value={item.name} onChange={(e) => updateIntervention(index, 'name', e.target.value)} required maxLength={100} />
            <label htmlFor={`ctwf-reduction-${index}`}>Target reduction (%)</label>
            <div className="ctwf-range-row"><input id={`ctwf-reduction-${index}`} type="number" min="0.001" max="100" step="0.1" required value={item.reductionPercent} onChange={(e) => updateIntervention(index, 'reductionPercent', e.target.value)} /><span>{Number(item.reductionPercent) > 0 && Number(item.reductionPercent) <= 100 ? 'Scenario input' : 'Enter 0–100%'}</span></div>
          </div>)}
          <button className="ctwf-primary" type="submit" disabled={busy || !roomId.trim() || interventions.some((i) => !i.name.trim() || !Number.isFinite(Number(i.reductionPercent)) || Number(i.reductionPercent) <= 0 || Number(i.reductionPercent) > 100)}>{busy ? 'Calculating…' : 'Compare scenarios'} <span aria-hidden="true">↗</span></button>
          <p className="ctwf-footnote">This control runs a backend calculation only. It does not control a device or update the impact ledger.</p>
        </form>

        <div className="ctwf-results" aria-live="polite" aria-busy={busy}>
          {!result ? <div className="ctwf-panel ctwf-empty"><span aria-hidden="true">◇</span><h3>Run a comparison</h3><p>Results will show baseline provenance, projected energy, optional cost/carbon estimates, assumptions and unavailable inputs.</p></div> : <>
            <div className="ctwf-panel ctwf-explanation">
              <div className="ctwf-response-top"><div><p className="ctwf-eyebrow">BACKEND RESULT</p><h3>{result.summary}</h3></div><ProvenanceTag value={result.mode} /></div>
              <ol>{result.explanation_lines.map((line, index) => <li key={`${index}-${line}`}>{line}</li>)}</ol>
              <p className="ctwf-source-status">Facts source: <strong>{result.grounding.source_status}</strong> · Evidence is not treated as measured impact unless its provenance supports that claim.</p>
            </div>
            <div className="ctwf-cards">
              {result.comparisons.map((item, index) => <article className="ctwf-panel ctwf-scenario-card" key={`${item.name}-${index}`}>
                <div className="ctwf-scenario-title"><div><span className="ctwf-number">0{index + 1}</span><h3>{item.name}</h3></div><span className={`ctwf-status ctwf-status-${item.status.toLowerCase()}`}>{item.status}</span></div>
                <div className="ctwf-card-subtitle"><strong>{shown(item.reduction_percent, '%')}</strong> target reduction <span>·</span> {shown(item.duration_hours, 'h')}</div>
                <div className="ctwf-primary-metric"><span>Projected energy avoided</span><strong>{shown(item.projected_avoided_energy_kwh, 'kWh')}</strong></div>
                <div className="ctwf-mini-grid">
                  <div><span>Baseline power</span><strong>{shown(item.baseline_power_watts, 'W')}</strong><small>{item.baseline_provenance}</small></div>
                  <div><span>Baseline energy</span><strong>{shown(item.baseline_energy_kwh, 'kWh')}</strong></div>
                  <div><span>Projected remaining</span><strong>{shown(item.projected_remaining_energy_kwh, 'kWh')}</strong></div>
                  <div><span>Projected cost avoided</span><strong>{shown(item.projected_cost_avoided, item.cost_currency ?? '')}</strong></div>
                  <div><span>Projected CO₂ avoided</span><strong>{shown(item.projected_co2_avoided_kg, 'kg')}</strong></div>
                  <div><span>Impact status</span><strong>NOT VERIFIED</strong></div>
                </div>
                <div className="ctwf-subsections"><h4>Assumptions</h4><ul>{item.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>{item.missing_inputs.length > 0 && <><h4>Unavailable inputs</h4><ul>{item.missing_inputs.map((missing) => <li key={missing}>{missing}</li>)}</ul></>}{item.source_ids.length > 0 && <p className="ctwf-source-ids">Baseline source: {item.source_ids.join(', ')}</p>}</div>
              </article>)}
            </div>
            {result.limitations.length > 0 && <details className="ctwf-panel ctwf-details"><summary>Trust, assumptions and limitations</summary><ul>{result.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}{Object.entries(result.grounding.assumptions).map(([key, value]) => <li key={key}><strong>{key}:</strong> {value}</li>)}{result.grounding.unavailable_inputs.map((item) => <li key={item}>Unavailable: {item}</li>)}</ul></details>}
          </>}
        </div>
      </div>
    </section>
  );
}
