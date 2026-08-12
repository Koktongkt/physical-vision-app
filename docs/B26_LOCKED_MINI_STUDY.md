# B26 locked mini-study workflow

Status: `protocol_only` / `live_pending` / `public_supplement_omitted`

Protocol: `B26-live-v1.0`

Normative implementation base: `af0541ea8f69bcf665aac9135017b6600906fb50`

This workflow implements the bounded evidence harness required by `docs/IMPLEMENTATION_SPEC.md` §§12, 13, and 15 B26. It does not contain live observations and does not claim validation, production readiness, liveness, broad device support, payload accuracy, or approval of an operating point.

## Harness contracts

`physical_vision_study` validates three versioned live documents:

- `b26-study-manifest-v1`: exact versions, frozen configuration, capture paths, preregistered reasons, and ordered session plan;
- `b26-study-manifest-lock-v1`: canonical SHA-256 fingerprint plus UTC lock time and pseudonymous signer; and
- `b26-study-report-v2`: deterministic content-free aggregates with explicit status, claim
  boundaries, and sufficient content-free metric evidence counters.

It also validates `b26-public-supplement-report-v1`. The current public decision is an omitted report because no audited source has verified artifact-specific image rights plus transitive provenance.

Canonical JSON is ASCII UTF-8, sorted by key, compact separators, finite JSON numbers only, and one trailing LF. The manifest fingerprint is SHA-256 over exactly those canonical manifest bytes. A changed locked manifest, mismatched observation fingerprint, public/live track mixture, duplicate observation identity, unplanned reason, unaccounted planned session, or observation beyond the six-sample bound fails closed. An analyzed session uses contiguous indices from 1, `session_end: null` on intermediate rows, and exactly one non-null terminal row last; `max_observations` is valid only on row 6. Missing or excluded sessions use one accounting row at index 1.

The observation action contract is exactly the non-`NONE` product `BarcodeGuidanceAction` enum: `camera_closer`, `camera_farther`, `camera_left`, `camera_right`, `camera_up`, `camera_down`, `camera_steady`, and `reduce_glare`. Each system decision has at most one action, so a displayed guidance decision has exactly one; absence remains measurable rather than being rejected based on the human label. Fictional `move_*` and `tilt` values fail closed.

Observation labels and decisions are coherent, not merely shape-valid. Human `target_support` is the
exact `supported_1d` / `hard_negative` / `unsupported_2d` enum and must agree with human count;
human ready cannot coexist with guidance eligibility. System readiness and guidance require count
`one` and successful localization; non-`one` decisions require null localization and no readiness or
guidance. Localization is exact boolean/null. Latency is finite and nonnegative with booleans
rejected. An unsafe row is always included in `unsafe_or_worsening`, including when its transition is
`not_evaluable`.

The live manifest requires these exact-value groups before lock:

- clean repository commit and app build;
- report, OpenCV, detector recipe, ready policy, guidance policy, Python, browser, and OS versions;
- payload-decode-off and learned-detector-off assertions;
- frozen ready thresholds, measurement tolerances, resource limits, seed `260826`, 10,000 bootstrap replicates, and six observations per session;
- pseudonymous operator/labeler IDs;
- exactly two capture paths with explicit `desktop_webcam` and `phone_camera` roles, bounded
  pseudonymous device/camera tokens, positive two-integer resolution, and bounded sample rate; and
- exactly 24 ordered sessions: eight distinct supported physical 1D items once per path plus the
  four coherent controls per path (`ordinary_zero_code`, `stripe_text_hard_negative`,
  `two_visible_supported_1d`, and `qr_only`). `control_kind` makes this partition explicit.

The allowed-reason list is the exact bounded protocol enum (maximum six entries), and subgroup
labels are safe bounded tokens drawn from frozen enums. Lock metadata uses a valid-calendar strict
RFC3339 UTC timestamp with literal `Z` and a bounded content-free pseudonymous signer.

IDs must be non-content identifiers. Validators reject path/URL/image-byte/payload-like fields, 12–14 digit payload-like values, Host/Origin material, data-image values, and exception-like text with content-free errors.

## Commands

Run commands from the repository root with the pinned Python environment:

```text
.venv/Scripts/python.exe scripts/run_b26_study.py validate --kind manifest --input <manifest.json>
.venv/Scripts/python.exe scripts/run_b26_study.py lock-manifest --input <manifest.json> --locked-at <UTC-Z> --signer-id <pseudonym> --output <locked.json>
.venv/Scripts/python.exe scripts/run_b26_study.py validate --kind lock --input <locked.json>
.venv/Scripts/python.exe scripts/run_b26_study.py aggregate-live --locked-manifest <locked.json> --observations <observations.json> --output <report.json>
.venv/Scripts/python.exe scripts/run_b26_study.py validate --kind report --input <report.json>
.venv/Scripts/python.exe scripts/run_b26_study.py validate --kind public-report --input <public-report.json>
.venv/Scripts/python.exe scripts/run_b26_study.py public-supplement --decision omitted --output docs/B26_PUBLIC_SUPPLEMENT_REPORT.json
```

Store real manifest, observations, deviation log, and any retained media only in an approved private location outside Git. Do not put a private path in any harness document. The tracked public report and eventual reviewed live report must remain content-free.

## Human-operated live gate

Expected duration: 60–90 minutes. A human with the real desktop webcam and phone path must perform this gate; synthetic, replayed, or public images cannot substitute.

1. In a private working directory outside Git, populate all exact version/configuration fields and all 24 rows: eight single-1D items on each of two capture paths plus four controls per path (ordinary zero-code, stripe/text hard negative, two visible 1D codes, and QR-only). Keep repeated observations under the same physical-item/session group.
2. Confirm two capture paths and eight distinct physical 1D items. If a path is unavailable, keep its preregistered rows and record the frozen missing reason; do not replace rows after outcomes are visible.
3. Confirm an empty private observation location, payload decode off, no learned detector, no media/log/telemetry shadow copies, and the delete-after-adjudication-or-seven-days lifecycle. Record only a non-sensitive location ID.
4. Validate and lock the manifest before viewing the first locked outcome. Record the printed fingerprint. Do not change thresholds, recipe, policy, labels, order, groups, metrics, exclusions, or sample size afterward. A substantive change requires `B26-live-v2`.
5. Follow rows in locked order. Commit the human count/support/ready reference before revealing the system decision. For a displayed action, follow that one action once and label only the next bounded observation. Never choose among multiple actions or keep trying until success.
6. End each session at ready plus human shutter, user exit, terminal outcome, or six observations. Stop the whole run at 24 attempted sessions, 90 minutes, a privacy/safety concern, repeated camera/app failure preventing the next row, or a frozen resource guard.
7. Give every planned session analyzed, missing, or excluded accounting using only preregistered reasons. Return only the locked fingerprint, canonical content-free observation JSON, deviation log, and validated aggregate report. Never return raw images, payloads, private paths, Host/Origin values, or exception text.
8. Run aggregation twice from the same locked inputs and byte-compare the outputs. Production
   aggregation always uses seed `260826` and 10,000 bootstrap replicates. A run is
   `completed_locked_run` only with all 24 sessions attempted/analyzed, no missing/excluded rows,
   and complete path/item/control coverage. Coherent all-accounted zero-evidence runs remain
   `live_pending`; partial analyzed evidence fails closed.

## Report interpretation

The aggregator reports planned/attempted/missing/excluded sessions, analyzed observations, physical-item clusters, count confusion, count/localization/ready/guidance proportions, cluster-bootstrap intervals, transition categories, latency nearest-rank summaries, separate missing and exclusion reason counts, and capture-path subgroup counts. Sequential observations are nested under physical-item groups; the report does not describe adjacent frames as independent samples. Report v2 adds compact, content-free `metric_evidence` counters sufficient to bind every metric numerator and denominator independently of the supplied metric object. The versioned report validator fails closed on every exact nested shape/type/range and on denominator, metric/evidence, confidence, confusion, latency, transition, subgroup, diagnostic, attempt, outcome, item, reason-total, group, status/evidence, and cross-field inconsistency.

The public report remains separately titled `offline_public_supplement`, has zero denominators, and makes every live claim boundary false. Live and public denominators are never pooled.

A future ONNX study is not approved here. It may be proposed only after a genuine completed locked run shows a reproducible live miss pattern in the same planned subgroup on at least two distinct physical items, with valid labels and frozen classical configuration. Any such work needs a later scoped stage/ADR and provenance/licence review.
