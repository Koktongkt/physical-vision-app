import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { validateDocument } from "../src/validator.mjs";

const fixtureRoots = [
  path.resolve("packages/contracts/fixtures"),
  path.resolve("packages/contracts/fixtures/v3.1"),
];

test("generated exports include the v3.1 policy boundary", async () => {
  const generatedIndex = await readFile(
    path.resolve("packages/contracts/src/generated/index.ts"),
    "utf8",
  );

  assert.match(generatedIndex, /VisionEvidenceSnapshotV31/);
  assert.match(generatedIndex, /PolicyDecisionV31/);
});

test("v3.1 policy actions retain typed referent validity", async () => {
  const v31 = JSON.parse(
    await readFile(
      path.resolve(
        "packages/contracts/schemas/v3.1/policy-decision.schema.json",
      ),
      "utf8",
    ),
  );
  const action31 = v31.properties.primary_action;

  assert.deepEqual(action31.oneOf[0].properties.kind.enum, [
    "camera_left",
    "camera_right",
    "camera_up",
    "camera_down",
    "camera_closer",
    "camera_farther",
    "camera_tilt_direct",
    "camera_reduce_glare",
  ]);
  assert.equal(action31.oneOf[0].properties.referent.const, "camera");
  assert.deepEqual(action31.oneOf[1].properties.kind.enum, [
    "none",
    "manual",
    "unable",
  ]);
  assert.equal(action31.oneOf[1].properties.referent.type, "null");
});

for (const [fixture, mutate] of [
  [
    "positive-unsupported-no-label-unreadable.json",
    (ocr) => {
      ocr.raw_string = "SYNTH-31";
      ocr.displayed_string = "SYNTH-31";
    },
  ],
  [
    "unknown-multiple-labels-ambiguous-ocr.json",
    (ocr) => {
      ocr.raw_string = "";
      ocr.displayed_string = "";
    },
  ],
]) {
  test(`v3.1 rejects incoherent OCR evidence derived from ${fixture}`, async () => {
    const document = JSON.parse(
      await readFile(
        path.resolve("packages/contracts/fixtures/v3.1/valid", fixture),
        "utf8",
      ),
    );
    mutate(document.ocr);

    assert.throws(
      () => validateDocument("vision-evidence-snapshot", document),
      /ocr\.reason/i,
    );
  });
}

async function manifest(root, group) {
  return JSON.parse(
    await readFile(path.join(root, group, "manifest.json"), "utf8"),
  );
}

for (const fixtureRoot of fixtureRoots) {
  const version = path.basename(fixtureRoot) === "v3.1" ? "v3.1" : "v3.0";
  for (const fixture of await manifest(fixtureRoot, "valid")) {
    test(`TypeScript path accepts ${version}/${fixture.file}`, async () => {
      const document = JSON.parse(
        await readFile(path.join(fixtureRoot, "valid", fixture.file), "utf8"),
      );

      assert.doesNotThrow(() => validateDocument(fixture.kind, document));
    });
  }

  for (const fixture of await manifest(fixtureRoot, "invalid")) {
    test(`TypeScript path rejects ${version}/${fixture.file}`, async () => {
      const raw = await readFile(
        path.join(fixtureRoot, "invalid", fixture.file),
        "utf8",
      );
      let document;
      try {
        document = JSON.parse(raw);
      } catch {
        return;
      }

      assert.throws(
        () => validateDocument(fixture.kind, document),
        new RegExp(fixture.error_contains, "i"),
      );
    });
  }
}
