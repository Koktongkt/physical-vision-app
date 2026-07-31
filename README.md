# Physical Vision App

A privacy-conscious, local-first application for extracting and evaluating physical-device serial information from camera imagery. This repository currently contains the normative implementation specification, architecture research, and an implementation-ready project skeleton; application functionality has not yet been added.

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
- `experiments/vision-baseline` — isolated vision experiments
- `tests` — cross-component verification
- `data/manifests` and `models/manifests` — metadata only; private data and weights are ignored

## Status

Stage 0 bootstrap only. Do not treat placeholder directories as implemented components.
