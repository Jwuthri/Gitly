// The TS redaction mirror must mask the same canonical fixtures as the python redactors
// (backend/tests/test_redaction_parity.py). Run via `npm test` (builds first).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { redact } from "../dist/lib.js";

const here = dirname(fileURLToPath(import.meta.url));
const { secrets } = JSON.parse(readFileSync(join(here, "../../../shared/redaction_fixtures.json"), "utf8"));

for (const fx of secrets) {
  test(`mcp redact masks ${fx.name}`, () => {
    const hidden = fx.must_hide ?? fx.text;
    assert.ok(!redact(`payload with ${fx.text} inside`).includes(hidden));
  });
}
