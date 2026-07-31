import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { validateDocument } from "../src/validator.mjs";

const fixtureRoot = path.resolve("packages/contracts/fixtures");

async function manifest(group) {
  return JSON.parse(
    await readFile(path.join(fixtureRoot, group, "manifest.json"), "utf8"),
  );
}

for (const fixture of await manifest("valid")) {
  test(`TypeScript path accepts ${fixture.file}`, async () => {
    const document = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid", fixture.file), "utf8"),
    );

    assert.doesNotThrow(() => validateDocument(fixture.kind, document));
  });
}

for (const fixture of await manifest("invalid")) {
  test(`TypeScript path rejects ${fixture.file}`, async () => {
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
