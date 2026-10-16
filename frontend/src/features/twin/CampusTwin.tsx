import { useEffect, useMemo, useState, type KeyboardEvent } from 'react';
import type {
  BuildingStatus,
  CampusTwinProps,
  DataProvenance,
  EventSeverity,
  TwinBuilding,
  TwinEvent,
  TwinReading,
  TwinRoom,
} from './types';
import './campusTwin.css';

const STATUS_META: Record<BuildingStatus, { label: string; icon: string }> = {
  healthy: { label: 'Healthy', icon: '✓' },
  attention: { label: 'Needs attention', icon: '!' },
  critical: { label: 'Critical', icon: '×' },
  unknown: { label: 'Unknown', icon: '?' },
};

const SEVERITY_LABEL: Record<EventSeverity, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

function provenanceLabel(value: DataProvenance): string {
  return value === 'REAL' ? 'Real' : value === 'SIMULATED' ? 'Simulated' : 'Derived';
}

function formatAge(observedAt: string | null | undefined, now: Date): string {
  if (!observedAt) return 'Timestamp unavailable';
  const time = Date.parse(observedAt);
  if (!Number.isFinite(time)) return 'Timestamp invalid';
  const delta = Math.max(0, Math.floor((now.getTime() - time) / 1000));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

function formatNumber(value: number, unit: string): string {
  const formatted = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
  return unit ? `${formatted} ${unit}` : formatted;
}

function latestReadings(readings: TwinReading[]): TwinReading[] {
  const preferred = ['energy', 'water', 'waste', 'occupancy'];
  return [...readings].sort((a, b) => {
    const pa = preferred.indexOf(a.resourceType);
    const pb = preferred.indexOf(b.resourceType);
    return (pa === -1 ? 99 : pa) - (pb === -1 ? 99 : pb);
  });
}

function ReadingRow({ reading, now }: { reading: TwinReading; now: Date }) {
  const unavailable = reading.value === null || reading.status === 'unavailable';
  return (
    <div className="ct-reading-row">
      <div className="ct-reading-main">
        <span className="ct-reading-resource">{reading.resourceType}</span>
        <strong>{unavailable ? 'Unavailable' : formatNumber(reading.value as number, reading.unit)}</strong>
      </div>
      <div className="ct-reading-meta">
        <span className={`ct-pill ct-pill--${reading.provenance.toLowerCase()}`}>{provenanceLabel(reading.provenance)}</span>
        <span className={`ct-freshness ct-freshness--${reading.status}`}>{reading.status === 'stale' ? 'Stale' : reading.status === 'unavailable' ? 'Unavailable' : 'Fresh'}</span>
        <span>{formatAge(reading.observedAt, now)}</span>
        {reading.sourceLabel ? <span className="ct-source-label">· {reading.sourceLabel}</span> : null}
      </div>
    </div>
  );
}

function EventRow({
  event,
  onOpenEvent,
  onRequestAction,
}: {
  event: TwinEvent;
  onOpenEvent?: (eventId: string) => void;
  onRequestAction?: (eventId: string) => void;
}) {
  return (
    <article className="ct-event-row">
      <span className={`ct-severity-dot ct-severity-dot--${event.severity}`} aria-hidden="true" />
      <div className="ct-event-copy">
        <strong>{event.title}</strong>
        <span>{event.type.replaceAll('_', ' ')} · {SEVERITY_LABEL[event.severity]} · {event.status}</span>
        {event.summary ? <p>{event.summary}</p> : null}
      </div>
      <div className="ct-event-actions">
        {onOpenEvent ? <button type="button" className="ct-text-button" onClick={() => onOpenEvent(event.id)}>View event</button> : null}
        {event.actionAvailable && onRequestAction ? <button type="button" className="ct-small-action" onClick={() => onRequestAction(event.id)}>Review action</button> : null}
      </div>
    </article>
  );
}

function RoomTile({ room, selected, onSelect }: { room: TwinRoom; selected: boolean; onSelect: () => void }) {
  const eventCount = room.events.filter((event) => !['resolved', 'closed'].includes(event.status.toLowerCase())).length;
  const stateLabel = room.occupancy.state === 'OCCUPIED' ? 'Occupied' : room.occupancy.state === 'LIKELY_EMPTY' ? 'Likely empty' : 'Unknown';
  return (
    <button
      type="button"
      className={`ct-room-tile${selected ? ' is-selected' : ''}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className={`ct-occupancy-icon ct-occupancy-icon--${room.occupancy.state.toLowerCase()}`} aria-hidden="true">
        {room.occupancy.state === 'OCCUPIED' ? '●' : room.occupancy.state === 'LIKELY_EMPTY' ? '○' : '?' }
      </span>
      <span className="ct-room-tile-copy">
        <strong>{room.name}</strong>
        <span>{stateLabel} · {provenanceLabel(room.occupancy.provenance)}</span>
      </span>
      <span className="ct-room-event-count" aria-label={`${eventCount} open events`}>{eventCount}</span>
    </button>
  );
}

function mapPosition(building: TwinBuilding, index: number): { x: number; y: number; width: number; height: number } {
  if (building.mapPosition) {
    return {
      x: building.mapPosition.x,
      y: building.mapPosition.y,
      width: building.mapPosition.width ?? 218,
      height: building.mapPosition.height ?? 126,
    };
  }
  const col = index % 3;
  const row = Math.floor(index / 3);
  return { x: 56 + col * 320, y: 74 + row * 202, width: 218, height: 126 };
}

function BuildingShape({
  building,
  index,
  selected,
  onSelect,
}: {
  building: TwinBuilding;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const { x, y, width, height } = mapPosition(building, index);
  const status = STATUS_META[building.status];
  const shortName = building.shortCode || building.name;
  const openEvents = (building.events || building.rooms.flatMap((room) => room.events)).filter(
    (event) => !['resolved', 'closed'].includes(event.status.toLowerCase()),
  ).length;
  const handleKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect();
    }
  };

  return (
    <g
      className={`ct-map-building ct-map-building--${building.status}${selected ? ' is-selected' : ''}`}
      role="button"
      tabIndex={0}
      aria-label={`${building.name}, ${status.label}, ${building.rooms.length} rooms, ${openEvents} open events`}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
      transform={`translate(${x} ${y})`}
    >
      <rect className="ct-building-shadow" x="4" y="5" width={width} height={height} rx="14" />
      <rect className="ct-building-body" width={width} height={height} rx="14" />
      <rect className="ct-building-roof" x="10" y="10" width={width - 20} height="22" rx="7" />
      <text className="ct-building-code" x="20" y="26">{shortName.length > 17 ? `${shortName.slice(0, 16)}…` : shortName}</text>
      <text className="ct-building-name" x="18" y="57">{building.rooms.length} rooms</text>
      <text className="ct-building-status" x="18" y="81">{status.icon} {status.label}</text>
      {openEvents > 0 ? <>
        <circle className="ct-building-event-mark" cx={width - 23} cy="55" r="13" />
        <text className="ct-building-event-count" x={width - 23} y="59">{openEvents > 9 ? '9+' : openEvents}</text>
      </> : null}
      <rect className="ct-building-focus-ring" x="-3" y="-3" width={width + 6} height={height + 6} rx="17" />
    </g>
  );
}

function statusClass(status: BuildingStatus): string {
  return `ct-status-label ct-status-label--${status}`;
}

export function CampusTwin({
  buildings,
  selectedBuildingId,
  selectedRoomId,
  now = new Date(),
  className = '',
  onBuildingSelect,
  onRoomSelect,
  onOpenEvent,
  onRequestAction,
}: CampusTwinProps) {
  const [internalBuildingId, setInternalBuildingId] = useState<string | undefined>(selectedBuildingId);
  const [internalRoomId, setInternalRoomId] = useState<string | undefined>(selectedRoomId);
  useEffect(() => setInternalBuildingId(selectedBuildingId), [selectedBuildingId]);
  useEffect(() => setInternalRoomId(selectedRoomId), [selectedRoomId]);

  const effectiveBuildingId = selectedBuildingId ?? internalBuildingId;
  const activeBuilding = useMemo(
    () => buildings.find((building) => building.id === effectiveBuildingId) ?? buildings[0],
    [buildings, effectiveBuildingId],
  );
  const activeRoom = useMemo(() => {
    if (!activeBuilding) return undefined;
    return activeBuilding.rooms.find((room) => room.id === (selectedRoomId ?? internalRoomId)) ?? activeBuilding.rooms[0];
  }, [activeBuilding, internalRoomId, selectedRoomId]);

  const selectBuilding = (buildingId: string) => {
    setInternalBuildingId(buildingId);
    setInternalRoomId(undefined);
    onBuildingSelect?.(buildingId);
    const building = buildings.find((item) => item.id === buildingId);
    if (building?.rooms[0]) onRoomSelect?.(buildingId, building.rooms[0].id);
  };
  const selectRoom = (roomId: string) => {
    if (!activeBuilding) return;
    setInternalRoomId(roomId);
    onRoomSelect?.(activeBuilding.id, roomId);
  };

  const canvasHeight = Math.max(450, Math.ceil(buildings.length / 3) * 202 + 90);
  const visibleEvents = activeRoom?.events?.length ? activeRoom.events : activeBuilding?.events ?? [];
  const orderedReadings = activeRoom ? latestReadings(activeRoom.readings) : [];

  if (buildings.length === 0) {
    return (
      <section className={`ct-twin ct-twin--empty ${className}`} aria-labelledby="ct-twin-title">
        <div className="ct-twin-heading">
          <div><p className="ct-eyebrow">CAMPUS / SPATIAL VIEW</p><h2 id="ct-twin-title">Campus twin</h2></div>
          <span className="ct-muted-label">No site data</span>
        </div>
        <div className="ct-empty-state">
          <span className="ct-empty-icon" aria-hidden="true">⌖</span>
          <h3>Campus layout unavailable</h3>
          <p>Building metadata has not been returned yet. Check the connection or load a clearly labelled demo scenario.</p>
        </div>
      </section>
    );
  }

  return (
    <section className={`ct-twin ${className}`} aria-labelledby="ct-twin-title">
      <div className="ct-twin-heading">
        <div>
          <p className="ct-eyebrow">CAMPUS / SPATIAL VIEW</p>
          <h2 id="ct-twin-title">Campus twin <span className="ct-heading-count">{buildings.length} buildings</span></h2>
          <p className="ct-twin-subtitle">Select a building, then a room, to inspect current evidence and open events.</p>
        </div>
        <div className="ct-status-legend" aria-label="Building status legend">
          {(Object.keys(STATUS_META) as BuildingStatus[]).map((status) => (
            <span key={status} className={statusClass(status)}><i aria-hidden="true">{STATUS_META[status].icon}</i>{STATUS_META[status].label}</span>
          ))}
        </div>
      </div>

      <div className="ct-twin-layout">
        <div className="ct-map-panel">
          <div className="ct-map-toolbar">
            <div><span className="ct-live-indicator" aria-hidden="true" /> <strong>Site overview</strong></div>
            <span>Illustrative schematic · not to scale</span>
          </div>
          <div className="ct-map-scroll">
            <svg className="ct-campus-map" viewBox={`0 0 1000 ${canvasHeight}`} role="group" aria-label="Interactive campus schematic">
              <title>Interactive campus building map</title>
              <desc>Choose a building to inspect its status, rooms, readings and events. Status includes words and symbols, not color alone.</desc>
              <defs>
                <pattern id="ct-map-grid" width="36" height="36" patternUnits="userSpaceOnUse">
                  <path d="M 36 0 L 0 0 0 36" fill="none" className="ct-map-grid-line" />
                </pattern>
              </defs>
              <rect width="1000" height={canvasHeight} className="ct-map-ground" rx="18" />
              <rect width="1000" height={canvasHeight} fill="url(#ct-map-grid)" rx="18" />
              <path className="ct-map-road" d={`M -20 260 C 180 220, 270 290, 450 260 S 760 235, 1020 280 M 310 -20 C 360 140, 290 330, 350 ${canvasHeight + 20} M 720 -20 C 665 140, 760 330, 690 ${canvasHeight + 20}`} />
              <path className="ct-map-walkway" d={`M 0 430 C 200 410, 340 450, 500 425 S 790 400, 1000 440 M 500 0 L 500 ${canvasHeight}`} />
              {Array.from({ length: 18 }).map((_, index) => {
                const x = 25 + (index % 9) * 118;
                const y = 24 + Math.floor(index / 9) * Math.max(300, canvasHeight - 60);
                return <g key={`tree-${index}`} className="ct-map-tree" transform={`translate(${x} ${y})`} aria-hidden="true"><circle r="8" /><circle cx="5" cy="-4" r="5" /></g>;
              })}
              {buildings.map((building, index) => (
                <BuildingShape
                  key={building.id}
                  building={building}
                  index={index}
                  selected={building.id === activeBuilding?.id}
                  onSelect={() => selectBuilding(building.id)}
                />
              ))}
            </svg>
          </div>
          <div className="ct-map-footer"><span><strong>{buildings.filter((building) => building.status === 'critical' || building.status === 'attention').length}</strong> buildings need attention</span><span>Building locations may be schematic if no layout coordinates are supplied.</span></div>
        </div>

        {activeBuilding ? <aside className="ct-inspector" aria-label={`${activeBuilding.name} inspector`}>
          <div className="ct-inspector-header">
            <div>
              <p className="ct-eyebrow">BUILDING INSPECTOR</p>
              <h3>{activeBuilding.name}</h3>
              <p>{activeBuilding.rooms.length} rooms · <span className={`ct-status-inline ct-status-inline--${activeBuilding.status}`}>{STATUS_META[activeBuilding.status].icon} {STATUS_META[activeBuilding.status].label}</span></p>
            </div>
            <span className={`ct-building-monogram ct-building-monogram--${activeBuilding.status}`} aria-hidden="true">{(activeBuilding.shortCode || activeBuilding.name).slice(0, 2).toUpperCase()}</span>
          </div>

          <div className="ct-room-section">
            <div className="ct-section-heading"><h4>Rooms</h4><span>{activeBuilding.rooms.length} tracked</span></div>
            {activeBuilding.rooms.length ? <div className="ct-room-list">
              {activeBuilding.rooms.map((room) => <RoomTile key={room.id} room={room} selected={room.id === activeRoom?.id} onSelect={() => selectRoom(room.id)} />)}
            </div> : <div className="ct-inline-empty">No room records are available for this building.</div>}
          </div>

          {activeRoom ? <>
            <div className="ct-detail-divider" />
            <div className="ct-section-heading ct-selected-room-heading"><div><p className="ct-eyebrow">ROOM DETAILS</p><h4>{activeRoom.name}</h4></div><span className={`ct-pill ct-pill--${activeRoom.occupancy.provenance.toLowerCase()}`}>{provenanceLabel(activeRoom.occupancy.provenance)}</span></div>
            <div className="ct-occupancy-card">
              <span className={`ct-occupancy-glyph ct-occupancy-glyph--${activeRoom.occupancy.state.toLowerCase()}`} aria-hidden="true">{activeRoom.occupancy.state === 'OCCUPIED' ? '●' : activeRoom.occupancy.state === 'LIKELY_EMPTY' ? '○' : '?'}</span>
              <div><strong>{activeRoom.occupancy.state === 'OCCUPIED' ? 'Occupied' : activeRoom.occupancy.state === 'LIKELY_EMPTY' ? 'Likely empty' : 'Occupancy unknown'}</strong><span>Observed {formatAge(activeRoom.occupancy.observedAt, now)}</span></div>
              {activeRoom.occupancy.state === 'UNKNOWN' ? <span className="ct-freshness ct-freshness--unavailable">Unknown</span> : null}
            </div>

            <div className="ct-section-heading"><h4>Resource readings</h4><span>{orderedReadings.length} signals</span></div>
            {orderedReadings.length ? <div className="ct-reading-list">{orderedReadings.map((reading) => <ReadingRow key={reading.id} reading={reading} now={now} />)}</div> : <div className="ct-inline-empty">No resource readings are available. Missing data is not treated as normal operation.</div>}

            <div className="ct-section-heading ct-camera-heading"><h4>Camera health</h4></div>
            {activeRoom.camera ? <div className="ct-camera-card">
              <span className={`ct-camera-indicator ct-camera-indicator--${activeRoom.camera.status}`} aria-hidden="true" />
              <div className="ct-camera-copy"><strong>{activeRoom.camera.status === 'connected' ? 'Camera connected' : activeRoom.camera.status === 'unavailable' ? 'Camera unavailable' : 'Camera state unknown'}</strong><span>{activeRoom.camera.inferenceMode === 'real' ? 'Local inference' : activeRoom.camera.inferenceMode === 'simulated' ? 'Simulated occupancy' : 'Inference mode unknown'}</span><span>Last frame: {formatAge(activeRoom.camera.lastFrameAt, now)}</span></div>
              <div className="ct-coverage"><strong>{typeof activeRoom.camera.coveragePercent === 'number' ? `${Math.round(activeRoom.camera.coveragePercent)}%` : '—'}</strong><span>coverage</span></div>
            </div> : <div className="ct-inline-empty">Camera telemetry has not been supplied for this room.</div>}

            <div className="ct-events-section">
              <div className="ct-section-heading"><h4>Recent events</h4><span>{visibleEvents.length}</span></div>
              {visibleEvents.length ? <div className="ct-events-list">{visibleEvents.slice(0, 4).map((event) => <EventRow key={event.id} event={event} onOpenEvent={onOpenEvent} onRequestAction={onRequestAction} />)}</div> : <div className="ct-inline-empty">No events returned for this room. This is not proof that every sensor is healthy.</div>}
            </div>
          </> : <div className="ct-inline-empty">Choose a room to inspect its readings and events.</div>}
        </aside> : null}
      </div>
    </section>
  );
}

export default CampusTwin;
