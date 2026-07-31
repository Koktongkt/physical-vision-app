import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";
import { format } from "prettier";

const directory = path.dirname(fileURLToPath(import.meta.url));
const contractsRoot = path.resolve(directory, "..");
const schemaRoot = path.join(contractsRoot, "schemas/v3.0");
const generatedRoot = path.join(contractsRoot, "src/generated");
const check = process.argv.includes("--check");
const files = [
  "vision-evidence-snapshot",
  "policy-decision",
  "analysis-result",
  "completion",
  "failure-envelope",
  "retained-photo-lifecycle",
];
const exportedTypes = {
  "vision-evidence-snapshot": "VisionEvidenceSnapshot",
  "policy-decision": "PolicyDecision",
  "analysis-result": "AnalysisResult",
  completion: "Completion",
  "failure-envelope": "FailureEnvelope",
  "retained-photo-lifecycle": "RetainedPhotoLifecycle",
};
const authorityPrefix = "https://physical-vision.local/contracts/v3.0/";

if (!check) await mkdir(generatedRoot, { recursive: true });

function localizeReferences(value) {
  if (Array.isArray(value)) return value.map(localizeReferences);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [
        key,
        key === "$ref" &&
        typeof child === "string" &&
        child.startsWith(authorityPrefix)
          ? child.slice(authorityPrefix.length)
          : localizeReferences(child),
      ]),
    );
  }
  return value;
}

async function emit(file, content) {
  if (check) {
    let existing;
    try {
      existing = await readFile(file, "utf8");
    } catch {
      throw new Error(`generated contract type is missing: ${file}`);
    }
    if (existing !== content) {
      throw new Error(`generated contract type drift detected: ${file}`);
    }
    return;
  }
  await writeFile(file, content, "utf8");
}

for (const name of files) {
  const schema = JSON.parse(
    await readFile(path.join(schemaRoot, `${name}.schema.json`), "utf8"),
  );
  const localized = localizeReferences(schema);
  const compiled = await compile(localized, schema.title, {
    cwd: schemaRoot,
    bannerComment:
      "/* AUTO-GENERATED from JSON Schema Draft 2020-12. DO NOT EDIT. */",
    additionalProperties: false,
    enableConstEnums: false,
    style: { singleQuote: false, semi: true },
  });
  const output = await format(compiled, { parser: "typescript" });
  await emit(path.join(generatedRoot, `${name}.ts`), output);
}

const index = `${files
  .map((file) => `export type { ${exportedTypes[file]} } from "./${file}.js";`)
  .join("\n")}\n`;
await emit(path.join(generatedRoot, "index.ts"), index);
console.log(
  check
    ? "generated contract types are in sync"
    : "generated contract types updated",
);
