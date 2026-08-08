# Physical Vision App

A privacy-conscious, local-first browser application that helps a user **frame one 1D barcode** with **live camera guidance** until a **ready** state (e.g. green) indicates they may take the picture. This repository contains the normative implementation specification, architecture research, an implementation-ready project skeleton, executable contracts, and vision baselines from earlier stages.

**Active MVP (spec v1.6):** detect-only 1D barcode framing guidance — not serial OCR, not barcode payload decode.

## Source of truth

- `docs/IMPLEMENTATION_SPEC.md` — normative product and implementation requirements (**v1.6**)
- `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md` — architecture research and evidence
- `AGENTS.md` — repository rules for contributors and coding agents
- `docs/PROVENANCE.md` — license and provenance register

## Layout

- `apps/web` — browser application
- `services/api` — local API/service boundary
- `packages/contracts` — shared versioned contracts
- `packages/policy` — deterministic policy and safety rules
- `packages/vision` — bounded safe image decode, OpenCV geometry/ROI/quality, classical localization, optional OCR baseline, and resource observation
- `experiments/vision-baseline` — isolated vision experiments
- `tests` — cross-component verification
- `data/manifests` and `models/manifests` — metadata only; private data and weights are ignored

## Status

**Product goal (v1.6):** live 1D barcode detection + quality + one-action camera guidance + ready-to-shoot UI. Multi/zero barcodes abstain. Public barcode datasets may supplement training only.

**Engineering already on `main` (Stages 1–5b):** contracts v3.0/v3.1, thin policy, safe Pillow decode, OpenCV geometry, classical localization, PaddleOCR baseline (parked for serial track). These are infrastructure — not a completed live barcode product.

**Stage 6 (merged — B21+B22):** `physical_vision_barcode` analyze API (`none|one|multiple` + box, decode off), localhost FastAPI `POST /v1/barcode/analyze`, and `apps/web` live preview + shutter/retake + overlay. Composes Stage 5 classical localization.

**Stage 7 (this branch — B23+B24):** readiness gates + green ready UI + exactly one camera-referent guidance action from the dominant failing gate. Recipe `barcode-frame-ready-v1`. Decode still off. Thresholds are VT seeds — not a claim of calibrated production ready rates.

**Next critical path after Stage 7 merge:** B25 privacy/resource hardening, B26 live pilot evidence.

## MVP implementation path (RI)

First build (no PaddleOCR, no decode in product):

1. **Live camera** — permission, preview, bounded sampling, shutter, freeze/retake
2. **Detect** — OpenCV barcode detector + existing Stage 5 classical barcode proposals → `none | one | multiple` + box
3. **Ready/green** — geometry/quality only: one box, min area/short side, margins, blur (Laplacian), aspect/skew sanity
4. **Guide** — exactly one camera-referent action from the dominant failing gate; abstain if not exactly one barcode
5. **Escalate later only if needed** — one-class nano detector → ONNX/ORT after measured misses on real devices

Optional barcode **decode** stays offline-only as a scanner-readable diagnostic, not MVP UX.

**Deferred:** serial OCR completion PET, barcode payload decode, bottle-only serial AR.

Still not approved: production, remote/multi-user, Ultralytics distribution, or accuracy claims without locked evidence.

## Local Stage 7 smoke (camera optional)

```bash
# API (loopback)
uvx --from uv==0.11.31 uv run python scripts/run_local_barcode_api.py

# Web static client (separate terminal)
python -m http.server 5173 --directory apps/web
# open http://127.0.0.1:5173 — Start camera → Analyze / Shutter / Retake
# ready = green “you may take the picture”; guidance = one camera cue
```

Automated tests do not require a camera. See `apps/web/README.md` and `services/api/README.md`.
