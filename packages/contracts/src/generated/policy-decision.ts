/* AUTO-GENERATED from JSON Schema Draft 2020-12. DO NOT EDIT. */

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
