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
