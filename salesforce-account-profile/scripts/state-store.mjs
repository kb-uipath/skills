import { randomBytes } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  chmod,
  link,
  lstat,
  mkdir,
  open,
  rename,
  unlink,
} from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, join } from "node:path";

import {
  CAPS,
  CLASSIFICATION,
  CONTRACTS,
  SESSION_TTL_MS,
} from "./constants.mjs";
import { validateReadPlan } from "./read-plan.mjs";
import {
  assertExactKeys,
  canonicalJson,
  readStableRegularFile,
  SafetyError,
  sanitizeText,
  validateAlias,
} from "./security.mjs";

const SESSION_SCHEMA = CONTRACTS.session;
const SESSION_INDEX_SCHEMA = "salesforce-account-profile-session-index/v1";
const SESSION_ID = /^[a-f0-9]{32}$/;
const SESSION_STATES = Object.freeze([
  "new",
  "org_confirmation",
  "account_resolution",
  "account_choice",
  "family_approval",
  "executing",
  "complete",
]);
const PAYLOAD_KEYS = Object.freeze([
  "target_org",
  "friendly_org",
  "request",
  "read_plan",
  "org_approval_receipt",
  "account_receipt",
  "resolution_choices",
  "family_manifest",
  "family_approval_receipt",
  "query_count",
  "pending_action",
  "recovery",
]);
const SESSION_FILE_KEYS = Object.freeze([
  "schema_version",
  "session_id",
  "state",
  "created_at",
  "updated_at",
  "expires_at",
  ...PAYLOAD_KEYS,
]);
const SESSION_CREATE_KEYS = Object.freeze([
  "session_id",
  "state",
  ...PAYLOAD_KEYS,
]);
const SESSION_PATCH_KEYS = Object.freeze([
  "state",
  ...PAYLOAD_KEYS,
]);
const REGISTRY_ENTRY_KEYS = Object.freeze([
  "session_id",
  "state",
  "created_at",
  "updated_at",
  "expires_at",
]);
const FORBIDDEN_EXACT_KEYS = new Set([
  "relationship_context",
  "raw_output",
  "result",
  "results",
  "records",
  "totalsize",
  "done",
  "attributes",
]);
const TOKEN_VALUE = /(?:Bearer\s+[A-Za-z0-9._~+/-]+=*|00D[A-Za-z0-9]{10,}![A-Za-z0-9._-]{10,})/i;
const MAX_JSON_DEPTH = 40;
const MAX_LOCK_BYTES = 4_096;
const LOCK_RECLAIM_ATTEMPTS = 3;

function compareText(left, right) {
  const a = String(left ?? "");
  const b = String(right ?? "");
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

function cloneJson(value) {
  return JSON.parse(canonicalJson(value));
}

function validateSessionId(sessionId) {
  if (typeof sessionId !== "string" || !SESSION_ID.test(sessionId)) {
    throw new SafetyError("INVALID_SESSION_ID", "session_id must be exactly 32 lowercase hexadecimal characters");
  }
  return sessionId;
}

function validateState(state) {
  if (!SESSION_STATES.includes(state)) {
    throw new SafetyError("INVALID_SESSION_STATE", "Session state is unsupported");
  }
  return state;
}

function canonicalInstant(value, label) {
  if (typeof value !== "string") {
    throw new SafetyError("INVALID_SESSION_STATE", `${label} must be a canonical ISO timestamp`);
  }
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime()) || instant.toISOString() !== value) {
    throw new SafetyError("INVALID_SESSION_STATE", `${label} must be a canonical ISO timestamp`);
  }
  return instant;
}

function currentInstant(now) {
  const value = now();
  const instant = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (!Number.isFinite(instant.getTime())) {
    throw new SafetyError("INVALID_CLOCK", "State-store clock returned an invalid instant");
  }
  return instant;
}

function forbiddenKey(key) {
  const normalized = key.toLowerCase().replace(/-/g, "_");
  const compact = normalized.replace(/_/g, "");
  return normalized.includes("profile")
    || normalized.includes("token")
    || ["authorization", "password", "client_secret"].includes(normalized)
    || FORBIDDEN_EXACT_KEYS.has(normalized)
    || compact.includes("relationshipcontext")
    || compact.includes("rawoutput");
}

function validateJsonValue(value, label, seen = new WeakSet(), depth = 0) {
  if (depth > MAX_JSON_DEPTH) {
    throw new SafetyError("INVALID_SESSION_PAYLOAD", `${label} exceeds the JSON nesting limit`);
  }
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new SafetyError("INVALID_SESSION_PAYLOAD", `${label} contains a non-finite number`);
    }
    return;
  }
  if (typeof value === "string") {
    if (sanitizeText(value) !== value
      || TOKEN_VALUE.test(value)
      || value.includes("salesforce-account-profile-profile-result/")) {
      throw new SafetyError("UNSAFE_SESSION_PAYLOAD", `${label} contains unsafe or token-like text`);
    }
    return;
  }
  if (typeof value !== "object") {
    throw new SafetyError("INVALID_SESSION_PAYLOAD", `${label} is not JSON-compatible`);
  }
  if (seen.has(value)) {
    throw new SafetyError("INVALID_SESSION_PAYLOAD", `${label} contains a cycle`);
  }
  seen.add(value);
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      validateJsonValue(value[index], `${label}[${index}]`, seen, depth + 1);
    }
  } else {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new SafetyError("INVALID_SESSION_PAYLOAD", `${label} must contain plain JSON objects`);
    }
    if (value.status === "complete"
      && "selected_account" in value
      && Array.isArray(value.opportunities)
      && Array.isArray(value.products)
      && Array.isArray(value.team)) {
      throw new SafetyError(
        "FORBIDDEN_SESSION_DATA",
        `${label} contains a completed profile-shaped result`,
      );
    }
    for (const [key, item] of Object.entries(value)) {
      if (forbiddenKey(key)) {
        throw new SafetyError(
          "FORBIDDEN_SESSION_DATA",
          `${label} contains forbidden raw-output, profile, relationship-context, result, or token data`,
        );
      }
      validateJsonValue(item, `${label}.${key}`, seen, depth + 1);
    }
  }
  seen.delete(value);
}

function validatePayload(payload, label) {
  for (const key of PAYLOAD_KEYS) {
    if (!(key in payload)) continue;
    validateJsonValue(payload[key], `${label}.${key}`);
  }
  if ("target_org" in payload && payload.target_org !== null) validateAlias(payload.target_org);
  if ("query_count" in payload
    && payload.query_count !== null
    && (!Number.isInteger(payload.query_count)
      || payload.query_count < 0
      || payload.query_count > CAPS.queries)) {
    throw new SafetyError("INVALID_SESSION_PAYLOAD", "query_count must be null or an integer within the query cap");
  }
  if ("read_plan" in payload && payload.read_plan !== null) {
    validateReadPlan(payload.read_plan);
    if ("session_id" in payload && payload.read_plan.session_id !== payload.session_id) {
      throw new SafetyError("INVALID_SESSION_PAYLOAD", "read_plan.session_id does not match the stored session");
    }
  }
  const encoded = Buffer.byteLength(canonicalJson(payload));
  if (encoded > CAPS.inputBytes) {
    throw new SafetyError("SESSION_TOO_LARGE", "Session state exceeds the private-state size cap");
  }
}

function validateTimeline(record) {
  const createdAt = canonicalInstant(record.created_at, "created_at");
  const updatedAt = canonicalInstant(record.updated_at, "updated_at");
  const expiresAt = canonicalInstant(record.expires_at, "expires_at");
  if (expiresAt.getTime() - createdAt.getTime() !== SESSION_TTL_MS
    || updatedAt < createdAt
    || updatedAt > expiresAt) {
    throw new SafetyError(
      "INVALID_SESSION_STATE",
      "Session timestamps must preserve one exact 30-minute lifetime",
    );
  }
  return { createdAt, updatedAt, expiresAt };
}

function validateStoredSession(session) {
  assertExactKeys(
    session,
    SESSION_FILE_KEYS,
    ["schema_version", "session_id", "state", "created_at", "updated_at", "expires_at"],
    "session",
  );
  if (session.schema_version !== SESSION_SCHEMA) {
    throw new SafetyError("INVALID_SESSION_STATE", "Session schema version is unsupported");
  }
  validateSessionId(session.session_id);
  validateState(session.state);
  validateTimeline(session);
  validatePayload(session, "session");
  if (session.read_plan !== null
    && session.read_plan !== undefined
    && session.read_plan.session_id !== session.session_id) {
    throw new SafetyError("INVALID_SESSION_PAYLOAD", "read_plan.session_id does not match the stored session");
  }
  return session;
}

function validateRegistryEntry(entry, index) {
  assertExactKeys(
    entry,
    REGISTRY_ENTRY_KEYS,
    REGISTRY_ENTRY_KEYS,
    `registry.entries[${index}]`,
  );
  validateSessionId(entry.session_id);
  validateState(entry.state);
  validateTimeline(entry);
  return entry;
}

function canonicalRegistry(entries) {
  if (!Array.isArray(entries)) {
    throw new SafetyError("INVALID_SESSION_REGISTRY", "Registry entries must be an array");
  }
  const validated = entries.map((entry, index) =>
    validateRegistryEntry(cloneJson(entry), index));
  if (new Set(validated.map((entry) => entry.session_id)).size !== validated.length) {
    throw new SafetyError("INVALID_SESSION_REGISTRY", "Registry session IDs must be unique");
  }
  return validated.sort((left, right) => compareText(left.session_id, right.session_id));
}

function sessionIndexDocument(entries) {
  return {
    schema_version: SESSION_INDEX_SCHEMA,
    entries: canonicalRegistry(entries),
  };
}

function validateSessionIndexDocument(document) {
  assertExactKeys(
    document,
    ["schema_version", "entries"],
    ["schema_version", "entries"],
    "session_index",
  );
  if (document.schema_version !== SESSION_INDEX_SCHEMA) {
    throw new SafetyError("INVALID_SESSION_REGISTRY", "Session-index schema version is unsupported");
  }
  const entries = canonicalRegistry(document.entries);
  if (canonicalJson(entries) !== canonicalJson(document.entries)) {
    throw new SafetyError("INVALID_SESSION_REGISTRY", "Registry entries must use canonical session-ID order");
  }
  return entries;
}

function emptyOrgRegistry() {
  return {
    schema_version: CONTRACTS.orgRegistry,
    classification: CLASSIFICATION,
    entries: [],
  };
}

function validateOrgRegistryDocument(document) {
  assertExactKeys(
    document,
    ["schema_version", "classification", "entries"],
    ["schema_version", "classification", "entries"],
    "org_registry",
  );
  if (document.schema_version !== CONTRACTS.orgRegistry
    || document.classification !== CLASSIFICATION
    || !Array.isArray(document.entries)) {
    throw new SafetyError("INVALID_ORG_REGISTRY", "Org registry envelope is invalid");
  }
  validateJsonValue(document.entries, "org_registry.entries");
  if (Buffer.byteLength(canonicalJson(document)) > CAPS.inputBytes) {
    throw new SafetyError("ORG_REGISTRY_TOO_LARGE", "Org registry exceeds the private-state size cap");
  }
  return cloneJson(document);
}

function entryFor(session) {
  return Object.fromEntries(REGISTRY_ENTRY_KEYS.map((key) => [key, session[key]]));
}

function defaultStateRoot() {
  const configured = process.env.CODEX_HOME;
  const codexHome = configured ?? join(homedir(), ".codex");
  if (!isAbsolute(codexHome)) {
    throw new SafetyError("INVALID_STATE_ROOT", "CODEX_HOME must be an absolute path");
  }
  return join(codexHome, "state");
}

function requireAbsoluteRoot(root) {
  if (typeof root !== "string" || !isAbsolute(root)) {
    throw new SafetyError("INVALID_STATE_ROOT", "State root must be an absolute path");
  }
  return root;
}

async function pathMetadata(path) {
  try {
    return await lstat(path);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function ensureDirectory(path, { exactPrivateMode }) {
  await mkdir(path, { recursive: true, mode: 0o700 });
  const before = await lstat(path);
  if (!before.isDirectory() || before.isSymbolicLink()) {
    throw new SafetyError("UNSAFE_STATE_PATH", "State directories must be real directories, not symlinks");
  }
  if (exactPrivateMode) {
    await chmod(path, 0o700);
    const after = await lstat(path);
    if (!after.isDirectory()
      || after.isSymbolicLink()
      || after.dev !== before.dev
      || after.ino !== before.ino
      || (after.mode & 0o777) !== 0o700) {
      throw new SafetyError("INSECURE_STATE_PERMISSIONS", "Skill and sessions directories require exact mode 0700");
    }
  }
}

function exclusiveFlags() {
  if (!Number.isInteger(fsConstants.O_NOFOLLOW)) {
    throw new SafetyError("UNSAFE_STATE_PATH", "This runtime cannot enforce no-follow state access");
  }
  return fsConstants.O_WRONLY
    | fsConstants.O_CREAT
    | fsConstants.O_EXCL
    | fsConstants.O_NOFOLLOW
    | (fsConstants.O_CLOEXEC ?? 0);
}

async function writeTemporary(path, content) {
  let handle;
  try {
    handle = await open(path, exclusiveFlags(), 0o600);
    await handle.chmod(0o600);
    await handle.writeFile(content, { encoding: "utf8" });
    await handle.sync();
  } finally {
    await handle?.close();
  }
}

async function syncDirectory(directory) {
  let handle;
  try {
    handle = await open(
      directory,
      fsConstants.O_RDONLY | (fsConstants.O_DIRECTORY ?? 0) | (fsConstants.O_CLOEXEC ?? 0),
    );
    await handle.sync();
  } finally {
    await handle?.close();
  }
}

function temporaryPath(path) {
  return `${path}.${process.pid}.${randomBytes(12).toString("hex")}.tmp`;
}

async function atomicCreate(path, value, existsCode) {
  const temporary = temporaryPath(path);
  await writeTemporary(temporary, `${canonicalJson(value)}\n`);
  try {
    await link(temporary, path);
    await syncDirectory(dirname(path));
  } catch (error) {
    if (error?.code === "EEXIST") {
      throw new SafetyError(existsCode, "Private state target already exists");
    }
    throw error;
  } finally {
    await unlink(temporary).catch(() => {});
  }
}

async function atomicReplace(path, value) {
  await readStableRegularFile(path, {
    maximumBytes: CAPS.inputBytes,
    requiredMode: 0o600,
  });
  const temporary = temporaryPath(path);
  await writeTemporary(temporary, `${canonicalJson(value)}\n`);
  try {
    await rename(temporary, path);
    await syncDirectory(dirname(path));
  } finally {
    await unlink(temporary).catch(() => {});
  }
}

async function readPrivateJson(path, label) {
  const { bytes } = await readStableRegularFile(path, {
    maximumBytes: CAPS.inputBytes,
    requiredMode: 0o600,
  });
  try {
    return JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new SafetyError("INVALID_STATE_JSON", `${label} is not valid JSON`);
  }
}

function validateLockOwner(value) {
  assertExactKeys(
    value,
    ["pid", "acquired_at"],
    ["pid", "acquired_at"],
    "private_lock",
  );
  if (!Number.isSafeInteger(value.pid) || value.pid < 1) {
    throw new SafetyError(
      "INVALID_STATE_LOCK",
      "Private lock owner PID is invalid",
    );
  }
  canonicalInstant(value.acquired_at, "private_lock.acquired_at");
  return value;
}

function processIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code !== "ESRCH";
  }
}

async function readLockOwner(path) {
  const { bytes, metadata } = await readStableRegularFile(path, {
    maximumBytes: MAX_LOCK_BYTES,
    requiredMode: 0o600,
  });
  let parsed;
  try {
    parsed = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new SafetyError(
      "INVALID_STATE_LOCK",
      "Private lock metadata is not valid JSON",
    );
  }
  return {
    owner: validateLockOwner(parsed),
    metadata,
  };
}

async function reclaimDeadLock(path) {
  let observed;
  try {
    observed = await readLockOwner(path);
  } catch {
    // An absent lock is retryable. Malformed or unsafe lock state stays
    // fail-closed because it may belong to a live writer.
    return await pathMetadata(path) === null;
  }
  if (processIsAlive(observed.owner.pid)) return false;
  const current = await pathMetadata(path);
  if (!current) return true;
  if (!current.isFile()
    || current.isSymbolicLink()
    || current.dev !== observed.metadata.dev
    || current.ino !== observed.metadata.ino
    || (current.mode & 0o777) !== 0o600) {
    return false;
  }
  try {
    await unlink(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return true;
    throw error;
  }
}

async function acquireLock(path, code, now) {
  for (let attempt = 0; attempt < LOCK_RECLAIM_ATTEMPTS; attempt += 1) {
    let handle;
    try {
      handle = await open(path, exclusiveFlags(), 0o600);
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      if (attempt < LOCK_RECLAIM_ATTEMPTS - 1
        && await reclaimDeadLock(path)) {
        continue;
      }
      throw new SafetyError(
        code,
        "Private state is already locked by another continuation",
      );
    }
    try {
      await handle.chmod(0o600);
      await handle.writeFile(`${canonicalJson({
        pid: process.pid,
        acquired_at: currentInstant(now).toISOString(),
      })}\n`);
      await handle.sync();
      const identity = await handle.stat();
      return {
        async assertOwned() {
          const current = await lstat(path).catch(() => null);
          if (!current
            || !current.isFile()
            || current.isSymbolicLink()
            || current.dev !== identity.dev
            || current.ino !== identity.ino
            || (current.mode & 0o777) !== 0o600) {
            throw new SafetyError("SESSION_LOCK_LOST", "Private session lock is no longer owned");
          }
        },
        async release() {
          const current = await lstat(path).catch(() => null);
          await handle.close();
          if (current
            && current.isFile()
            && !current.isSymbolicLink()
            && current.dev === identity.dev
            && current.ino === identity.ino) {
            await unlink(path);
          }
        },
      };
    } catch (error) {
      await handle.close().catch(() => {});
      await unlink(path).catch(() => {});
      throw error;
    }
  }
  throw new SafetyError(
    code,
    "Private state is already locked by another continuation",
  );
}

export function createStateStore({
  stateRoot = defaultStateRoot(),
  now = () => new Date(),
} = {}) {
  const root = requireAbsoluteRoot(stateRoot);
  if (typeof now !== "function") {
    throw new SafetyError("INVALID_CLOCK", "State-store clock must be a function");
  }
  const skillDirectory = join(root, "salesforce-account-profile");
  const sessionsDirectory = join(skillDirectory, "sessions");
  const sessionIndexPath = join(skillDirectory, "session-index.json");
  const sessionIndexLockPath = join(skillDirectory, "session-index.lock");
  const orgRegistryPath = join(skillDirectory, "org-registry.json");
  const orgRegistryLockPath = join(skillDirectory, "org-registry.lock");
  let initialization;

  const sessionPath = (sessionId) =>
    join(sessionsDirectory, `${validateSessionId(sessionId)}.json`);
  const sessionLockPath = (sessionId) =>
    join(sessionsDirectory, `${validateSessionId(sessionId)}.lock`);

  async function initializeStore() {
    await ensureDirectory(root, { exactPrivateMode: false });
    await ensureDirectory(skillDirectory, { exactPrivateMode: true });
    await ensureDirectory(sessionsDirectory, { exactPrivateMode: true });
    try {
      await atomicCreate(sessionIndexPath, sessionIndexDocument([]), "REGISTRY_EXISTS");
    } catch (error) {
      if (error?.code !== "REGISTRY_EXISTS") throw error;
      validateSessionIndexDocument(await readPrivateJson(sessionIndexPath, "Session index"));
    }
  }

  async function initialize() {
    if (!initialization) {
      initialization = initializeStore().catch((error) => {
        initialization = null;
        throw error;
      });
    }
    await initialization;
    await ensureDirectory(root, { exactPrivateMode: false });
    await ensureDirectory(skillDirectory, { exactPrivateMode: true });
    await ensureDirectory(sessionsDirectory, { exactPrivateMode: true });
  }

  async function readSessionIndexUnlocked() {
    const document = await readPrivateJson(sessionIndexPath, "Session index");
    return validateSessionIndexDocument(document);
  }

  async function writeSessionIndexUnlocked(entries) {
    const document = sessionIndexDocument(entries);
    await readSessionIndexUnlocked();
    await atomicReplace(sessionIndexPath, document);
    return cloneJson(document.entries);
  }

  async function withIndexLock(operation) {
    const lock = await acquireLock(sessionIndexLockPath, "STATE_STORE_BUSY", now);
    try {
      await lock.assertOwned();
      const result = await operation();
      await lock.assertOwned();
      return result;
    } finally {
      await lock.release();
    }
  }

  async function readSessionIndex() {
    await initialize();
    return cloneJson(await readSessionIndexUnlocked());
  }

  async function writeSessionIndex(entries) {
    await initialize();
    return await withIndexLock(async () =>
      await writeSessionIndexUnlocked(entries));
  }

  async function readOrgRegistry() {
    await initialize();
    if (!await pathMetadata(orgRegistryPath)) return emptyOrgRegistry();
    return validateOrgRegistryDocument(
      await readPrivateJson(orgRegistryPath, "Org registry"),
    );
  }

  async function writeOrgRegistry(document) {
    await initialize();
    const validated = validateOrgRegistryDocument(cloneJson(document));
    const lock = await acquireLock(orgRegistryLockPath, "STATE_STORE_BUSY", now);
    try {
      await lock.assertOwned();
      if (await pathMetadata(orgRegistryPath)) {
        validateOrgRegistryDocument(
          await readPrivateJson(orgRegistryPath, "Org registry"),
        );
        await atomicReplace(orgRegistryPath, validated);
      } else {
        await atomicCreate(orgRegistryPath, validated, "ORG_REGISTRY_EXISTS");
      }
      await lock.assertOwned();
      return cloneJson(validated);
    } finally {
      await lock.release();
    }
  }

  async function updateOrgRegistry(operation) {
    await initialize();
    if (typeof operation !== "function") {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY_OPERATION",
        "Org registry update requires a function",
      );
    }
    const lock = await acquireLock(
      orgRegistryLockPath,
      "STATE_STORE_BUSY",
      now,
    );
    try {
      await lock.assertOwned();
      const current = await pathMetadata(orgRegistryPath)
        ? validateOrgRegistryDocument(
          await readPrivateJson(orgRegistryPath, "Org registry"),
        )
        : emptyOrgRegistry();
      const next = validateOrgRegistryDocument(cloneJson(
        await operation(cloneJson(current)),
      ));
      if (await pathMetadata(orgRegistryPath)) {
        await atomicReplace(orgRegistryPath, next);
      } else {
        await atomicCreate(
          orgRegistryPath,
          next,
          "ORG_REGISTRY_EXISTS",
        );
      }
      await lock.assertOwned();
      return cloneJson(next);
    } finally {
      await lock.release();
    }
  }

  async function readSessionFile(sessionId, { allowExpired }) {
    const path = sessionPath(sessionId);
    const metadata = await pathMetadata(path);
    if (!metadata) throw new SafetyError("SESSION_NOT_FOUND", "Private session does not exist");
    const session = validateStoredSession(await readPrivateJson(path, "Private session"));
    if (session.session_id !== sessionId) {
      throw new SafetyError("SESSION_ID_MISMATCH", "Session file does not match its filename");
    }
    const expiry = new Date(session.expires_at);
    if (!allowExpired && currentInstant(now) >= expiry) {
      throw new SafetyError("SESSION_EXPIRED", "Private session has reached its 30-minute expiry");
    }
    return session;
  }

  async function readSession(sessionId) {
    await initialize();
    validateSessionId(sessionId);
    return cloneJson(await readSessionFile(sessionId, { allowExpired: false }));
  }

  async function createSession(input) {
    await initialize();
    assertExactKeys(
      input,
      SESSION_CREATE_KEYS,
      ["session_id", "state"],
      "session",
    );
    validateSessionId(input.session_id);
    validateState(input.state);
    if (input.state === "complete") {
      throw new SafetyError("TERMINAL_SESSION_STATE", "Completed sessions must be deleted, not created");
    }
    validatePayload(input, "session");
    const issuedAt = currentInstant(now);
    const session = validateStoredSession({
      schema_version: SESSION_SCHEMA,
      ...cloneJson(input),
      created_at: issuedAt.toISOString(),
      updated_at: issuedAt.toISOString(),
      expires_at: new Date(issuedAt.getTime() + SESSION_TTL_MS).toISOString(),
    });
    const lock = await acquireLock(sessionLockPath(session.session_id), "SESSION_LOCKED", now);
    let created = false;
    try {
      await atomicCreate(sessionPath(session.session_id), session, "SESSION_EXISTS");
      created = true;
      await withIndexLock(async () => {
        const entries = await readSessionIndexUnlocked();
        if (entries.some((entry) => entry.session_id === session.session_id)) {
          throw new SafetyError("SESSION_EXISTS", "Session registry already contains this session");
        }
        await writeSessionIndexUnlocked([...entries, entryFor(session)]);
      });
      return cloneJson(session);
    } catch (error) {
      if (created) await unlink(sessionPath(session.session_id)).catch(() => {});
      throw error;
    } finally {
      await lock.release();
    }
  }

  async function replaceSessionLocked(current, next) {
    await atomicReplace(sessionPath(current.session_id), next);
    try {
      await withIndexLock(async () => {
        const entries = await readSessionIndexUnlocked();
        const index = entries.findIndex((entry) => entry.session_id === current.session_id);
        if (index < 0) {
          throw new SafetyError("SESSION_REGISTRY_MISMATCH", "Session is absent from its registry");
        }
        const replacement = [...entries];
        replacement[index] = entryFor(next);
        await writeSessionIndexUnlocked(replacement);
      });
    } catch (error) {
      await atomicReplace(sessionPath(current.session_id), current).catch(() => {});
      throw error;
    }
    return next;
  }

  async function deleteSessionLocked(sessionId) {
    const path = sessionPath(sessionId);
    const exists = await pathMetadata(path);
    let prior = null;
    if (exists) prior = await readSessionFile(sessionId, { allowExpired: true });
    if (prior) await unlink(path);
    try {
      await withIndexLock(async () => {
        const entries = await readSessionIndexUnlocked();
        await writeSessionIndexUnlocked(entries.filter((entry) => entry.session_id !== sessionId));
      });
    } catch (error) {
      if (prior) await atomicCreate(path, prior, "SESSION_EXISTS").catch(() => {});
      throw error;
    }
    return Boolean(prior);
  }

  async function withSessionLock(sessionId, operation) {
    await initialize();
    validateSessionId(sessionId);
    if (typeof operation !== "function") {
      throw new SafetyError("INVALID_SESSION_OPERATION", "Session continuation must be a function");
    }
    const lock = await acquireLock(sessionLockPath(sessionId), "SESSION_LOCKED", now);
    let deleted = false;
    try {
      const initial = await readSessionFile(sessionId, { allowExpired: false });
      const continuation = Object.freeze({
        session: cloneJson(initial),
        async read() {
          await lock.assertOwned();
          if (deleted) throw new SafetyError("SESSION_NOT_FOUND", "Private session was deleted");
          return cloneJson(await readSessionFile(sessionId, { allowExpired: false }));
        },
        async update(changes) {
          await lock.assertOwned();
          if (deleted) throw new SafetyError("SESSION_NOT_FOUND", "Private session was deleted");
          assertExactKeys(changes, SESSION_PATCH_KEYS, [], "session_update");
          const current = await readSessionFile(sessionId, { allowExpired: false });
          const nextState = changes.state ?? current.state;
          validateState(nextState);
          if (nextState === "complete") {
            await deleteSessionLocked(sessionId);
            deleted = true;
            return null;
          }
          const updatedAt = currentInstant(now);
          if (updatedAt >= new Date(current.expires_at)) {
            throw new SafetyError("SESSION_EXPIRED", "Private session has reached its 30-minute expiry");
          }
          const next = validateStoredSession({
            ...current,
            ...cloneJson(changes),
            state: nextState,
            updated_at: updatedAt.toISOString(),
          });
          validatePayload(next, "session");
          return cloneJson(await replaceSessionLocked(current, next));
        },
        async complete() {
          await lock.assertOwned();
          if (deleted) return false;
          const removed = await deleteSessionLocked(sessionId);
          deleted = true;
          return removed;
        },
        async abort() {
          await lock.assertOwned();
          if (deleted) return false;
          const removed = await deleteSessionLocked(sessionId);
          deleted = true;
          return removed;
        },
      });
      return await operation(continuation);
    } finally {
      await lock.release();
    }
  }

  async function updateSession(sessionId, changes) {
    return await withSessionLock(sessionId, async (continuation) =>
      await continuation.update(changes));
  }

  async function deleteSession(sessionId, outcome) {
    if (!["abort", "complete"].includes(outcome)) {
      throw new SafetyError("INVALID_SESSION_OUTCOME", "Session deletion requires abort or complete");
    }
    return await withSessionLock(sessionId, async (continuation) =>
      outcome === "abort"
        ? await continuation.abort()
        : await continuation.complete());
  }

  async function listSessions({ includeExpired = false } = {}) {
    await initialize();
    if (typeof includeExpired !== "boolean") {
      throw new SafetyError("INVALID_LIST_OPTIONS", "includeExpired must be boolean");
    }
    const current = currentInstant(now);
    const entries = await readSessionIndexUnlocked();
    const listed = [];
    for (const entry of entries) {
      const expired = current >= new Date(entry.expires_at);
      if (expired && !includeExpired) continue;
      const session = await readSessionFile(entry.session_id, { allowExpired: true });
      if (canonicalJson(entryFor(session)) !== canonicalJson(entry)) {
        throw new SafetyError("SESSION_REGISTRY_MISMATCH", "Session metadata does not match its registry entry");
      }
      listed.push(entry);
    }
    return cloneJson(listed);
  }

  async function cleanupExpiredSessions() {
    await initialize();
    const current = currentInstant(now);
    const entries = await readSessionIndexUnlocked();
    const expired = entries
      .filter((entry) => current >= new Date(entry.expires_at))
      .map((entry) => entry.session_id);
    const deleted = [];
    const locked = [];
    for (const sessionId of expired) {
      let lock;
      try {
        lock = await acquireLock(sessionLockPath(sessionId), "SESSION_LOCKED", now);
      } catch (error) {
        if (error?.code === "SESSION_LOCKED") {
          locked.push(sessionId);
          continue;
        }
        throw error;
      }
      try {
        await deleteSessionLocked(sessionId);
        deleted.push(sessionId);
      } finally {
        await lock.release();
      }
    }
    return { deleted, locked };
  }

  return Object.freeze({
    paths: Object.freeze({
      state_root: root,
      skill_directory: skillDirectory,
      sessions_directory: sessionsDirectory,
      session_index: sessionIndexPath,
      session_index_lock: sessionIndexLockPath,
      org_registry: orgRegistryPath,
      org_registry_lock: orgRegistryLockPath,
      session: sessionPath,
      session_lock: sessionLockPath,
    }),
    initialize,
    readSessionIndex,
    writeSessionIndex,
    readOrgRegistry,
    updateOrgRegistry,
    writeOrgRegistry,
    createSession,
    readSession,
    updateSession,
    withSessionLock,
    listSessions,
    cleanupExpiredSessions,
    deleteSession,
  });
}

export const stateStoreContracts = Object.freeze({
  session_schema: SESSION_SCHEMA,
  session_index_schema: SESSION_INDEX_SCHEMA,
  org_registry_schema: CONTRACTS.orgRegistry,
  session_states: SESSION_STATES,
  payload_keys: PAYLOAD_KEYS,
});
