import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import {
  chmod,
  mkdir,
  mkdtemp,
  realpath,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { createProductionSfClient } from "../scripts/sf-client.mjs";
import {
  discoverSfRuntime,
  loadVerifiedSfRuntime,
  writeSfRuntimeManifest,
} from "../scripts/sf-runtime.mjs";

function childWithJson(payload, code = 0) {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => {};
  queueMicrotask(() => {
    child.stdout.emit("data", Buffer.from(JSON.stringify(payload)));
    child.emit("close", code);
  });
  return child;
}

async function runtimeFixture() {
  const root = await mkdtemp(join(tmpdir(), "sf-runtime-"));
  const packageRoot = join(root, "cli");
  const bin = join(packageRoot, "bin");
  await mkdir(bin, { recursive: true, mode: 0o700 });
  const nodePath = join(root, "node");
  const sfEntrypoint = join(bin, "run.js");
  const sfLink = join(root, "sf");
  const packageJson = join(packageRoot, "package.json");
  await writeFile(nodePath, "#!/bin/sh\nexit 0\n", { mode: 0o755 });
  await writeFile(sfEntrypoint, "#!/usr/bin/env -S node --no-deprecation\n", { mode: 0o755 });
  await writeFile(packageJson, JSON.stringify({ name: "@salesforce/cli", version: "2.99.0" }), { mode: 0o600 });
  await symlink(sfEntrypoint, sfLink);
  return {
    root,
    nodePath: await realpath(nodePath),
    sfEntrypoint: await realpath(sfEntrypoint),
    sfLink,
    packageJson: await realpath(packageJson),
  };
}

test("enrolled runtime invokes the pinned Node and Salesforce entrypoint with shell false", async () => {
  const fixture = await runtimeFixture();
  const manifestPath = join(fixture.root, "sf-runtime.json");
  try {
    const manifest = await discoverSfRuntime({
      pathEnv: fixture.root,
      nodePath: fixture.nodePath,
      now: new Date("2030-01-01T00:00:00.000Z"),
    });
    await writeSfRuntimeManifest(manifestPath, manifest);
    let captured;
    const client = await createProductionSfClient({
      targetOrg: "synthetic",
      runtimeManifestPath: manifestPath,
      runner: (file, args, options) => {
        captured = { file, args, options };
        return childWithJson({
          result: {
            id: "00D000000000001AAA",
            username: "synthetic@example.invalid",
            instanceUrl: "https://synthetic.example.invalid",
          },
        });
      },
    });
    await client.orgDisplay();
    assert.equal(captured.file, fixture.nodePath);
    assert.deepEqual(captured.args.slice(0, 4), [
      "--no-deprecation",
      fixture.sfEntrypoint,
      "org",
      "display",
    ]);
    assert.equal(captured.options.shell, false);
    assert.equal(client.attestationDigest, manifest.attestation_digest);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("runtime verification ignores later PATH order and uses only the private manifest", async () => {
  const fixture = await runtimeFixture();
  const manifestPath = join(fixture.root, "sf-runtime.json");
  try {
    const manifest = await discoverSfRuntime({ pathEnv: fixture.root, nodePath: fixture.nodePath });
    await writeSfRuntimeManifest(manifestPath, manifest);
    const originalPath = process.env.PATH;
    process.env.PATH = "/untrusted/first";
    try {
      const verified = await loadVerifiedSfRuntime(manifestPath);
      assert.equal(verified.command.executable, fixture.nodePath);
      assert.equal(verified.command.fixedArgs[1], fixture.sfEntrypoint);
    } finally {
      process.env.PATH = originalPath;
    }
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("runtime drift requires explicit re-attestation", async () => {
  const fixture = await runtimeFixture();
  const manifestPath = join(fixture.root, "sf-runtime.json");
  try {
    const manifest = await discoverSfRuntime({ pathEnv: fixture.root, nodePath: fixture.nodePath });
    await writeSfRuntimeManifest(manifestPath, manifest);
    await writeFile(fixture.sfEntrypoint, "#!/usr/bin/env -S node --no-deprecation\n// changed\n");
    await chmod(fixture.sfEntrypoint, 0o755);
    await assert.rejects(
      () => loadVerifiedSfRuntime(manifestPath),
      { code: "SF_EXECUTABLE_REATTESTATION_REQUIRED" },
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("runtime enrollment records owner-controlled group-write risk and rejects world-write", async () => {
  const fixture = await runtimeFixture();
  try {
    await chmod(fixture.nodePath, 0o775);
    const warned = await discoverSfRuntime({ pathEnv: fixture.root, nodePath: fixture.nodePath });
    assert(warned.permission_warnings.includes("NODE_GROUP_WRITABLE"));
    await chmod(fixture.nodePath, 0o777);
    await assert.rejects(
      () => discoverSfRuntime({ pathEnv: fixture.root, nodePath: fixture.nodePath }),
      { code: "INSECURE_INPUT_PERMISSIONS" },
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("runtime manifest is private, create-once, and rejects package identity drift", async () => {
  const fixture = await runtimeFixture();
  const manifestPath = join(fixture.root, "sf-runtime.json");
  try {
    const manifest = await discoverSfRuntime({ pathEnv: fixture.root, nodePath: fixture.nodePath });
    await writeSfRuntimeManifest(manifestPath, manifest);
    await assert.rejects(() => writeSfRuntimeManifest(manifestPath, manifest));
    await writeFile(fixture.packageJson, JSON.stringify({ name: "@salesforce/cli", version: "2.100.0" }), { mode: 0o600 });
    await assert.rejects(
      () => loadVerifiedSfRuntime(manifestPath),
      { code: "SF_EXECUTABLE_REATTESTATION_REQUIRED" },
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});
