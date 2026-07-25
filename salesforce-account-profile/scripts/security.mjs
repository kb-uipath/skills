import { createHash } from "node:crypto";
import { lstat, readFile, writeFile } from "node:fs/promises";
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

export async function readJsonInput(path, stdin) {
  let bytes;
  if (path) {
    const metadata = await lstat(path);
    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new SafetyError("UNSAFE_INPUT_PATH", "Input must be a regular non-symlink file");
    }
    if ((metadata.mode & 0o077) !== 0) {
      throw new SafetyError("INSECURE_INPUT_PERMISSIONS", "Input JSON file must have mode 0600");
    }
    if (metadata.size > CAPS.inputBytes) throw new SafetyError("INPUT_TOO_LARGE", "Input JSON exceeds the size cap");
    bytes = await readFile(path);
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
  if (typeof value !== "string" || value.length < 1 || value.length > 80 || /[\u0000-\u001f\u007f]/u.test(value)) {
    throw new SafetyError("INVALID_TARGET_ORG", "target_org must be a non-empty alias of at most 80 characters");
  }
  return value;
}
