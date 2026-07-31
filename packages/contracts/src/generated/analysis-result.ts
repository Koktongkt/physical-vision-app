/* AUTO-GENERATED from JSON Schema Draft 2020-12. DO NOT EDIT. */

export type Completion = {
  [k: string]: unknown;
} & {
  schema_version: "3.0";
  completion_version: "1.0";
  completion_id: string;
  task_id: string;
  session_id: string;
  result_id: string;
  decision_id: string;
  snapshot_id: string;
  raw_candidate: string;
  displayed_candidate: string;
  final_serial: string;
  completion_source:
    | "automatic_ocr"
    | "user_confirmed_ocr_unchanged"
    | "user_corrected";
  threshold_version: string;
  threshold_classification: "PET";
  auto_threshold_strictly_greater_than: 0.8;
  whole_string_exact_probability_calibrated: number | null;
  gate_outcomes: {
    support: boolean;
    localization: boolean;
    quality: boolean;
    ocr_integrity: boolean;
    freshness: boolean;
    format_policy: boolean;
    deterministic_safety: boolean;
    no_unknown_blocking: boolean;
    version_compatibility: boolean;
  };
  policy_version: string;
  calibration_version: string;
  model_version: string;
  preprocess_version: string;
  schema_version_used: "3.0";
  idempotency_key: string;
  idempotency_fingerprint: string;
  created_at: string;
  supersedes_completion_id: string | null;
};
export type FailureEnvelope = {
  [k: string]: unknown;
} & {
  schema_version: "3.0";
  code:
    | "PHOTO_PICKER_UNAVAILABLE"
    | "UPLOAD_UNAVAILABLE"
    | "SESSION_EXPIRED"
    | "SEQUENCE_CONFLICT"
    | "ATTEMPT_SUPERSEDED"
    | "IDEMPOTENCY_CONFLICT"
    | "UNSUPPORTED_MEDIA_TYPE"
    | "ANIMATED_OR_MULTIFRAME_UNSUPPORTED"
    | "INVALID_OR_CORRUPT_IMAGE"
    | "IMAGE_DIMENSIONS_UNSUPPORTED"
    | "INPUT_TOO_LARGE"
    | "DECODE_BUDGET_EXCEEDED"
    | "NO_LABEL_FOUND"
    | "MULTIPLE_LABELS_AMBIGUOUS"
    | "UNSUPPORTED_LABEL_OR_OBJECT"
    | "SUPPORT_UNKNOWN"
    | "QUALITY_INSUFFICIENT"
    | "SERIAL_UNREADABLE"
    | "OCR_AMBIGUOUS"
    | "FORMAT_POLICY_MISMATCH"
    | "PROCESSING_TIMEOUT"
    | "DEPENDENCY_UNAVAILABLE"
    | "LOCAL_STORAGE_LIMIT"
    | "DELETION_PENDING"
    | "DELETION_FAILED"
    | "INTERNAL_PROCESSING_ERROR";
  category:
    | "capability"
    | "not-found"
    | "ambiguous"
    | "quality"
    | "unsupported-input"
    | "unsupported-subject"
    | "unknown"
    | "timeout"
    | "local-resource"
    | "deletion"
    | "dependency"
    | "internal";
  recoverable: boolean;
  retryable: boolean;
  retry_after_ms: number | null;
  message_key: string;
  identity_conflict: {
    identity_kind: "upload" | "completion";
    idempotency_key: string;
    expected_fingerprint: string;
    received_fingerprint: string;
  } | null;
};

export interface AnalysisResult {
  schema_version: "3.0";
  result_id: string;
  session: {
    task_id: string;
    session_id: string;
    source_epoch: number;
    upload_sequence: number;
    upload_idempotency_key: string;
    content_fingerprint: string;
  };
  source: {
    media_type: "image/jpeg" | "image/png";
    capture_method:
      | "screen_capture"
      | "smartphone_camera_capture"
      | "ordinary_file_upload";
    capture_provenance: "physical" | "replayed";
    orientation_transform_id: "exif-once-v1";
  };
  vision_evidence_snapshot: VisionEvidenceSnapshot;
  policy_decision: PolicyDecision;
  status:
    | "guidance"
    | "waiting"
    | "ready_for_verification"
    | "automatic_complete"
    | "user_complete"
    | "ocr_uncertain"
    | "no_label"
    | "ambiguous_label"
    | "unsupported_subject"
    | "unsupported_input"
    | "manual_required"
    | "internal_error";
  capture_complete: boolean;
  business_complete: boolean;
  serial_candidate: {
    raw: string;
    displayed: string;
    editable: true;
  } | null;
  completion: Completion | null;
  recommendation: {
    [k: string]: unknown;
  } | null;
  failure: FailureEnvelope | null;
  versions: {
    schema: "3.0";
    model: string;
    preprocess: string;
    calibration: string;
    policy: string;
    threshold: string;
  };
}
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
export interface PolicyDecision {
  schema_version: "3.0";
  decision_version: "1.0";
  decision_id: string;
  result_id: string;
  snapshot_id: string;
  policy_version: string;
  threshold_version: string;
  threshold_classification: "PET";
  auto_threshold_strictly_greater_than: 0.8;
  status:
    | "guidance"
    | "waiting"
    | "ready_for_verification"
    | "automatic_complete"
    | "user_complete"
    | "ocr_uncertain"
    | "no_label"
    | "ambiguous_label"
    | "unsupported_subject"
    | "unsupported_input"
    | "manual_required"
    | "internal_error";
  primary_action: {
    [k: string]: unknown;
  };
  gate_outcomes: {
    support: boolean;
    localization: boolean;
    quality: boolean;
    ocr_integrity: boolean;
    freshness: boolean;
    format_policy: boolean;
    deterministic_safety: boolean;
    no_unknown_blocking: boolean;
    version_compatibility: boolean;
  };
  all_required_gates_pass: boolean;
  automatic_completion_eligible: boolean;
  candidate_ready: boolean;
  evaluated_at: string;
}
