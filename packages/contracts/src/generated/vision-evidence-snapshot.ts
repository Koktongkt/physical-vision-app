/* AUTO-GENERATED from JSON Schema Draft 2020-12. DO NOT EDIT. */

export interface VisionEvidenceSnapshot {
  schema_version: "3.0";
  snapshot_version: "1.0";
  snapshot_id: string;
  result_id: string;
  observed_at: string;
  support: {
    state: "pass" | "fail" | "unknown";
    ood_state: "in_distribution" | "out_of_distribution" | "unknown";
    probability_calibrated: number | null;
  };
  localization: {
    state: "pass" | "fail" | "unknown";
    label_region: Region | null;
    text_region: Region | null;
    text_containment: number | null;
    label_confidence: number | null;
  };
  quality: {
    crop: Gate;
    scale: Gate;
    center: Gate;
    blur: Gate;
    exposure: Gate;
    contrast: Gate;
    glare: Gate;
    occlusion: Gate;
    perspective: Gate;
    ocr_integrity: Gate;
    overall: Gate;
  };
  ocr: {
    raw_string: string;
    displayed_string: string;
    whole_string_exact_probability_calibrated: number | null;
    format_warning: string | null;
    checksum_warning: string | null;
    silent_repair_applied: false;
    candidate_mutated: false;
  };
  freshness: {
    is_current_attempt: boolean;
    age_ms: number;
    max_age_ms: number;
  };
  versions: {
    model: string;
    preprocess: string;
    calibration: string;
    schema: "3.0";
    policy_compatible: string;
    threshold_compatible: string;
  };
}
export interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface Gate {
  state: "pass" | "fail" | "unknown";
}
