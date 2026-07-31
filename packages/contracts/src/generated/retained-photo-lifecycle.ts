/* AUTO-GENERATED from JSON Schema Draft 2020-12. DO NOT EDIT. */

export type RetainedPhotoLifecycle = {
  [k: string]: unknown;
} & {
  schema_version: "3.0";
  retained_photo_id: string;
  result_id: string;
  storage_key: string;
  content_fingerprint: string;
  media_type: "image/jpeg" | "image/png";
  width: number;
  height: number;
  capture_method: "screen_capture" | "smartphone_camera_capture";
  created_at: string;
  lifecycle: "retained" | "deletion_pending";
  deletion: {
    requested_at: string;
    image_readable: false;
    metadata_readable: false;
    attempt_count: number;
  } | null;
};
