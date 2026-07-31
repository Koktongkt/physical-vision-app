/* AUTO-GENERATED from JSON Schema Draft 2020-12. DO NOT EDIT. */

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
