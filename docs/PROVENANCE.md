# License and provenance register

This register records provenance and review status. Absence from this register is not evidence of permission to use, distribute, or publish an artifact.

## Repository code and documentation

| Artifact | Source | License / terms | Verification status | Distribution status |
|---|---|---|---|---|
| Repository-authored code and documentation | This repository | All rights reserved pending an explicit project licensing decision | Initial register only | No public distribution grant recorded |

## External dependencies, datasets, and model artifacts

| Artifact | Exact source/version | License evidence | Integrity evidence | Approved use | Status |
|---|---|---|---|---|---|
| `jsonschema` | 4.25.1; https://pypi.org/project/jsonschema/4.25.1/ | MIT; installed package metadata and https://github.com/python-jsonschema/jsonschema/blob/v4.25.1/COPYING | Exact resolution and hashes in `uv.lock` | Draft 2020-12 Python contract validation | Approved for Stage 1 local development, 2026-07-31 |
| `pytest` | 8.4.1; https://pypi.org/project/pytest/8.4.1/ | MIT; installed package metadata and https://github.com/pytest-dev/pytest/blob/8.4.1/LICENSE | Exact resolution and hashes in `uv.lock` | Python contract tests | Approved for Stage 1 development, 2026-07-31 |
| `ruff` | 0.12.7; https://pypi.org/project/ruff/0.12.7/ | MIT; installed package classifier and https://github.com/astral-sh/ruff/blob/0.12.7/LICENSE | Exact resolution and hashes in `uv.lock` | Python formatting and linting | Approved for Stage 1 development, 2026-07-31 |
| `ajv` | 8.20.0; https://www.npmjs.com/package/ajv/v/8.20.0 | MIT; installed `package.json` and https://github.com/ajv-validator/ajv/blob/v8.20.0/LICENSE | Exact resolution and integrity in `package-lock.json`; `npm audit` reports zero vulnerabilities on 2026-07-31 | Draft 2020-12 JavaScript contract validation | Approved for Stage 1 local development, 2026-07-31 |
| `ajv-formats` | 3.0.1; https://www.npmjs.com/package/ajv-formats/v/3.0.1 | MIT; installed `package.json` and https://github.com/ajv-validator/ajv-formats/blob/v3.0.1/LICENSE | Exact resolution and integrity in `package-lock.json` | RFC 3339/date-time format validation | Approved for Stage 1 local development, 2026-07-31 |
| `json-schema-to-typescript` | 15.0.4; https://www.npmjs.com/package/json-schema-to-typescript/v/15.0.4 | MIT; installed `package.json` and https://github.com/bcherny/json-schema-to-typescript/blob/15.0.4/LICENSE | Exact resolution and integrity in `package-lock.json` | Generate checked-in TypeScript types from authoritative schemas | Approved for Stage 1 development, 2026-07-31 |
| `prettier` | 3.6.2; https://www.npmjs.com/package/prettier/v/3.6.2 | MIT; installed `package.json` and https://github.com/prettier/prettier/blob/3.6.2/LICENSE | Exact resolution and integrity in `package-lock.json` | JavaScript/TypeScript/JSON/Markdown formatting | Approved for Stage 1 development, 2026-07-31 |
| `typescript` | 5.9.2; https://www.npmjs.com/package/typescript/v/5.9.2 | Apache-2.0; installed `package.json` and https://github.com/microsoft/TypeScript/blob/v5.9.2/LICENSE.txt | Exact resolution and integrity in `package-lock.json` | Static checking of generated contract types | Approved for Stage 1 development, 2026-07-31 |
| Evaluation or training datasets | None committed | Not verified | Not recorded | None | Unapproved |
| Model weights | None committed | Not verified | Not recorded | None | Unapproved |

## Registration requirements

Before adding or using an external dependency, dataset, model, or weight, record its exact name and version, canonical source, license text or URL, relevant restrictions, checksum or immutable identifier, intended use, reviewer, and decision date. Keep private data and model binaries out of Git; track metadata only under `data/manifests/` or `models/manifests/`.

Research references and candidate technologies in `docs/research/AI_VISION_ARCHITECTURE_RESEARCH.md` are not license clearance. In particular, no model-weight or dataset redistribution rights are asserted by this repository.
