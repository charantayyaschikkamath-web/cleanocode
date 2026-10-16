import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity, AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, Check, CheckCircle2, ChevronRight,
  CircleDot, Clock3, Download, Droplets, FileJson, Filter, Gauge, History, Info, Leaf, LoaderCircle,
  LockKeyhole, RefreshCw, Search, Send, ShieldAlert, ShieldCheck, Siren, Sparkles, TrendingDown, Waves, X, Zap,
} from 'lucide-react';
import { api, ApiError } from './api/client';
import { AppShell } from './components/AppShell';
import { PageHeader, Toasts, type ToastMessage } from './components/Toast';
import { ActionStatusTag, EventStatusTag, ProvenanceTag, SeverityTag, StatusPill } from './components/StatusPill';
import { TwinRoute } from './features/twin/TwinRoute';
import { CameraRoute } from './features/camera/CameraRoute';
import { createDemoOverview, demoActions, demoCopilot, demoEvents } from './demo/demoData';
import type {
  ActionState, ActionTransition, CampusAction, CampusEvent, CampusSettings, CopilotResponse, DashboardOverview,
  LedgerEntry, NavKey, ScenarioOutcome, SystemHealth, WhatIfRequest, WhatIfResponse,
} from './types';
import { csvCell, downloadFile, formatDate, formatNumber, timeAgo } from './utils/format';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
const POLL_INTERVAL = Math.max(5000, Number(import.meta.env.VITE_POLL_INTERVAL_MS || 15000));

function IconButton({ children, label, onClick, disabled, className = '' }: { children: ReactNode; label: string; onClick?: () => void; disabled?: boolean; className?: string }) {
  return <button className={`icon-button ${className}`} aria-label={label} title={label} onClick={onClick} disabled={disabled}>{children}</button>;
}

function MetricCard({ title, value, unit, icon, accent, note, provenance }: { title: string; value: number | null; unit: string; icon: ReactNode; accent: string; note?: string; provenance: 'REAL' | 'SIMULATED' | 'DERIVED' | 'UNKNOWN' }) {
  return <article className="metric-card">
    <div className={`metric-icon ${accent}`}>{icon}</div>
    <div className="metric-title-row"><span>{title}</span><ProvenanceTag value={provenance} /></div>
    <div className="metric-value">{value === null ? '—' : formatNumber(value)}<small>{value === null ? '' : ` ${unit}`}</small></div>
    <div className="metric-note">{note || (value === null ? 'Data unavailable' : 'Current reporting period')}</div>
  </article>;
}

function SectionTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="section-title-row"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}

function EmptyState({ title, text, icon = <Activity size={21} />, action }: { title: string; text: string; icon?: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-state-icon">{icon}</span><h3>{title}</h3><p>{text}</p>{action}</div>;
}

function HealthStripFallback({ retry }: { retry: () => void }) {
  return <div className="connection-error"><div className="connection-error-icon"><AlertCircle size={18} /></div><div><strong>Backend data is unavailable</strong><p>No live metrics are being substituted. Start the backend and check <code>VITE_API_BASE_URL</code>, then retry.</p></div><button className="button button-secondary button-small" onClick={retry}><RefreshCw size={14} /> Retry connection</button></div>;
}

function EventRow({ event, onSelect }: { event: CampusEvent; onSelect: (id: string) => void }) {
  return <button className="event-row" onClick={() => onSelect(event.id)}>
    <span className={`event-severity-dot sev-${event.severity.toLowerCase()}`} />
    <span className="event-row-main"><strong>{event.title}</strong><span>{event.buildingName}{event.roomName ? ` · ${event.roomName}` : ''}</span></span>
    <span className="event-row-meta"><SeverityTag value={event.severity} /><small>{timeAgo(event.updatedAt)}</small></span>
    <ChevronRight size={16} className="muted-icon" />
  </button>;
}

function DetailDrawer({ event, onClose, onFeedback }: { event: CampusEvent; onClose: () => void; onFeedback: (id: string, feedback: 'FALSE_ALARM' | 'CONFIRMED') => void }) {
  return <div className="drawer-backdrop" role="presentation" onMouseDown={(eventMouse) => { if (eventMouse.target === eventMouse.currentTarget) onClose(); }}>
    <aside className="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="event-detail-title">
      <div className="drawer-header"><div><span className="eyebrow">EVENT EVIDENCE · {event.id}</span><h2 id="event-detail-title">{event.title}</h2></div><IconButton label="Close event detail" onClick={onClose}><X size={18} /></IconButton></div>
      <div className="drawer-status-line"><SeverityTag value={event.severity} /><EventStatusTag value={event.status} /><ProvenanceTag value={event.provenance} /></div>
      <p className="drawer-summary">{event.summary}</p>
      <div className="detail-context-grid"><div><span>Location</span><strong>{event.buildingName}</strong><small>{event.roomName || 'Building-level event'}</small></div><div><span>Last updated</span><strong>{formatDate(event.updatedAt)}</strong><small>{timeAgo(event.updatedAt)}</small></div></div>
      <div className="evidence-rule-card"><div className="evidence-card-icon"><ShieldCheck size={17} /></div><div><span>TRIGGERING RULE</span><strong>{event.triggerRule}</strong><p>{event.threshold}</p></div></div>
      <div className="drawer-section"><div className="drawer-section-title"><h3>Why this triggered</h3><span className="tiny-label">RULE EXPLANATION</span></div><p>{event.explanation}</p></div>
      <div className="drawer-section"><div className="drawer-section-title"><h3>Evidence received</h3><span className="count-bubble">{event.evidence.length}</span></div>
        <div className="evidence-list">{event.evidence.map((item) => <div className="evidence-item" key={item.id}><span className="evidence-item-icon">{item.reading?.resourceType === 'WATER' ? <Droplets size={16} /> : item.reading?.resourceType === 'ENERGY' ? <Zap size={16} /> : item.reading?.resourceType === 'OCCUPANCY' ? <Activity size={16} /> : <Info size={16} />}</span><div className="evidence-item-copy"><strong>{item.label}</strong><span>{item.detail}</span>{item.reading && <div className="reading-inline"><b>{String(item.reading.value ?? '—')} {item.reading.unit}</b><span>{item.reading.sourceName}</span><span>{formatDate(item.reading.observedAt)}</span></div>}</div>{item.reading && <ProvenanceTag value={item.reading.provenance} />}</div>)}</div>
      </div>
      <div className="drawer-section"><div className="drawer-section-title"><h3>Evidence limits</h3><ShieldAlert size={16} /></div><ul className="limitation-list">{event.limitations.map((limitation, index) => <li key={`${event.id}-limit-${index}`}>{limitation}</li>)}</ul></div>
      <div className="drawer-footer"><button className="button button-secondary" onClick={() => onFeedback(event.id, 'FALSE_ALARM')}><X size={15} /> Mark false alarm</button><button className="button button-primary" onClick={() => onFeedback(event.id, 'CONFIRMED')}><Check size={15} /> Confirm event</button></div>
    </aside>
  </div>;
}

function OverviewPage({
  overview, events, actions, onOpenEvent, onRunScenario, onGo, refreshing,
}: {
  overview: DashboardOverview | null; events: CampusEvent[]; actions: CampusAction[]; onOpenEvent: (id: string) => void;
  onRunScenario: (scenario: string) => void; onGo: (key: NavKey) => void; refreshing: boolean;
}) {
  const [scenario, setScenario] = useState('empty_room_high_power');
  if (!overview) return <div className="page-stack"><PageHeader eyebrow="CAMPUS OPERATIONS" title="Campus command center" description="Your campus sustainability picture, with evidence attached to every signal." /><EmptyState title="Waiting for trusted data" text="No persisted records are available yet. Run an explicitly labelled synthetic scenario to initialize the local demo flow, or connect real campus data." icon={<Gauge size={22} />} action={<button className="button button-primary" onClick={() => onRunScenario('empty_room_high_power')}>Run a labelled demo scenario <ArrowRight size={15} /></button>} /></div>;
  const kpiCards = [
    { title: 'Energy consumed', metric: overview.kpis.energy, icon: <Zap size={18} />, accent: 'accent-energy' },
    { title: 'Water used', metric: overview.kpis.water, icon: <Droplets size={18} />, accent: 'accent-water' },
    { title: 'Waste capacity', metric: overview.kpis.waste, icon: <Waves size={18} />, accent: 'accent-waste' },
    { title: 'Estimated cost', metric: overview.kpis.cost, icon: <Activity size={18} />, accent: 'accent-cost' },
    { title: 'CO₂e estimate', metric: overview.kpis.co2, icon: <Leaf size={18} />, accent: 'accent-carbon' },
    { title: 'Verified savings', metric: overview.kpis.verifiedSavings, icon: <TrendingDown size={18} />, accent: 'accent-savings' },
  ];
  return <div className="page-stack">
    <PageHeader eyebrow="THURSDAY · CAMPUS OPERATIONS" title="Campus command center" description="See what needs attention, why it happened, and what has actually been verified."
      actions={<><div className="refresh-meta"><span className="small-live-dot" />Updated {timeAgo(overview.generatedAt)}</div><button className="button button-secondary button-small" onClick={() => onGo('reports')}><FileJson size={15} /> Export report</button></>} />
    <div className="overview-meta-row"><div className="meta-note"><span className="meta-note-icon"><LockKeyhole size={14} /></span><span><strong>Evidence-first reporting</strong> · Missing factors stay unavailable; simulated inputs stay labelled.</span></div><div className="last-check">{refreshing && <LoaderCircle className="spin" size={14} />} Last refresh: {formatDate(overview.generatedAt, { year: undefined })}</div></div>
    <div className="metric-grid">{kpiCards.map((card) => <MetricCard key={card.title} title={card.title} value={card.metric.value} unit={card.metric.unit} icon={card.icon} accent={card.accent} note={card.metric.note || card.metric.period} provenance={card.metric.provenance} />)}</div>
    <div className="overview-top-grid">
      <section className="panel pulse-panel">
        <div className="panel-heading"><div><span className="eyebrow">CAMPUS SUSTAINABILITY PULSE</span><h2>{overview.pulse.label}</h2><p>A transparent operational heuristic—not a validated sustainability certification.</p></div><span className="pulse-icon"><Gauge size={20} /></span></div>
        <div className="pulse-score-row"><div className="pulse-score">{overview.pulse.value === null ? '—' : overview.pulse.value}<small>{overview.pulse.value === null ? '' : '/100'}</small></div><div className="pulse-score-copy"><strong>{overview.pulse.value === null ? 'Score unavailable' : overview.pulse.value >= 80 ? 'Operationally steady' : overview.pulse.value >= 60 ? 'Attention needed' : 'Intervention needed'}</strong><span>Calculated from named inputs, where available.</span><button className="text-link" onClick={() => onGo('reports')}>View formula <ArrowUpRight size={13} /></button></div></div>
        <div className="pulse-breakdown">{overview.pulse.components.map((part) => <div className="pulse-breakdown-row" key={part.label}><span>{part.label}</span><div className="mini-bar-track"><span style={{ width: `${Math.max(0, Math.min(100, part.value ?? 0))}%` }} /></div><strong>{part.value === null ? '—' : part.value}</strong></div>)}</div>
        <div className="formula-note"><Info size={13} /><span>{overview.pulse.formula}</span></div>
      </section>
      <section className="panel priority-panel">
        <div className="panel-heading"><div><span className="eyebrow">NEXT BEST ACTION</span><h2>Attention queue</h2><p>Prioritize using visible evidence—not an opaque score.</p></div><span className="priority-count">{overview.counts.actionsAwaitingApproval.toString().padStart(2, '0')}</span></div>
        <div className="queue-stats"><div><span>Open events</span><strong>{overview.counts.openEvents}</strong></div><div><span>Need approval</span><strong>{overview.counts.actionsAwaitingApproval}</strong></div><div><span>Verified actions</span><strong>{overview.counts.verifiedActions}</strong></div></div>
        {actions.filter((action) => action.state === 'PENDING_APPROVAL').slice(0, 2).map((action) => <button className="priority-action" key={action.id} onClick={() => onGo('actions')}><span className="priority-action-mark"><ShieldCheck size={16} /></span><span><strong>{action.proposedAction}</strong><small>{action.buildingName} · Human approval required</small></span><ArrowUpRight size={15} /></button>)}
        {actions.filter((action) => action.state === 'PENDING_APPROVAL').length === 0 && <div className="queue-empty"><CheckCircle2 size={16} /><span>No action is waiting for approval in the loaded records.</span></div>}
        <button className="button button-secondary full-width" onClick={() => onGo('actions')}>Review action history <ArrowRight size={15} /></button>
      </section>
    </div>
    <div className="overview-bottom-grid">
      <section className="panel building-panel">
        <div className="panel-heading"><div><h2>Buildings at a glance</h2><p>Issues and energy readings by building; values may have different completeness.</p></div><button className="text-link" onClick={() => onGo('twin')}>Open campus twin <ArrowUpRight size={13} /></button></div>
        <div className="building-list">{overview.buildings.slice(0, 4).map((building) => <button className="building-list-row" key={building.id} onClick={() => onGo('twin')}><span className={`building-mini-icon state-${building.state.toLowerCase()}`}><span>{building.shortName.slice(0, 2)}</span></span><span className="building-list-copy"><strong>{building.name}</strong><small>{building.rooms ?? '—'} rooms · {building.activeEvents ?? '—'} active issues</small></span><span className="building-reading">{building.energyKwh === null ? '—' : formatNumber(building.energyKwh)}<small>{building.energyKwh === null ? 'No reading' : 'kWh'}</small></span><StatusPill value={building.state} /><ChevronRight size={15} /></button>)}</div>
        <div className="panel-footer-row"><span><span className="footer-marker" /> {overview.counts.buildingsWithIssues} buildings with issues reported</span><button className="text-link" onClick={() => onGo('twin')}>Inspect locations <ArrowRight size={13} /></button></div>
      </section>
      <section className="panel quick-scenario-panel">
        <div className="panel-heading"><div><span className="eyebrow">REPEATABLE TEST</span><h2>Scenario lab</h2><p>Trigger a named scenario and inspect the actual result.</p></div><span className="scenario-icon"><FlaskIcon /></span></div>
        <label className="field-label" htmlFor="quick-scenario">Scenario preset</label>
        <select id="quick-scenario" className="form-select" value={scenario} onChange={(event) => setScenario(event.target.value)}>
          <option value="empty_room_high_power">Empty room + high power</option><option value="night_water_flow">Night-time water flow</option><option value="bin_overflow">Bin overflow</option><option value="normal_operation">Normal campus operation</option><option value="sensor_unavailable">Sensor missing / stale</option><option value="command_dropped">Command dropped</option><option value="acknowledged_ignored">Acknowledged but ignored</option><option value="verified_success">Successful verified response</option>
        </select>
        <div className="scenario-truth-note"><Info size={14} /><span>{DEMO_MODE ? 'This will change local synthetic preview state only.' : 'This sends a scenario request to the backend; source provenance comes from its response.'}</span></div>
        <button className="button button-primary full-width" onClick={() => onRunScenario(scenario)}><Sparkles size={15} /> Run scenario <ArrowRight size={15} /></button>
        <div className="scenario-preset-foot"><span><CheckCircle2 size={13} /> Repeatable</span><span><History size={13} /> Audit-friendly</span></div>
      </section>
    </div>
    <section className="panel event-feed-panel">
      <div className="panel-heading"><div><h2>Recent events</h2><p>Open a record to see the trigger, evidence, freshness and limits.</p></div><button className="button button-ghost button-small" onClick={() => onGo('events')}>All events <ArrowRight size={14} /></button></div>
      {events.length ? <div className="event-table">{events.slice(0, 4).map((event) => <EventRow key={event.id} event={event} onSelect={onOpenEvent} />)}</div> : <EmptyState title="No event records" text="No event data was returned for the current view." />}
    </section>
  </div>;
}

function FlaskIcon() { return <FlaskConicalFallback />; }
function FlaskConicalFallback() { return <Sparkles size={19} />; }

function EventsPage({ events, selectedId, setSelectedId, search, setSearch, status, setStatus, severity, setSeverity, resource, setResource, onFeedback }: {
  events: CampusEvent[]; selectedId: string | null; setSelectedId: (id: string | null) => void; search: string; setSearch: (s: string) => void;
  status: string; setStatus: (s: string) => void; severity: string; setSeverity: (s: string) => void; resource: string; setResource: (s: string) => void; onFeedback: (id: string, feedback: 'FALSE_ALARM' | 'CONFIRMED') => void;
}) {
  const filtered = useMemo(() => events.filter((event) => {
    const query = search.toLowerCase().trim();
    return (!query || [event.title, event.id, event.buildingName, event.roomName, event.summary, event.eventType].some((value) => value?.toLowerCase().includes(query)))
      && (status === 'ALL' || event.status === status) && (severity === 'ALL' || event.severity === severity)
      && (resource === 'ALL' || (resource === 'ENERGY' && (event.eventType.includes('energy') || event.evidence.some((item) => item.reading?.resourceType === 'ENERGY')))
        || (resource === 'WATER' && (event.eventType.includes('water') || event.evidence.some((item) => item.reading?.resourceType === 'WATER')))
        || (resource === 'WASTE' && (event.eventType.includes('bin') || event.eventType.includes('waste')))
        || (resource === 'OCCUPANCY' && (event.eventType.includes('occupancy') || event.eventType.includes('sensor') || event.evidence.some((item) => item.reading?.resourceType === 'OCCUPANCY'))));
  }), [events, search, status, severity, resource]);
  const selected = filtered.find((event) => event.id === selectedId) ?? null;
  return <div className="page-stack">
    <PageHeader eyebrow="INCIDENT MANAGEMENT" title="Live events" description="Investigate the evidence behind each signal before approving a response." actions={<div className="small-counter"><span>{filtered.length}</span> records in view</div>} />
    <div className="panel filters-panel"><div className="search-field"><Search size={17} /><input aria-label="Search events" placeholder="Search title, room, event ID…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><div className="filter-select-wrap"><Filter size={15} /><select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">All statuses</option><option value="OPEN">Open</option><option value="ACKNOWLEDGED">Acknowledged</option><option value="RESOLVED">Resolved</option><option value="FALSE_ALARM">False alarm</option></select></div><div className="filter-select-wrap"><CircleDot size={15} /><select aria-label="Filter by severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="ALL">All severities</option><option value="CRITICAL">Critical</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option></select></div><div className="filter-select-wrap resource-filter"><Waves size={15} /><select aria-label="Filter by resource" value={resource} onChange={(event) => setResource(event.target.value)}><option value="ALL">All resources</option><option value="ENERGY">Energy</option><option value="WATER">Water</option><option value="WASTE">Waste</option><option value="OCCUPANCY">Occupancy / sensors</option></select></div></div>
    <div className="events-layout">
      <section className="panel event-list-panel"><div className="panel-heading"><div><h2>Event queue</h2><p>Sorted by most recently updated.</p></div><span className="count-bubble">{filtered.length}</span></div>
        {filtered.length ? <div className="event-list">{filtered.map((event) => <button key={event.id} className={`event-card ${event.id === selectedId ? 'selected' : ''}`} onClick={() => setSelectedId(event.id)}><span className={`event-card-rail rail-${event.severity.toLowerCase()}`} /><div className="event-card-top"><span className="tiny-label">{event.id}</span><SeverityTag value={event.severity} /></div><h3>{event.title}</h3><p>{event.summary}</p><div className="event-card-bottom"><span><BuildingIcon /> {event.buildingName}{event.roomName ? ` · ${event.roomName}` : ''}</span><span>{timeAgo(event.updatedAt)}</span></div><div className="event-card-bottom"><EventStatusTag value={event.status} /><ProvenanceTag value={event.provenance} /></div></button>)}</div> : <EmptyState title="No matching events" text="Try a different search or clear one of the filters." icon={<Search size={21} />} action={<button className="button button-secondary button-small" onClick={() => { setSearch(''); setStatus('ALL'); setSeverity('ALL'); setResource('ALL'); }}>Clear filters</button>} />}
      </section>
      <section className="panel event-inspector-panel">{selected ? <>
        <div className="panel-heading"><div><span className="eyebrow">EVIDENCE INSPECTOR</span><h2>{selected.id}</h2><p>{selected.title}</p></div><ProvenanceTag value={selected.provenance} /></div>
        <div className="inspector-trigger"><span className="inspector-trigger-icon"><ShieldCheck size={17} /></span><div><span>Matched rule</span><strong>{selected.triggerRule}</strong><p>{selected.threshold}</p></div></div>
        <p className="inspector-explanation">{selected.explanation}</p>
        <div className="inspector-section-head"><h3>Evidence points</h3><span>{selected.evidence.length} attached</span></div>
        {selected.evidence.map((item) => <div className="inspector-evidence" key={item.id}><div className="inspector-evidence-mark">{item.reading?.resourceType === 'WATER' ? <Droplets size={16} /> : item.reading?.resourceType === 'ENERGY' ? <Zap size={16} /> : <Info size={16} />}</div><div><strong>{item.label}</strong><p>{item.detail}</p>{item.reading && <div className="inspector-reading"><strong>{String(item.reading.value ?? '—')} {item.reading.unit}</strong><span>Age: {item.reading.ageSeconds === null ? 'unknown' : `${formatNumber(item.reading.ageSeconds, 0)} seconds`}</span><span>Source: {item.reading.sourceName}</span><span>Health: {item.reading.health}</span></div>}</div></div>)}
        <div className="inspector-limits"><ShieldAlert size={15} /><div><strong>What is still uncertain?</strong><ul>{selected.limitations.map((limit, i) => <li key={`${selected.id}-l-${i}`}>{limit}</li>)}</ul></div></div>
        <div className="inspector-actions"><button className="button button-secondary" onClick={() => onFeedback(selected.id, 'FALSE_ALARM')}><X size={14} /> False alarm</button><button className="button button-primary" onClick={() => onFeedback(selected.id, 'CONFIRMED')}><Check size={14} /> Confirm event</button></div>
      </> : <EmptyState title="Choose an event" text="Select a record from the queue to inspect its trigger rule and evidence." icon={<ShieldCheck size={22} />} />}</section>
    </div>
  </div>;
}

function BuildingIcon() { return <Activity size={12} />; }

function Timeline({ action }: { action: CampusAction }) {
  return <div className="action-timeline">{action.transitions.map((transition, index) => <div className="timeline-row" key={transition.id}><span className={`timeline-marker ${index === action.transitions.length - 1 ? 'current' : ''}`}><span /></span><div className="timeline-content"><div><strong>{transition.toState.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())}</strong><span>{formatDate(transition.at)}</span></div><p>{transition.note || `Recorded by ${transition.actor || 'system'}.`}</p></div></div>)}</div>;
}

function ActionsPage({ actions, onApprove, onReject, busyActionId, outcome, setOutcome }: { actions: CampusAction[]; onApprove: (id: string) => void; onReject: (id: string) => void; busyActionId: string | null; outcome: ScenarioOutcome; setOutcome: (value: ScenarioOutcome) => void }) {
  const pending = actions.filter((action) => action.state === 'PENDING_APPROVAL');
  const completed = actions.filter((action) => action.state !== 'PENDING_APPROVAL');
  return <div className="page-stack">
    <PageHeader eyebrow="HUMAN-IN-THE-LOOP CONTROL" title="Actions & audit" description="A request, acknowledgement and verified outcome are different states. Review every transition." actions={<div className="audit-commitment"><ShieldCheck size={15} /><span>Append-only timeline</span></div>} />
    {DEMO_MODE && <section className="panel demo-outcome-panel"><div><span className="eyebrow">CONTROLLED FAILURE INJECTION</span><h3>Choose how the next approval behaves</h3><p>This changes local simulation only. It never controls a real device.</p></div><select aria-label="Demo command outcome" className="form-select outcome-select" value={outcome} onChange={(event) => setOutcome(event.target.value as ScenarioOutcome)}><option value="VERIFIED_SUCCESS">Success · verified change</option><option value="COMMAND_DROPPED">Failure · command dropped</option><option value="ACKNOWLEDGED_IGNORED">Failure · acknowledged but ignored</option></select></section>}
    <div className="action-summary-grid"><div className="summary-tile"><span className="summary-tile-icon amber"><Clock3 size={17} /></span><div><span>Awaiting approval</span><strong>{pending.length}</strong></div></div><div className="summary-tile"><span className="summary-tile-icon blue"><Activity size={17} /></span><div><span>Completed / failed</span><strong>{completed.length}</strong></div></div><div className="summary-tile"><span className="summary-tile-icon green"><CheckCircle2 size={17} /></span><div><span>Verified successes</span><strong>{actions.filter((action) => action.state === 'VERIFIED_SUCCESS').length}</strong></div></div><div className="summary-tile"><span className="summary-tile-icon slate"><History size={17} /></span><div><span>Total audit transitions</span><strong>{actions.reduce((sum, action) => sum + action.transitions.length, 0)}</strong></div></div></div>
    {pending.length > 0 && <section className="action-section"><SectionTitle title="Needs your decision" subtitle="Review the evidence and proposed response before approving." />{pending.map((action) => <article className="panel action-card pending-card" key={action.id}><div className="action-card-main"><div className="action-card-icon"><ShieldCheck size={20} /></div><div className="action-card-copy"><div className="action-card-meta"><span className="tiny-label">{action.id}</span><ActionStatusTag value={action.state} /><ProvenanceTag value={action.provenance} /></div><h3>{action.proposedAction}</h3><p>{action.eventTitle} · {action.buildingName}{action.roomName ? ` / ${action.roomName}` : ''}</p><div className="verification-spec"><span><b>Baseline</b>{action.baselineValue === null || action.baselineValue === undefined ? 'Unavailable' : `${formatNumber(action.baselineValue)}${action.eventId.includes('1042') ? ' W' : ''}`}</span><span><b>Required change</b>{action.requiredDropPercent === null || action.requiredDropPercent === undefined ? 'Unavailable' : `≥ ${action.requiredDropPercent}%`}</span><span><b>Verify window</b>{action.verificationWindowSeconds === null || action.verificationWindowSeconds === undefined ? 'Unavailable' : `${action.verificationWindowSeconds}s`}</span></div></div></div><div className="action-card-actions"><button className="button button-secondary" disabled={busyActionId === action.id} onClick={() => onReject(action.id)}><X size={14} /> Reject</button><button className="button button-primary" disabled={busyActionId === action.id} onClick={() => onApprove(action.id)}>{busyActionId === action.id ? <LoaderCircle className="spin" size={14} /> : <Check size={14} />} Approve & run</button></div></article>)}</section>}
    <section className="action-section"><SectionTitle title="Action history" subtitle="Outcomes below are taken from action records; only VERIFIED_SUCCESS may update the ledger." />{completed.length ? <div className="action-history-list">{completed.map((action) => <article className="panel action-history-card" key={action.id}><div className="action-history-head"><div><span className="tiny-label">{action.id} · {action.eventId}</span><h3>{action.proposedAction}</h3><p>{action.buildingName}{action.roomName ? ` · ${action.roomName}` : ''}</p></div><div className="action-result-badges"><ActionStatusTag value={action.state} /><ProvenanceTag value={action.provenance} /></div></div><div className="action-result-grid"><div><span>Baseline</span><strong>{action.baselineValue === null || action.baselineValue === undefined ? 'Unavailable' : formatNumber(action.baselineValue)}</strong></div><div><span>Observed after action</span><strong>{action.observedValue === null || action.observedValue === undefined ? 'Unavailable' : formatNumber(action.observedValue)}</strong></div><div><span>Observed reduction</span><strong>{action.observedDropPercent === null || action.observedDropPercent === undefined ? 'Unavailable' : `${formatNumber(action.observedDropPercent)}%`}</strong></div><div><span>Verified impact</span><strong className={action.state === 'VERIFIED_SUCCESS' ? 'success-text' : 'muted-text'}>{action.state === 'VERIFIED_SUCCESS' ? 'Eligible for ledger' : 'Not credited'}</strong></div></div><div className="timeline-expander"><div className="timeline-expander-title"><History size={15} /><strong>State transition audit</strong><span>{action.transitions.length} entries</span></div><Timeline action={action} /></div>{action.state !== 'VERIFIED_SUCCESS' && <div className="not-credited-note"><LockKeyhole size={13} /> This outcome did not meet verified-success criteria; no savings should be credited.</div>}</article>)}</div> : <EmptyState title="No action history yet" text="Approved, rejected and verified actions will appear here as records arrive." icon={<History size={22} />} />}</section>
  </div>;
}

function CopilotPage({ onAsk, result, loading, events, onOpenEvent }: { onAsk: (question: string) => void; result: CopilotResponse | null; loading: boolean; events: CampusEvent[]; onOpenEvent: (id: string) => void }) {
  const [question, setQuestion] = useState('Why did the Learning Commons alert trigger, and what evidence is still uncertain?');
  const prompts = ['Why did this alert happen?', 'Which open issue should we prioritize?', 'What evidence is missing?', 'What is verified versus simulated?'];
  return <div className="page-stack copilot-page">
    <PageHeader eyebrow="GROUNDED ASSISTANCE" title="Sustainability copilot" description="Ask operational questions. Numeric facts come from persisted data and deterministic calculations; AI only explains them." actions={<div className="copilot-mode-indicator"><span className="copilot-spark"><Sparkles size={16} /></span><span><strong>Grounded response</strong><small>No video frames sent to the model</small></span></div>} />
    <div className="copilot-layout"><section className="panel copilot-chat-panel"><div className="chat-header"><div className="chat-avatar"><Sparkles size={20} /></div><div><strong>CampusTwin Copilot</strong><span><span className="small-live-dot" /> Context-aware · provenance-aware</span></div><span className="chat-header-tag">FACTS → EXPLANATION</span></div>
      <div className="chat-body">{!result && !loading ? <div className="chat-welcome"><div className="chat-welcome-mark"><Sparkles size={24} /></div><h2>Make the next decision clearer.</h2><p>Ask about an alert, compare priorities or separate verified outcomes from projections. Answers are grounded in available records.</p><div className="prompt-grid">{prompts.map((prompt) => <button key={prompt} className="prompt-chip" onClick={() => setQuestion(prompt)}>{prompt}<ArrowUpRight size={13} /></button>)}</div></div> : <>
        {loading && <div className="assistant-message"><span className="assistant-message-avatar"><Sparkles size={14} /></span><div className="assistant-bubble"><span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" /><small>Checking the structured facts…</small></div></div>}
        {result && <div className="assistant-message"><span className="assistant-message-avatar"><Sparkles size={14} /></span><div className="assistant-answer"><div className="assistant-answer-top"><strong>Response</strong><StatusPill value={result.mode} /><span>{formatDate(result.createdAt)}</span></div><p>{result.answer}</p>{result.groundedIn.length > 0 && <div className="grounding-block"><span>GROUNDED IN</span><div>{result.groundedIn.map((ref) => <span key={ref} className="grounding-tag">{ref}</span>)}</div></div>}{result.suggestions?.length ? <div className="assistant-suggestions"><strong>Suggested next steps</strong>{result.suggestions.map((suggestion, i) => <div key={i}><CheckCircle2 size={14} />{suggestion}</div>)}</div> : null}{result.limitations?.length ? <div className="assistant-limits"><Info size={14} /><span>{result.limitations.join(' · ')}</span></div> : null}</div></div>}
      </>}</div>
      <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); const cleaned = question.trim(); if (cleaned) onAsk(cleaned); }}><textarea aria-label="Ask the sustainability copilot" value={question} onChange={(event) => setQuestion(event.target.value)} rows={2} placeholder="Ask about events, impact, or uncertainty…" /><div className="composer-footer"><span><LockKeyhole size={12} /> No camera frames or secrets are sent</span><button type="submit" className="button button-primary" disabled={!question.trim() || loading}>{loading ? <LoaderCircle className="spin" size={15} /> : <Send size={15} />} Ask copilot</button></div></form>
    </section>
    <aside className="copilot-side-column"><section className="panel context-panel"><div className="panel-heading"><div><h2>Available context</h2><p>Records the copilot can reference.</p></div><span className="context-icon"><Activity size={16} /></span></div><div className="context-count-list"><div><span><Siren size={15} /> Events</span><strong>{events.length}</strong></div><div><span><ShieldCheck size={15} /> Structured evidence</span><strong>{events.reduce((sum, event) => sum + event.evidence.length, 0)}</strong></div><div><span><History size={15} /> Verified outcomes</span><strong>Uses ledger</strong></div></div><p className="context-disclaimer">The assistant cannot invent missing metrics, confidence scores or citations. Unknown data stays unknown.</p></section><section className="panel recent-context-panel"><div className="panel-heading"><div><h2>Reference an event</h2><p>Open a record for evidence-level details.</p></div></div>{events.slice(0, 4).map((event) => <button className="reference-event" key={event.id} onClick={() => onOpenEvent(event.id)}><span className={`event-severity-dot sev-${event.severity.toLowerCase()}`} /><span><strong>{event.title}</strong><small>{event.id} · {event.buildingName}</small></span><ChevronRight size={14} /></button>)}</section></aside></div>
  </div>;
}

function WhatIfPage({ buildings, result, running, onRun }: { buildings: DashboardOverview['buildings']; result: WhatIfResponse | null; running: boolean; onRun: (request: WhatIfRequest) => void }) {
  const [buildingId, setBuildingId] = useState(buildings[0]?.id || '');
  const [intervention, setIntervention] = useState<WhatIfRequest['intervention']>('REDUCE_POWER');
  const [durationHours, setDurationHours] = useState(2);
  const [reductionPercent, setReductionPercent] = useState(20);
  useEffect(() => { if (!buildingId && buildings[0]) setBuildingId(buildings[0].id); }, [buildings, buildingId]);
  const handleSubmit = (event: FormEvent) => { event.preventDefault(); onRun({ buildingId, intervention, durationHours, reductionPercent }); };
  return <div className="page-stack">
    <PageHeader eyebrow="SCENARIO COMPARISON" title="What-if lab" description="Estimate the direction and scale of an intervention using the same baseline and explicit assumptions." actions={<StatusPill value="PROJECTED ≠ VERIFIED" />} />
    <div className="whatif-layout"><section className="panel whatif-controls-panel"><div className="panel-heading"><div><h2>Configure intervention</h2><p>Values are sent to deterministic backend calculations.</p></div><span className="whatif-control-icon"><FlaskConicalFallback /></span></div>
      <form onSubmit={handleSubmit} className="whatif-form"><label className="field-label" htmlFor="whatif-building">Building</label><select id="whatif-building" className="form-select" value={buildingId} onChange={(event) => setBuildingId(event.target.value)} required><option value="" disabled>Select a building</option>{buildings.map((building) => <option key={building.id} value={building.id}>{building.name}</option>)}</select>
        <label className="field-label" htmlFor="whatif-intervention">Intervention</label><select id="whatif-intervention" className="form-select" value={intervention} onChange={(event) => setIntervention(event.target.value as WhatIfRequest['intervention'])}><option value="REDUCE_POWER">Reduce power draw</option><option value="WATER_REPAIR">Repair water-flow anomaly</option><option value="SCHEDULE_OPTIMIZATION">Optimize room schedule</option></select>
        <div className="range-field"><div><label className="field-label" htmlFor="duration-hours">Duration</label><strong>{durationHours} hours</strong></div><input id="duration-hours" type="range" min="1" max="12" step="1" value={durationHours} onChange={(event) => setDurationHours(Number(event.target.value))} /><div className="range-ticks"><span>1 hour</span><span>12 hours</span></div></div>
        <div className="range-field"><div><label className="field-label" htmlFor="reduction-pct">Target reduction</label><strong>{reductionPercent}%</strong></div><input id="reduction-pct" type="range" min="5" max="60" step="5" value={reductionPercent} onChange={(event) => setReductionPercent(Number(event.target.value))} /><div className="range-ticks"><span>5%</span><span>60%</span></div></div>
        <div className="assumption-callout"><Info size={15} /><span>This is a projection. Missing baselines, tariffs or emission factors must be returned as unavailable, not replaced with defaults.</span></div><button type="submit" className="button button-primary full-width" disabled={running || !buildingId}>{running ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />} Run comparison</button>
      </form></section>
      <section className="whatif-results-column">{result ? <><div className="panel whatif-result-panel"><div className="result-top"><div><span className="eyebrow">SCENARIO RESULT</span><h2>{result.status === 'UNAVAILABLE' ? 'Not enough evidence' : 'Projected change'}</h2></div><ProvenanceTag value={result.provenance} /></div>{result.status === 'UNAVAILABLE' ? <EmptyState title="Projection unavailable" text="The backend reported that a required input is missing. Add the required data in settings or connect the relevant sensor." icon={<AlertCircle size={22} />} /> : <><div className="result-hero-number">{result.delta === null ? '—' : formatNumber(result.delta)}<small> {result.unit}</small><span>projected difference</span></div><div className="result-comparison"><div><span>Baseline</span><strong>{result.baseline === null ? 'Unavailable' : `${formatNumber(result.baseline)} ${result.unit}`}</strong></div><ArrowDownRight size={17} /><div><span>After intervention</span><strong>{result.projected === null ? 'Unavailable' : `${formatNumber(result.projected)} ${result.unit}`}</strong></div></div><div className="result-secondary-grid"><div><span>Estimated cost change</span><strong>{result.costDelta === null ? 'Unavailable' : `₹${formatNumber(result.costDelta)}`}</strong></div><div><span>Estimated CO₂e change</span><strong>{result.co2DeltaKg === null ? 'Unavailable' : `${formatNumber(result.co2DeltaKg)} kg`}</strong></div></div></>}
        <div className="formula-block"><span>CALCULATION</span><p>{result.formula}</p><span>ASSUMPTIONS</span><ul>{result.assumptions.map((assumption, i) => <li key={i}>{assumption}</li>)}</ul></div><div className="projected-warning"><ShieldAlert size={15} /><span>Projected values are not verified savings. Only a successful independent verification can credit the impact ledger.</span></div></div></> : <div className="panel whatif-empty-panel"><div className="whatif-illustration"><div className="illustration-ring ring-one" /><div className="illustration-ring ring-two" /><div className="illustration-center"><FlaskConicalFallback /></div><span className="illustration-node node-a"><Zap size={15} /></span><span className="illustration-node node-b"><Droplets size={15} /></span><span className="illustration-node node-c"><TrendingDown size={15} /></span></div><h2>Compare before you commit.</h2><p>Configure an intervention and run it against the selected baseline. The result will show the assumptions and formula—not just a headline number.</p><div className="whatif-empty-foot"><span><CheckCircle2 size={14} /> Same baseline</span><span><CheckCircle2 size={14} /> Explicit assumptions</span><span><CheckCircle2 size={14} /> Projection labelled</span></div></div>}</section></div>
  </div>;
}

function ReportsPage({ overview, events, actions, onExport }: { overview: DashboardOverview | null; events: CampusEvent[]; actions: CampusAction[]; onExport: (format: 'json' | 'csv') => void }) {
  const ledger = overview?.ledger ?? [];
  const verified = actions.filter((action) => action.state === 'VERIFIED_SUCCESS').length;
  return <div className="page-stack">
    <PageHeader eyebrow="ACCOUNTABLE IMPACT" title="Reports & impact" description="Every metric needs a source, period, formula and provenance. Exportable records retain those limits." actions={<><button className="button button-secondary button-small" onClick={() => onExport('csv')}><Download size={14} /> Export CSV</button><button className="button button-primary button-small" onClick={() => onExport('json')}><FileJson size={14} /> Evidence packet JSON</button></>} />
    <div className="report-hero panel"><div className="report-hero-copy"><span className="eyebrow">IMPACT LEDGER</span><h2>{ledger.length === 0 ? 'No verified impact credited yet' : `${ledger.length} ledger ${ledger.length === 1 ? 'entry' : 'entries'}`}</h2><p>The ledger changes only when an action reaches <code>VERIFIED_SUCCESS</code>. Projections and acknowledgements remain separate.</p><div className="report-hero-qualifiers"><span><LockKeyhole size={14} /> Append-only intent</span><span><CheckCircle2 size={14} /> Evidence-linked</span><span><Info size={14} /> Assumptions retained</span></div></div><div className="report-hero-graphic"><div className="ledger-orbit orbit-a" /><div className="ledger-orbit orbit-b" /><div className="ledger-center"><Leaf size={28} /><strong>{ledger.length}</strong><small>ledger entries</small></div></div></div>
    <div className="report-stats-grid"><div className="report-stat panel"><div className="report-stat-icon"><Siren size={17} /></div><span>Events in view</span><strong>{events.length}</strong><small>Current loaded event records</small></div><div className="report-stat panel"><div className="report-stat-icon"><ShieldCheck size={17} /></div><span>Verified actions</span><strong>{verified}</strong><small>Only successful verification counts</small></div><div className="report-stat panel"><div className="report-stat-icon"><Zap size={17} /></div><span>Verified energy saving</span><strong>{overview?.kpis.verifiedSavings.value === null || !overview ? '—' : `${formatNumber(overview.kpis.verifiedSavings.value)} ${overview.kpis.verifiedSavings.unit}`}</strong><small>{overview?.kpis.verifiedSavings.provenance === 'SIMULATED' ? 'Synthetic scenario total' : 'As returned by the backend'}</small></div><div className="report-stat panel"><div className="report-stat-icon"><Activity size={17} /></div><span>Failed / not verified</span><strong>{actions.filter((action) => action.state !== 'VERIFIED_SUCCESS' && action.state !== 'PENDING_APPROVAL').length}</strong><small>No impact credited</small></div></div>
    <section className="panel ledger-table-panel"><div className="panel-heading"><div><h2>Impact ledger entries</h2><p>Each record carries a calculation, source provenance and assumptions.</p></div><span className="tiny-label">{ledger.length} ENTRIES</span></div>{ledger.length ? <div className="table-overflow"><table className="data-table"><thead><tr><th>Entry</th><th>Resource</th><th>Quantity</th><th>Impact status</th><th>Formula / basis</th><th>Created</th></tr></thead><tbody>{ledger.map((entry: LedgerEntry) => <tr key={entry.id}><td><strong>{entry.id}</strong><small>{entry.actionId}</small></td><td>{entry.resourceType}</td><td><strong>{formatNumber(entry.quantity, 4)} {entry.unit}</strong></td><td><StatusPill value={entry.status} /></td><td><span className="table-formula">{entry.formula}</span><small>{entry.assumptions.join(' · ')}</small></td><td>{formatDate(entry.createdAt)}</td></tr>)}</tbody></table></div> : <EmptyState title="The ledger is empty" text="An action acknowledgement is not enough. Successful independent verification will create a ledger record; failed or inconclusive actions must leave this table unchanged." icon={<LockKeyhole size={22} />} />}</section>
    <section className="panel report-coverage-panel"><div className="panel-heading"><div><h2>Data quality & report coverage</h2><p>Distinguish unavailable inputs from zero and derived estimates from measured values.</p></div></div><div className="coverage-grid"><div><span>Event evidence attached</span><strong>{events.filter((event) => event.evidence.length > 0).length} / {events.length || 0}</strong><div className="coverage-bar"><span style={{ width: `${events.length ? (events.filter((event) => event.evidence.length > 0).length / events.length) * 100 : 0}%` }} /></div></div><div><span>Real-provenance events</span><strong>{events.filter((event) => event.provenance === 'REAL').length}</strong><p>{events.some((event) => event.provenance === 'REAL') ? 'Real-source records are present in this view.' : 'No events are currently labelled REAL.'}</p></div><div><span>Impact factors configured</span><strong>{overview?.kpis.cost.value !== null && overview?.kpis.cost.value !== undefined && overview?.kpis.co2.value !== null ? 'Available' : 'Incomplete'}</strong><p>Tariff and emission factor are shown as unavailable when missing.</p></div></div></section>
  </div>;
}

function SettingsPage({ settings, setSettings, onSave, saving, loaded, loadError }: { settings: CampusSettings; setSettings: (next: CampusSettings) => void; onSave: () => void; saving: boolean; loaded: boolean; loadError: string | null }) {
  const update = (key: keyof CampusSettings, value: number | null) => setSettings({ ...settings, [key]: value });
  return <div className="page-stack">
    <PageHeader eyebrow="CONFIGURATION & ASSUMPTIONS" title="Settings" description="Rules, factors and virtual time are visible configuration—not magic constants hidden in code." actions={<button className="button button-primary" onClick={onSave} disabled={saving || !loaded} title={!loaded ? 'Load the current server configuration before saving.' : undefined}>{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save configuration</button>} />
    {!loaded && <div className="connection-error"><div className="connection-error-icon"><AlertCircle size={18} /></div><div><strong>Current settings are not loaded</strong><p>{loadError || 'Waiting for the configuration endpoint. Saving is disabled to avoid overwriting unknown server settings.'}</p></div></div>}
    <div className="settings-layout"><section className="panel settings-section"><div className="settings-section-heading"><span className="settings-section-icon"><Gauge size={18} /></span><div><h2>Detection rules</h2><p>Threshold plus persistence, with unknowns kept unknown.</p></div></div><div className="settings-form-grid"><label className="settings-field"><span>Energy waste threshold</span><div className="input-with-unit"><input type="number" min="0" value={settings.energyWasteWatts} onChange={(event) => update('energyWasteWatts', Number(event.target.value))} /><span>W</span></div><small>Power threshold for suspected empty-room waste.</small></label><label className="settings-field"><span>Low-use water flow threshold</span><div className="input-with-unit"><input type="number" min="0" step="0.1" value={settings.waterNightFlowLitresPerMinute} onChange={(event) => update('waterNightFlowLitresPerMinute', Number(event.target.value))} /><span>L/min</span></div><small>Applied only in the configured low-use window.</small></label><label className="settings-field"><span>Persistence window</span><div className="input-with-unit"><input type="number" min="1" value={settings.persistenceMinutes} onChange={(event) => update('persistenceMinutes', Number(event.target.value))} /><span>min</span></div><small>Condition must persist before a rule creates an alert.</small></label><label className="settings-field"><span>Verification threshold</span><div className="input-with-unit"><input type="number" min="1" max="100" value={settings.verificationDropPercent} onChange={(event) => update('verificationDropPercent', Number(event.target.value))} /><span>% drop</span></div><small>Required observed change compared with the stored baseline.</small></label><label className="settings-field"><span>Verification window</span><div className="input-with-unit"><input type="number" min="1" value={settings.verificationWindowSeconds} onChange={(event) => update('verificationWindowSeconds', Number(event.target.value))} /><span>sec</span></div><small>Virtual-time window for post-command observations.</small></label></div></section>
      <section className="panel settings-section"><div className="settings-section-heading"><span className="settings-section-icon green"><Leaf size={18} /></span><div><h2>Impact assumptions</h2><p>Leave unknown factors empty; no hidden replacement values.</p></div></div><div className="settings-form-grid"><label className="settings-field"><span>Electricity tariff</span><div className="input-with-unit"><span className="prefix">₹</span><input type="number" min="0" step="0.01" value={settings.tariffPerKwh ?? ''} placeholder="Not configured" onChange={(event) => update('tariffPerKwh', event.target.value === '' ? null : Number(event.target.value))} /><span>/ kWh</span></div><small>Used for estimates only with compatible energy units.</small></label><label className="settings-field"><span>CO₂ emission factor</span><div className="input-with-unit"><input type="number" min="0" step="0.0001" value={settings.co2KgPerKwh ?? ''} placeholder="Not configured" onChange={(event) => update('co2KgPerKwh', event.target.value === '' ? null : Number(event.target.value))} /><span>kg / kWh</span></div><small>Use an attributable source and record its version in the backend.</small></label><label className="settings-field"><span>Scenario clock multiplier</span><div className="input-with-unit"><input type="number" min="1" max="1000" value={settings.scenarioClockMultiplier} onChange={(event) => update('scenarioClockMultiplier', Number(event.target.value))} /><span>×</span></div><small>Only affects scenario virtual time—not wall-clock camera freshness.</small></label></div></section>
      <section className="settings-privacy-card"><div className="privacy-card-icon"><LockKeyhole size={19} /></div><div><h3>Privacy & trust boundaries</h3><p>Camera frames must remain in memory and must never be stored, logged or sent to the copilot. No face recognition or identity matching. Missing/stale frames mean <code>UNKNOWN</code>, not empty.</p></div><StatusPill value="POLICY" /></section>
      <section className="panel settings-system-panel"><div className="panel-heading"><div><h2>System configuration</h2><p>Source status is based on the latest actual check.</p></div></div><div className="system-config-grid"><div><span>Configuration last saved</span><strong>{settings.updatedAt ? formatDate(settings.updatedAt) : 'Not recorded in this view'}</strong></div><div><span>Backend configuration</span><strong>{DEMO_MODE ? 'Local preview values' : 'Backend-backed when connected'}</strong></div><div><span>Secret storage</span><strong>Server-side environment only</strong></div><div><span>Missing factors</span><strong>Reported unavailable</strong></div></div></section></div>
  </div>;
}

function HelpModal({ onClose, demoMode, onNavigate }: { onClose: () => void; demoMode: boolean; onNavigate: (key: NavKey) => void }) {
  const steps: { key: NavKey; title: string; detail: string; number: string }[] = [
    { key: 'overview', number: '01', title: 'Start with the signal', detail: 'Use the command center to choose a real or explicitly synthetic event.' },
    { key: 'events', number: '02', title: 'Inspect the evidence', detail: 'Check thresholds, timestamps, data age, provenance and limitations.' },
    { key: 'actions', number: '03', title: 'Approve, then verify', detail: 'Acknowledgement is not success. Only independent verification can credit impact.' },
    { key: 'reports', number: '04', title: 'Trace every claim', detail: 'Export the ledger and assumptions; failed actions must leave savings unchanged.' },
  ];
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title"><div className="help-modal-header"><div className="brand-mark"><Leaf size={20} /></div><button className="icon-button" onClick={onClose} aria-label="Close guide"><X size={17} /></button></div><span className="eyebrow">QUICK START</span><h2 id="help-title">A trustworthy demo in four steps.</h2><p className="help-modal-description">The strongest story is not “AI found something.” It is “here is the evidence, here is the human decision, and here is the independently verified result.”</p>{demoMode && <div className="help-demo-alert"><Info size={15} /><span>You are in local synthetic demo mode. Do not present these records as live campus data.</span></div>}<div className="help-steps">{steps.map((step) => <button key={step.key} className="help-step" onClick={() => { onNavigate(step.key); onClose(); }}><span>{step.number}</span><div><strong>{step.title}</strong><small>{step.detail}</small></div><ArrowUpRight size={15} /></button>)}</div><button className="button button-primary full-width" onClick={() => { onNavigate('overview'); onClose(); }}>Open command center <ArrowRight size={15} /></button></section></div>;
}

const defaultSettings: CampusSettings = { tariffPerKwh: null, co2KgPerKwh: null, energyWasteWatts: 850, waterNightFlowLitresPerMinute: 1.5, persistenceMinutes: 10, verificationDropPercent: 25, verificationWindowSeconds: 120, scenarioClockMultiplier: 30 };

export default function App() {
  const [active, setActive] = useState<NavKey>('overview');
  const [overview, setOverview] = useState<DashboardOverview | null>(() => DEMO_MODE ? createDemoOverview() : null);
  const [events, setEvents] = useState<CampusEvent[]>(() => DEMO_MODE ? [...demoEvents] : []);
  const [actions, setActions] = useState<CampusAction[]>(() => DEMO_MODE ? [...demoActions] : []);
  const [demoLedger, setDemoLedger] = useState<LedgerEntry[]>([]);
  const [settings, setSettings] = useState<CampusSettings>(defaultSettings);
  const [settingsLoaded, setSettingsLoaded] = useState(DEMO_MODE);
  const [settingsLoadError, setSettingsLoadError] = useState<string | null>(null);
  const [connection, setConnection] = useState<'connected' | 'offline' | 'loading'>('loading');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [drawerEventId, setDrawerEventId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [eventStatus, setEventStatus] = useState('ALL');
  const [eventSeverity, setEventSeverity] = useState('ALL');
  const [eventResource, setEventResource] = useState('ALL');
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [showHelp, setShowHelp] = useState(false);
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [nextOutcome, setNextOutcome] = useState<ScenarioOutcome>('VERIFIED_SUCCESS');
  const [copilotResult, setCopilotResult] = useState<CopilotResponse | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [whatIfResult, setWhatIfResult] = useState<WhatIfResponse | null>(null);
  const [whatIfRunning, setWhatIfRunning] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);

  const addToast = useCallback((title: string, message: string | undefined, kind: ToastMessage['kind'] = 'info') => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    setToasts((current) => [...current.slice(-3), { id, title, message, kind }]);
    window.setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), 5200);
  }, []);

  const syncDemoOverview = useCallback((nextEvents: CampusEvent[], nextActions: CampusAction[], nextLedger: LedgerEntry[]) => {
    setEvents(nextEvents);
    setActions(nextActions);
    setDemoLedger(nextLedger);
    setOverview(createDemoOverview(nextEvents, nextActions, nextLedger));
  }, []);

  const refresh = useCallback(async (quiet = false) => {
    if (DEMO_MODE) {
      setConnection('connected');
      setLoadError(null);
      if (!quiet) addToast('Local preview refreshed', 'Current records remain synthetic and local.', 'success');
      return;
    }
    if (!quiet) setRefreshing(true);
    setConnection((current) => current === 'connected' ? current : 'loading');
    const [overviewResult, eventsResult, actionsResult] = await Promise.allSettled([api.getOverview(), api.getEvents(), api.getActions()]);
    const overviewValue = overviewResult.status === 'fulfilled' ? overviewResult.value : null;
    if (overviewValue) {
      setOverview({ ...overviewValue, health: { ...overviewValue.health, connection: 'CONNECTED' } });
      setConnection('connected');
      setLoadError(null);
    } else {
      setConnection('offline');
      const error = overviewResult.status === 'rejected' ? overviewResult.reason : null;
      const message = error instanceof Error ? error.message : 'The overview endpoint did not return data.';
      setLoadError(message);
    }
    if (eventsResult.status === 'fulfilled') setEvents(eventsResult.value);
    else if (overviewValue?.recentEvents) setEvents(overviewValue.recentEvents);
    if (actionsResult.status === 'fulfilled') setActions(actionsResult.value);
    else if (overviewValue?.priorityActions) setActions(overviewValue.priorityActions);
    if (!quiet && overviewValue) addToast('Data refreshed', 'Records were updated from the backend.', 'success');
    if (!quiet) setRefreshing(false);
  }, [addToast]);

  useEffect(() => {
    void refresh(true);
    if (DEMO_MODE) return;
    const handle = window.setInterval(() => void refresh(true), POLL_INTERVAL);
    return () => window.clearInterval(handle);
  }, [refresh]);

  useEffect(() => {
    if (active === 'settings' && !DEMO_MODE) {
      setSettingsLoaded(false);
      setSettingsLoadError(null);
      api.getSettings().then((value) => { setSettings(value); setSettingsLoaded(true); }).catch((error: unknown) => {
        setSettingsLoadError(getErrorMessage(error));
      });
    }
  }, [active]);

  const selectedEvent = events.find((event) => event.id === drawerEventId) ?? null;
  const openEvent = useCallback((id: string) => {
    setSelectedEventId(id);
    setDrawerEventId(id);
    setActive('events');
  }, []);

  const submitFeedback = useCallback(async (id: string, feedback: 'FALSE_ALARM' | 'CONFIRMED') => {
    if (DEMO_MODE) {
      const nextEvents = events.map((event) => event.id === id ? { ...event, status: feedback === 'FALSE_ALARM' ? 'FALSE_ALARM' as const : 'ACKNOWLEDGED' as const, updatedAt: new Date().toISOString() } : event);
      syncDemoOverview(nextEvents, actions, demoLedger);
      addToast(feedback === 'FALSE_ALARM' ? 'Event marked as a false alarm' : 'Event confirmed', 'Updated the local synthetic record.', feedback === 'FALSE_ALARM' ? 'info' : 'success');
      return;
    }
    try {
      await api.sendFeedback(id, feedback);
      addToast('Feedback saved', 'The backend accepted the event feedback.', 'success');
      await refresh(true);
    } catch (error) {
      addToast('Feedback was not saved', getErrorMessage(error), 'error');
    }
  }, [actions, addToast, demoLedger, events, refresh, syncDemoOverview]);

  const runScenario = useCallback(async (scenario: string) => {
    if (DEMO_MODE) {
      if (scenario === 'normal_operation') {
        addToast('Normal operation scenario', 'No incident was created; this is an explicit local synthetic scenario.', 'info');
        return;
      }
      if (scenario === 'command_dropped' || scenario === 'acknowledged_ignored' || scenario === 'verified_success') {
        const pending = actions.find((action) => action.state === 'PENDING_APPROVAL');
        if (pending) {
          setNextOutcome(scenario === 'command_dropped' ? 'COMMAND_DROPPED' : scenario === 'acknowledged_ignored' ? 'ACKNOWLEDGED_IGNORED' : 'VERIFIED_SUCCESS');
          setActive('actions');
          addToast('Failure injection selected', 'Review the selected outcome, then approve an action to run the controlled test.', 'info');
        } else {
          addToast('No pending action', 'Run an event scenario first, then select the action outcome.', 'info');
        }
        return;
      }
      const template = scenario === 'night_water_flow' ? demoEvents[1] : scenario === 'sensor_unavailable' ? demoEvents[2] : scenario === 'bin_overflow' ? { ...demoEvents[1], eventType: 'likely_bin_overflow', title: 'Bin nearing overflow capacity', summary: 'A simulated capacity reading passed the configured warning threshold.', triggerRule: 'likely_bin_overflow', threshold: 'Capacity > 85% for the configured persistence period', explanation: 'The capacity value is generated by the local demo scenario; no physical bin detector is connected.', limitations: ['This is a synthetic/manual event.', 'No local vision detector is running.'] } : demoEvents[0];
      const id = `EVT-LOCAL-${Date.now().toString().slice(-6)}`;
      const newEvent: CampusEvent = { ...template, id, firstSeenAt: new Date().toISOString(), updatedAt: new Date().toISOString(), provenance: 'SIMULATED', evidence: template.evidence.map((item, index) => ({ ...item, id: `${id}-E${index + 1}`, reading: item.reading ? { ...item.reading, id: `${id}-R${index + 1}`, observedAt: new Date().toISOString(), provenance: 'SIMULATED' } : undefined })) };
      const nextEvents = [newEvent, ...events];
      const nextActions = scenario === 'empty_room_high_power' ? [{ ...demoActions[0], id: `ACT-LOCAL-${Date.now().toString().slice(-6)}`, eventId: id, eventTitle: newEvent.title, buildingName: newEvent.buildingName, roomName: newEvent.roomName, state: 'PENDING_APPROVAL' as const, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), transitions: [{ id: `TR-${Date.now()}`, fromState: null, toState: 'PENDING_APPROVAL' as const, at: new Date().toISOString(), actor: 'LOCAL_SCENARIO', note: `Created by explicit scenario ${scenario}.` }] }, ...actions] : actions;
      syncDemoOverview(nextEvents, nextActions, demoLedger);
      addToast('Scenario created', `${newEvent.title} · synthetic scenario only.`, 'success');
      setSelectedEventId(id);
      setActive(scenario === 'empty_room_high_power' ? 'actions' : 'events');
      return;
    }
    try {
      const result = await api.runScenario({ scenario, outcome: scenario === 'command_dropped' ? 'COMMAND_DROPPED' : scenario === 'acknowledged_ignored' ? 'ACKNOWLEDGED_IGNORED' : scenario === 'verified_success' ? 'VERIFIED_SUCCESS' : undefined });
      addToast('Scenario request accepted', `${result.message} · ${result.provenance} · run ${result.runId}`, 'success');
      await refresh(true);
      if (result.createdEventIds[0]) openEvent(result.createdEventIds[0]);
    } catch (error) {
      addToast('Scenario did not run', getErrorMessage(error), 'error');
    }
  }, [actions, addToast, demoLedger, events, openEvent, refresh, syncDemoOverview]);

  const approveAction = useCallback(async (id: string) => {
    const action = actions.find((item) => item.id === id);
    if (!action || action.state !== 'PENDING_APPROVAL') {
      addToast('Action is not awaiting approval', 'Duplicate approvals are ignored. Refresh the record before trying again.', 'info');
      return;
    }
    setBusyActionId(id);
    if (DEMO_MODE) {
      const now = new Date();
      const at = (offsetSeconds: number) => new Date(now.getTime() + offsetSeconds * 1000).toISOString();
      const transitions: ActionTransition[] = [
        ...action.transitions,
        { id: `${id}-TR-SENT-${now.getTime()}`, fromState: 'PENDING_APPROVAL', toState: 'COMMAND_SENT', at: at(0), actor: 'DEMO_OPERATOR', note: 'Human approval recorded in local simulation.' },
      ];
      let finalState: ActionState;
      let observedValue: number | null = null;
      let observedDropPercent: number | null = null;
      let outcomeNote = '';
      if (nextOutcome === 'COMMAND_DROPPED') {
        finalState = 'COMMAND_FAILED'; outcomeNote = 'The simulated command was deliberately dropped before acknowledgement.';
        transitions.push({ id: `${id}-TR-FAIL-${now.getTime()}`, fromState: 'COMMAND_SENT', toState: 'COMMAND_FAILED', at: at(1), actor: 'SIMULATOR', note: outcomeNote });
      } else {
        transitions.push({ id: `${id}-TR-ACK-${now.getTime()}`, fromState: 'COMMAND_SENT', toState: 'ACKED', at: at(1), actor: 'SIMULATOR', note: 'The simulator acknowledged receipt; acknowledgement is not success.' });
        transitions.push({ id: `${id}-TR-VERIFY-${now.getTime()}`, fromState: 'ACKED', toState: 'VERIFYING', at: at(2), actor: 'VERIFIER', note: `Readings compared against baseline over ${action.verificationWindowSeconds ?? 120} virtual seconds.` });
        if (nextOutcome === 'VERIFIED_SUCCESS') {
          finalState = 'VERIFIED_SUCCESS';
          observedValue = typeof action.baselineValue === 'number' ? Math.round(action.baselineValue * 0.68 * 10) / 10 : null;
          observedDropPercent = observedValue !== null && typeof action.baselineValue === 'number' && action.baselineValue > 0 ? ((action.baselineValue - observedValue) / action.baselineValue) * 100 : null;
          outcomeNote = `Required threshold of ${action.requiredDropPercent ?? 25}% met by the synthetic post-action reading.`;
        } else {
          finalState = 'VERIFICATION_FAILED';
          observedValue = action.baselineValue ?? null;
          observedDropPercent = 0;
          outcomeNote = 'Acknowledged, but the synthetic post-action reading did not meet the required change.';
        }
        transitions.push({ id: `${id}-TR-FINAL-${now.getTime()}`, fromState: 'VERIFYING', toState: finalState, at: at(3), actor: 'VERIFIER', note: outcomeNote });
      }
      const updated: CampusAction = { ...action, state: finalState, updatedAt: at(3), actor: 'DEMO_OPERATOR', outcome: outcomeNote, observedValue, observedDropPercent, transitions };
      const nextActions = actions.map((item) => item.id === id ? updated : item);
      let nextLedger = demoLedger;
      if (finalState === 'VERIFIED_SUCCESS') {
        const baseline = action.baselineValue;
        const after = observedValue;
        const wattsAvoided = baseline !== null && baseline !== undefined && after !== null ? Math.max(0, baseline - after) : null;
        const kwh = wattsAvoided === null ? null : wattsAvoided / 1000 * ((action.verificationWindowSeconds ?? 120) / 3600);
        if (kwh !== null && Number.isFinite(kwh)) {
          nextLedger = [...demoLedger, { id: `LEDGER-LOCAL-${now.getTime()}`, actionId: id, eventId: action.eventId, resourceType: 'ENERGY', quantity: Number(kwh.toFixed(6)), unit: 'kWh', estimatedCost: null, estimatedCo2Kg: null, formula: '(baseline watts − observed watts) / 1000 × verified duration in hours', assumptions: ['Local UI simulation only', 'Synthetic baseline and post-action readings', 'Tariff and CO₂ factor unavailable'], observationPeriod: `${action.verificationWindowSeconds ?? 120} virtual seconds`, provenance: 'SIMULATED', status: 'VERIFIED_SIMULATED', createdAt: at(3) }];
        }
      }
      syncDemoOverview(events, nextActions, nextLedger);
      addToast(finalState === 'VERIFIED_SUCCESS' ? 'Verification passed' : finalState === 'COMMAND_FAILED' ? 'Command failure recorded' : 'Verification failed', finalState === 'VERIFIED_SUCCESS' ? 'A simulated ledger entry was added only after the verification condition passed.' : 'No savings were added to the impact ledger.', finalState === 'VERIFIED_SUCCESS' ? 'success' : 'error');
      setBusyActionId(null);
      return;
    }
    try {
      await api.approveAction(id);
      addToast('Approval submitted', 'The backend owns the action state machine and verification result.', 'success');
      await refresh(true);
    } catch (error) {
      addToast('Action was not approved', getErrorMessage(error), 'error');
    } finally {
      setBusyActionId(null);
    }
  }, [actions, addToast, demoLedger, events, nextOutcome, refresh, syncDemoOverview]);

  const rejectAction = useCallback(async (id: string) => {
    if (DEMO_MODE) {
      const now = new Date().toISOString();
      const nextActions = actions.map((action) => action.id !== id || action.state !== 'PENDING_APPROVAL' ? action : { ...action, state: 'REJECTED' as const, updatedAt: now, transitions: [...action.transitions, { id: `${id}-TR-REJECT-${Date.now()}`, fromState: 'PENDING_APPROVAL' as const, toState: 'REJECTED' as const, at: now, actor: 'DEMO_OPERATOR', note: 'Human operator rejected the proposed action.' }] });
      syncDemoOverview(events, nextActions, demoLedger);
      addToast('Action rejected', 'No command was sent and no savings were credited.', 'info');
      return;
    }
    try {
      await api.rejectAction(id, 'Rejected by operator from action review.');
      addToast('Action rejected', 'The backend recorded the human decision.', 'success');
      await refresh(true);
    } catch (error) { addToast('Rejection was not saved', getErrorMessage(error), 'error'); }
  }, [actions, addToast, demoLedger, events, refresh, syncDemoOverview]);

  const askCopilot = useCallback(async (question: string) => {
    setCopilotLoading(true);
    if (DEMO_MODE) {
      setCopilotResult(demoCopilot(question));
      setCopilotLoading(false);
      return;
    }
    try {
      const result = await api.askCopilot(question, selectedEventId ? { eventId: selectedEventId } : undefined);
      setCopilotResult(result);
    } catch (error) {
      addToast('Copilot could not answer', `${getErrorMessage(error)} The backend should return a TEMPLATE response when no model key or network is available.`, 'error');
    } finally { setCopilotLoading(false); }
  }, [addToast, selectedEventId]);

  const runWhatIf = useCallback(async (request: WhatIfRequest) => {
    setWhatIfRunning(true);
    if (DEMO_MODE) {
      const chosen = events.find((event) => event.buildingId === request.buildingId && event.evidence.some((item) => item.reading?.resourceType === 'ENERGY' && typeof item.reading.value === 'number'));
      const reading = chosen?.evidence.find((item) => item.reading?.resourceType === 'ENERGY' && typeof item.reading.value === 'number')?.reading;
      const baselineWatts = typeof reading?.value === 'number' ? reading.value : null;
      const projected = baselineWatts === null ? null : baselineWatts * (1 - request.reductionPercent / 100);
      const delta = baselineWatts === null ? null : baselineWatts - (projected ?? baselineWatts);
      setWhatIfResult({ baseline: baselineWatts, projected, delta, unit: 'W', costDelta: null, co2DeltaKg: null, formula: '(baseline watts × reduction percent) gives the projected power difference; duration is recorded for later energy estimates. Cost and CO₂ omitted because no factors are configured.', assumptions: ['Synthetic event reading used as baseline', `Selected duration: ${request.durationHours} hours`, `Target reduction: ${request.reductionPercent}%`, 'This is a local preview projection, not verified savings'], provenance: 'SIMULATED', status: baselineWatts === null ? 'UNAVAILABLE' : 'PROJECTED' });
      setWhatIfRunning(false);
      return;
    }
    try {
      setWhatIfResult(await api.runWhatIf(request));
    } catch (error) {
      addToast('What-if request failed', getErrorMessage(error), 'error');
    } finally { setWhatIfRunning(false); }
  }, [events, addToast]);

  const saveSettings = useCallback(async () => {
    setSettingsSaving(true);
    if (DEMO_MODE) {
      setSettings({ ...settings, updatedAt: new Date().toISOString() });
      addToast('Local settings updated', 'Values stay in this preview and are not saved to a backend database.', 'success');
      setSettingsSaving(false);
      return;
    }
    try {
      const saved = await api.saveSettings(settings);
      setSettings(saved);
      addToast('Configuration saved', 'The backend returned the updated settings.', 'success');
    } catch (error) { addToast('Settings were not saved', getErrorMessage(error), 'error'); }
    finally { setSettingsSaving(false); }
  }, [settings, addToast]);

  const exportReport = useCallback((format: 'json' | 'csv') => {
    const packet = {
      reportType: 'CampusTwin evidence packet',
      generatedAt: new Date().toISOString(),
      mode: DEMO_MODE ? 'LOCAL_UI_SIMULATION' : 'BACKEND_DATA_EXPORT',
      notes: ['Values retain their provenance labels.', 'Projections are not measured savings.', 'Only VERIFIED_SUCCESS actions are eligible for impact ledger credit.'],
      events, actions, impactLedger: overview?.ledger ?? [], settings,
    };
    const stamp = new Date().toISOString().slice(0, 10);
    if (format === 'json') downloadFile(`campustwin-evidence-${stamp}.json`, JSON.stringify(packet, null, 2), 'application/json;charset=utf-8');
    else {
      const rows: string[][] = [['record_type', 'id', 'title_or_state', 'building', 'status', 'provenance', 'updated_at']];
      events.forEach((event) => rows.push(['event', event.id, event.title, event.buildingName, event.status, event.provenance, event.updatedAt]));
      actions.forEach((action) => rows.push(['action', action.id, action.state, action.buildingName, action.state, action.provenance, action.updatedAt]));
      (overview?.ledger ?? []).forEach((entry) => rows.push(['impact_ledger', entry.id, `${entry.quantity} ${entry.unit}`, entry.resourceType, entry.status, entry.provenance, entry.createdAt]));
      downloadFile(`campustwin-evidence-${stamp}.csv`, rows.map((row) => row.map(csvCell).join(',')).join('\r\n'), 'text/csv;charset=utf-8');
    }
    addToast('Evidence export created', `${format.toUpperCase()} contains the currently loaded records and their provenance.`, 'success');
  }, [actions, events, overview, settings, addToast]);

  const resetDemo = useCallback(async () => {
    if (DEMO_MODE) {
      setSelectedEventId(null);
      setDrawerEventId(null);
      setNextOutcome('VERIFIED_SUCCESS');
      setCopilotResult(null);
      setWhatIfResult(null);
      syncDemoOverview([...demoEvents], [...demoActions], []);
      addToast('Local demo reset', 'Synthetic preview state returned to its original fixture set.', 'success');
      return;
    }
    try {
      const result = await api.resetDemo();
      addToast('Backend demo reset', result.message || 'Reset endpoint returned success.', 'success');
      await refresh(true);
    } catch (error) { addToast('Demo reset failed', getErrorMessage(error), 'error'); }
  }, [addToast, refresh, syncDemoOverview]);

  const renderContent = () => {
    if (active === 'overview') return <>
      {!DEMO_MODE && loadError && <HealthStripFallback retry={() => void refresh(false)} />}
      <OverviewPage overview={overview} events={events} actions={actions} onOpenEvent={openEvent} onRunScenario={(scenario) => void runScenario(scenario)} onGo={setActive} refreshing={refreshing} />
      <div className="view-tools-row"><span><Info size={13} /> {DEMO_MODE ? 'Demo fixture values are synthetic.' : overview ? 'Data shown from backend response; missing inputs remain unavailable.' : 'No live values are being fabricated.'}</span>{DEMO_MODE && <button className="text-link" onClick={() => void resetDemo()}>Reset demo <RefreshCw size={13} /></button>}</div>
    </>;
    if (active === 'twin') return <TwinRoute buildings={overview?.buildings ?? []} events={events} onOpenEvent={openEvent} />;
    if (active === 'camera') return <CameraRoute />;
    if (active === 'events') return <EventsPage events={events} selectedId={selectedEventId} setSelectedId={setSelectedEventId} search={search} setSearch={setSearch} status={eventStatus} setStatus={setEventStatus} severity={eventSeverity} setSeverity={setEventSeverity} resource={eventResource} setResource={setEventResource} onFeedback={(id, feedback) => void submitFeedback(id, feedback)} />;
    if (active === 'actions') return <ActionsPage actions={actions} onApprove={(id) => void approveAction(id)} onReject={(id) => void rejectAction(id)} busyActionId={busyActionId} outcome={nextOutcome} setOutcome={setNextOutcome} />;
    if (active === 'copilot') return <CopilotPage onAsk={(question) => void askCopilot(question)} result={copilotResult} loading={copilotLoading} events={events} onOpenEvent={openEvent} />;
    if (active === 'whatif') return <WhatIfPage buildings={overview?.buildings ?? []} result={whatIfResult} running={whatIfRunning} onRun={(request) => void runWhatIf(request)} />;
    if (active === 'reports') return <ReportsPage overview={overview} events={events} actions={actions} onExport={exportReport} />;
    return <SettingsPage settings={settings} setSettings={setSettings} onSave={() => void saveSettings()} saving={settingsSaving} loaded={settingsLoaded} loadError={settingsLoadError} />;
  };

  const connectionLabel = DEMO_MODE ? 'Demo simulation' : connection === 'connected' ? 'Connected' : connection === 'loading' ? 'Connecting…' : 'Offline';
  const currentHealth: SystemHealth | undefined = overview?.health;

  return <>
    <AppShell active={active} setActive={setActive} health={currentHealth} demoMode={DEMO_MODE} connectionLabel={connectionLabel} onRefresh={() => void refresh(false)} onHelp={() => setShowHelp(true)}>
      {renderContent()}
    </AppShell>
    {selectedEvent && <DetailDrawer event={selectedEvent} onClose={() => setDrawerEventId(null)} onFeedback={(id, feedback) => void submitFeedback(id, feedback)} />}
    {showHelp && <HelpModal onClose={() => setShowHelp(false)} demoMode={DEMO_MODE} onNavigate={setActive} />}
    <Toasts items={toasts} onDismiss={(id) => setToasts((current) => current.filter((toast) => toast.id !== id))} />
  </>;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message}${error.requestId ? ` (request ${error.requestId})` : ''}`;
  if (error instanceof Error) return error.message;
  return 'Unexpected error. Check the backend logs and try again.';
}
