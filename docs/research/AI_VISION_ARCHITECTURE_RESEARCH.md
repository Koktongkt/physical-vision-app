# AI vision architecture research for the physical-vision-app MVP

**Status:** architecture recommendation and experiment plan; not measured project performance and not production approval  
**Product authority:** `docs/IMPLEMENTATION_SPEC.md` v1.3 (2026-07-23)  
**Research cut-off and source access date:** 2026-07-25  
**Scope:** localhost-only, one-user, iterative still-photo assistance for printed serial/text near a barcode on an ordinary wraparound plastic-water-bottle label

## 1. Executive recommendation

Use a **hybrid, observable pipeline**, not an end-to-end model that directly invents camera instructions:

1. A bounded decoder applies EXIF orientation exactly once and produces one canonical RGB image plus a reversible transform.
2. OpenCV supplies deterministic geometry, ROI extraction/rectification, visualization, and raw quality measurements.
3. A lightweight learned localizer supplies bottle, label/barcode-landmark and printed-text-region evidence. Start with box detection; benchmark a small instance-segmentation model because masks are more informative for curved wraparound labels.
4. Run OCR only on a versioned, minimally enhanced rectified text ROI. The primary benchmark should be **PP-OCRv6 mobile detection/recognition components or a compact SVTR/CTC recognizer**, with Tesseract as a cheap independent baseline. Preserve raw text, leading zeros and separators. Never auto-correct a candidate into a valid-looking serial.
5. Keep most quality gates classical and interpretable. Add a small learned MobileNetV3/EfficientNet-Lite-class crop-quality/OOD model only where the locked data shows classical measurements are insufficient. Do not begin with one monolithic multi-task network.
6. Export frozen learned artifacts to ONNX and use **ONNX Runtime CPUExecutionProvider as the portability baseline**. Benchmark OpenVINO EP on Intel hardware and an optional Windows GPU path; do not make accelerator availability part of correctness.
7. A pure deterministic policy maps validated measurements to exactly one next-photo action. Models provide evidence, calibrated confidence and `unknown`; they do not produce UI prose. The policy prevents `closer` when crop risk exists, prioritizes glare over adding light, and abstains when action direction is unsupported.
8. OCR always returns an editable `serial_candidate`; `capture_complete=true` means only ready for explicit user verification.

### Concrete disposition

| Candidate | Decision | Reason |
|---|---|---|
| OpenCV | **Adopt** | Mature geometry/ROI/measurements/overlays; deterministic and inexpensive. It is not, alone, a robust open-world label/OCR solution. |
| Pillow safe header gate + EXIF transpose | **Adopt with OpenCV** | Restrict to JPEG/PNG, bound pixels/frames/metadata, apply orientation once, then hand canonical pixels to OpenCV. |
| YOLO-family nano detector/segmenter | **Conditionally adopt for the bake-off** | Strong deployment ergonomics and box/mask tasks, but project-specific evidence is absent and Ultralytics code/weights require AGPL-3.0 compliance or an enterprise license. Benchmark current nano segmentation and detection exports; freeze exact artifact. |
| RT-DETR/RT-DETRv2 | **Conditional permissive-license detector alternative** | Official Apache-2.0 implementation and NMS-free detection; likely more compute than nano CNN models and no native mask advantage. Benchmark only if YOLO licensing or accuracy is unacceptable. |
| EfficientDet / MobileNet-SSD | **Baseline, not target** | Useful permissive, CPU-friendly historical controls; older tooling and box-only output make them less attractive for curved-label masks. |
| Classical barcode/contour localization | **Baseline/landmark evidence only** | Very cheap and useful when barcode edges are clear, but brittle under curvature, glare, low contrast and partial visibility. Barcode payload is never used as final output. |
| MobileNet-family quality model | **Conditionally adopt after ablation** | Efficient shared features are plausible for support/OOD and ambiguous defects; classical heads remain easier to calibrate, diagnose and maintain with limited data. |
| PaddleOCR / compact SVTR path | **Preferred OCR benchmark** | Modern detection/recognition components, mobile models and Apache-2.0 repository; exact model-card/weight and dependency licenses still require an SBOM check. |
| Tesseract | **Adopt as baseline/fallback experiment** | Apache-2.0, CPU-local, controllable page segmentation and alphabet; likely weaker on curved/reflected scene text without excellent rectification. |
| EasyOCR | **Reject as target; optional baseline** | Easy integration, but PyTorch-heavy packaging and a less controlled model path add footprint without a demonstrated project advantage. |
| TrOCR | **Reject for MVP target** | Transformer encoder-decoder is unnecessarily large/complex for a short constrained serial unless the compact OCR bake-off proves otherwise. |
| PyTorch runtime in shipped MVP | **Reject as default** | Keep for training and reference inference; ONNX runtime packaging is smaller and isolates training code from deployment. |
| OpenVINO Model Server | **Reject for MVP** | A local in-process adapter is enough for one user; a model server adds process/network/version complexity without a throughput need. |

**Confidence:** high in the staged architecture and deterministic boundary; medium in the named model families; low in any model winner, threshold, memory figure or latency until the application corpus and target Windows hardware are measured.

## 2. Requirements and assumptions

### 2.1 Normative constraints preserved

- Input is exactly one completed JPEG/JPG or PNG still per attempt; no live stream or temporal-frame requirement.
- A sufficient first photo is allowed.
- The barcode-bearing area is localization evidence, not the business value.
- OCR reads nearby printed Latin letters, Arabic digits and common separators and returns only an editable candidate.
- No confidence score, checksum or model may confirm the serial; explicit user confirmation is mandatory.
- One insufficient attempt produces exactly one physical next-camera action plus overlay/text.
- The service is loopback-only, single-user and best effort on Windows; latency is measured, not an SLO.
- Camera-origin images retained under v1.3 remain linked to analysis/model/policy/preprocess/calibration versions until manual pair deletion; ordinary file uploads remain ephemeral.

### 2.2 Assumptions to validate

- The target serial is spatially near a visible one-dimensional barcode, but its side, line count and typography may vary.
- Ordinary wraparound curvature is supportable with a local planar or strip-wise approximation; severe wrinkles, transparent labels and extreme curvature remain unsupported.
- Ground truth can be independently double-transcribed/adjudicated. OCR output must never seed its own ground truth.
- The first test machine is x86-64 Windows. Exact CPU, RAM and optional GPU are unresolved, so no absolute latency or memory promise is made.
- License compatibility and commercial intent are unresolved. Personal local testing does not eliminate open-source obligations.

## 3. Candidate pipeline

```text
JPEG/PNG bytes
  -> admission limits + header/type/frame checks
  -> Pillow decode + exif_transpose exactly once
  -> canonical RGB image + source_to_canonical transform + content hash
  -> OpenCV color/geometry pyramid
  -> bottle/label/barcode/text candidates (learned + classical landmark evidence)
  -> select exactly zero/one/multiple supported candidate(s)
  -> label mask/box + text polygon -> conservative rectification
  -> raw quality measurements on full image, label ROI and text ROI
  -> OCR hypothesis set (raw strings, top-k, per-character evidence, format result)
  -> optional lightweight support/OOD and ambiguity heads
  -> schema/range validation + calibrated evidence
  -> frozen MeasurementSnapshot
  -> deterministic policy
       -> ready_for_verification + editable serial_candidate
       OR exactly one next-photo action
       OR unknown/unsupported/manual/error
  -> canonical overlay geometry + one camera-referent wording adapter
```

Do not discard the unenhanced canonical image. Enhancement outputs are derivative evidence and must identify their recipe. A model may never see orientation that differs from the coordinate system returned to the UI.

## 4. Component evidence review

### 4.1 Safe decode, orientation and OpenCV

**Verified capabilities.** Pillow identifies formats from content, permits the decoder allowlist to be restricted, lazily loads pixels, exposes multi-frame state, warns on decompression-bomb pixel counts, and provides `ImageOps.exif_transpose`. OpenCV provides memory decode, color conversion, filtering, morphology, thresholding, contours, connected components, homographies/warps, remapping and drawing. OpenCV also has barcode detection APIs. These are capabilities, not proof that defaults are safe for untrusted uploads.

**Recommended boundary.** Before full decode, cap request bytes and inspect only bounded metadata. Decode in a cancellable worker with deadline and memory limits. Restrict formats to JPEG/PNG, require one frame, reject impossible/zero dimensions, bound `width*height*channels`, ICC/EXIF sizes and decoded memory, and convert alpha onto a declared background. Treat Pillow's pixel warning as one guard, not the complete resource policy. Apply EXIF transpose once, strip orientation from the derivative, and record the 3x3 source-to-canonical transform. Do not then let OpenCV apply orientation again.

**Classical measurements that are adequate as raw evidence:**

| Dimension | Measurement candidates | Limits / learned fallback trigger |
|---|---|---|
| Crop/full visibility | signed mask/box-to-frame margins, edge contact, contour/mask truncation, predicted enlarged bounds | A detector trained on clipped labels may still score them highly; explicitly annotate edge visibility/completeness. |
| Scale | label area/short side; text-component or recognized-character height; stroke width | Pixel bands are camera/domain dependent; OCR confidence cannot clear an undersampling gate. |
| Sharpness | variance of Laplacian, Tenengrad/Sobel energy, high-frequency energy, edge-width on the text ROI | Texture, sharpening and noise can fool one score; use several features or a learned ambiguity head. |
| Directional/motion blur | gradient anisotropy, line-spread/cepstral evidence | A single still cannot reliably establish physical camera motion. Output `motion=unknown` unless directional-blur evidence was validated; `hold_steady` must be conservative. |
| Exposure/illumination | ROI luminance percentiles, clipped-low/high fractions, local contrast, shadow non-uniformity | Whole-frame mean is invalid when the serial ROI is dark. |
| Glare/specular | high value + low saturation/low texture mask, connected components, overlap with expected text strokes | White label substrate and bright ink are confounders; learned segmentation or physical data may be needed. |
| Occlusion | missing expected strokes/boundaries, segmentation residual, occluder head/mask | Crop, print damage and occlusion are ambiguous in one still; emit unknown rather than a directional claim. |
| Perspective | corner/edge convergence, quadrilateral opposite-side ratios, local character-scale gradient, homography condition | A curved label is not globally planar. Do not report a physical angle from a homography without calibration. |
| Geometry/ROI | contour proposals, minimum-area rectangle, polygon simplification, perspective warp, strip-wise remap | Rectification must not hallucinate hidden wraparound content. |
| Visualization | boxes, polygons, masks, heat/quality overlays and arrows in canonical coordinates | Rendering must round-trip through the stored transform and be tested on EXIF rotations. |

Color normalization should be conservative: canonical sRGB/RGB conversion and a fixed documented scaling policy. CLAHE, white balance, thresholding, denoising and sharpening may be tested as OCR variants but must never erase leading strokes or create completion evidence unless validated end to end. Keep the unmodified ROI and recipe/version.

### 4.2 Localization: boxes, masks and model families

The learned localizer should represent distinct concepts rather than one overloaded `label` class:

- bottle/support candidate;
- full label visible region (mask preferred, box minimum);
- barcode landmark region (payload ignored);
- printed serial/text region (polygon or quadrilateral);
- optional label-edge visibility and text-line orientation heads.

**Boxes versus masks.** A box is sufficient for coarse bottle/label selection and provides the fastest annotation baseline. On a cylindrical wraparound label, a rectangular box includes background and cannot directly express curved top/bottom edges, visible arc, local glare overlap or clipped-edge completeness. A mask improves ROI containment, overlap-based glare/occlusion features and conservative crop margins. It does not solve unseen backside content or produce a valid global planar homography. Use a mask to define the visible label and a separate text quadrilateral/centerline for local rectification; consider piecewise strip rectification only after physical evidence.

**Candidate assessment:**

- **Current Ultralytics nano detection/segmentation exports (YOLO11n/YOLO26n class).** Official documentation supports detect/segment and ONNX/OpenVINO export. These are the most practical first custom-model experiments. Generic COCO speed/mAP is non-transferable. Benchmark the exact current nano artifacts on bottle/session splits. Ultralytics' AGPL-3.0/enterprise dual-license is a material constraint for code and weights.
- **RT-DETR/RT-DETRv2.** The official Apache-2.0 repository implements NMS-free real-time detection and supports decoder-layer speed tuning. Published T4/COCO results do not predict Windows CPU or bottle performance. It is a credible box detector when permissive licensing matters, not an automatic segmentation solution.
- **EfficientDet-D0.** BiFPN/compound scaling make it a useful efficiency baseline, but ecosystem age, anchor tuning and box-only geometry reduce target appeal.
- **MobileNet-SSD.** Simple and historically mobile-friendly; use as a lower-bound deployment control, not the presumed winner for small text-adjacent landmarks.
- **Segmentation alternatives.** A MobileNetV3-LR-ASPP semantic model can be compact, but semantic masks need instance separation if more than one label appears. A small instance segmenter gives selection plus mask at higher annotation/inference cost.
- **Classical barcode/contour.** OpenCV barcode/gradient/morphological proposals are nearly free and interpretable. Use them as a landmark feature, proposal recall baseline or detector disagreement signal. Curvature, glare, quiet-zone loss, low resolution and nearby text prevent relying on them alone.

**Recommendation:** baseline with classical barcode/contour + OCR-text proposal; target bake-off with one current nano detector and one nano segmenter. Select by label/text containment, unsupported false positives, unsafe-policy outcomes and CPU p95—not generic mAP. If Ultralytics licensing is unacceptable, evaluate an Apache-2.0 RT-DETRv2 small detector plus a separate permissively licensed mask/geometry component.

### 4.3 Feature extraction and quality modeling

MobileNetV3 was hardware-aware designed for mobile CPUs and includes compact detection/segmentation adaptations. This makes a MobileNetV3-Small-class backbone a reasonable learned feature candidate, but its paper does not validate bottle-label defect prediction.

**Recommended hybrid heads:**

1. Exact deterministic geometry heads: crop margins, scale, center, mask/text containment, clipping, homography validity.
2. Classical photometric heads: luminance/clipping/local contrast and a candidate glare mask.
3. Classical sharpness heads plus learned `ocr_ambiguity` if necessary.
4. A small learned multi-label head only for `supported_subject`, `supported_label`, hard occlusion, glare ambiguity, focus/blur subtype and OOD embedding.
5. Severity regression only where controlled-rig continuous ground truth exists; otherwise use ordinal bins plus `not_determinable`.

**One shared multi-task model:** potentially reuses compute and features and can exploit correlated defects. It also couples release cadence, creates negative transfer, needs complete multi-task labels, obscures why a gate changed, and makes missing labels/loss weighting/calibration harder. A single crop can contain defects that require different spatial scales.

**Separate models/classical heads:** easier per-signal calibration, ablation and rollback; permits classical replacements and sparse labels. It may duplicate preprocessing/inference and miss shared features.

**Decision:** do not train a monolith first. Establish classical baselines and data coverage. Then compare (A) hybrid classical + one small learned support/ambiguity model against (B) one shared lightweight multi-task backbone with separate calibrated heads. Require the shared model to improve policy-level outcomes, not merely average AUROC. Keep every head independently versioned and able to return `unknown`.

OOD must combine positive support evidence and hard-negative evaluation; maximum softmax is only a baseline and neural scores can be overconfident. Evaluate energy/embedding-distance or Mahalanobis-style scores only after a frozen support taxonomy. Low support confidence means `unknown`; `unsupported` requires positive out-of-scope evidence.

### 4.4 OCR for a short serial near the barcode

**Geometry first.** Use label/barcode/text geometry to crop a narrow ROI, estimate baseline orientation, and rectify only the locally visible text patch. Run the recognizer on the raw rectified ROI and a small locked set of enhancement variants. A full general-purpose text detector is useful when the serial position varies; if annotation shows stable placement relative to the barcode, a dedicated text-region detector is simpler and safer.

**Candidates:**

- **PaddleOCR / PP-OCRv6 mobile components:** preferred first modern pipeline benchmark. It separates text detection and recognition, has compact models and an Apache-2.0 repository. Freeze downloaded weights and dictionaries; independently verify each model/weight/data/dependency license.
- **Tesseract 5:** strong clean-ROI CPU baseline. Use single-line/raw-line page segmentation, disable language dictionaries for serials, and apply an explicit character allowlist only if the product alphabet is complete. Its docs emphasize rescaling, binarization, deskew and crop borders. Confidence is not an exact-string probability.
- **EasyOCR:** Apache-2.0 code and convenient detection+recognition, but its PyTorch dependency/model download path is heavier. Keep only if the same locked bake-off shows a useful error-diversity or accuracy advantage.
- **CRNN/CTC:** compact, sequence-length flexible and suitable for a constrained alphabet. CTC can expose per-timestep alternatives but repeated-character and alignment errors need targeted data.
- **SVTR/SVTR-LCNet:** compact scene-text recognition candidate integrated with the Paddle ecosystem; benchmark if generic PP-OCR recognition systematically fails.
- **TrOCR:** transformer pretraining is technically capable but over-sized and language-model bias can be undesirable for non-word serials. Reject unless smaller methods fail and locked CPU data supports it.

**String integrity contract:** retain `raw_text`, `display_candidate`, exact Unicode/code-point sequence, whitespace/separators, top-k hypotheses when available, per-character alternatives/ranges, recognizer score, format/checksum outcome and engine/version. No dictionary correction, Unicode confusable replacement, character voting or checksum repair may silently create the displayed candidate. Normalization must be explicit, reversible for presentation, versioned and limited to approved rules. Test `0/O`, `1/I/l`, `2/Z`, `5/S`, `6/G`, `8/B`, repeated characters, leading zeros, spaces, `-`, `/`, `.`, broken print and checksum-valid near misses.

Calibrate against **whole-string correctness** using held-out calibration sessions. Candidate features may include recognizer sequence score, minimum character score, top-two margin, format result and measured ROI quality. Temperature/logistic/isotonic calibration are candidates, not guaranteed winners. Report risk-coverage and false-accept plus coverage. Because the candidate is always user-confirmed, `false_accept` here means a policy incorrectly declaring the candidate ready/low-risk—not autonomous business acceptance.

### 4.5 Runtime and Windows packaging

**Default:** train in PyTorch/Paddle as needed, export the chosen frozen components to ONNX, validate numerical parity, and ship an in-process ONNX Runtime adapter with CPU EP. ORT provides one API across CPU and accelerators and is MIT licensed. Use fixed batch 1 and preferably fixed input shapes per artifact. Record execution-provider ordering; provider fallback must be visible in diagnostics.

**Benchmark paths:**

- ORT CPU baseline on every target machine.
- OpenVINO EP on Intel CPU/iGPU/NPU; OpenVINO 2025 documents device-specific latency/throughput tuning and Windows packages and is Apache-2.0.
- Optional CUDA EP for NVIDIA development hardware.
- On heterogeneous Windows GPUs, investigate current WinML rather than building new dependence on DirectML EP: ORT docs state DirectML is in sustained engineering and new Windows work moved to WinML.

Do not ship PyTorch or Paddle training runtimes unless ONNX export correctness/operator support blocks the selected model. Do not add OpenVINO Model Server for a single local user.

**Release manifest:** model semantic name/version; SHA-256; source commit/release; training dataset and split manifest IDs; code/weight license; ONNX opset and IR; exporter/runtime versions; input shape/layout/color/range; output schema; calibration profile; thresholds; quantization recipe/calibration set; supported EPs; reference-output fixtures; SBOM. Record the actual EP, CPU/GPU identity, thread settings and warm/cold status per attempt.

**Memory/latency expectations:** nano CNNs and mobile OCR should be materially smaller than transformer-heavy alternatives, but graph, input size, OCR detector resolution, thread pools and EP copies dominate real footprint. No number is claimed. Quantization may reduce model memory/compute but ORT warns that gains depend on hardware and can regress performance; validate exact-string, localization and calibration parity on the locked set before release.

## 5. Deterministic policy boundary

### 5.1 Policy principles

- Inputs are a frozen validated measurement snapshot plus explicitly eligible bounded history; output is deterministic for identical versions/configuration.
- Learned outputs are measurements, not prose or actions.
- Unknown required evidence blocks readiness. Unknown alone does not justify a directional move.
- Positive unsupported evidence yields `unsupported`; low confidence yields `unknown`/search/manual, not unsupported.
- Generate all eligible action candidates, then select exactly one by fixed priority and tie-break.
- Every action must identify its evidence, threshold, uncertainty, predicted effect and vetoes.
- Do not advise an action predicted to create a hard fail. Use a conservative generic action or abstain if the effect cannot be signed.

### 5.2 Fixed priority and safety vetoes

1. Input/resource/dependency/system terminal state.
2. Trustworthy severe directional/motion-blur evidence -> `hold_steady`; suppress spatial arrows.
3. No trustworthy candidate: gross underexposure -> `improve_lighting`; adequate image with no label -> `search`; unknown evidence -> `wait`/`retry`/manual depending on policy.
4. Multiple materially tied labels -> `show_one_label`; positive unsupported -> `unsupported`.
5. Recover full visibility/crop: opposite or multiple edge violations -> farther; known single-edge correction only when extent and sign are reliable.
6. Center a fully visible label.
7. Correct scale: too large -> farther; too small -> closer only if predicted enlarged mask remains inside all safe margins.
8. Excessive projective risk -> `reduce_tilt` without claiming an uncalibrated physical angle.
9. Harmful glare -> `avoid_glare` before generic `improve_lighting`.
10. Confident obstruction -> `clear_obstruction`; stable defocus/blur -> the approved steady/focus/retry wording.
11. OCR ambiguity with all capture defects clear -> one conservative reacquisition action or ready for user editing under the approved risk/coverage operating point.
12. `ready_for_verification` only when every required current-attempt gate passes.

Hard fail outranks soft fail; known actionable evidence outranks unknown; then use severity normalized to its threshold, evidence confidence, predicted number of hard fails cleared, smaller safe action, and a fixed enum order. Never randomize.

**Worsening prevention:** simulate candidate movement against current mask/box and uncertainty envelope; veto `closer` if any plausible enlarged extent crosses a crop margin; veto translation when multiple edges or localization sign are uncertain; veto “add light” wording under specular glare; suppress geometry under unstable/directional blur; do not alternate opposite actions near thresholds—use enter/clear hysteresis or ask for a neutral retry.

### 5.3 Calibration and abstention

Calibrate each model head and OCR readiness separately on held-out sessions; do not average unrelated raw confidences. Report ECE and Brier where probabilities are meaningful, but reliability plots and risk-coverage are required because scalar ECE can hide bins/subgroups. Fit simple post-hoc methods first and freeze them before test. Measure calibration by bottle/label family/device/capture source/lighting subgroup.

An OOD advisory score is never proof of support. Define separate states: `supported`, `positive_unsupported`, `unknown`, and `measurement_unavailable`. All except supported block readiness. Repeated attempts do not turn unknown into support and there is no attempt-count ceiling; user exit/manual and resource/dependency terminal paths remain.

## 6. Two credible end-to-end architectures

### 6.1 Minimal evidence baseline

- Pillow allowlisted decode/orientation + OpenCV canonical image.
- OpenCV barcode detector, gradient/morphological barcode proposals, contours and OCR text boxes to propose one label/text ROI.
- OpenCV measurements for crop, scale, blur, exposure, contrast, glare and perspective.
- Tesseract 5 single-line/raw-line OCR on rectified ROI; optional PP-OCR mobile recognizer comparison.
- Pure deterministic policy; all weak/missing evidence abstains.
- Python in-process runtime; no custom learned model.

**Value:** fastest data/evaluation harness; interpretable failure collection; validates contracts and guidance mechanics. **Ceiling:** classical localization will fail on curved, borderless, reflective and cluttered labels and cannot robustly establish support/OOD.

### 6.2 Recommended target

- Same safe decode/canonical/OpenCV foundation.
- One lightweight custom detector plus label instance mask or keypoint/text-region head; barcode detector remains auxiliary evidence.
- Local text quadrilateral or curved centerline rectification, not whole-label forced planar dewarping.
- Hybrid quality vector: classical geometry/photometry/sharpness plus a small learned support/OOD/ambiguity model only where ablation proves value.
- PP-OCRv6 mobile or compact SVTR/CTC recognizer selected on strict exact-string risk-coverage; Tesseract retained as a benchmark/disagreement diagnostic if useful.
- ONNX Runtime CPU baseline, OpenVINO benchmark/optional acceleration, exact artifact/calibration/version manifest.
- Pure deterministic, cost-aware, abstaining guidance policy.

**Recommended detector bake-off:** current nano box detector vs current nano instance segmenter; if Ultralytics licensing is unacceptable, use the best permissive detector/segmenter combination proven by the same experiment. The architecture selects a task result, not a brand.

## 7. Decision matrix

Scores are architecture judgments (1 poor–5 strong), not measured project results.

| Approach | Curved ROI evidence | CPU/package | Data burden | Interpretability | License clarity | Recommendation |
|---|---:|---:|---:|---:|---:|---|
| Classical contour/barcode + Tesseract | 2 | 5 | 5 | 5 | 5 | Required baseline |
| Nano box detector + PP-OCR | 3 | 4 | 3 | 4 | 2–4 depending implementation | Strong intermediate |
| Nano instance mask + text polygon + PP-OCR/SVTR | 5 | 3 | 2 | 4 | 2–4 | Preferred target bake-off |
| RT-DETR box + separate mask + OCR | 4 | 2–3 | 2 | 3 | 4 | Conditional permissive alternative |
| One MobileNet multi-task network + OCR | 3 | 4 | 1–2 | 2 | 4 | Only after hybrid baseline/ablation |
| TrOCR-centric end-to-end system | 2 | 1–2 | 2 | 2 | model-specific | Reject for MVP |

## 8. Exact measurement/output contract

The inference adapter should emit JSON-compatible data equivalent to the following typed contract. `null` means unavailable; it must not be replaced by fabricated zero.

```text
VisionEvidenceSnapshot {
  snapshot_schema_version
  result_id, upload_sequence
  source {
    sha256, decoded_media_type, width_px, height_px, frame_count
    orientation_applied_degrees, source_to_canonical_3x3
    capture_method
  }
  preprocessing {
    policy_version, decoder_name_version, canonical_color_space
    model_resize_transform_3x3, enhancement_variant_ids[]
  }
  candidates[] {
    candidate_id, class: bottle|label|barcode_landmark|text_region
    support_state: supported|positive_unsupported|unknown
    box_norm, polygon_norm?, mask_rle_ref?
    score_raw?, score_calibrated?, calibration_profile_id?
    edge_visibility {top,right,bottom,left: visible|clipped|unknown}
  }
  selection {state: none|selected|ambiguous|unknown, selected_candidate_id?}
  geometry {
    label_box_norm?, label_polygon_norm?, text_polygon_norm?
    frame_margins_norm {top,right,bottom,left: value_or_null}
    center_offset_norm {dx,dy}?
    label_area_fraction?, text_height_px?, perspective_risk?, homography_condition?
    rectification_valid: true|false|unknown
  }
  quality {
    crop|scale|motion|blur|illumination|glare|occlusion|perspective|ocr_ambiguity|overall: {
      state: pass|soft_fail|hard_fail|unknown
      severity: [0,1]|null
      confidence: [0,1]|null
      reason_code
      affected_polygon_norm?
      measurements: {bounded named finite values or null}
      method_id, calibration_profile_id?
    }
  }
  ocr {
    roi_variant_id, engine_name_version, model_sha256
    hypotheses[] {raw_text, display_candidate, score_raw?, score_calibrated?, rank}
    uncertain_ranges[] {start,end, alternatives[]}
    exact_string_probability_calibrated?, top2_margin?
    format_id?, format_outcome: pass|fail|not_applicable|unknown
    normalization_policy_id
  }?
  ood {method_id, score?, operating_state: supported|positive_unsupported|unknown}
  versions {detector, quality_models[], ocr, runtime, execution_provider, calibration, policy}
  timings_ms {decode, canonicalize, localization, measurements, rectify, ocr, policy, end_to_end}
  diagnostics {warnings[], provider_fallback, deterministic_replay_key}
}
```

Policy output:

```text
PolicyDecision {
  status
  capture_complete
  serial: null
  serial_candidate? {display_value, raw_value, exact_string_evidence, uncertain_ranges[]}
  recommendation {
    action: move|hold_steady|improve_lighting|avoid_glare|clear_obstruction|
            reduce_tilt|search|wait|show_one_label|retry|manual|unsupported|none
    referent: camera|object|null
    direction?, distance_delta?, angle_hint?, lighting_hint?
    image_correction {dx,dy,scale_delta}?
    overlay_geometry_norm?
    priority, reason_code, confidence?
    evidence_keys[], vetoed_actions[]
  }
  decision_trace_hash
}
```

Validate finite ranges, region containment, status invariants and candidate character policy after inference. Hash exact artifacts/configuration plus normalized snapshot to support deterministic replay.

## 9. Dataset and annotation plan

### 9.1 Collection units and splits

The independent unit is a **physical bottle/label instance**, not an image. Give each physical bottle, printed-label instance, capture session, device and iterative task opaque group IDs. Every photo from one physical bottle and all derived crops/augmentations remain in one split; all photos from one session/task remain together. Where multiple bottles share an identical printed batch/template, group or stratify by print batch to measure template leakage.

Create development-train, development-validation, calibration/threshold, locked representative test, and prospective time/device-shift sets. Lock the representative test manifest and labels before final model/threshold choice; do no post-hoc threshold tuning. Keep a separate challenge/OOD set that is not silently pooled into in-distribution accuracy.

Collect in waves and use learning curves and subgroup confidence widths rather than declaring a fixed image count sufficient. Prespecify minimum independent bottles/sessions per critical subgroup; frames cannot inflate the independent denominator.

### 9.2 Required annotations

- Bottle/support class: supported plastic water bottle, positive unsupported object/label, no target, unknown/adjudication-needed.
- Instance polygons or masks for bottle and visible label; edge visibility/clipping flags; barcode landmark box/polygon; exact printed-text polygon and baseline/centerline.
- Independently verified verbatim serial plus format family; dual transcription and adjudication on locked test.
- Capture defect labels: crop edges, scale, center, blur subtype/severity, exposure/shadow, glare mask, occlusion mask/source, perspective/curvature, and `not_determinable`.
- Controlled-rig values where available: camera distance, yaw/pitch/roll, exposure/light placement and known obstruction—not inferred as truth from the image.
- Expert primary action, action cost, unsafe alternatives and acceptable equivalent actions under the frozen policy.
- Device/camera, capture source, session, label material/finish, print process/font, bottle shape/color, environment and provenance/rights.

Double-annotate locked-test localization, transcription, support/OOD and guidance labels. Report inter-annotator agreement; retain ambiguity instead of forcing consensus. Masks need boundary QA near glare, transparency and frame edges.

### 9.3 Coverage and hard negatives

Cover glossy/matte labels; common bottle diameters and curvature; label seams; water/condensation; clear/colored plastic; fonts, print batches, faint/damaged print; all EXIF rotations; smartphone/webcam sources; distance, off-center and all frame edges; yaw/pitch/roll; defocus/directional blur; under/overexposure; point-source glare; partial obstruction; clutter and multiple bottles.

Hard negatives/OOD include other bottle materials, cans/jars, barcode-only packages, labels with multiple barcodes/serial-like text, QR codes, shelf text, screens/photos of labels, unsupported languages/handwriting, transparent/foil labels, unrelated alphanumeric strings, checksum-valid near misses, adversarially similar stickers, malformed images and no-label scenes.

### 9.4 Synthetic data limits

Use synthetic serial rendering, perspective/curvature warps and controlled degradations for recognizer pretraining, class balancing and metamorphic tests. Preserve fonts/assets licenses and provenance. Synthetic blur/glare/noise does not reproduce ISP sharpening, demosaicing, autofocus, rolling shutter, curved specular reflection, condensation or real print defects; it cannot replace real-camera locked evaluation. Derived variants stay in their source bottle/session split. Cap synthetic proportion as an experiment variable and ablate it.

## 10. Metrics, provisional gates and statistical protocol

### 10.1 Localization

Report box and mask IoU, COCO-style mAP50–95 where sample size supports it, class-wise precision/recall at the frozen operating point, full-visible-label containment, text-ROI containment (fraction of ground-truth text pixels/characters inside proposed ROI), barcode-landmark recall, zero/one/multiple selection accuracy, false candidate rate on no-target/unsupported scenes, and positive unsupported false-positive rate. A high box IoU does not guarantee text containment.

### 10.2 Quality/features and support

Per defect report precision/recall/F1 and confusion matrices at frozen gates; AUROC plus AUPRC for ranking, especially imbalanced defects; ordinal/continuous severity MAE, RMSE and rank/Pearson correlation only when ground truth justifies regression; missing/unknown rate; ECE, reliability diagrams and Brier for probabilistic heads; OOD AUROC/AUPRC, false-positive rate at prespecified support recall, unknown detection and abstention/coverage. Report mask IoU for glare/occlusion when annotated.

### 10.3 Guidance

Top-1 action correctness is insufficient. Report:

- exact expert-policy agreement and agreement allowing prespecified equivalent actions;
- cost-weighted action accuracy/confusion matrix;
- **unsafe/worsening-action rate** with every event reviewed;
- abstention/unknown/manual rate;
- action-direction sign accuracy;
- next-photo change in the targeted metric and in overall hard-fail count;
- fraction that improves, is neutral, worsens or creates a new hard fail;
- task completion rate, explicit-confirmation rate, attempts-to-completion and time-to-completion;
- oscillation/opposite-action rate and repeated-identical-action behavior;
- subgroup intervals by device, capture source, label finish, bottle geometry, defect and action.

Physically execute each action in controlled and cooperative-user trials. Offline expert labels cannot prove that wording improves the next photo.

### 10.4 OCR

Primary: strict verbatim whole-string correctness of the displayed candidate, preserving leading zeros and separators under the approved normalization contract. Diagnostic: CER, per-character confusion matrix, edit type/location and uncertain-range recall. Selective: false-ready/false-accept rate **with coverage**, risk-coverage curve, calibration/reliability/Brier, false-reject/manual rate, format/checksum stratification, and unchanged-versus-user-corrected confirmation rate. Report subgroup confidence intervals. Neither 99.0% nor 99.9% is accepted without the locked evidence and owner approval.

### 10.5 System

Cold and warm per-stage and end-to-end p50/p95 (p99 exploratory), peak working-set RAM and optional VRAM, serialized model size, startup/model-load time, preprocessing/rectification cost, batch-1 throughput, EP fallback, timeout/failure/abstention counts and deterministic replay equivalence. Benchmark one request at a time plus bounded supersession/cancellation; multi-user throughput is irrelevant.

### 10.6 Provisional hypotheses, not approved claims

For early experiments only, investigate whether: localization/text containment can support a usable OCR coverage; unsafe/worsening guidance can be held below a stakeholder-approved bound; and exact-string risk can be reduced by selective abstention while retaining useful coverage. Do **not** put fixed percentages into a release gate until harm tolerance, denominator, subgroup policy and locked evidence are approved.

### 10.7 Statistical protocol and sample-size logic

- Preregister primary endpoints, operating thresholds, subgroup list, missing-data handling and multiplicity policy before unlocking test.
- Split and resample at physical-bottle/session clusters. Use cluster bootstrap intervals for correlated metrics and paired cluster bootstrap/permutation for architecture deltas.
- For binomial rates, use Wilson intervals for routine reporting and one-sided exact/Clopper–Pearson bounds for rare safety failures. Zero observed failures does not imply zero risk; choose the number of independent eligible decisions so the one-sided upper bound is below the approved harm rate.
- Determine sample size from the desired confidence-bound width and minimum detectable paired difference using pilot **between-bottle/session** variance; simulate clustered designs when intra-session correlation is material. Increase for prespecified subgroup gates and expected OCR coverage, because only accepted/ready cases enter the false-ready denominator.
- For severity regression, power the paired model comparison on bottle/session-level error differences rather than image count.
- Report effect sizes and intervals, not only p-values. If a subgroup is underpowered, label it unresolved rather than pool it post hoc.
- Run the locked test once for the chosen release candidate. Model, preprocessing, threshold or policy changes create a new version and require a new untouched test or explicitly labeled follow-up study.

## 11. Ablation plan

Run all candidates on identical group splits and exact runtime artifacts:

1. Classical barcode/contour/text proposal vs learned box detector.
2. Box detector vs mask segmenter, focusing on full-label/text containment and glare/crop policy errors.
3. Barcode landmark absent vs auxiliary feature/proposal.
4. Raw ROI vs planar rectification vs piecewise curved rectification.
5. No enhancement vs each locked enhancement; measure strict exact-string regressions and character creation/deletion.
6. Tesseract vs PP-OCR mobile vs compact SVTR/CTC; optional disagreement ensemble without character-wise synthesis.
7. Classical quality heads vs +learned support/ambiguity model vs shared multi-task model.
8. No OOD head vs support classifier vs embedding/energy-distance candidate.
9. Raw confidence vs each calibrator, with risk-coverage and subgroup drift.
10. FP32 vs selected FP16/INT8 artifact; require localization, exact-string, calibration and guidance non-inferiority.
11. ORT CPU vs OpenVINO EP vs optional GPU, measuring outputs as well as latency/RAM.
12. Stateless current-photo policy vs bounded eligible history; history must not create a two-photo requirement.
13. Policy safety vetoes/hysteresis on vs off, measuring worsening and oscillation.
14. Real-only training vs real+synthetic at prespecified ratios.

A component survives only if it materially improves a prespecified end-to-end outcome or reduces resource cost without violating safety/calibration—not because its standalone benchmark improves.

## 12. CPU/GPU benchmark plan

1. Define at least a low/typical/high available Windows CPU tier and record model, cores, instruction set, RAM, OS/build and power mode. Add Intel iGPU/NPU and one NVIDIA/heterogeneous GPU only if actually available.
2. Freeze 100% local representative JPEG/PNG inputs by resolution, EXIF orientation, source and defect; include malformed/large safety fixtures separately.
3. Benchmark cold process/model load, first inference, then warm randomized runs. Use batch 1, one local user, fixed thread/affinity settings, and enough repetitions for stable percentiles.
4. Measure admission/decode/orientation, localization, feature heads, rectification, OCR, policy and full response separately; record peak process RAM/VRAM and model bytes.
5. Compare ORT CPU first; then OpenVINO EP on Intel; optional CUDA/WinML path. Record provider fallback and unsupported operators. Verify outputs against reference tolerances before timing.
6. Benchmark FP32 first; then FP16/INT8 only with representative quantization data. Re-run the locked inference suite and calibration; do not assume faster or equivalent.
7. Exercise cancellation, supersession, repeated attempts, storage pressure and timeout. Best effort does not permit unbounded work.
8. Publish raw machine-readable results, versions, warmup policy, sample counts and confidence intervals. External COCO/T4 figures remain non-transferable.

## 13. Risks, failure modes, licensing and unresolved decisions

### 13.1 Technical and product risks

- Ordinary cylindrical curvature violates one global homography; aggressive dewarping can manufacture misleading glyphs.
- Detector confidence does not prove full label visibility; clipped-object training can teach false completeness.
- A single still cannot reliably distinguish physical motion from defocus or identify the correct physical movement under ambiguous geometry.
- Simple sharpness scores can reward noise/oversharpening; simple glare masks confuse white substrate/ink.
- OCR language priors and checksums can turn uncertain evidence into plausible wrong serials. They must never repair the candidate silently.
- Repeated systematic OCR errors can survive multiple photos; history is supporting evidence, not truth.
- OOD detection is incomplete by nature. Unknown must remain first-class.
- Calibration shifts with device/ISP, print supplier, model export, quantization and preprocessing.
- Small generic benchmark gains may vanish on curved reflective bottle labels. No external number is a project claim.
- Direction/arrow inversion can occur through EXIF/display transforms or camera-vs-object referents; physical end-to-end tests are mandatory.
- Stored camera-origin photos and OCR alternatives are sensitive local data and must obey linked deletion and content-free telemetry rules.

### 13.2 Licensing

- OpenCV is Apache-2.0 (modern 4.x); Pillow uses HPND-style licensing; verify packaged codecs.
- ONNX Runtime is MIT. OpenVINO, PaddleOCR, Tesseract, EasyOCR and official RT-DETR repositories are Apache-2.0 at the cited sources.
- Ultralytics uses AGPL-3.0 or enterprise licensing. The project must choose a compliant path before embedding/distributing code or weights; do not assume local-only use nullifies obligations.
- Repository code license is not automatically the license of pretrained weights, training datasets, fonts, dictionaries, sample images or transitive binaries. Preserve model cards and download hashes, create an SBOM/notices bundle, and require explicit provenance for every artifact.
- COCO or other generic datasets may be useful only under their own terms and do not replace consent/rights for manufacturer labels and serials.
- This report is engineering guidance, not legal advice.

### 13.3 Unresolved decisions

1. Exact serial layouts, alphabets, lengths and legitimate normalization/format/checksum rules.
2. Whether Ultralytics AGPL compliance is acceptable or a permissive implementation is required.
3. Exact CPU/RAM/GPU target matrix and package-size tolerance.
4. Ground-truth acquisition rights and whether real serials may be retained in evaluation metadata.
5. Minimum useful OCR readiness coverage and maximum tolerated false-ready/worsening rates.
6. Which label finishes/curvature extremes remain supported after data collection.
7. Whether a screen/photo replay of a real label is acceptable; static RGB quality is not liveness.
8. Valid user action equivalences and camera/object referent wording.
9. Final decoder/resource limits and locked test sample size after pilot variance/coverage are known.

## 14. Dependency-ordered implementation experiments for cody

### Experiment 1 — safe canonicalization and classical baseline

Implement an **experiment-only** harness, not production endpoints: allowlisted JPEG/PNG admission; Pillow bounded decode and one EXIF transpose; canonical transform record; OpenCV ROI/quality measurements, barcode/contour proposals and overlays; Tesseract single-line/raw-line OCR. Build fixtures for all EXIF rotations, frame count, decompression guard, transform round-trip, leading zeros/separators and deterministic JSON snapshots. Output latency/RAM and failure corpus.

**Exit evidence:** canonical pixels/coordinates are reproducible; malformed inputs are bounded; overlay round-trip is correct; baseline localization/OCR/quality metrics run on a small adjudicated corpus.

### Experiment 2 — annotation schema and localizer bake-off

Freeze the bottle/session grouped manifest and annotation guide. Annotate bottle, visible label mask/edges, barcode landmark and text polygon plus support/OOD hard negatives. Compare classical proposals, one current nano box detector and one current nano segmenter (or permissive equivalents if licensing requires). Export to ONNX and report text containment, full-label completeness, subgroup intervals, ORT CPU p50/p95/RAM and license manifest.

**Exit evidence:** one candidate selected by end-to-end containment/false-positive/resource outcomes; no generic benchmark decides the winner.

### Experiment 3 — OCR/rectification and selective calibration bake-off

Using frozen text polygons and exact double-transcribed strings, compare raw crop, local homography and any piecewise curved rectification across Tesseract, PP-OCR mobile and compact SVTR/CTC candidates. Preserve exact strings and top alternatives. Fit calibration on a separate grouped calibration split; report exact-string correctness, CER/confusions, false-ready + coverage, risk-coverage, ECE/Brier, subgroup intervals, ORT/OpenVINO CPU timing and quantization parity.

**Exit evidence:** selected OCR artifact/recipe and provisional operating range ready for policy simulation, still requiring locked-test owner approval.

### Later experiments

4. Classical quality vs lightweight learned support/ambiguity heads on controlled physical defects.  
5. Frozen deterministic policy simulator with exhaustive conflicts/vetoes/unknown states.  
6. Controlled physical next-photo trial measuring metric improvement and worsening.  
7. Full locked representative evaluation and owner decision on operating points.

## 15. Evidence classification

**Verified from primary sources:** cited framework capabilities, model architecture descriptions, publication dates, repository-level licenses, calibration/selective-classification findings on their reported datasets, and runtime provider/quantization documentation.

**Reasonable engineering interpretations:** masks are more useful than boxes for this curved-label ROI; a hybrid quality design is safer to maintain; ORT CPU is the best portability baseline; PP-OCR mobile/compact SVTR are stronger target candidates than TrOCR for this short CPU-local task.

**Preliminary/unreplicated for this project:** every model ranking, expected latency/memory, defect separability, OCR accuracy, calibration method and synthetic-data benefit. No physical-vision-app dataset was available for measurement in this research task.

**Not claimed:** any 99.0%/99.9% OCR result, any maximum angle/distance, any universal confidence/blur/glare threshold, or commercial license clearance.

## 16. Source bibliography

All sources accessed 2026-07-25. Version dates below are publication/release/document-family dates visible in the source; mutable documentation/repositories must be pinned during implementation.

1. Physical Vision App, `docs/IMPLEMENTATION_SPEC.md` v1.3, 2026-07-23 (local normative source).
2. OpenCV, image codecs / orientation behavior, 4.x docs: https://docs.opencv.org/4.x/d4/da8/group__imgcodecs.html
3. OpenCV, geometric image transforms, 4.x docs: https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html
4. OpenCV, structural analysis/contours, 4.x docs: https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html
5. OpenCV, `BarcodeDetector`, 4.x docs: https://docs.opencv.org/4.x/dc/df7/classcv_1_1barcode_1_1BarcodeDetector.html
6. OpenCV license (Apache-2.0 for 4.5.0+): https://opencv.org/license/
7. Pillow, `Image.open`, format restriction and decompression-bomb guard, stable docs: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.open
8. Pillow, `ImageOps.exif_transpose`, stable docs: https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose
9. Pillow image formats/content identification, stable docs: https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html
10. Ultralytics, YOLO11 (released 2024-09-10), official docs: https://docs.ultralytics.com/models/yolo11/
11. Ultralytics, YOLO26 current model family, official docs: https://docs.ultralytics.com/models/yolo26/
12. Ultralytics, *YOLO26: Unified Real-Time End-to-End Vision Models*, submitted 2026-06: https://arxiv.org/abs/2606.03748
13. Ultralytics, segmentation task and model/export information: https://docs.ultralytics.com/tasks/segment/
14. Ultralytics, ONNX integration/export: https://docs.ultralytics.com/integrations/onnx/
15. Ultralytics, OpenVINO integration/export: https://docs.ultralytics.com/integrations/openvino/
16. Ultralytics licensing (AGPL-3.0/enterprise), official: https://www.ultralytics.com/license
17. Zhao et al., *DETRs Beat YOLOs on Real-time Object Detection*, submitted 2023, revised 2024: https://arxiv.org/abs/2304.08069
18. Official RT-DETR/RT-DETRv2 repository (Apache-2.0): https://github.com/lyuwenyu/RT-DETR
19. Tan, Pang & Le, *EfficientDet*, submitted 2019 / CVPR 2020: https://arxiv.org/abs/1911.09070
20. Liu et al., *SSD: Single Shot MultiBox Detector*, 2015/2016: https://arxiv.org/abs/1512.02325
21. Howard et al., *Searching for MobileNetV3*, ICCV 2019: https://arxiv.org/abs/1905.02244
22. PaddleOCR official repository and Apache-2.0 code license: https://github.com/PaddlePaddle/PaddleOCR
23. PaddleOCR v3.7.0 release (2026) and release notes: https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.7.0
24. PaddleOCR current text-recognition model documentation, including PP-OCRv6 options: https://www.paddleocr.ai/latest/en/version3.x/module_usage/text_recognition.html
25. PP-OCRv6 tiny ONNX model card (Apache-2.0 metadata; pin commit/hash): https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_rec_onnx
26. Tesseract official repository (Apache-2.0): https://github.com/tesseract-ocr/tesseract
27. Tesseract 5.5.3 release (2026): https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3
28. Tesseract, improving OCR quality/page segmentation/patterns/whitelist: https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html
29. EasyOCR official repository, v1.7.2 dated 2024-09-24, Apache-2.0: https://github.com/JaidedAI/EasyOCR
30. Shi, Bai & Yao, *CRNN for image-based sequence recognition*, 2015: https://arxiv.org/abs/1507.05717
31. Du et al., *SVTR: Scene Text Recognition with a Single Visual Model*, 2022: https://arxiv.org/abs/2205.00159
32. Li et al., *TrOCR: Transformer-based OCR*, 2021: https://arxiv.org/abs/2109.10282
33. Microsoft, ONNX Runtime execution providers, mutable official docs: https://onnxruntime.ai/docs/execution-providers/
34. Microsoft, ORT OpenVINO EP: https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html
35. Microsoft, ORT DirectML sustained-engineering notice / WinML direction: https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html
36. Microsoft, ORT quantization and hardware-dependent performance caveats: https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html
37. Microsoft, ONNX Runtime repository and MIT license: https://github.com/microsoft/onnxruntime
38. Intel, OpenVINO 2025 inference optimization: https://docs.openvino.ai/2025/openvino-workflow/running-inference/optimize-inference.html
39. Intel, OpenVINO 2025 Windows installation/versioned archive: https://docs.openvino.ai/2025/get-started/install-openvino/install-openvino-archive-windows.html
40. Intel, OpenVINO repository and Apache-2.0 license: https://github.com/openvinotoolkit/openvino
41. Guo et al., *On Calibration of Modern Neural Networks*, ICML 2017: https://proceedings.mlr.press/v70/guo17a.html
42. Geifman & El-Yaniv, *Selective Classification for Deep Neural Networks*, 2017: https://arxiv.org/abs/1705.08500
43. Hendrycks & Gimpel, OOD/misclassification softmax baseline, ICLR 2017 / rev. 2018: https://arxiv.org/abs/1610.02136
44. Lee et al., Mahalanobis OOD framework, NeurIPS 2018: https://arxiv.org/abs/1807.03888
45. COCO evaluation/task definitions: https://cocodataset.org/#detection-eval
46. scikit-learn, grouped cross-validation guidance, stable docs: https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data
47. NIST/SEMATECH, Wilson and exact binomial confidence intervals: https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm
48. statsmodels, binomial proportion confidence interval methods: https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_confint.html
49. SciPy, bootstrap confidence intervals: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html

### Bibliography cautions

- arXiv benchmark values are evidence only for the paper's data/hardware/protocol and are non-transferable to bottle labels.
- Mutable docs and GitHub default branches must be replaced in the implementation SBOM by exact releases, commits, downloaded-weight hashes and license files.
- A repository badge/license was treated only as repository-level evidence, not automatic clearance of every model weight or dataset.
