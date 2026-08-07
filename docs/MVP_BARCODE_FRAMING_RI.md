# MVP barcode framing — recommended implementation (RI)

Normative product rules live in `IMPLEMENTATION_SPEC.md` **v1.6** (section 0.1 AR, section 0.2 RI). This file is a short engineer checklist.

## In

- Live guide to frame **one 1D barcode**
- Ready (green) = user may take the picture (human shutter)
- Detect-only (no payload in product UX)
- Abstain on zero or multiple 1D codes

## Out

- PaddleOCR / serial OCR
- Product barcode decode string
- Pick-largest multi-barcode heuristics
- Ultralytics in distributed app artifact

## Build order

1. Live camera client (permission, preview, sample budget, shutter, freeze/retake)
2. OpenCV `BarcodeDetector` + Stage 5 `physical_vision_localization` classical barcode proposals
3. Map proposals → `none | one | multiple` + single box when one
4. Quality: area, short side px, margins, Laplacian blur, aspect/skew
5. Ready when all gates pass; else one camera-referent action from dominant failure
6. Measure on webcam/phone; only then consider one-class ONNX nano detector

## Reuse on `main`

- `physical_vision_localization` — barcode landmark proposals (OpenCV + morph)
- `physical_vision_geometry` — boxes, ROI, quality primitives, overlays
- `physical_vision_image` / resources — bounded decode for captured stills
- `physical_vision_ocr` — **parked**, not required for this MVP
