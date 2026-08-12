# B26 locked mini-study workflow

Status: `protocol_only` / `live_pending` / `public_supplement_omitted`

Protocol: `B26-live-v1.0`

Normative implementation base: `af0541ea8f69bcf665aac9135017b6600906fb50`

This workflow implements the bounded evidence harness required by `docs/IMPLEMENTATION_SPEC.md` §§12, 13, and 15 B26. It does not contain live observations and does not claim validation, production readiness, liveness, broad device support, payload accuracy, or approval of an operating point.

## Harness contracts

`physical_vision_study` validates three versioned live documents:

- `b26-study-manifest-v1`: exact versions, frozen configuration, capture paths, preregistered reasons, and ordered session plan;
- `b26-study-manifest-lock-v1`: canonical SHA-256 fingerprint plus UTC lock time and pseudonymous signer; and
- `b26-study-report-v1`: deterministic content-free aggregates with explicit status and claim boundaries.

It also validates `b26-public-supplement-report-v1`. The current public decision is an omitted report because no audited source has verified artifact-specific image rights plus transitive provenance.

Canonical JSON is ASCII UTF-8, sorted by key, compact separators, finite JSON numbers only, and one trailing LF. The manifest fingerprint is SHA-256 over exactly those canonical manifest bytes. A changed locked manifest, mismatched observation fingerprint, public/live track mixture, duplicate observation identity, unplanned reason, unaccounted planned session, or observation beyond the six-sample bound fails closed.

The live manifest requires these exact-value groups before lock:

- clean repository commit and app build;
- report, OpenCV, detector recipe, ready policy, guidance policy, Python, browser, and OS versions;
- payload-decode-off and learned-detector-off assertions;
- frozen ready thresholds, measurement tolerances, resource limits, seed `260826`, 10,000 bootstrap replicates, and six observations per session;
- pseudonymous operator/labeler IDs;
- device, camera, resolution, and sample rate for each capture path; and
- ordered session, physical-item/control-family, truth/support, challenge, appearance, and capture-path assignments.

IDs must be non-content identifiers. Validators reject path/URL/image-byte/payload-like fields, 12–14 digit payload-like values, Host/Origin material, data-image values, and exception-like text with content-free errors.

## Commands

Run commands from the repository root with the pinned Python environment:

```text
.venv/Scripts/python.exe scripts/run_b26_study.py validate --kind manifest --input <manifest.json>
.venv/Scripts/python.exe scripts/run_b26_study.py lock-manifest --input <manifest.json> --locked-at <UTC-Z> --signer-id <pseudonym> --output <locked.json>
.venv/Scripts/python.exe scripts/run_b26_study.py validate --kind lock --input <locked.json>
.venv/Scripts/python.exe scripts/run_b26_study.py aggregate-live --locked-manifest <locked.json> --observations <observations.json> --output <report.json>
.venv/Scripts/python.exe scripts/run_b26_study.py validate --kind report --input <report.json>
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
8. Run aggregation twice from the same locked inputs and byte-compare the outputs. A run with no analyzed live observation remains `live_pending`; it cannot appear as completed.

## Report interpretation

The aggregator reports planned/attempted/missing/excluded sessions, analyzed observations, physical-item clusters, count confusion, count/localization/ready/guidance proportions, cluster-bootstrap intervals, transition categories, latency nearest-rank summaries, missing reasons, and capture-path subgroup counts. Sequential observations are nested under physical-item groups; the report does not describe adjacent frames as independent samples.

The public report remains separately titled `offline_public_supplement`, has zero denominators, and makes every live claim boundary false. Live and public denominators are never pooled.

A future ONNX study is not approved here. It may be proposed only after a genuine completed locked run shows a reproducible live miss pattern in the same planned subgroup on at least two distinct physical items, with valid labels and frozen classical configuration. Any such work needs a later scoped stage/ADR and provenance/licence review.
