// node --test consumption-plan/tests/cli.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const skillRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

// Skills are installed as symlinks into ~/.claude/skills. Node resolves a main
// module to its real path but leaves argv[1] as typed, so a guard comparing the
// two decided the script was imported and printed nothing.
test("scripts run through a symlinked skill install", () => {
  const link = join(mkdtempSync(join(tmpdir(), "consumption-plan-link-")), "consumption-plan");
  symlinkSync(skillRoot, link);
  const result = spawnSync(process.execPath, [join(link, "scripts", "resolve-quarters.mjs"), "2026-08-01"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Q\+1 FY27 Q4 → Q\+4 FY28 Q3/);
});
