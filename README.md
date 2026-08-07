# Physical Vision App

A privacy-conscious, local-first application for extracting and evaluating physical-device serial information from camera imagery. This repository currently contains the normative implementation specification, architecture research, an implementation-ready project skeleton, and executable versioned contracts; application functionality beyond the contract boundary has not yet been added.

## Source of truth

- `docs/IMPLEMENTATION_SPEC.md` — normative product and implementation requirements
- `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md` — architecture research and evidence
- `AGENTS.md` — repository rules for contributors and coding agents
- `docs/PROVENANCE.md` — license and provenance register

## Layout

- `apps/web` — browser application
- `services/api` — local API/service boundary
- `packages/contracts` — shared versioned contracts
- `packages/policy` — deterministic policy and safety rules
- `packages/vision` — bounded safe image decode, OpenCV geometry/ROI/quality, classical localization, PaddleOCR OCR baseline, and resource observation
- `experiments/vision-baseline` — isolated vision experiments
- `tests` — cross-component verification
- `data/manifests` and `models/manifests` — metadata only; private data and weights are ignored

## Status

Stage 2 is complete. The thin additive contract v3.1 and deterministic policy
engine are implemented under `packages/contracts` and `packages/policy`, while
contract v3.0 remains supported.

Stage 3 B02+B06 (bounded resource plan and safe Pillow decode) lives under
`packages/vision` as `physical_vision_image` / `physical_vision_resources`.

Stage 4 B07 (OpenCV geometry, ROI/rectification, raw quality measurements, and
overlay primitives) is implemented under `packages/vision` as
`physical_vision_geometry`.

Stage 5 closes the **code/fixture portion of specification Phase 2**: classical
barcode/contour localization and a PaddleOCR single-line OCR baseline under
`packages/vision` as `physical_vision_localization` and `physical_vision_ocr`,
with a thin experiment harness in `experiments/vision-baseline/`. Synthetic
fixtures only. This is not product validation and does not claim bake-off winners.

Still later: B08 physical/replayed adjudicated corpus, B09 classical-vs-box-vs-mask
localization bake-off, B10 multi-engine OCR bake-off completion, API/UI, persistence, and
policy/completion integration.
