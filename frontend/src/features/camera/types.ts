export type EvidenceStatus = "AVAILABLE" | "UNKNOWN" | "UNAVAILABLE";
export type OccupancySignal = "PERSON_DETECTED" | "NO_PERSON_DETECTED" | "UNKNOWN";
export type Provenance = "REAL" | "SIMULATED" | "DERIVED";
export type PersistenceStatus = "RECORDED" | "NOT_CONFIGURED" | "FAILED" | "NOT_DUE";

export interface OccupancyEvidence {
  evidence_id: string;
  room_id: string;
  status: EvidenceStatus;
  signal: OccupancySignal;
  provenance: Provenance;
  raw_person_count: number | null;
  smoothed_person_count: number | null;
  observed_at: string;
  received_at: string;
  frame_age_ms: number | null;
  camera_label: string | null;
  coverage_confirmed: boolean;
  eligible_for_empty_timer: boolean;
  reason_code: string | null;
  explanation: string;
  frame_mean_luminance: number | null;
  frame_luminance_stddev: number | null;
  detector_name: string | null;
  detector_confidence_threshold: number | null;
  smoothing_window: number;
  persistence_status: PersistenceStatus;
}

export interface VisionHealth {
  status: EvidenceStatus;
  detector_available: boolean;
  detector_name: string | null;
  detector_confidence_threshold: number | null;
  detector_nms_threshold: number | null;
  model_configured: boolean;
  model_license_reviewed: boolean;
  persistence_sink_configured: boolean;
  max_frame_bytes: number;
  max_frame_age_ms: number;
  smoothing_window: number;
  privacy: string;
  message: string;
}

export interface CurrentOccupancyResponse {
  status: EvidenceStatus;
  evidence: OccupancyEvidence | null;
  age_ms: number | null;
  message: string;
}
