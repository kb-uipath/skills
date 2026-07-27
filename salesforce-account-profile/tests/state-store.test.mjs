import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  chmod,
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  symlink,
  unlink,
  writeFile,
} from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  CLASSIFICATION,
  CONTRACTS,
  SESSION_TTL_MS,
} from "../scripts/constants.mjs";
import {
  buildOfflineRegistryEntry,
  emptyOrgRegistry,
  upsertRegistryEntry,
} from "../scripts/org-registry.mjs";
import {
  createStateStore,
  stateStoreContracts,
} from "../scripts/state-store.mjs";

const SESSION_1 = "0123456789abcdef0123456789abcdef";
const SESSION_2 = "abcdef0123456789abcdef0123456789";
const START = Date.parse("2030-01-01T00:00:00.000Z");
const stateStoreModuleUrl = new URL(
  "../scripts/state-store.mjs",
  import.meta.url,
).href;

async function fixture(t) {
  const stateRoot = await mkdtemp(join(tmpdir(), "account-profile-state-"));
  let clock = START;
  const store = createStateStore({
    stateRoot,
    now: () => new Date(clock),
  });
  t.after(async () => await rm(stateRoot, { recursive: true, force: true }));
  return {
    stateRoot,
    store,
    now: () => clock,
    advance(milliseconds) {
      clock += milliseconds;
    },
  };
}

function newSession(sessionId = SESSION_1, overrides = {}) {
  return {
    session_id: sessionId,
    state: "new",
    target_org: "synthetic",
    friendly_org: { label: "Synthetic UAT" },
    request: { action: "start" },
    query_count: 0,
    pending_action: null,
    ...overrides,
  };
}

function indexEntry(sessionId, state = "new", offset = 0) {
  const created = new Date(START + offset);
  return {
    session_id: sessionId,
    state,
    created_at: created.toISOString(),
    updated_at: created.toISOString(),
    expires_at: new Date(created.getTime() + SESSION_TTL_MS).toISOString(),
  };
}

async function crashWhileHoldingSessionLock(stateRoot, sessionId) {
  const source = `
    import { createStateStore } from ${JSON.stringify(stateStoreModuleUrl)};
    const store = createStateStore({
      stateRoot: ${JSON.stringify(stateRoot)},
      now: () => new Date(${JSON.stringify(new Date(START).toISOString())}),
    });
    await store.withSessionLock(${JSON.stringify(sessionId)}, async () => {
      await new Promise((resolve) => process.stdout.write("locked\\n", resolve));
      process.exit(0);
    });
  `;
  await new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      ["--input-type=module", "--eval", source],
      {
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      const output = Buffer.concat(stdout).toString("utf8");
      const error = Buffer.concat(stderr).toString("utf8");
      if (code !== 0 || output !== "locked\n") {
        reject(new Error(
          `Lock-holder process failed (${code}): ${error || output}`,
        ));
        return;
      }
      resolve();
    });
  });
}

test("default root is beneath the Codex state root without touching it", () => {
  const store = createStateStore();
  const codexHome = process.env.CODEX_HOME ?? join(homedir(), ".codex");

  assert.equal(store.paths.state_root, join(codexHome, "state"));
  assert.equal(
    store.paths.skill_directory,
    join(codexHome, "state", "salesforce-account-profile"),
  );
});

test("initialization creates exact private directories and a session index", async (t) => {
  const { store } = await fixture(t);

  await store.initialize();

  assert.equal((await stat(store.paths.skill_directory)).mode & 0o777, 0o700);
  assert.equal((await stat(store.paths.sessions_directory)).mode & 0o777, 0o700);
  assert.equal((await stat(store.paths.session_index)).mode & 0o777, 0o600);
  assert.deepEqual(await store.readSessionIndex(), []);
  assert.deepEqual(await store.readOrgRegistry(), {
    schema_version: CONTRACTS.orgRegistry,
    classification: CLASSIFICATION,
    entries: [],
  });
  await assert.rejects(() => stat(store.paths.org_registry), { code: "ENOENT" });
});

test("session create, read, and update preserve a fixed 30-minute lifetime atomically", async (t) => {
  const { store, advance } = await fixture(t);

  const created = await store.createSession(newSession());
  assert.equal(created.schema_version, CONTRACTS.session);
  assert.equal(created.created_at, "2030-01-01T00:00:00.000Z");
  assert.equal(created.updated_at, created.created_at);
  assert.equal(created.expires_at, "2030-01-01T00:30:00.000Z");
  assert.equal((await stat(store.paths.session(SESSION_1))).mode & 0o777, 0o600);
  assert.deepEqual(await store.readSession(SESSION_1), created);

  advance(60_000);
  const updated = await store.updateSession(SESSION_1, {
    state: "org_confirmation",
    friendly_org: { label: "Synthetic UAT", confirmed: true },
  });
  assert.equal(updated.state, "org_confirmation");
  assert.equal(updated.updated_at, "2030-01-01T00:01:00.000Z");
  assert.equal(updated.created_at, created.created_at);
  assert.equal(updated.expires_at, created.expires_at);
  assert.deepEqual(await store.listSessions(), [{
    session_id: SESSION_1,
    state: "org_confirmation",
    created_at: created.created_at,
    updated_at: updated.updated_at,
    expires_at: created.expires_at,
  }]);

  const sessionFiles = await readdir(store.paths.sessions_directory);
  assert.deepEqual(sessionFiles, [`${SESSION_1}.json`]);
  assert.equal(sessionFiles.some((name) => name.endsWith(".tmp")), false);
});

test("duplicate session creation is create-once and preserves the original", async (t) => {
  const { store } = await fixture(t);
  const original = await store.createSession(newSession());

  await assert.rejects(
    () => store.createSession(newSession(SESSION_1, { state: "account_resolution" })),
    { code: "SESSION_EXISTS" },
  );
  assert.deepEqual(await store.readSession(SESSION_1), original);
});

test("strict lowercase session IDs prevent path traversal and aliases", async (t) => {
  const { store } = await fixture(t);
  const invalid = [
    "../0123456789abcdef0123456789ab",
    "0123456789ABCDEF0123456789ABCDEF",
    "0123456789abcdef",
    "g123456789abcdef0123456789abcdef",
  ];

  for (const sessionId of invalid) {
    await assert.rejects(
      () => store.createSession(newSession(sessionId)),
      { code: "INVALID_SESSION_ID" },
    );
    assert.throws(() => store.paths.session(sessionId), { code: "INVALID_SESSION_ID" });
  }
});

test("per-session wx lock blocks concurrent continuation and update", async (t) => {
  const { store } = await fixture(t);
  await store.createSession(newSession());
  let entered;
  const enteredPromise = new Promise((resolve) => {
    entered = resolve;
  });
  let release;
  const releasePromise = new Promise((resolve) => {
    release = resolve;
  });

  const held = store.withSessionLock(SESSION_1, async (continuation) => {
    assert.equal(continuation.session.session_id, SESSION_1);
    assert.equal((await stat(store.paths.session_lock(SESSION_1))).mode & 0o777, 0o600);
    entered();
    await releasePromise;
  });
  await enteredPromise;

  await assert.rejects(
    () => store.withSessionLock(SESSION_1, async () => {}),
    { code: "SESSION_LOCKED" },
  );
  await assert.rejects(
    () => store.updateSession(SESSION_1, { state: "account_resolution" }),
    { code: "SESSION_LOCKED" },
  );

  release();
  await held;
  await assert.rejects(() => stat(store.paths.session_lock(SESSION_1)), { code: "ENOENT" });
  assert.equal(
    (await store.updateSession(SESSION_1, { state: "account_resolution" })).state,
    "account_resolution",
  );
});

test("expiry is exact, list can expose expired metadata, and cleanup deletes state", async (t) => {
  const { store, advance } = await fixture(t);
  await store.createSession(newSession());

  advance(SESSION_TTL_MS - 1);
  assert.equal((await store.readSession(SESSION_1)).state, "new");
  advance(1);
  await assert.rejects(() => store.readSession(SESSION_1), { code: "SESSION_EXPIRED" });
  assert.deepEqual(await store.listSessions(), []);
  assert.equal((await store.listSessions({ includeExpired: true })).length, 1);

  assert.deepEqual(await store.cleanupExpiredSessions(), {
    deleted: [SESSION_1],
    locked: [],
  });
  assert.deepEqual(await store.readSessionIndex(), []);
  await assert.rejects(() => store.readSession(SESSION_1), { code: "SESSION_NOT_FOUND" });
});

test("cleanup never removes an expired session with an active continuation lock", async (t) => {
  const { store, advance } = await fixture(t);
  await store.createSession(newSession());
  let entered;
  const enteredPromise = new Promise((resolve) => {
    entered = resolve;
  });
  let release;
  const releasePromise = new Promise((resolve) => {
    release = resolve;
  });
  const held = store.withSessionLock(SESSION_1, async () => {
    entered();
    await releasePromise;
  });
  await enteredPromise;
  advance(SESSION_TTL_MS);

  assert.deepEqual(await store.cleanupExpiredSessions(), {
    deleted: [],
    locked: [SESSION_1],
  });
  release();
  await held;
  assert.deepEqual(await store.cleanupExpiredSessions(), {
    deleted: [SESSION_1],
    locked: [],
  });
});

test("dead-owner locks are reclaimed without stealing live locks and expiry cleanup recovers after a crash", async (t) => {
  const {
    stateRoot,
    store,
    advance,
  } = await fixture(t);
  await store.createSession(newSession(SESSION_1));
  await store.createSession(newSession(SESSION_2));

  await crashWhileHoldingSessionLock(stateRoot, SESSION_1);
  await crashWhileHoldingSessionLock(stateRoot, SESSION_2);
  assert.equal(
    (await store.updateSession(SESSION_1, {
      state: "account_resolution",
    })).state,
    "account_resolution",
  );

  let entered;
  const enteredPromise = new Promise((resolve) => {
    entered = resolve;
  });
  let release;
  const releasePromise = new Promise((resolve) => {
    release = resolve;
  });
  const live = store.withSessionLock(SESSION_1, async () => {
    entered();
    await releasePromise;
  });
  await enteredPromise;
  await assert.rejects(
    () => store.updateSession(SESSION_1, { state: "account_choice" }),
    { code: "SESSION_LOCKED" },
  );
  release();
  await live;

  advance(SESSION_TTL_MS);
  assert.deepEqual(await store.cleanupExpiredSessions(), {
    deleted: [SESSION_1, SESSION_2],
    locked: [],
  });
  assert.deepEqual(await store.readSessionIndex(), []);
});

test("abort, explicit completion, and complete-state update delete session state", async (t) => {
  const { store } = await fixture(t);
  await store.createSession(newSession(SESSION_1));
  await store.createSession(newSession(SESSION_2));

  assert.equal(await store.deleteSession(SESSION_1, "abort"), true);
  assert.equal(await store.updateSession(SESSION_2, { state: "complete" }), null);
  assert.deepEqual(await store.readSessionIndex(), []);
  await assert.rejects(() => store.readSession(SESSION_1), { code: "SESSION_NOT_FOUND" });
  await assert.rejects(() => store.readSession(SESSION_2), { code: "SESSION_NOT_FOUND" });

  await assert.rejects(
    () => store.createSession(newSession(SESSION_1, { state: "complete" })),
    { code: "TERMINAL_SESSION_STATE" },
  );
  await assert.rejects(
    () => store.deleteSession(SESSION_1, "expired"),
    { code: "INVALID_SESSION_OUTCOME" },
  );
});

test("only allowlisted session keys are accepted", async (t) => {
  const { store } = await fixture(t);

  await assert.rejects(
    () => store.createSession({
      ...newSession(),
      unexpected: "value",
    }),
    { code: "UNKNOWN_INPUT_FIELD" },
  );

  const created = await store.createSession({
    ...newSession(),
    org_approval_receipt: { approved: true },
    account_receipt: { account: { Id: "001000000000001AAA", Name: "Example" } },
    resolution_choices: { rows: [], warnings: [] },
    family_manifest: { account_ids: ["001000000000001AAA"] },
    family_approval_receipt: null,
    recovery: { action: "retry" },
  });
  assert.equal(created.recovery.action, "retry");

  await assert.rejects(
    () => store.updateSession(SESSION_1, { expires_at: "2099-01-01T00:00:00.000Z" }),
    { code: "UNKNOWN_INPUT_FIELD" },
  );
});

test("raw results, profiles, relationship context, and tokens are rejected deeply", async (t) => {
  const { store } = await fixture(t);
  const forbidden = [
    { recovery: { profile: { status: "complete" } } },
    { recovery: { relationship_context: {} } },
    { recovery: { relationshipContext: {} } },
    { recovery: { raw_output: "raw" } },
    { recovery: { rawOutput: "raw" } },
    { recovery: { results: [] } },
    { recovery: { records: [] } },
    { recovery: { totalSize: 0, done: true } },
    { recovery: { access_token: "secret" } },
    {
      recovery: {
        snapshot: {
          status: "complete",
          selected_account: {},
          opportunities: [],
          products: [],
          team: [],
        },
      },
    },
  ];

  for (const payload of forbidden) {
    await assert.rejects(
      () => store.createSession(newSession(SESSION_1, payload)),
      { code: "FORBIDDEN_SESSION_DATA" },
    );
  }
  await assert.rejects(
    () => store.createSession(newSession(SESSION_1, {
      request: { schema_version: CONTRACTS.profileResult },
    })),
    { code: "UNSAFE_SESSION_PAYLOAD" },
  );
  await assert.rejects(
    () => store.createSession(newSession(SESSION_1, {
      friendly_org: "Bearer abcdefghijklmnop",
    })),
    { code: "UNSAFE_SESSION_PAYLOAD" },
  );
});

test("session and index reads reject wrong modes and symlinks via no-follow descriptors", async (t) => {
  await t.test("session mode", async (st) => {
    const { store } = await fixture(st);
    await store.createSession(newSession());
    await chmod(store.paths.session(SESSION_1), 0o640);
    await assert.rejects(
      () => store.readSession(SESSION_1),
      { code: "INSECURE_INPUT_PERMISSIONS" },
    );
  });

  await t.test("session symlink", async (st) => {
    const { store } = await fixture(st);
    await store.createSession(newSession());
    const sessionPath = store.paths.session(SESSION_1);
    const target = join(store.paths.sessions_directory, "target.json");
    await unlink(sessionPath);
    await writeFile(target, "{}\n", { mode: 0o600 });
    await symlink(target, sessionPath);
    await assert.rejects(() => store.readSession(SESSION_1), { code: "UNSAFE_INPUT_PATH" });
  });

  await t.test("session index mode", async (st) => {
    const { store } = await fixture(st);
    await store.initialize();
    await chmod(store.paths.session_index, 0o400);
    await assert.rejects(
      () => store.readSessionIndex(),
      { code: "INSECURE_INPUT_PERMISSIONS" },
    );
  });

  await t.test("session index symlink", async (st) => {
    const { store } = await fixture(st);
    await store.initialize();
    const target = join(store.paths.skill_directory, "target-index.json");
    await unlink(store.paths.session_index);
    await writeFile(target, '{"schema_version":"decoy","entries":[]}\n', { mode: 0o600 });
    await symlink(target, store.paths.session_index);
    await assert.rejects(
      () => store.readSessionIndex(),
      { code: "UNSAFE_INPUT_PATH" },
    );
  });
});

test("skill and sessions directories are rechecked and reject symlink replacement", async (t) => {
  const { store, stateRoot } = await fixture(t);
  await store.initialize();
  await rm(store.paths.sessions_directory, { recursive: true });
  const target = join(stateRoot, "decoy-sessions");
  await mkdir(target, { mode: 0o700 });
  await symlink(target, store.paths.sessions_directory);

  await assert.rejects(() => store.readSessionIndex(), { code: "UNSAFE_STATE_PATH" });
});

test("org registry uses a distinct confidential envelope and atomic private file", async (t) => {
  const { store } = await fixture(t);
  const first = {
    schema_version: CONTRACTS.orgRegistry,
    classification: CLASSIFICATION,
    entries: [{ anything: "storage remains semantically generic" }],
  };

  assert.deepEqual(await store.readOrgRegistry(), {
    schema_version: CONTRACTS.orgRegistry,
    classification: CLASSIFICATION,
    entries: [],
  });
  assert.deepEqual(await store.writeOrgRegistry(first), first);
  assert.equal((await stat(store.paths.org_registry)).mode & 0o777, 0o600);
  assert.deepEqual(await store.readOrgRegistry(), first);

  const second = {
    ...first,
    entries: [{ arbitrary: "replacement" }],
  };
  assert.deepEqual(await store.writeOrgRegistry(second), second);
  assert.deepEqual(await store.readOrgRegistry(), second);
  const third = await store.updateOrgRegistry((current) => ({
    ...current,
    entries: [...current.entries, { added: "under one lock" }],
  }));
  assert.deepEqual(third.entries, [
    { arbitrary: "replacement" },
    { added: "under one lock" },
  ]);
  assert.deepEqual(await store.readOrgRegistry(), third);
  assert.equal(
    (await readdir(store.paths.skill_directory)).some((name) => name.endsWith(".tmp")),
    false,
  );
});

test("org-registry semantic module output round-trips without entry interpretation", async (t) => {
  const { store } = await fixture(t);
  const entry = buildOfflineRegistryEntry({
    alias: "synthetic",
    friendlyLabel: "Synthetic UAT",
    identity: {
      org_id: "00D000000000001AAA",
      username: "synthetic@example.invalid",
      instance_url: "https://synthetic.example.invalid",
      connected_status: "Connected",
    },
    orgType: "sandbox",
    environment: "sandbox",
    now: new Date(START),
  });
  const registry = upsertRegistryEntry(emptyOrgRegistry(), entry);

  assert.deepEqual(await store.writeOrgRegistry(registry), registry);
  assert.deepEqual(await store.readOrgRegistry(), registry);
});

test("org registry rejects unsafe envelopes, modes, and symlinks", async (t) => {
  await t.test("envelope", async (st) => {
    const { store } = await fixture(st);
    await assert.rejects(
      () => store.writeOrgRegistry({
        schema_version: CONTRACTS.orgRegistry,
        classification: CLASSIFICATION,
        entries: [],
        extra: true,
      }),
      { code: "UNKNOWN_INPUT_FIELD" },
    );
  });

  await t.test("mode", async (st) => {
    const { store } = await fixture(st);
    await store.writeOrgRegistry({
      schema_version: CONTRACTS.orgRegistry,
      classification: CLASSIFICATION,
      entries: [],
    });
    await chmod(store.paths.org_registry, 0o640);
    await assert.rejects(
      () => store.readOrgRegistry(),
      { code: "INSECURE_INPUT_PERMISSIONS" },
    );
  });

  await t.test("symlink", async (st) => {
    const { store } = await fixture(st);
    await store.initialize();
    const target = join(store.paths.skill_directory, "target-registry.json");
    await writeFile(target, `${JSON.stringify({
      schema_version: CONTRACTS.orgRegistry,
      classification: CLASSIFICATION,
      entries: [],
    })}\n`, { mode: 0o600 });
    await symlink(target, store.paths.org_registry);
    await assert.rejects(
      () => store.readOrgRegistry(),
      { code: "UNSAFE_INPUT_PATH" },
    );
  });

  await t.test("malformed existing registry is not overwritten", async (st) => {
    const { store } = await fixture(st);
    const valid = {
      schema_version: CONTRACTS.orgRegistry,
      classification: CLASSIFICATION,
      entries: [],
    };
    await store.writeOrgRegistry(valid);
    await writeFile(store.paths.org_registry, "{not-json}\n", { mode: 0o600 });
    await assert.rejects(
      () => store.writeOrgRegistry(valid),
      { code: "INVALID_STATE_JSON" },
    );
    assert.equal(await readFile(store.paths.org_registry, "utf8"), "{not-json}\n");
  });
});

test("session index read/write is strict, canonical, and metadata-only", async (t) => {
  const { store } = await fixture(t);
  const entries = [
    indexEntry(SESSION_2, "account_choice", 1_000),
    indexEntry(SESSION_1, "new", 0),
  ];

  assert.deepEqual(await store.writeSessionIndex(entries), [
    entries[1],
    entries[0],
  ]);
  assert.deepEqual(await store.readSessionIndex(), [
    entries[1],
    entries[0],
  ]);
  const stored = JSON.parse(await readFile(store.paths.session_index, "utf8"));
  assert.equal(stored.schema_version, stateStoreContracts.session_index_schema);
  assert.deepEqual(stored.entries, [entries[1], entries[0]]);

  await assert.rejects(
    () => store.writeSessionIndex([{ ...entries[0], raw_output: "forbidden" }]),
    { code: "UNKNOWN_INPUT_FIELD" },
  );
  await assert.rejects(
    () => store.writeSessionIndex([entries[0], entries[0]]),
    { code: "INVALID_SESSION_REGISTRY" },
  );

  await writeFile(store.paths.session_index, "{not-json}\n", { mode: 0o600 });
  await assert.rejects(
    () => store.writeSessionIndex(entries),
    { code: "INVALID_STATE_JSON" },
  );
  assert.equal(await readFile(store.paths.session_index, "utf8"), "{not-json}\n");
});
