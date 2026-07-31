import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const directory = path.dirname(fileURLToPath(import.meta.url));
const schemaRoot = path.resolve(directory, "../schemas/v3.0");
const schemaFiles = {
  "vision-evidence-snapshot": "vision-evidence-snapshot.schema.json",
  "policy-decision": "policy-decision.schema.json",
  "analysis-result": "analysis-result.schema.json",
  completion: "completion.schema.json",
  "failure-envelope": "failure-envelope.schema.json",
  "retained-photo-lifecycle": "retained-photo-lifecycle.schema.json",
};

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const schemas = new Map();
for (const [kind, file] of Object.entries(schemaFiles)) {
  const schema = JSON.parse(readFileSync(path.join(schemaRoot, file), "utf8"));
  schemas.set(kind, schema);
  ajv.addSchema(schema);
}
const validators = new Map(
  [...schemas].map(([kind, schema]) => [kind, ajv.getSchema(schema.$id)]),
);

export class ContractValidationError extends Error {}

function fail(message) {
  throw new ContractValidationError(message);
}

function validateRegionContainment(snapshot) {
  const { label_region: label, text_region: text } = snapshot.localization;
  for (const [name, region] of [
    ["label_region", label],
    ["text_region", text],
  ]) {
    if (
      region !== null &&
      (region.x + region.width > 1 || region.y + region.height > 1)
    ) {
      fail(`localization.${name}: region exceeds normalized image bounds`);
    }
  }
  if (
    label !== null &&
    text !== null &&
    !(
      text.x >= label.x &&
      text.y >= label.y &&
      text.x + text.width <= label.x + label.width &&
      text.y + text.height <= label.y + label.height
    )
  ) {
    fail("localization.text_region: must be contained by label_region");
  }
}

function allGatesPass(gates) {
  return Object.values(gates).every(Boolean);
}

function sameRecord(left, right) {
  const keys = Object.keys(left);
  return (
    keys.length === Object.keys(right).length &&
    keys.every((key) =>
      Object.hasOwn(right, key) ? left[key] === right[key] : false,
    )
  );
}

function validatePolicy(decision) {
  const conjunction = allGatesPass(decision.gate_outcomes);
  if (decision.all_required_gates_pass !== conjunction) {
    fail(
      "policy_decision.all_required_gates_pass: must equal gate conjunction",
    );
  }
  if (
    decision.automatic_completion_eligible &&
    !(conjunction && decision.candidate_ready)
  ) {
    fail(
      "policy_decision.automatic_completion_eligible: requires every gate and a candidate",
    );
  }
}

function validateCompletion(completion) {
  if (completion.supersedes_completion_id === completion.completion_id)
    fail("completion: cannot supersede itself");
  if (completion.completion_source === "automatic_ocr") {
    if (
      !completion.raw_candidate ||
      !completion.displayed_candidate ||
      !completion.final_serial
    )
      fail(
        "completion: automatic completion requires non-empty serial evidence",
      );
    const probability = completion.whole_string_exact_probability_calibrated;
    if (
      probability === null ||
      probability <= completion.auto_threshold_strictly_greater_than
    ) {
      fail(
        "completion: automatic calibrated whole-string evidence must be strictly above PET",
      );
    }
    if (!allGatesPass(completion.gate_outcomes)) {
      fail("completion: automatic completion requires every gate");
    }
  }
  if (
    completion.completion_source === "user_confirmed_ocr_unchanged" &&
    !(
      completion.raw_candidate === completion.displayed_candidate &&
      completion.displayed_candidate === completion.final_serial
    )
  ) {
    fail("completion: unchanged confirmation must preserve verbatim candidate");
  }
}

function validateResult(result) {
  const snapshot = result.vision_evidence_snapshot;
  const decision = result.policy_decision;
  const completion = result.completion;
  validateRegionContainment(snapshot);
  validatePolicy(decision);
  if (completion !== null) {
    validateCompletion(completion);
    if (
      completion.completion_source === "automatic_ocr" &&
      result.status !== "automatic_complete"
    )
      fail(
        "analysis_result: automatic_ocr completion requires automatic_complete status",
      );
    if (
      ["user_corrected", "user_confirmed_ocr_unchanged"].includes(
        completion.completion_source,
      ) &&
      result.status !== "user_complete"
    )
      fail("analysis_result: user completion requires user_complete status");
  }
  if (result.status === "automatic_complete") {
    if (completion === null || completion.completion_source !== "automatic_ocr")
      fail(
        "analysis_result: automatic_complete status requires automatic_ocr completion",
      );
    if (decision.primary_action.kind !== "none")
      fail(
        "analysis_result: automatic completion cannot include a primary action",
      );
  }
  if (
    result.status === "user_complete" &&
    (completion === null ||
      !["user_corrected", "user_confirmed_ocr_unchanged"].includes(
        completion.completion_source,
      ))
  )
    fail(
      "analysis_result: user_complete status requires a user confirmation or correction",
    );

  if (
    result.result_id !== snapshot.result_id ||
    result.result_id !== decision.result_id
  )
    fail("analysis_result: mismatched result identity");
  if (snapshot.snapshot_id !== decision.snapshot_id)
    fail("analysis_result: mismatched snapshot identity");
  if (result.status !== decision.status)
    fail("analysis_result: policy and result status must match");
  const expectedRecommendation =
    decision.primary_action.kind === "none" ? null : decision.primary_action;
  if (
    result.recommendation !== expectedRecommendation &&
    (result.recommendation === null ||
      expectedRecommendation === null ||
      !sameRecord(result.recommendation, expectedRecommendation))
  )
    fail(
      "analysis_result.recommendation: must exactly mirror the single primary action",
    );
  if (result.business_complete !== (completion !== null))
    fail(
      "analysis_result.business_complete: must exactly track immutable completion linkage",
    );
  if (completion !== null && !result.capture_complete)
    fail(
      "analysis_result.capture_complete: must be true for a completed result",
    );
  if (
    completion !== null &&
    (completion.result_id !== result.result_id ||
      completion.session_id !== result.session.session_id ||
      completion.decision_id !== decision.decision_id ||
      completion.snapshot_id !== snapshot.snapshot_id)
  )
    fail("analysis_result: completion provenance linkage mismatch");
  if (completion !== null) {
    if (
      completion.raw_candidate !== snapshot.ocr.raw_string ||
      completion.displayed_candidate !== snapshot.ocr.displayed_string
    )
      fail(
        "analysis_result.completion: candidate provenance must remain verbatim",
      );
    if (
      completion.whole_string_exact_probability_calibrated !==
      snapshot.ocr.whole_string_exact_probability_calibrated
    )
      fail(
        "analysis_result.completion: calibrated probability provenance mismatch",
      );
    if (!sameRecord(completion.gate_outcomes, decision.gate_outcomes))
      fail("analysis_result.completion: gate provenance mismatch");
    if (
      completion.completion_source === "automatic_ocr" &&
      !(
        completion.raw_candidate === completion.displayed_candidate &&
        completion.displayed_candidate === completion.final_serial
      )
    )
      fail(
        "analysis_result.completion: automatic final serial must remain verbatim",
      );
  }

  const candidate = result.serial_candidate;
  if (
    candidate !== null &&
    (candidate.raw !== snapshot.ocr.raw_string ||
      candidate.displayed !== snapshot.ocr.displayed_string)
  )
    fail("analysis_result: candidate mutation or silent repair detected");

  const expectedVersions = {
    schema: snapshot.versions.schema,
    model: snapshot.versions.model,
    preprocess: snapshot.versions.preprocess,
    calibration: snapshot.versions.calibration,
    policy: decision.policy_version,
    threshold: decision.threshold_version,
  };
  if (!sameRecord(result.versions, expectedVersions))
    fail("analysis_result: stale or mismatched active versions");
  if (
    completion !== null &&
    (completion.schema_version_used !== result.versions.schema ||
      completion.model_version !== result.versions.model ||
      completion.preprocess_version !== result.versions.preprocess ||
      completion.calibration_version !== result.versions.calibration ||
      completion.policy_version !== result.versions.policy ||
      completion.threshold_version !== result.versions.threshold)
  )
    fail("analysis_result.completion: version provenance mismatch");
  if (
    snapshot.versions.policy_compatible !== decision.policy_version ||
    snapshot.versions.threshold_compatible !== decision.threshold_version
  )
    fail("analysis_result: incompatible evidence versions");

  const fresh =
    snapshot.freshness.is_current_attempt &&
    snapshot.freshness.age_ms <= snapshot.freshness.max_age_ms;
  if (result.status === "automatic_complete") {
    const evidenceGatesPass =
      snapshot.support.state === "pass" &&
      snapshot.support.ood_state === "in_distribution" &&
      snapshot.localization.state === "pass" &&
      Object.values(snapshot.quality).every((gate) => gate.state === "pass") &&
      fresh;
    if (
      !(
        result.capture_complete &&
        result.business_complete &&
        completion !== null &&
        completion.completion_source === "automatic_ocr" &&
        decision.automatic_completion_eligible &&
        evidenceGatesPass
      )
    )
      fail(
        "analysis_result: automatic completion requires current passing evidence and provenance",
      );
    const probability = snapshot.ocr.whole_string_exact_probability_calibrated;
    if (
      probability === null ||
      probability <= decision.auto_threshold_strictly_greater_than
    )
      fail(
        "analysis_result: calibrated whole-string evidence must be strictly above PET",
      );
  }
  if (
    result.status === "ready_for_verification" &&
    !(
      result.capture_complete &&
      !result.business_complete &&
      completion === null &&
      candidate !== null &&
      decision.candidate_ready
    )
  )
    fail(
      "analysis_result: candidate-ready state separates capture from business completion",
    );
}

export function validateDocument(kind, document) {
  const validator = validators.get(kind);
  if (!validator) fail(`unknown contract kind: ${kind}`);
  if (!validator(document)) {
    fail(JSON.stringify(validator.errors));
  }
  if (kind === "vision-evidence-snapshot") validateRegionContainment(document);
  else if (kind === "policy-decision") validatePolicy(document);
  else if (kind === "completion") validateCompletion(document);
  else if (kind === "analysis-result") validateResult(document);
  return document;
}
