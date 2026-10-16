import { useState } from 'react';
import { Activity, ArrowUpRight, Building2, Droplets, Zap } from 'lucide-react';
import type { BuildingSummary, CampusEvent } from '../../types';
import { formatNumber } from '../../utils/format';
import { ProvenanceTag, StatusPill } from '../../components/StatusPill';

/**
 * Stable route-level twin slot. Account 6 can replace this component with the dedicated
 * interactive SVG twin without changing app navigation or dashboard contracts.
 * This fallback is data-driven and intentionally 2D / dependency-light.
 */
export function TwinRoute({ buildings, events, onOpenEvent }: { buildings: BuildingSummary[]; events: CampusEvent[]; onOpenEvent: (id: string) => void }) {
  const [selected, setSelected] = useState(buildings[0]?.id ?? '');
  const activeBuilding = buildings.find((building) => building.id === selected) ?? buildings[0];
  const buildingEvents = events.filter((event) => event.buildingId === activeBuilding?.id && event.status !== 'RESOLVED');
  return <div className="page-stack">
    <div className="page-header"><div><div className="eyebrow">SPATIAL OPERATIONS</div><h1>Campus twin</h1><p>Select a building to inspect its resource status and linked evidence.</p></div><div className="page-header-actions"><StatusPill value="2D SCHEMATIC" /><span className="helper-note">Interactive fallback view</span></div></div>
    <div className="twin-layout">
      <section className="panel twin-canvas-panel">
        <div className="panel-heading"><div><h2>North campus map</h2><p>Not to scale · state is backed by the current dataset</p></div><div className="map-legend"><span><i className="legend-dot good" /> Normal</span><span><i className="legend-dot warn" /> Attention</span><span><i className="legend-dot danger" /> Critical</span><span><i className="legend-dot muted" /> Unknown</span></div></div>
        <div className="campus-schematic" role="group" aria-label="Select a campus building">
          <div className="schematic-path path-one" /><div className="schematic-path path-two" />
          {buildings.map((building, index) => <button key={building.id} className={`building-block block-${index + 1} state-${building.state.toLowerCase()} ${selected === building.id ? 'selected' : ''}`} onClick={() => setSelected(building.id)} aria-pressed={selected === building.id}>
            <span className="building-block-icon"><Building2 size={22} /></span><strong>{building.shortName}</strong><span>{building.name}</span><small>{building.activeEvents ?? '—'} open issues</small>
          </button>)}
          <div className="schematic-caption"><span className="campus-mark"><Activity size={14} /></span><span>NORTH CAMPUS</span><span className="caption-line" /></div>
        </div>
        <div className="twin-note"><Activity size={15} /><span>Building states use status labels as well as colour. Unknown means evidence is missing or unhealthy—not that the building is normal.</span></div>
      </section>
      <aside className="panel building-detail-panel">
        {activeBuilding ? <>
          <div className="building-detail-cover"><div className="detail-cover-mark"><Building2 size={27} /></div><div><span className="eyebrow">BUILDING PROFILE</span><h2>{activeBuilding.name}</h2><p>{activeBuilding.shortName} · {activeBuilding.rooms ?? '—'} rooms</p></div><StatusPill value={activeBuilding.state} /></div>
          <div className="building-stats"><div><span>Open issues</span><strong>{activeBuilding.activeEvents ?? '—'}</strong></div><div><span>Energy today</span><strong>{activeBuilding.energyKwh === null ? '—' : `${formatNumber(activeBuilding.energyKwh)} kWh`}</strong></div></div>
          <div className="data-row resource-detail-row"><div className="resource-icon energy"><Zap size={17} /></div><div><strong>Energy use</strong><span>{activeBuilding.energyKwh === null ? 'No comparable reading' : `${formatNumber(activeBuilding.energyKwh)} kWh · source period unavailable`}</span></div><ProvenanceTag value={activeBuilding.provenance} /></div>
          <div className="data-row resource-detail-row"><div className="resource-icon water"><Droplets size={17} /></div><div><strong>Water use</strong><span>{activeBuilding.waterLitres === null ? 'Reading unavailable' : `${formatNumber(activeBuilding.waterLitres)} L`}</span></div></div>
          <div className="section-divider" />
          <div className="section-headline"><h3>Linked events</h3><span className="count-bubble">{buildingEvents.length}</span></div>
          {buildingEvents.length ? <div className="compact-event-list">{buildingEvents.map((event) => <button key={event.id} className="compact-event" onClick={() => onOpenEvent(event.id)}><span className={`event-severity-dot sev-${event.severity.toLowerCase()}`} /><span><strong>{event.title}</strong><small>{event.roomName || event.buildingName} · {event.id}</small></span><ArrowUpRight size={15} /></button>)}</div> : <div className="empty-inline"><span className="empty-icon"><Activity size={17} /></span><strong>No linked active events</strong><span>This only reflects the loaded event feed.</span></div>}
          <div className="twin-data-footnote"><span>Data source</span><ProvenanceTag value={activeBuilding.provenance} /><span>Room-level occupancy and camera coverage appear when supplied by the vision module.</span></div>
        </> : <div className="empty-state"><Building2 size={25} /><h3>No building data</h3><p>Connect the backend or load an explicit demo scenario to see the campus twin.</p></div>}
      </aside>
    </div>
  </div>;
}

