export type DataProvenance = 'REAL' | 'SIMULATED' | 'DERIVED';
export type PointStatus = 'available' | 'stale' | 'unavailable';

export interface ChartPoint {
  /** ISO 8601 timestamp, normally UTC as returned by the API. */
  timestamp: string;
  value: number | null;
  provenance?: DataProvenance;
  status?: PointStatus;
  sourceId?: string;
}

export interface ChartSeriesInput {
  id: string;
  label: string;
  points: ChartPoint[];
  /** Use MIXED when the API series combines different provenance types. */
  provenance?: DataProvenance | 'MIXED';
}

export interface VerificationSummary {
  /** Values and outcome returned by the backend verification record. */
  outcome: 'VERIFIED_SUCCESS' | 'VERIFICATION_FAILED' | 'VERIFYING' | 'VERIFICATION_TIMEOUT' | 'UNKNOWN' | string;
  requiredDrop: number | null;
  observedDrop: number | null;
  unit: string;
  windowStart?: string | null;
  windowEnd?: string | null;
  sourceIds?: string[];
  provenance?: DataProvenance | 'MIXED';
}
