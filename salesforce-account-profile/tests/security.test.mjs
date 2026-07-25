import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { CAPS } from "../scripts/constants.mjs";
import {
  escapeSoqlLiteral,
  escapeSoqlLikePrefix,
  markdownText,
  readJsonInput,
  redactDeep,
  sanitizeText,
} from "../scripts/security.mjs";

test("sanitizes control, bidi, and ANSI characters", () => {
  assert.equal(sanitizeText("safe\t\n\r\u0000\u202e\u001b[31mtext"), "safetext");
});

test("escapes apostrophes and SOQL metacharacters as inert literals", () => {
  assert.equal(escapeSoqlLiteral("O'Brien\\_%"), "O\\'Brien\\\\_%");
});

test("escapes prefix LIKE wildcards as literal CRM text", () => {
  assert.equal(escapeSoqlLikePrefix("A%_\\'"), "A\\%\\_\\\\\\'");
});

test("escapes CRM Markdown rather than rendering it", () => {
  assert.equal(markdownText("**run** [link](x) | row"), "\\*\\*run\\*\\* \\[link\\]\\(x\\) \\| row");
});

test("redacts token-bearing keys and Salesforce session token shapes", () => {
  const value = redactDeep({ accessToken: "secret", message: "Bearer abc.def", nested: { password: "x" } });
  assert.deepEqual(value, { accessToken: "[REDACTED]", message: "[REDACTED]", nested: { password: "[REDACTED]" } });
});

test("private JSON input accepts mode 0600", async () => {
  const dir = await mkdtemp(join(tmpdir(), "profile-test-"));
  const path = join(dir, "input.json");
  try {
    await writeFile(path, "{}", { mode: 0o600 });
    assert.deepEqual(await readJsonInput(path, null), {});
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("private JSON input rejects group-readable files", async () => {
  const dir = await mkdtemp(join(tmpdir(), "profile-test-"));
  const path = join(dir, "input.json");
  try {
    await writeFile(path, "{}", { mode: 0o600 });
    await chmod(path, 0o640);
    await assert.rejects(() => readJsonInput(path, null), { code: "INSECURE_INPUT_PERMISSIONS" });
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("private JSON input rejects oversized files", async () => {
  const dir = await mkdtemp(join(tmpdir(), "profile-test-"));
  const path = join(dir, "input.json");
  try {
    await writeFile(path, Buffer.alloc(CAPS.inputBytes + 1), { mode: 0o600 });
    await assert.rejects(() => readJsonInput(path, null), { code: "INPUT_TOO_LARGE" });
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
