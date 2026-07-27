import { createHash } from "node:crypto";
import { open, writeFile } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";

import { CAPS } from "./constants.mjs";

const CONTROL_BIDI_ANSI = /(?:\u001b\[[0-?]*[ -/]*[@-~]|[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069])/gu;
const TOKEN_KEYS = /(?:access[_-]?token|refresh[_-]?token|authorization|client[_-]?secret|password|session(?:id)?|bearer)/i;
const TOKEN_VALUES = /(?:Bearer\s+[A-Za-z0-9._~+/-]+=*|00D[A-Za-z0-9]{10,}![A-Za-z0-9._-]{10,})/gi;

export class SafetyError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "SafetyError";
    this.code = code;
    this.details = details;
  }
}

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function digest(value) {
  return createHash("sha256").update(canonicalJson(value)).digest("hex");
}

export function sanitizeText(value) {
  if (value === null || value === undefined) return value;
  return String(value).normalize("NFC").replace(CONTROL_BIDI_ANSI, "").replace(TOKEN_VALUES, "[REDACTED]");
}

export function markdownText(value) {
  return sanitizeText(value)
    .replace(/\\/g, "\\\\")
    .replace(/([`*_[\]{}()#+.!|<>-])/g, "\\$1")
    .replace(/\r?\n/g, " ");
}

export function redactDeep(value) {
  if (Array.isArray(value)) return value.map(redactDeep);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key,
      TOKEN_KEYS.test(key) ? "[REDACTED]" : redactDeep(item),
    ]));
  }
  return typeof value === "string" ? sanitizeText(value) : value;
}

export function assertExactKeys(object, allowed, required, label) {
  if (!object || typeof object !== "object" || Array.isArray(object)) {
    throw new SafetyError("INVALID_INPUT", `${label} must be an object`);
  }
  for (const key of Object.keys(object)) {
    if (!allowed.includes(key)) throw new SafetyError("UNKNOWN_INPUT_FIELD", `${label}.${key} is not allowed`);
  }
  for (const key of required) {
    if (!(key in object)) throw new SafetyError("MISSING_INPUT_FIELD", `${label}.${key} is required`);
  }
}

export async function readStableRegularFile(path, {
  maximumBytes,
  requiredMode = null,
  forbidGroupOtherWrite = false,
} = {}) {
  if (!Number.isInteger(maximumBytes) || maximumBytes < 1) {
    throw new SafetyError("INTERNAL_ERROR", "A positive file-size cap is required");
  }
  const noFollow = fsConstants.O_NOFOLLOW;
  if (!Number.isInteger(noFollow)) {
    throw new SafetyError("UNSAFE_INPUT_PATH", "This runtime cannot enforce no-follow file access");
  }
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_RDONLY | noFollow | (fsConstants.O_CLOEXEC ?? 0) | (fsConstants.O_NONBLOCK ?? 0),
    );
  } catch {
    throw new SafetyError("UNSAFE_INPUT_PATH", "Path must be an existing regular non-symlink file");
  }
  try {
    const before = await handle.stat();
    if (!before.isFile()) {
      throw new SafetyError("UNSAFE_INPUT_PATH", "Path must be a regular non-symlink file");
    }
    if (requiredMode !== null && (before.mode & 0o777) !== requiredMode) {
      throw new SafetyError("INSECURE_INPUT_PERMISSIONS", `File must have exact mode ${requiredMode.toString(8).padStart(4, "0")}`);
    }
    if (forbidGroupOtherWrite && (before.mode & 0o022) !== 0) {
      throw new SafetyError("INSECURE_INPUT_PERMISSIONS", "File must not be group- or world-writable");
    }
    if (before.size > maximumBytes) throw new SafetyError("INPUT_TOO_LARGE", "File exceeds the size cap");
    const bytes = await handle.readFile();
    const after = await handle.stat();
    if (bytes.length > maximumBytes) throw new SafetyError("INPUT_TOO_LARGE", "File exceeds the size cap");
    if (before.dev !== after.dev
      || before.ino !== after.ino
      || before.size !== after.size
      || before.mtimeMs !== after.mtimeMs
      || before.ctimeMs !== after.ctimeMs
      || bytes.length !== after.size) {
      throw new SafetyError("INPUT_CHANGED", "File changed while it was being read");
    }
    return { bytes, metadata: after };
  } finally {
    await handle.close();
  }
}

export async function hashStableRegularFile(path, {
  maximumBytes,
  forbidGroupOtherWrite = false,
} = {}) {
  if (!Number.isInteger(maximumBytes) || maximumBytes < 1) {
    throw new SafetyError("INTERNAL_ERROR", "A positive file-size cap is required");
  }
  const noFollow = fsConstants.O_NOFOLLOW;
  if (!Number.isInteger(noFollow)) {
    throw new SafetyError("UNSAFE_INPUT_PATH", "This runtime cannot enforce no-follow file access");
  }
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_RDONLY | noFollow | (fsConstants.O_CLOEXEC ?? 0) | (fsConstants.O_NONBLOCK ?? 0),
    );
  } catch {
    throw new SafetyError("UNSAFE_INPUT_PATH", "Path must be an existing regular non-symlink file");
  }
  try {
    const before = await handle.stat();
    if (!before.isFile()) throw new SafetyError("UNSAFE_INPUT_PATH", "Path must be a regular non-symlink file");
    if ((before.mode & 0o111) === 0) throw new SafetyError("UNSAFE_INPUT_PATH", "Executable file is not executable");
    if (forbidGroupOtherWrite && (before.mode & 0o022) !== 0) {
      throw new SafetyError("INSECURE_INPUT_PERMISSIONS", "Executable must not be group- or world-writable");
    }
    if (before.size > maximumBytes) throw new SafetyError("INPUT_TOO_LARGE", "File exceeds the size cap");
    const hash = createHash("sha256");
    const chunk = Buffer.allocUnsafe(64 * 1024);
    const prefix = Buffer.alloc(Math.min(256, before.size));
    let position = 0;
    while (position < before.size) {
      const length = Math.min(chunk.length, before.size - position);
      const { bytesRead } = await handle.read(chunk, 0, length, position);
      if (bytesRead === 0) break;
      if (position < prefix.length) {
        chunk.copy(prefix, position, 0, Math.min(bytesRead, prefix.length - position));
      }
      hash.update(chunk.subarray(0, bytesRead));
      position += bytesRead;
      if (position > maximumBytes) throw new SafetyError("INPUT_TOO_LARGE", "File exceeds the size cap");
    }
    const after = await handle.stat();
    if (before.dev !== after.dev
      || before.ino !== after.ino
      || before.size !== after.size
      || before.mtimeMs !== after.mtimeMs
      || before.ctimeMs !== after.ctimeMs
      || position !== after.size) {
      throw new SafetyError("INPUT_CHANGED", "File changed while it was being hashed");
    }
    return {
      sha256: hash.digest("hex"),
      prefix,
      metadata: after,
    };
  } finally {
    await handle.close();
  }
}

export async function statRegularFileNoFollow(path, { forbidGroupOtherWrite = false } = {}) {
  const noFollow = fsConstants.O_NOFOLLOW;
  if (!Number.isInteger(noFollow)) {
    throw new SafetyError("UNSAFE_INPUT_PATH", "This runtime cannot enforce no-follow file access");
  }
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_RDONLY | noFollow | (fsConstants.O_CLOEXEC ?? 0) | (fsConstants.O_NONBLOCK ?? 0),
    );
  } catch {
    throw new SafetyError("UNSAFE_INPUT_PATH", "Path must be an existing regular non-symlink file");
  }
  try {
    const metadata = await handle.stat();
    if (!metadata.isFile()) throw new SafetyError("UNSAFE_INPUT_PATH", "Path must be a regular non-symlink file");
    if (forbidGroupOtherWrite && (metadata.mode & 0o022) !== 0) {
      throw new SafetyError("INSECURE_INPUT_PERMISSIONS", "File must not be group- or world-writable");
    }
    return metadata;
  } finally {
    await handle.close();
  }
}

export async function readJsonInput(path, stdin) {
  let bytes;
  if (path) {
    ({ bytes } = await readStableRegularFile(path, {
      maximumBytes: CAPS.inputBytes,
      requiredMode: 0o600,
    }));
  } else {
    const chunks = [];
    let length = 0;
    for await (const chunk of stdin) {
      length += chunk.length;
      if (length > CAPS.inputBytes) throw new SafetyError("INPUT_TOO_LARGE", "Input JSON exceeds the size cap");
      chunks.push(chunk);
    }
    bytes = Buffer.concat(chunks);
  }
  try {
    return JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new SafetyError("INVALID_JSON", "Input is not valid JSON");
  }
}

export async function writeJsonOutput(path, value, stdout) {
  const content = `${canonicalJson(value)}\n`;
  if (!path) {
    stdout.write(content);
    return;
  }
  await writeFile(path, content, { mode: fsConstants.S_IRUSR | fsConstants.S_IWUSR, flag: "wx" });
}

export function escapeSoqlLiteral(value) {
  return sanitizeText(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

export function escapeSoqlLikePrefix(value) {
  return sanitizeText(value).replace(/[\\'%_]/g, (character) => `\\${character}`);
}

export function validateAlias(value) {
  if (typeof value !== "string" || value.length < 1 || value.length > 80 || sanitizeText(value) !== value) {
    throw new SafetyError("INVALID_TARGET_ORG", "target_org must be safe text between 1 and 80 characters");
  }
  return value;
}
