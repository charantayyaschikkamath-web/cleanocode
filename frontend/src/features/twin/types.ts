export type DataProvenance = 'REAL' | 'SIMULATED' | 'DERIVED';

export type BuildingStatus = 'healthy' | 'attention' | 'critical' | 'unknown';
export type OccupancyState = 'OCCUPIED' | 'LIKELY_EMPTY' | 'UNKNOWN';
export type ResourceType = 'energy' | 'water' | 'waste' | 'occupancy' | 'other';
export type ReadingStatus = 'available' | 'stale' | 'unavailable';
export type EventSeverity = 'low' | 'medium' | 'high' | 'critical';

/** Coordinates are in the schematic's 1000-unit viewBox, not geographic coordinates. */
export interface MapPosition {
  x: number;
  y: number;
  width?: number;
  height?: number;
}

export interface TwinReading {
  id: string;
  resourceType: ResourceType;
  value: number | null;
  unit: string;
  observedAt: string;
  provenance: DataProvenance;
  status: ReadingStatus;
  sourceLabel?: string;
}

export interface TwinEvent {
  id: string;
  title: string;
  type: string;
  severity: EventSeverity;
  status: string;
  createdAt: string;
  summary?: string;
  actionAvailable?: boolean;
}

export interface CameraHealth {
  status: 'connected' | 'unavailable' | 'unknown';
  inferenceMode: 'real' | 'simulated' | 'unknown';
  lastFrameAt?: string | null;
  coveragePercent?: number | null;
}

export interface TwinRoom {
  id: string;
  name: string;
  occupancy: {
    state: OccupancyState;
    provenance: DataProvenance;
    observedAt?: string | null;
  };
  readings: TwinReading[];
  events: TwinEvent[];
  camera?: CameraHealth | null;
}

export interface TwinBuilding {
  id: string;
  name: string;
  shortCode?: string;
  status: BuildingStatus;
  mapPosition?: MapPosition;
  rooms: TwinRoom[];
  events?: TwinEvent[];
}

export interface CampusTwinProps {
  buildings: TwinBuilding[];
  selectedBuildingId?: string;
  selectedRoomId?: string;
  now?: Date;
  className?: string;
  onBuildingSelect?: (buildingId: string) => void;
  onRoomSelect?: (buildingId: string, roomId: string) => void;
  onOpenEvent?: (eventId: string) => void;
  onRequestAction?: (eventId: string) => void;
}
