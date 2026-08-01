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

test("v3.1 preserves v3.0 policy action referent conditionals and adds vertical actions", async () => {
  const v30 = JSON.parse(
    await readFile(
      path.resolve(
        "packages/contracts/schemas/v3.0/policy-decision.schema.json",
      ),
      "utf8",
    ),
  );
  const v31 = JSON.parse(
    await readFile(
      path.resolve(
        "packages/contracts/schemas/v3.1/policy-decision.schema.json",
      ),
      "utf8",
    ),
  );
  const action30 = v30.properties.primary_action;
  const action31 = v31.properties.primary_action;

  assert.equal(action31.type, action30.type);
  assert.deepEqual(action31.allOf, [
    {
      ...action30.allOf[0],
      if: {
        properties: {
          kind: {
            enum: [
              ...action30.allOf[0].if.properties.kind.enum.slice(0, 2),
              "camera_up",
              "camera_down",
              ...action30.allOf[0].if.properties.kind.enum.slice(2),
            ],
          },
        },
      },
    },
    action30.allOf[1],
  ]);
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
