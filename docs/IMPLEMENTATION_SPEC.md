# Physical Vision App — Authoritative Implementation Specification

**Product:** Iterative still-photo-guided serial-label capture MVP  
**Specification status:** Approved for localhost-only, single-user personal prototype implementation and evaluation with G1–G8 and A1–A15/D1–D7 decisions incorporated; **not approved for production implementation, distribution of restricted model code/weights, remote availability, operational support, or launch**  
**Version:** 1.4  
**Last amended:** 2026-07-26  
**Normative source tasks:** `t_edafa288`, `t_9db4b5de`, `t_3bb8d5b2`, `t_e3187d49`, `t_95ff3002`, `t_88bc938f`, `t_f9f6d927`, `t_9d8f876a`, `t_f8132754`, `t_fb42469a`

## 0. How to read this specification

This document consolidates the completed parent-card handoffs into the implementation authority for subsequent planning and Kanban decomposition. If a downstream design conflicts with this specification, this document wins unless a named open decision has since been approved and recorded as a versioned amendment.

Decision labels:

- **Approved requirement (AR):** behavior fixed by the completed planning work.
- **Recommended implementation choice (RI):** a concrete engineering default proposed here to make decomposition possible; it is not a stakeholder-approved product constraint and may change through an ADR.
- **Validation-dependent threshold (VT):** a measurable seed or hypothesis that must be calibrated on representative evidence before release.
- **Provisional experimental threshold (PET):** a Product Owner-approved, versioned localhost experiment setting that permits bounded behavior but is neither a validated accuracy claim nor a production release threshold.
- **Human decision required (HD):** consequential unresolved choice. No production commitment may silently assume an answer.

`MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` are normative only when applied to an AR. Numeric values marked VT are test seeds, not guarantees. PET values are approved only for the stated personal experiment and MUST remain visibly qualified, versioned, logged, and subject to replacement or reaffirmation by the named evidence gate.

---

## 1. Product objective and target users

### 1.1 Objective

**AR:** Help a cooperative user obtain one trustworthy, verbatim printed serial/text value from the barcode-bearing wraparound label of one plastic water bottle with minimal manual effort. The barcode-bearing area helps localize the label; rectified OCR reads the nearby printed serial/text while preserving leading zeros, separators, and displayed characters. The workflow ends with one traceable final value, an editable candidate, one next-photo action, or an explicit failure/manual outcome.

The MVP optimizes for **observable, abstaining assisted capture**. Capture readiness and business completion remain separate. Automatic business completion is now permitted only by the narrowly bounded PET rule in §3.4; otherwise the product exposes an editable `serial_candidate` and optional confirmation/correction path. No raw recognizer score, checksum, format match, multi-photo agreement, or character repair may independently authorize completion, and no OCR/format/checksum correction may be silent.

### 1.2 Users

**Primary:** one personal tester using the localhost application from a laptop/desktop browser and submitting still photos, including webcam screen captures and photos transferred from a smartphone camera.

**Future users only:** field technicians, installers, depot workers, inventory operators, back-office staff, supervisors, and pilot administrators. Multi-user, reviewer, administrative, and remote-access workflows are not personal-test prototype features.

**Not targeted by the MVP:** unattended production-line inspection, high-volume scanning, forensic recovery, arbitrary scene/document OCR, or operation requiring fully non-visual verification.

### 1.3 Priority use cases

1. Begin with one uploaded JPEG/JPG or PNG still photo.
2. When evidence is insufficient, receive one concrete camera movement, angle, distance, steadiness, obstruction, or lighting action and upload another still photo.
3. Repeat analysis and guided recapture without restarting the business task until evidence is sufficient or retry/manual policy ends the attempt.
4. Receive a visibly identified automatic completion only when every §3.4 gate passes, or inspect/edit a `serial_candidate` and optionally confirm or correct it.
5. Exit honestly to manual/escalation or terminal failure when iterative still-photo capture cannot succeed.

---

## 2. MVP scope and explicit non-goals

### 2.1 Approved scope

- One task contains one plastic water bottle, one ordinary matte or glossy printed wraparound barcode-bearing label, and one printed serial/text value near the barcode.
- The initial MVP is an iterative still-photo workflow. It starts with one uploaded JPEG/JPG or PNG photo and MAY request additional still-photo uploads with one concrete recapture instruction at a time.
- Text scope is printed Latin letters, Arabic numerals, and common separators (`-`, `/`, `.`, spaces), preserving meaningful leading zeros and separators.
- The barcode-bearing area MAY be used to identify or localize the relevant label region. The barcode payload MUST NOT be decoded or used as the final value; OCR MUST read the printed serial/text near it.
- The G1 pilot allowlist is plastic water bottles with ordinary matte or glossy printed wraparound labels. Other objects and label families are unsupported until separately approved and validated.
- The product is a browser-only web application served on localhost for one personal tester. It supports standards-compatible desktop and mobile browsers, including iOS Safari, as still-photo sources through the browser file/photo picker; photos may originate from smartphone cameras or ordinary built-in/USB webcams, but every analysis receives a completed JPEG/JPG or PNG still. There are no native iOS, Android, or desktop applications. Continuous live-camera preview, frame streaming, and real-time guidance are deferred.
- Expected use is indoor or sheltered, cooperative, safely accessible, and normally allows adjustment of distance, angle, steadiness, obstruction, or ambient light.
- Ordinary matte and glossy printed wraparound labels, including ordinary curvature, are in evaluation scope. Transparent, foil, severely wrinkled, and heavily damaged labels are positive unsupported/OOD classes. Partial obstruction is actionable only when reliable evidence supports a safe camera direction/angle that should improve visibility; otherwise the policy emits unknown/manual.
- Guidance recommends user actions. The product does not claim control of focus, zoom, exposure, flash, lens, camera movement, or object movement.
- The user may inspect, edit, confirm, or correct the proposed serial. Machine proposal, automatic completion, user confirmation, and later correction/supersession remain distinguishable.

### 2.2 Explicit non-goals

- Objects other than plastic water bottles; unsupported label families or languages; handwriting; transparent or foil labels; severe wrinkles, heavy damage, severe curvature distortion, dot-peen marks, or severe-damage recovery.
- Multiple labels/serials, batches, uploaded video, animated/multi-frame media, continuous live-camera preview/streaming/guidance, multi-camera rigs, conveyors, robots, or background scanning.
- Manufacturer-specific camera control, guaranteed autofocus/exposure/flash/zoom, calibrated physical tilt measurement, or external triggers.
- Unbounded autonomous acceptance/submission, silent OCR repair, asset identity proof, counterfeit detection, condition assessment, or safety certification. The only automatic completion allowed is the localhost PET rule in §3.4.
- ERP/inventory integration, reviewer portal, account administration, analytics dashboard, production media-management service, or production training pipeline.
- Authentication, accounts, tenancy, anonymous remote access, remote/public availability, multi-user concurrency, production availability, formal operational support, regulated chain of custody, or hard real-time guarantees.
- Accessibility conformance, localization beyond English, audio/haptic guidance, or non-visual verification in this personal-test version.
- Barcode/QR value decoding. The presence of a barcode may help localize the label, but the MVP reads printed serial/text near it.

---

## 3. Approved user workflow

### 3.1 Entry and first still photo

1. Explain the supported scope and that the MVP works from uploaded still photos, not a continuous live feed.
2. Offer one **Upload photo** action. The browser MAY invoke a device camera through its file/photo picker, but the application receives one completed still image per attempt.
3. Accept exactly one JPEG/JPG or PNG still image per attempt. Validate actual decoded type rather than trusting the extension or header, plus frame count, dimensions, bytes, metadata, decompression work, and processing budget before inference. Preprocessing MAY resize valid large photos for model input; a model input dimension is not a product-quality upload cap. Necessary pre-decode, decompression-bomb, memory, CPU, temporary-disk, and retained-local-storage guards remain mandatory, with exact numeric limits provisional.
4. Classify the submission source as `screen_capture`, `smartphone_camera_capture`, or `ordinary_file_upload` using explicit client/user provenance. Retention eligibility depends on this classification and MUST NOT be inferred from image content.
5. Show the chosen photo and a bounded processing state; every accepted attempt returns one result or an explicit timeout/failure.

### 3.2 Iterative still-photo guidance

1. Analyze each uploaded still through the bounded observable pipeline in §9.
2. If every current-attempt support, localization, quality, OCR-integrity, freshness, format-policy, and deterministic safety gate passes with no unknown/blocking evidence, return either `status=automatic_complete` under §3.4 or `status=ready_for_verification` with an editable `serial_candidate`.
3. `capture_complete=true` means capture analysis is sufficient for a completion path; `business_complete=true` means a traceable final value has actually been created. They MUST NOT be conflated.
4. If evidence is insufficient but recoverable, return both flags false with exactly one safe recommendation for the **next photo** and invite another JPEG/JPG or PNG upload.
5. Initial-prototype wording is camera-referent only. Approved patterns include “Move the camera left.”, “Move the camera closer.”, “Tilt the camera to face the label more directly.”, and “Move the camera or light to reduce glare.” Do not mix camera and object referents in one workflow without a later versioned decision.
6. Render the action directly on the analyzed still with a clear overlay/arrow and matching English text before the user takes the next photo.
7. Preserve task/session context and increment `upload_sequence`. Analyze the current still independently; use only explicitly versioned, policy-eligible bounded history. Replayed photos/screens are permitted for algorithm testing only when marked `capture_provenance=replayed`; they are excluded from representative physical-workflow and locked physical-guidance claims, and no liveness claim is made.
8. Repeat without a product attempt-count ceiling until completion/candidate readiness, user exit, or terminal unsupported/input/resource/dependency/internal-error outcome. A sufficient first photo may complete or expose a candidate; no two-frame requirement applies.

### 3.3 Deferred live-camera path

Continuous preview, automatic frame sampling/streaming, real-time camera guidance, stale-frame handling, temporal frame persistence, and live track lifecycle are deferred to a later phase. They are not initial-MVP requirements or release gates. A future live mode requires a versioned amendment and separate privacy, browser, performance, accessibility, and validation evidence.

### 3.4 Candidate, automatic, and user completion

1. Preserve and display the recognizer’s verbatim raw/displayed string, including leading zeros and separators. Format/checksum evidence is a warning only and MUST NOT silently rewrite, normalize, repair, or substitute characters.
2. **AR/PET:** For the localhost personal-test prototype, automatic creation of `final_serial` and business completion MAY occur only when a calibrated estimate of whole-string exact correctness is **strictly greater than `0.80`** and every required current-attempt support, localization, quality, OCR-integrity, freshness, format-policy, and deterministic safety gate passes with no unknown or blocking evidence.
3. Raw recognizer confidence, checksum validity, format match, multi-photo agreement, or character repair alone MUST NOT qualify. The policy must consume the validated `VisionEvidenceSnapshot`, not vendor prose or unvalidated fields.
4. `0.80` is a Product Owner-approved **PET**, not a validated accuracy claim or production release threshold. It may change only through versioned configuration and must be replaced or reaffirmed through G2’s calibration and locked-study process, including approval of false-ready/false-accept, coverage, and worsening/unsafe-action bounds.
5. If the automatic rule fails, show an editable `serial_candidate` with optional user confirmation/correction, or one next-photo action when evidence is not candidate-ready. Explicit confirmation is no longer universally mandatory.
6. Automatic results MUST be visibly identified, retain source/evidence linkage, record `completion_source=automatic_ocr`, and remain reviewable/correctable. User completion records `completion_source=user_confirmed_ocr_unchanged | user_corrected`.
7. A correction never overwrites evidence or a prior completion. It creates a new version linked by `supersedes_completion_id`; the earlier record remains traceable until manual pair deletion.
8. Log threshold, policy, calibration, model, preprocessing, and schema versions plus completion provenance. Idempotency replay MUST NOT duplicate the business action.

### 3.5 Failure and exit

Recoverable outcomes preserve task context and provide one valid next-photo action. Terminal outcomes stop suggesting identical retries and offer only another source photo, manual entry if policy permits, unable-to-capture, or escalation.

---

## 4. Final logical system architecture

The approved architecture is a hybrid, observable pipeline. Roles MAY be co-located, but the versioned evidence/policy/completion boundaries are ARs.

```text
Browser still-photo client
  -> bounded JPEG/PNG admission
  -> Pillow decode + EXIF transpose exactly once
  -> canonical image + transforms
  -> deterministic OpenCV geometry/ROI/raw quality evidence/overlays
  -> learned localization/support/OOD evidence as needed
  -> rectification + OCR candidates
  -> schema-validated VisionEvidenceSnapshot (immutable)
  -> deterministic, versioned, cost-aware, abstaining one-action policy
  -> PolicyDecision (one action, candidate readiness, or automatic eligibility)
  -> automatic completion under PET OR editable candidate/user completion
  -> linked local evidence/completion store + content-free telemetry
```

OpenCV is the geometry and deterministic-measurement foundation, not an assumed robust open-world localizer or OCR engine. Learned models emit measurements, calibrated confidence, and explicit unknown states; they do not emit UI prose or bypass deterministic vetoes. `VisionEvidenceSnapshot` and `PolicyDecision` are separate versioned contracts, subject to executable-schema refinement.

### 4.1 Trust boundaries

- Raw content crosses only client-to-processing and minimum internal processing boundaries.
- Model/OCR output is untrusted and schema/range validated before policy use.
- OCR text is inert data: never execute, navigate, template-evaluate, shell, or inject unrestricted into privileged prompts.
- Ordinary logs, metrics, traces, analytics, alerts, and crash reports receive no image/crop bytes, incidental OCR, full serial, or other prohibited content.
- The personal-test prototype has no account, authentication, tenant, anonymous-remote, support, or public ingress boundary. Opaque IDs and local ownership/linkage constraints still prevent accidental cross-record mutation.

### 4.2 Deployment topology status

**AR G5:** deploy only as a same-machine localhost application for one personal tester. Bind services to loopback; do not expose a LAN/public listener, remote anonymous endpoint, account system, tenant model, production availability commitment, or operational-support surface.

**RI:** use a local modular monolith containing the web/API boundary, preprocessing orchestration, policy, local persistence, and completion/supersession service. Keep inference behind an internal adapter for testability, not as permission to expose a remote production service.

---

## 5. Component responsibilities

### 5.1 Web client

- Still-photo selection/capture through the browser file/photo picker, upload progress, one next-photo guidance action, iterative retry, verification, correction, confirmation, and terminal/manual states.
- Run as a standards-compatible browser application on desktop and mobile, including iOS Safari; no native application or continuous live-camera feed is required.
- Accept one still per attempt: JPEG (`.jpg`/`.jpeg`, `image/jpeg`) or PNG (`.png`, `image/png`), subject to validated decoder limits.
- Normalize display orientation exactly once; transform normalized service regions only for display.
- Render the one next-photo recommendation on the analyzed still as a clear overlay/arrow plus English text. The rendering MUST identify the physical camera action and applicable direction, angle, distance, or lighting change, and declare the action referent.
- Send task/session identity, upload idempotency key, capture-source classification, and monotonic `upload_sequence`; discard stale/superseded results.
- Provide clear visual states for the personal tester. G8 sets no formal accessibility conformance target and requires no localization, audio, haptic, or non-visual-verification implementation yet.

### 5.2 API/session coordinator

- Validate versioned envelopes and media limits.
- Create unguessable, expiring local sessions without authentication, accounts, or tenant scope.
- Enforce upload-attempt sequencing, deduplication, idempotency, bounded work queues, pre-decode/decompression and local-resource guards, deadlines, and cancellation; do not enforce a maximum guidance-attempt count.
- Distinguish user/input, capability, dependency, resource-safety, and internal failures; authorization and remote rate-limit failures are outside the localhost personal-test contract.
- Ensure every accepted attempt yields one valid result or explicit transport failure.

### 5.3 Preprocessor

- Use Pillow for bounded JPEG/PNG decode and apply EXIF transpose exactly once; reject malformed, spoofed, multi-frame, decompression-bomb, unsafe metadata, or over-budget inputs before expensive work.
- Produce the canonical oriented image and reversible source/canonical transform.
- Use OpenCV for deterministic geometry, ROI extraction/rectification, raw crop/scale/center/blur/exposure/contrast/glare/perspective measurements, and overlay geometry.
- Resize only under a versioned preprocessing policy; model dimensions are not product upload caps. Preserve unrectified source evidence and never claim enhancement created missing information.

### 5.4 Inference/evidence adapter

- Run a data-driven localization bake-off: classical barcode/contour baseline versus lightweight box detector versus lightweight instance segmenter. Select by full-label/text containment, unsupported false positives, guidance safety, OCR effect, CPU/GPU resource use, and latency—not generic mAP alone. Masks are candidates for curved visible labels, not an assumed winner.
- Produce support/localization/OOD evidence, rectified OCR candidates, per-sequence calibrated exact-string estimates, ambiguity evidence, and raw quality features. Keep label, OCR, action, and quality confidence separate.
- Begin with deterministic quality features. Add MobileNetV3/EfficientNet-Lite-class support/OOD/ambiguity heads only if ablation improves policy-level outcomes; do not begin with a monolithic multitask network.
- Preserve exact model/weight/dependency/calibration versions, validate ranges/schema, and emit unknown where evidence is absent. Never choose UI wording or perform completion.

### 5.5 Deterministic policy engine

- Consume an immutable, schema-validated `VisionEvidenceSnapshot` plus optional versioned, policy-eligible bounded history.
- Apply cost-aware safety ordering, hard vetoes, freshness, support, localization, quality, OCR-integrity, format-warning, calibrated-readiness, and tie-break rules. Unknown blocks automatic completion.
- Return one immutable `PolicyDecision`: exactly one next-photo action, candidate readiness, automatic-completion eligibility, manual/unsupported, or terminal failure.
- Use fixed camera-referent wording keys; preserve image-space correction separately. Replay identical snapshot/config/version byte-for-byte deterministically.

### 5.6 Completion/business service

- Revalidate local task/session/result linkage, latest-result freshness, policy/calibration/threshold/model versions, and all required automatic-completion gates.
- Create at most one idempotent initial completion with `completion_source=automatic_ocr | user_confirmed_ocr_unchanged | user_corrected`.
- Preserve raw candidate, displayed candidate, and final value separately. Never silently repair OCR.
- Corrections create immutable superseding completion records rather than overwriting evidence or history.

### 5.7 Storage and telemetry

- Retain locally each submitted photo explicitly classified as `screen_capture` or `smartphone_camera_capture`, together with its linked vision-analysis metadata, for personal evaluation until the user manually deletes it. Ordinary `ordinary_file_upload` photos are not automatically retained.
- Store each retained photo and analysis as one lifecycle unit with opaque photo/result linkage, capture source, timestamps, model, policy, preprocessing, calibration, and schema versions; keep raw/displayed candidates, automatic or user completion provenance, final value, and supersession chain distinguishable.
- Manual deletion MUST remove the retained image and all metadata whose only purpose is that image in one transactional operation, or mark the pair deletion-pending and make neither readable until retry completes. Shared immutable version records MAY remain only if they contain no photo-derived content. No backup, export, training, or reviewer copy is created by the personal-test prototype.
- Use allowlisted, bounded, content-free local telemetry with opaque IDs and versions; telemetry MUST NOT become a shadow copy of deleted image/analysis content.

---

## 6. Technology stack and rationale

A1–A10 approve the following experiment/deployment direction while framework selections remain ADR-controlled.

| Layer | Approved baseline / candidate | Rationale / constraint |
|---|---|---|
| Web/API | TypeScript/React/Vite and Python 3.11+/FastAPI/Pydantic remain RI | Browser still workflow and executable contracts; framework lock is not a product requirement. |
| Decode | Pillow bounded JPEG/PNG decode + EXIF transpose exactly once | Safer canonicalization boundary; fuzz and resource limits required. |
| Geometry/features | OpenCV | Canonical geometry, ROI extraction/rectification, deterministic raw quality measurements, and overlays; not a standalone open-world localizer/OCR claim. |
| Localization | Classical barcode/contour baseline vs permissive lightweight box detector vs lightweight instance segmenter | Bottle-data bake-off uses containment, unsupported FP, guidance/OCR outcomes, resources, and latency. Masks are conditional. |
| Restricted experiment | Ultralytics YOLO in controlled personal bake-off only | MUST NOT be distributed. Preserve AGPL/enterprise obligations; require a new licensing/distribution decision before any embedding. Include permissive alternatives such as RT-DETRv2-class candidates. |
| Quality/support/OOD | Deterministic features first; conditional MobileNetV3/EfficientNet-Lite-class heads | Add learned heads only after policy-level ablation gain; no initial monolithic multitask network. |
| OCR | PP-OCRv6 preferred initial candidate/primary benchmark; Tesseract baseline; compact SVTR/CTC fallback experiment | PP-OCRv6 is not validated until target-data evaluation and exact weight/dependency licence verification pass. |
| Training/reference | PyTorch and/or Paddle | Allowed for training/reference; not default shipped runtimes. |
| Portable inference | ONNX export + ONNX Runtime CPU | Deployment portability baseline. OpenVINO and CUDA/GPU are optional benchmark paths. |
| Policy/schema | Pure typed deterministic package; JSON Schema 2020-12/OpenAPI | Frozen evidence input, versioned decisions, executable validation and replay. |
| Durable data | Local SQLite + application-private media store | One-machine linkage, completion provenance/supersession, and manual pair deletion. |
| Packaging/observability | Pinned local process/container, SBOM, allowlisted metrics/traces | Loopback-only reproducibility, resource measurement, no content leakage. |

Experiment machine: NVIDIA RTX 5070 with 12 GB VRAM and 32 GB system RAM; CPU model is unspecified. Every workload MUST be bounded and observable and MUST NOT exhaust CPU, GPU, RAM, VRAM, disk, or thermal capacity. Exact budgets remain PET/VT pending measurement. Alternative stacks must preserve every contract, determinism, licence, privacy, and evaluation obligation.

## 7. Data model

### 7.1 Approved domain entities

The conceptual model below is AR. Physical table design is RI within the approved localhost, no-auth, single-user deployment.

#### CaptureTask

- `task_id`: opaque local identifier
- no principal, account, or tenant reference in the personal-test prototype
- lifecycle: `active | completed | manual | unable | abandoned`
- source epochs and current completion reference plus immutable supersession chain
- created/completed timestamps

#### CaptureSession

- `session_id`: unguessable opaque identifier
- `task_id`, `mode = iterative_upload`, `source_epoch`
- negotiated schema major/minor
- `action_referent = camera` for initial-prototype next-photo guidance
- bounded client capabilities
- active model/policy/preprocess/calibration/format versions
- expiry/deadline fields
- capture-source and retention-eligibility policy version

#### AnalysisAttempt / Result

- `result_id`, session/epoch/`upload_sequence` identity
- source facts, explicit `capture_method`, retention eligibility, and measured timings for one still-photo attempt
- linked immutable `VisionEvidenceSnapshot` and `PolicyDecision`, status, `capture_complete`, `business_complete`, label, raw/displayed `serial_candidate`, and calibrated whole-string estimate
- complete deterministic and learned evidence objects, one next-photo recommendation or `none`, automatic-eligibility gate outcomes, optional failure
- optional bounded references to policy-eligible prior-attempt measurements
- threshold, model, policy, preprocessing, calibration, and schema versions plus safe diagnostics
- `retained_photo_id` when the source is an eligible screen/smartphone camera capture; ordinary file-upload bytes are not part of the durable entity

#### Completion

- `completion_id`, `task_id`, `session_id`, referenced `result_id` and decision/snapshot IDs
- verbatim raw/displayed candidate and `final_serial`
- `completion_source = automatic_ocr | user_confirmed_ocr_unchanged | user_corrected`
- threshold/policy/calibration/model/preprocessing/schema versions and automatic gate outcomes
- idempotency key/fingerprint, timestamp, optional `supersedes_completion_id`; superseded records remain immutable and reviewable

#### RetainedPhoto

- `retained_photo_id`, linked `result_id`, local relative storage key, content fingerprint, decoded media facts, and `capture_method = screen_capture | smartphone_camera_capture`
- created timestamp and lifecycle `retained | deletion_pending`; no independent metadata lifetime after deletion
- model, policy, preprocessing, calibration, and schema versions are reachable through the linked result

#### PolicyVersion / ModelVersion

Opaque non-secret immutable release identifiers sufficient to reproduce evaluation. Exact artifacts/configurations are kept in controlled release storage, not embedded in response payloads.

#### AuditEvent

Content-free security/business event containing opaque actor/task/session/result references, event code, outcome, timestamp, and deployment-approved metadata. No image, crop, incidental OCR, unrestricted exception, or full serial in routine audit/telemetry.

### 7.2 RI relational constraints

- Unique `(session_id, source_epoch, upload_sequence)` for iterative still-photo attempts.
- Unique upload idempotency key per local session; key reuse with a different content fingerprint returns conflict.
- Unique completion idempotency key per local task/action; changed payload returns conflict.
- One task has one current business completion; corrections append a uniquely linked superseding record and atomically move the current pointer.
- Foreign keys enforce local task/session/result/retained-photo linkage; deleting a retained photo transactionally removes its linked photo-specific analysis metadata or makes the entire pair unreadable while deletion is pending.
- No backup/export/training copy is created. The complete serial and linked evaluation/completion/supersession record remain local until manual pair deletion; deletion must remove the linked sensitive record rather than leave a shadow copy.

### 7.3 Media lifecycle

**AR G6:** photos submitted as `screen_capture` or `smartphone_camera_capture` are retained in application-private local storage with their linked vision-analysis metadata until the user manually deletes them. The retained pair preserves capture source, content linkage, measurements/results, and model/policy/preprocessing/calibration/schema versions for evaluation. `ordinary_file_upload` bytes and crops are ephemeral and are deleted after result, timeout, cancellation, error, or session end unless a later versioned approval changes that policy. Manual deletion is pair-wise and transactional: remove the photo plus photo-specific metadata, or make both unreadable under `deletion_pending` until physical deletion succeeds. No automatic age expiry, backup residual, export, review copy, or training reuse exists in this personal-test version. Local storage exhaustion is an explicit resource failure; exact byte/item safety thresholds are provisional and must not silently evict retained records.

---

## 8. Contracts and illustrative schemas

### 8.1 Common conventions

- `schema_version` is `major.minor`; this amendment advances the illustrative contract to `3.0` because completion semantics changed.
- RFC 3339 UTC timestamps; finite `[0,1]` scores; unavailable evidence is `null`/`unknown`, never fabricated zero.
- Canonical coordinates use top-left origin, x right, y down, normalized `[0,1]`; Pillow EXIF transpose occurs once and display transforms are client-only.
- Raw/displayed OCR strings are verbatim. Format/checksum fields are warning evidence only.

### 8.2 RI HTTP surface

1. `POST /v3/capture-sessions` creates the loopback session and returns versioned resource, retention, threshold, model/policy/calibration/schema settings.
2. `POST /v3/capture-sessions/{session_id}/uploads` accepts one bounded JPEG/PNG, monotonic sequence, idempotency key, and explicit `capture_method` plus `capture_provenance=physical | replayed`. It returns a validated result and may atomically create an automatic completion only under §3.4.
3. `POST /v3/capture-sessions/{session_id}/completions` accepts the latest eligible result, final verbatim serial, completion source, and idempotency key for user completion/correction. Corrections require `supersedes_completion_id`.
4. `DELETE /v3/capture-sessions/{session_id}` cleans ephemeral bytes but not retained evaluation records.
5. `DELETE /v3/retained-photos/{retained_photo_id}` manually deletes the retained image and linked sensitive analysis/completion chain as one lifecycle unit.

### 8.3 Result envelope and contract separation

```json
{
  "schema_version": "3.0",
  "result_id": "opaque",
  "session": {"session_id": "opaque", "source_epoch": 1, "upload_sequence": 1},
  "source": {
    "media_type": "image/jpeg",
    "capture_method": "smartphone_camera_capture",
    "capture_provenance": "physical",
    "orientation_transform_id": "exif-once-v1"
  },
  "vision_evidence_snapshot": {
    "snapshot_version": "1.0",
    "snapshot_id": "opaque",
    "observed_at": "2026-07-26T00:00:00Z",
    "support": {"state": "pass", "ood_state": "in_distribution"},
    "localization": {"state": "pass", "label_region": [0.1, 0.2, 0.8, 0.6], "text_containment": 0.98},
    "quality": {
      "crop": {"state": "pass"}, "scale": {"state": "pass"}, "center": {"state": "pass"},
      "blur": {"state": "pass"}, "exposure": {"state": "pass"}, "contrast": {"state": "pass"},
      "glare": {"state": "pass"}, "occlusion": {"state": "pass"}, "perspective": {"state": "pass"},
      "ocr_integrity": {"state": "pass"}, "overall": {"state": "pass"}
    },
    "ocr": {
      "raw_string": "00A-17/9", "displayed_string": "00A-17/9",
      "whole_string_exact_probability_calibrated": 0.83,
      "format_warning": null, "checksum_warning": null, "silent_repair_applied": false
    },
    "versions": {"model": "model-id", "preprocess": "prep-id", "calibration": "cal-id"}
  },
  "policy_decision": {
    "decision_version": "1.0", "decision_id": "opaque", "policy_version": "policy-id",
    "threshold_version": "auto-exact-pet-v1", "auto_threshold_strictly_greater_than": 0.8,
    "status": "automatic_complete", "primary_action": "none", "all_required_gates_pass": true,
    "automatic_completion_eligible": true, "candidate_ready": true
  },
  "capture_complete": true,
  "business_complete": true,
  "serial_candidate": {"raw": "00A-17/9", "displayed": "00A-17/9", "editable": true},
  "completion": {"completion_id": "opaque", "completion_source": "automatic_ocr", "final_serial": "00A-17/9", "supersedes_completion_id": null},
  "recommendation": null,
  "failure": null
}
```

The JSON is illustrative; B06 must refine it into executable schemas without weakening the evidence/policy separation. `automatic_completion_eligible=true` is valid only when the calibrated estimate is strictly greater than the configured PET and every enumerated current-attempt gate passes with no unknown/blocker. Format/checksum match does not substitute for that rule.

### 8.4 Status invariants

Statuses: `guidance`, `waiting`, `ready_for_verification`, `automatic_complete`, `user_complete`, `ocr_uncertain`, `no_label`, `ambiguous_label`, `unsupported_subject`, `unsupported_input`, `manual_required`, `internal_error`.

- `business_complete=true` iff a linked immutable completion exists; it may be automatic or user-originated.
- `capture_complete=true` for candidate-ready or completed results, but never by itself proves business completion.
- Unknown/failing required evidence blocks automatic completion. One safe action, editable candidate, manual/unsupported outcome, or terminal failure follows.
- Directional actions use `referent=camera`; exactly one status and one primary action are emitted.
- Unsupported requires positive out-of-scope evidence; low-confidence/OOD ambiguity is unknown/manual.
- No silent OCR/format/checksum correction is valid in any state.

## 9. Vision inference pipeline

1. **Admission:** loopback/session/sequence/deadline checks and bounded JPEG/PNG byte, metadata, dimension, frame, decompression, memory, disk, and work budgets.
2. **Decode/canonicalize:** Pillow decode and EXIF transpose exactly once; preserve canonical transforms and source evidence.
3. **Deterministic OpenCV evidence:** ROI geometry/rectification plus raw crop, scale, center, blur, exposure, contrast, glare, occlusion, and perspective measurements.
4. **Localization/support:** run the selected bottle-data localizer and conditional support/OOD head; emit regions, containment, confidence, and unknown states. OpenCV alone is not presumed sufficient for open-world localization.
5. **Rectified OCR:** benchmark PP-OCRv6 first, Tesseract baseline, compact SVTR/CTC fallback; preserve verbatim strings, ambiguity, and warning-only format/checksum evidence.
6. **Validation:** assemble immutable, versioned `VisionEvidenceSnapshot`; reject invalid ranges, stale evidence, mismatched versions, or missing required gates.
7. **Policy:** deterministic, cost-aware ordering emits a separate `PolicyDecision`: automatic eligibility, editable candidate, exactly one camera action, manual/unsupported, or failure. Learned outputs never emit UI prose.
8. **Completion:** revalidate PET gates and provenance before automatic creation; otherwise expose candidate/optional user path or guidance. Corrections append supersession.
9. **Retention/telemetry:** retain approved source/evidence/completion linkage locally until manual pair deletion; emit only allowlisted content-free resource, latency, version, status, and aggregate evaluation fields.

### 9.1 Deterministic one-action safety order and vetoes

1. admission/privacy/resource/freshness failure;
2. positive unsupported subject/label finish or blocking OOD;
3. untrustworthy/multiple localization;
4. crop/overfill and safe search geometry;
5. motion/blur and scale/centering;
6. perspective;
7. glare/exposure/contrast;
8. actionable partial obstruction only with reliable safe direction; otherwise unknown/manual;
9. OCR integrity/ambiguity and warning-only format/checksum evidence;
10. automatic completion only if §3.4 passes; otherwise candidate readiness or highest-priority safe camera action.

Hard fail outranks soft fail. Unknown vetoes automatic completion and never invents direction. Fixed versioned costs/priority/ties produce deterministic replay. Attempt count alone never authorizes or terminates completion.

### 9.2 Camera-referent coordinate and wording rule

`image_correction` remains desired label movement in canonical image space. The adapter maps it exactly once to camera-referent wording and matching overlay. Initial approved examples are “Move the camera left.”, “Move the camera closer.”, “Tilt the camera to face the label more directly.”, and “Move the camera or light to reduce glare.” No object-referent wording may appear in this workflow without amendment. Physical tests must show that following a direction improves the next photo or safely changes/abstains.

### 9.3 Calibration, thresholds, and resources

The strict `>0.80` calibrated whole-string threshold is PET. It is not a claim that 80%+ of outputs are correct and not a production threshold. G2 must replace or reaffirm it using grouped calibration and locked physical test data, prespecified confidence intervals/subgroups, risk-coverage curves, false-ready/false-accept and coverage bounds, worsening/unsafe-action bounds, and no post-hoc tuning.

All other numeric crop/scale/blur/exposure/contrast/glare/occlusion/perspective, OOD, confidence, deadline, byte/dimension, CPU/GPU/RAM/VRAM/disk/thermal, and latency limits remain VT/PET. The RTX 5070 12 GB/32 GB RAM machine must be observed under bounded workloads; CPU remains unknown. Neither 99.0% nor 99.9% is an approved claim.

## 10. Error and failure handling

### 10.1 Failure envelope

`failure` contains stable `code`, category, `recoverable`, `retryable`, optional `retry_after_ms`, and safe message key. Personal-test categories: capability, not-found, ambiguous, quality, unsupported-input, unsupported-subject, unknown, timeout, local-resource, deletion, dependency, and internal.

Minimum codes:

- Capability/session: `PHOTO_PICKER_UNAVAILABLE`, `UPLOAD_UNAVAILABLE`, `SESSION_EXPIRED`, `SEQUENCE_CONFLICT`, `ATTEMPT_SUPERSEDED`, `IDEMPOTENCY_CONFLICT`.
- Input: `UNSUPPORTED_MEDIA_TYPE`, `ANIMATED_OR_MULTIFRAME_UNSUPPORTED`, `INVALID_OR_CORRUPT_IMAGE`, `IMAGE_DIMENSIONS_UNSUPPORTED`, `INPUT_TOO_LARGE`, `DECODE_BUDGET_EXCEEDED`.
- Evidence: `NO_LABEL_FOUND`, `MULTIPLE_LABELS_AMBIGUOUS`, `UNSUPPORTED_LABEL_OR_OBJECT`, `SUPPORT_UNKNOWN`, `QUALITY_INSUFFICIENT`, `SERIAL_UNREADABLE`, `OCR_AMBIGUOUS`, `FORMAT_POLICY_MISMATCH`.
- Local service/resource: `PROCESSING_TIMEOUT`, `DEPENDENCY_UNAVAILABLE`, `LOCAL_STORAGE_LIMIT`, `DELETION_PENDING`, `DELETION_FAILED`, `INTERNAL_PROCESSING_ERROR`. Authentication, authorization, remote rate-limit, and retry-budget-exhaustion codes are not personal-test contract outcomes.

### 10.2 Recovery rules

- Retry explicitly retryable local dependency failures and timeouts with bounded exponential backoff and jitter; do not treat image-quality guidance attempts as transport retries.
- Image-quality recovery requests a newly captured/uploaded still rather than retrying unchanged content.
- Do not automatically retry unchanged validation, unsupported, sequence-conflict, local-resource, deletion, or non-retryable subject outcomes.
- Explicitly distinguish OCR failure from label-not-found and dependency failure from image failure.
- Superseded upload attempts do not silently disappear.
- Retain eligible camera-origin photos according to G6; ordinary-upload bytes remain ephemeral.
- Cancellation propagates; work queues remain bounded; local overload or storage exhaustion returns an explicit resource outcome or supersession.
- No maximum guidance-attempt count applies. User exit and terminal unsupported/input/resource/dependency/internal-error outcomes remain available and never produce guessed success.

**AR G7:** this one-user personal test has no formal production SLO, availability, RTO/RPO, quota, or operational-support objective. Processing is best effort and every completed attempt records measured latency; exact safety deadlines and local resource guards remain provisional engineering limits, not product-quality claims.

---

## 11. Security and deployment approach

### 11.1 Approved security/privacy controls

- Treat submitted photos, crops, OCR text, serials, and linked analysis metadata as sensitive local application data.
- Bind the web/API service to loopback only and reject non-local host/origin access; no remote content transport, authentication, account, tenant, anonymous fallback, or public ingress is part of this version.
- Protect the application-private local database/media directory with OS user permissions. No backup or remote replica is created by the prototype.
- Browser delivery uses restrictive origin/CORS, frame, permissions, and content policies appropriate to localhost.
- File/photo-picker invocation is user initiated. The MVP does not acquire or retain a continuous camera track; any device camera UI opened by the picker remains browser/OS controlled.
- Validate decoded media, not filenames/headers. Resize valid large images for model input when appropriate, while bounding pre-decode bytes/dimensions/metadata, frame count, decompression work, CPU/GPU work, decoded RAM/VRAM, temporary disk, retained local storage, and thermal load under provisional numeric safety guards.
- Use unguessable expiring local session IDs and strict task/session/result/photo linkage; there is no authentication or tenant authorization layer.
- Dependencies/media parsers are scanned and kept current for personal testing; no formal operational patch/support SLA is claimed.
- Test malicious labels/URLs/QRs, forged overlays, parser fuzzing, marked replay, loopback binding/host-header rejection, decompression bombs, oversized metadata, silent-repair attempts, stale/forged automatic eligibility, deletion failures, and bounded CPU/GPU/RAM/VRAM/disk/thermal exhaustion.
- Retained camera-origin photos, complete verbatim serials, evidence snapshots, policy decisions, and completion/supersession records exist solely for local evaluation until manual pair deletion and never enter training, external review, export, backup, or remote telemetry without later approval.

### 11.2 Approved personal-test deployment

G5–G8 now define a localhost-only, one-user, English visual prototype with linked local retention and best-effort measured processing. Start the web/API and inference components on the same machine; bind listeners to loopback, keep persistence under an application-private local directory, and provide a user-visible retained-photo list with manual pair deletion.

There is no cloud provider, region, public/LAN accessibility, authentication, account, tenant, anonymous-remote quota, production SLO, availability/recovery commitment, operational-support obligation, or formal accessibility target. Any such capability requires a later versioned amendment and threat/privacy/operations review.


---

## 12. Testing and evaluation strategy

### 12.1 Required infrastructure and data discipline

- Consented grouped corpus spanning ordinary matte and glossy printed wraparound labels plus positive unsupported transparent, foil, severely wrinkled, and heavily damaged labels; partial obstruction includes actionable and unknown/manual examples.
- Split by physical bottle/item and capture session. Sequential/replayed variants never cross splits. Lock the representative physical test set before operating-point selection; replayed photos/screens are marked and excluded from representative physical guidance/liveness claims.
- Double-transcribed verbatim serial ground truth, localization/containment masks or boxes, per-defect/quality/support/OOD labels, physical guidance outcomes, source provenance, and adjudication records.
- Controlled physical rig, frozen evidence/policy fixtures, schema compatibility CI, browser/device fixtures, privacy canaries, and CPU/GPU/RAM/VRAM/disk/thermal/latency instrumentation.

### 12.2 Required evaluation layers

1. **Contracts:** positive/negative executable-schema tests for `VisionEvidenceSnapshot`, `PolicyDecision`, completion provenance, PET strictness, unknown vetoes, version mismatch, freshness, and supersession.
2. **Localization:** IoU/mAP diagnostics plus primary full-label/text-ROI containment, multiple/unsupported false-positive rates, OCR effect, guidance safety, latency, and peak resource use by subgroup.
3. **Quality/support/OOD:** per-defect precision/recall/F1 or AUROC/AUPRC, confusion matrices, justified severity MAE/RMSE/correlation, ECE/Brier, OOD/abstention, and policy-level ablations for every learned head.
4. **OCR/readiness:** strict verbatim whole-string exact correctness primary, CER diagnostic, calibration/risk-coverage, false-ready/false-accept with coverage, unchanged-versus-corrected rate, and format/checksum warning integrity. PP-OCRv6, Tesseract, and compact SVTR/CTC candidates remain unvalidated until target-data results and licensing checks pass.
5. **Policy/guidance:** exhaustive deterministic safety ordering/veto tests; expert agreement, cost-weighted action accuracy, unsafe/worsening action rate, abstention, next-photo metric improvement, completion rate, attempts-to-completion, and subgroup confidence intervals.
6. **System:** per-stage/end-to-end p50/p95 latency, peak RAM/VRAM, CPU/GPU utilization, disk growth, model size, preprocessing cost, thermal observations, deterministic replay, bounded failure, and no resource exhaustion.
7. **Completion:** strict `>0.80` boundary tests (exactly `0.80` fails), all-gates conjunction, no single-score/checksum/format/agreement/repair shortcut, visible automatic provenance, review/correction, immutable supersession, idempotency, and no duplicate completion.
8. **Security/privacy/browser:** parser fuzzing, loopback/host/origin rejection, picker/orientation, retained-pair deletion, ordinary cleanup, no shadow copy/content telemetry, and marked replay handling.

### 12.3 Locked reporting and claims

Preregister grouped splits, metrics, confidence methods, subgroup gates, resource procedures, operating points, and ablations. Report confidence intervals and full denominators. Do not tune on locked test results or make post-hoc success claims. Candidate aspirations such as ≥95% isolated-defect action, <0.5% worsening instructions, or 99.0%/99.9% exact-string performance remain unapproved. The `>0.80` PET permits only the stated personal experiment and must be replaced/reaffirmed by G2 with approved false-ready/coverage/worsening bounds.

## 13. Decision gates and approval status

| Gate | Status / owner | Approved decision or remaining decision | Recommendation / next evidence |
|---|---|---|---|
| G1 Product scope | **Approved (amended)** — Product Owner | Plastic water bottles with ordinary matte/glossy printed wraparound barcode-bearing labels. OCR preserves verbatim nearby serial text; barcode payload is not final value. Conditional automatic completion is allowed only by §3.4. | Build supported and positive unsupported/OOD corpus; keep one object/label/value per task. |
| G2 Quality study | **Protocol approved; operating point pending evidence** — Product Owner + ML/Quality Lead | Grouped physical-item/session splits, exact-string correctness, calibration/risk-coverage, false-ready/false-accept with coverage, worsening/unsafe guidance, confidence intervals/subgroups, locked test, and no post-hoc tuning. The `>0.80` value is PET only; 99.0%/99.9% claims remain unapproved. | Replace or reaffirm the PET and approve false-ready, coverage, worsening/unsafe-action and subgroup bounds from locked evidence. |
| G3 Iterative still-photo/completion policy | **Approved (amended again)** — Product Owner | A sufficient still may automatically complete only under strict `>0.80` calibrated whole-string PET plus every required gate; otherwise expose an editable candidate/optional user path or one camera-referent action. No two-frame rule; live guidance deferred. | Test the strict boundary, all vetoes, candidate path, automatic provenance/correction/supersession, and guided recovery. |
| G4 Platform matrix | **Approved scope; exact versions/limits provisional** — Product Owner | Browser-only web application; standards-compatible desktop/mobile browsers including iOS Safari; JPEG/JPG and PNG still-photo upload through file/photo pickers. No native apps and no initial-MVP continuous camera stream. | Client/QA owners must validate exact browser versions, picker/capture behavior, byte/dimension/decode limits, and minimum resources. |
| G5 Deployment | **Approved for personal test** — Product Owner | Same-machine localhost, one user, loopback-only. No authentication, account, tenant, anonymous remote access, public/LAN availability, production availability, or operational-support requirement. | Prove loopback binding and hostile host/origin rejection; reopen before any remote or multi-user use. |
| G6 Data governance | **Approved for personal evaluation** — Product Owner | Retain local screen-capture and smartphone-camera photos with linked vision-analysis metadata and model/policy/preprocess/calibration/schema versions until manual pair deletion. Ordinary file uploads are not automatically retained. No backup/export/review/training copy. | Test source classification, linkage, storage exhaustion, atomic/deletion-pending behavior, ordinary-upload cleanup, and no shadow copies. |
| G7 Service objectives | **Approved for personal test** — Product Owner | One user; best-effort processing with measured latency; no formal production SLO/availability/RTO/RPO/support target and no maximum guidance-attempt count. User exit and terminal unsupported/input/resource/dependency/internal-error outcomes remain. Model input size is not a product upload cap; provisional safety guards still apply. | Measure latency and calibrate exact pre-decode/decompression/local-storage guards without turning them into quality claims. |
| G8 Accessibility/localization | **Approved for visual personal test (wording amended)** — Product Owner | English camera-referent wording only, with matched overlays/arrows. Approved patterns cover camera direction, distance, tilt, and glare/light. Do not mix object referents. | Physically test wording/overlay correctness; reopen referent, accessibility, or localization choices before broader use. |

### 13.1 Consequential unresolved conflicts

1. **G2 operating point:** the study protocol is approved, but locked evidence must replace/reaffirm the `>0.80` PET and approve false-ready/false-accept, coverage, worsening/unsafe-action, confidence, and subgroup bounds. It remains a personal experiment setting, not a claim.
2. **Executable contracts and serial policy:** exact alphabet/layout/length rules remain data-dependent; B06 must refine schema v3.0 without allowing silent format/checksum repair.
3. **Model and licensing selection:** localization and OCR winners remain bake-off dependent. PP-OCRv6 weights/dependencies require exact licence verification. Ultralytics remains experiment-only and non-distributable absent a new licensing/distribution decision.
4. **Resource envelope:** CPU model and final CPU/GPU/RAM/VRAM/disk/thermal/latency limits remain unknown/measurement-dependent; workloads must still be bounded and observable.
5. **Future scope:** remote/multi-user deployment, production claims/SLO/support, accessibility/localization, backup/export/review/training reuse, liveness, and continuous camera guidance remain unapproved.

### 13.2 Missing source areas

The parents substantively specify product behavior, logical architecture, vision/policy, contracts, privacy/security controls, NFRs, and test obligations. They do **not** approve:

- frontend information architecture, visual design system, wireframes, or detailed component state designs;
- final frontend/backend framework details, persistence migrations, and queue/cache choices;
- final local database/media layout, crash-safe pair-deletion mechanism, local storage guard values, or final-serial deletion coupling details;
- production deployment provider, region, network topology, IaC, CI/CD platform, secrets product, or observability vendor, all outside current personal-test scope;
- representative dataset itself, winning localizer/OCR/conditional heads, exact third-party weight/dependency licences, calibrated production thresholds, final resource budgets, or completed locked evaluation evidence.

These omissions are explicit backlog work, not implicit approvals.

---

## 14. Recommended implementation phases and acceptance gates

### Phase 0 — Decisions, licences, and evidence foundation
**Work:** freeze v3 contracts/terminology, G2 preregistration, data/provenance/retention plan, licence register, resource instrumentation, and versioned PET configuration.  
**Gate:** no stale mandatory-confirmation invariant; exact PET qualification, Ultralytics non-distribution, camera referent, replay exclusions, and open G2/resource/licence decisions are traceable.

### Phase 1 — Contract and deterministic skeleton
**Work:** executable `VisionEvidenceSnapshot`, `PolicyDecision`, completion/supersession schemas; fake evidence; pure policy; session/idempotency; candidate/automatic/user UI states.  
**Gate:** strict `>0.80`, all-gate conjunction, unknown veto, version/freshness rejection, deterministic replay, completion provenance and correction supersession pass without model runtime.

### Phase 2 — Safe decode and OpenCV baseline
**Work:** Pillow bounded decode/EXIF-once canonicalization; OpenCV geometry, ROI/rectification, deterministic quality evidence and overlays; Tesseract/classical localization baseline.  
**Gate:** malformed/EXIF/resource/fuzz/coordinate fixtures pass and measured workloads remain bounded.

### Phase 3 — Grouped dataset and model bake-offs
**Work:** physical/replayed provenance, annotations, classical-vs-box-vs-mask localization, PP-OCRv6/Tesseract/SVTR OCR, permissive alternatives, exact licence review, conditional feature-head ablations.  
**Gate:** locked selection reports cover containment, unsupported FP, OCR/guidance outcome, calibration, latency/resources and subgroups; no generic-mAP-only or unvalidated-default claim.

### Phase 4 — One-action guidance and completion integration
**Work:** cost-aware abstaining policy, camera-only wording/overlays, candidate path, automatic PET path, user correction, immutable supersession, local linked retention/deletion.  
**Gate:** physical guidance and all completion/security/privacy invariants pass; replay is excluded from physical claims; no silent repair or duplicate completion.

### Phase 5 — Local hardening and G2 locked qualification
**Work:** loopback controls, resource/thermal guards, SBOM/licensing, privacy scans, locked grouped evaluation and preregistered ablations.  
**Gate:** Product Owner + ML/Quality Lead replace/reaffirm PET and approve false-ready/coverage/worsening/subgroup bounds; resource envelope and licences are acceptable for the personal prototype.

### Phase 6 — Personal-test decision
**Work:** personal test, automatic-result review/correction audit, retention/deletion audit, and future-scope review.  
**Gate:** localhost evidence is reported without production/distribution/liveness claims; broader use requires a new amendment.

## 15. Dependency-ordered implementation backlog

All items are planned; no application code is implemented by this amendment.

| ID | Backlog item | Depends on | Output / acceptance |
|---|---|---|---|
| B01 | Freeze A1–A15/D1–D7 decision, terminology, PET, replay and licence register | — | Versioned provenance and unresolved evidence decisions complete. |
| B02 | Define resource-observability/non-exhaustion plan for RTX 5070 12 GB/32 GB RAM and unknown CPU | B01 | Bounded CPU/GPU/RAM/VRAM/disk/thermal instrumentation and provisional budgets. |
| B03 | Refine executable schema v3.0 for evidence, decision, completion and supersession | B01 | Positive/negative fixtures cover versions, freshness, unknown veto, strict PET and no silent repair. |
| B04 | Implement pure deterministic cost-aware one-action policy against frozen snapshots | B03 | Ordering/veto/replay/candidate/automatic/manual tests pass. |
| B05 | Design UI state machine with camera-only wording and visible automatic provenance/review | B01, B03 | Candidate, guidance, automatic, user correction and supersession states reviewed. |
| B06 | Implement Pillow bounded JPEG/PNG decode and EXIF-once canonical contract | B02, B03 | Malformed/decompression/orientation/resource fixtures pass. |
| B07 | Implement OpenCV geometry, ROI/rectification, raw quality evidence and overlays | B06 | Coordinate round trip and raw measurement fixtures pass. |
| B08 | Assemble grouped physical/replayed corpus and adjudicated labels | B01 | Matte/glossy supported, positive unsupported/OOD, partial obstruction, verbatim serial and provenance coverage. |
| B09 | Run classical-vs-box-vs-mask localization bake-off with permissive alternatives | B02, B07, B08 | Containment, unsupported FP, OCR/guidance, latency/resource and subgroup report. |
| B10 | Run PP-OCRv6/Tesseract/compact-SVTR bake-off and exact licence review | B02, B07, B08 | Verbatim exactness, calibration/risk-coverage, resources and weight/dependency licences reported. |
| B11 | Ablate deterministic features vs conditional MobileNetV3/EfficientNet-Lite heads | B08–B10 | Learned heads retained only for policy-level outcome improvement. |
| B12 | Export selected models to ONNX and benchmark ORT CPU, optional OpenVINO/CUDA | B02, B09–B11 | Portable baseline, bounded resources, determinism/accuracy parity and versions reported. |
| B13 | Integrate upload/session API and browser picker with physical/replayed provenance | B03, B05–B07 | Sequence/idempotency/stale/cancel/retention tests pass. |
| B14 | Integrate policy, candidate, automatic/user completion, correction and supersession | B04, B05, B10–B13 | Strict PET/all-gates/provenance/idempotency/no-repair tests pass. |
| B15 | Integrate camera-referent overlays and physical one-action guidance | B04, B05, B07, B09, B11 | Expert/cost/worsening/next-photo physical evidence; replay excluded. |
| B16 | Implement linked local evidence/serial/completion retention and manual pair deletion | B03, B13, B14 | Full chain retained until deletion; no backup/export/training/shadow copy. |
| B17 | Harden loopback, dependencies/SBOM/licences, privacy and resource failure | B02, B06, B12–B16 | Security/privacy/storage/resource suites pass; Ultralytics absent from distributed artifact. |
| B18 | Execute preregistered grouped calibration and locked G2 study | B08–B17 | CI/subgroup/false-ready/coverage/worsening evidence with no post-hoc tuning. |
| B19 | Product Owner/ML Quality decision on PET and operating bounds | B18 | Versioned replace/reaffirm decision; no production claim implied. |
| B20 | Conduct personal test and future-scope review | B17–B19 | Local go/no-go, correction/deletion audit, residual risks and amendment needs. |

## 16. Source traceability

### 16.1 Source register

- `t_edafa288` — product framing: users, journeys, scope, recommendation-only boundary, explicit confirmation, failure taxonomy, non-goals, risks, release gate.
- `t_9db4b5de` — vision/guidance research: measurable quality evidence, coordinate/movement semantics, deterministic priority/conflicts, unsupported/unknown behavior, candidate thresholds, physical acceptance scenarios.
- `t_3bb8d5b2` — architecture/contract/NFRs: logical/trust boundaries, sessions/idempotency, schemas/status invariants, privacy/security, performance/resilience/accessibility/test infrastructure.
- `t_e3187d49` — synthesis: coherent PRD, machine-versus-business completion, conservative upload resolution, G1–G8 ownership, conditional planning approval.
- `t_95ff3002` — final root-reviewed PRD: incorporated dataset/evaluation traceability, preserved all eight gates, and explicitly surfaced the OCR target conflict.
- `t_88bc938f` — human-decision amendment: approved G1 plastic-water-bottle/barcode-bearing-label scope, approved the G2 study protocol while withholding thresholds, approved the earlier conservative G3 upload rule, and provisionally approved the G4 browser/camera/JPEG/PNG matrix.
- `t_f9f6d927` — workflow amendment: replaced the earlier G3 hard two-frame/single-upload restriction with iterative still-photo guidance; allows a sufficient first photo to be ready for explicit verification and defers continuous live-camera guidance.
- `t_9d8f876a` — personal-test amendment: approved G5 localhost/single-user/no-auth deployment, G6 camera-origin linked local retention/manual deletion, G7 best-effort measured processing without an attempt ceiling or product upload-size cap, and G8 English visual overlay/text guidance without a formal accessibility target.
- `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md` and task `t_f8132754` — evidence-backed hybrid pipeline, technology candidates, contracts, licensing risks, grouped evaluation/calibration/statistical framework, resource constraints, and dependency-ordered experiments.
- `t_fb42469a` — Product Owner normative amendment approving A1–A15/D1–D7, the provisional strict `>0.80` automatic-completion rule, camera referent, replay qualification, and supersession semantics.

### 16.2 Decision-to-source mapping

| Major decision | Source tasks/documents |
|---|---|
| Product/scope, browser still workflow, localhost/retention and G1–G8 history | `t_edafa288`, `t_e3187d49`, `t_95ff3002`, `t_88bc938f`, `t_f9f6d927`, `t_9d8f876a` |
| Hybrid Pillow/OpenCV/learned-localization/rectified-OCR pipeline and ONNX Runtime baseline | `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md`, `t_f8132754`, approved by `t_fb42469a` |
| Localization/OCR/quality-head bake-offs, permissive alternatives, Ultralytics restriction and licence checks | `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md`, `t_f8132754`, `t_fb42469a` |
| Separate `VisionEvidenceSnapshot`/`PolicyDecision`, deterministic one-action safety boundary | `t_9db4b5de`, `t_3bb8d5b2`, refined by research/task `t_f8132754`, approved by `t_fb42469a` |
| Optional automatic completion under strict `>0.80` PET; candidate/user fallback; no silent repair; supersession | `t_fb42469a`, superseding completion invariants in all prior source tasks |
| Grouped datasets, calibration/CIs, locked test/no post-hoc tuning, localization/quality/OOD/guidance/OCR/system/ablation metrics | G2 in `t_88bc938f`, expanded by research/task `t_f8132754`, approved by `t_fb42469a` |
| Full local serial/evidence retention until manual pair deletion; replay provenance; camera-only wording | `t_9d8f876a` as amended by `t_fb42469a` |
| Exact serial rules, final operating/resource bounds, model winners and distributable licences remain evidence/decision dependent | `t_f8132754`, `t_fb42469a` |

### 16.3 Resolved terminology

- `VisionEvidenceSnapshot` is immutable, versioned, schema-validated current-attempt measurement evidence; it is not a policy decision.
- `PolicyDecision` is the deterministic output selecting one action, candidate readiness, automatic eligibility, manual/unsupported, or failure; it does not contain model-authored UI prose.
- `capture_complete` means capture analysis supports a candidate/completion path. `business_complete` means an immutable linked completion exists.
- `serial_candidate.raw` and `.displayed` preserve recognizer output verbatim; format/checksum is warning evidence only.
- `completion_source=automatic_ocr` identifies PET-authorized completion; user sources remain distinct. Corrections create `supersedes_completion_id` chains.
- “Ready” no longer universally means mandatory confirmation. Explicit confirmation is optional when §3.4 automatic gates pass.
- `image_correction` is image-space evidence; initial UI wording is camera-referent only.
- `replayed` is test provenance, not liveness or representative physical-guidance evidence.
- Prior never-machine-accept/never-auto-submit/mandatory-confirmation wording is explicitly superseded by v1.4 only to the bounded §3.4 rule; the prohibition on guessed, silently repaired, uncalibrated, stale, or gate-incomplete automatic completion remains.

---

## 17. Implementation authority and change control

### 17.1 Amendment history

- **v1.4 — 2026-07-26 — task `t_fb42469a`:** Incorporated Product Owner approvals A1–A15/D1–D7 from `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md` / `t_f8132754`. Approved the bounded Pillow/OpenCV hybrid pipeline, localization/quality/OCR bake-offs, conditional learned heads, PP-OCRv6 benchmark qualification, ONNX Runtime CPU baseline, deterministic evidence/policy boundary, grouped locked evaluation framework, resource observability, replay qualification, camera-only wording, licensing restrictions, and full local evidence/completion supersession. Superseded universal never-machine-accept/mandatory-confirmation wording: automatic completion is permitted only when the calibrated whole-string estimate is strictly greater than the versioned PET `0.80` and every required current-attempt gate passes with no unknown/blocker; otherwise candidate/user/guidance paths apply. The PET is not a validated or production claim and remains subject to G2 replacement/reaffirmation.
- **v1.3 — 2026-07-23 — task `t_9d8f876a`:** Resolved G5–G8 for a one-user visual personal test. Fixed deployment to same-machine localhost with no authentication, accounts, tenancy, anonymous remote access, production availability, or support commitment. Approved local retention of screen-capture and smartphone-camera photos together with linked analysis and model/policy/preprocessing/calibration/schema versions until manual pair deletion; ordinary uploads remain ephemeral. Set best-effort processing with measured latency, no formal SLO and no guidance-attempt ceiling, while preserving terminal/user exits and provisional pre-decode/decompression/local-storage guards; model input size is not a product upload cap. Limited the prototype to English visual guidance with on-image overlays/arrows and physical direction/angle/distance/lighting text, no formal accessibility target, and still capture rather than continuous guidance. Advanced the additive illustrative result schema to v2.1. Preserved the then-current G2 locked-evidence and mandatory-confirmation invariants; those completion invariants are historically accurate but superseded by v1.4.
- **v1.2 — 2026-07-20 — task `t_f9f6d927`:** Amended G3 to an iterative still-photo workflow. The MVP starts with one JPEG/JPG or PNG upload; a sufficient photo, including the first, may set `capture_complete=true` only to present an editable `serial_candidate` for explicit verification. Insufficient evidence produces one concrete next-photo movement/angle/lighting/quality action and another upload invitation, repeated as needed. Removed the hard two-frame agreement requirement, deferred continuous live-camera guidance to a later phase, and advanced the illustrative API/result contract to v2 because completion semantics, session mode, sequencing, and endpoints changed. Preserved the then-current never-machine-accept/mandatory-confirmation invariant (superseded by v1.4), G2 evidence requirements, browser-only scope, and unresolved G5–G8.
- **v1.1 — 2026-07-20 — task `t_88bc938f`:** Incorporated confirmed G1–G4 decisions. Narrowed the object scope to plastic water bottles with ordinary printed wraparound barcode-bearing labels; defined the barcode as localization evidence rather than the final decoded value; made OCR a user-editable, then-never-machine-accepted `serial_candidate` (completion rule superseded by v1.4); approved the G2 locked-study protocol while withholding numeric claims; ratified the then-current single-upload `capture_complete=false` rule (superseded by v1.2); and established a browser-only desktop/mobile platform scope including iOS Safari and JPEG/PNG uploads. G5–G8 remain unresolved as stated.

Downstream work MAY implement the localhost personal-test phases under this v1.4 architecture and PET while G2, executable-schema refinement, final model/licence selection, and resource budgets remain open, provided provisional values are never represented as validated. Ultralytics MUST NOT be distributed. Production, remote/multi-user, support/SLO, accessibility/localization, backup/export/review/training reuse, liveness, continuous-camera, or broader licensing decisions require a later amendment. Production launch remains unapproved.

This amendment’s automatic-completion exception is narrow: only the versioned §3.4 conjunction may create `final_serial` automatically. No guessed, silently corrected, uncalibrated, stale, unsupported, unknown, or gate-incomplete serial may be auto-submitted.

Any amendment that changes scope, completion semantics, upload eligibility, data retention, deployment/auth model, status/schema meaning, movement convention, or quantitative release gate MUST:

1. name the approving owner and affected gate;
2. update the specification version and schema/policy version where applicable;
3. add migration/compatibility and test impacts;
4. update source traceability; and
5. preserve the bounded automatic-completion conjunction, no-silent-repair rule, provenance/supersession, and the invariant that no guessed or gate-incomplete serial is auto-submitted.

