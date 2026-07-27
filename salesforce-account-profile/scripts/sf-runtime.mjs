import { createHash } from "node:crypto";
import { access, realpath, writeFile } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, isAbsolute, join, resolve } from "node:path";

import { CAPS, CONTRACTS } from "./constants.mjs";
import {
  assertExactKeys,
  canonicalJson,
  digest,
  hashStableRegularFile,
  readStableRegularFile,
  SafetyError,
  statRegularFileNoFollow,
} from "./security.mjs";

const SHA256 = /^[a-f0-9]{64}$/;
const SEMVER = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/;
const FILE_KEYS = Object.freeze([
  "canonical_path",
  "sha256",
  "device",
  "inode",
  "size",
  "mode",
  "uid",
  "mtime_ms",
  "ctime_ms",
]);
const PERMISSION_WARNINGS = new Set([
  "NODE_GROUP_WRITABLE",
  "SF_ENTRYPOINT_GROUP_WRITABLE",
  "PACKAGE_METADATA_GROUP_WRITABLE",
]);

function currentUid() {
  if (typeof process.getuid !== "function") {
    throw new SafetyError("UNSUPPORTED_RUNTIME", "Salesforce runtime attestation currently requires macOS or Linux");
  }
  return process.getuid();
}

function validateExecutableOwnership(metadata) {
  if ((metadata.mode & 0o002) !== 0 || ![0, currentUid()].includes(metadata.uid)) {
    throw new SafetyError(
      "INSECURE_INPUT_PERMISSIONS",
      "Runtime files must be owned by the current user or root and must not be world-writable",
    );
  }
}

function fileFingerprint(path, sha256, metadata) {
  return {
    canonical_path: path,
    sha256,
    device: String(metadata.dev),
    inode: String(metadata.ino),
    size: metadata.size,
    mode: metadata.mode & 0o777,
    uid: metadata.uid,
    mtime_ms: metadata.mtimeMs,
    ctime_ms: metadata.ctimeMs,
  };
}

async function fingerprintExecutable(path) {
  const result = await hashStableRegularFile(path, {
    maximumBytes: CAPS.executableBytes,
    forbidGroupOtherWrite: false,
  });
  validateExecutableOwnership(result.metadata);
  return {
    fingerprint: fileFingerprint(path, result.sha256, result.metadata),
    prefix: result.prefix.toString("utf8"),
  };
}

async function fingerprintPackageJson(path) {
  const { bytes, metadata } = await readStableRegularFile(path, {
    maximumBytes: CAPS.packageMetadataBytes,
    forbidGroupOtherWrite: false,
  });
  validateExecutableOwnership(metadata);
  let parsed;
  try {
    parsed = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new SafetyError("INVALID_SF_RUNTIME", "Salesforce CLI package metadata is not valid JSON");
  }
  return {
    fingerprint: fileFingerprint(
      path,
      createHash("sha256").update(bytes).digest("hex"),
      metadata,
    ),
    parsed,
  };
}

async function findPackageJson(entrypoint) {
  let current = dirname(entrypoint);
  for (let depth = 0; depth < 8; depth += 1) {
    const candidate = join(current, "package.json");
    try {
      const canonical = await realpath(candidate);
      const result = await fingerprintPackageJson(canonical);
      if (result.parsed.name === "@salesforce/cli") return { path: canonical, ...result };
    } catch (error) {
      if (error instanceof SafetyError && error.code !== "UNSAFE_INPUT_PATH") throw error;
    }
    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }
  throw new SafetyError("INVALID_SF_RUNTIME", "Could not bind the Salesforce CLI entrypoint to @salesforce/cli package metadata");
}

async function findSfEntrypoint(pathEnv) {
  const directories = [...new Set(pathEnv.split(delimiter).filter((entry) => entry && isAbsolute(entry)))];
  for (const directory of directories) {
    const candidate = join(directory, "sf");
    try {
      await access(candidate, fsConstants.X_OK);
      return await realpath(candidate);
    } catch {
      // Continue through the bounded PATH list.
    }
  }
  throw new SafetyError("SF_EXECUTABLE_NOT_FOUND", "Salesforce CLI was not found for explicit runtime enrollment");
}

function validateFileFingerprint(file, label) {
  assertExactKeys(file, FILE_KEYS, FILE_KEYS, label);
  if (typeof file.canonical_path !== "string"
    || !isAbsolute(file.canonical_path)
    || !SHA256.test(file.sha256)
    || !/^\d+$/.test(file.device)
    || !/^\d+$/.test(file.inode)
    || !Number.isInteger(file.size)
    || file.size < 1
    || !Number.isInteger(file.mode)
    || !Number.isInteger(file.uid)
    || typeof file.mtime_ms !== "number"
    || typeof file.ctime_ms !== "number") {
    throw new SafetyError("INVALID_SF_RUNTIME", `${label} fingerprint is invalid`);
  }
}

export function validateSfRuntimeManifest(manifest) {
  assertExactKeys(
    manifest,
    [
      "schema_version",
      "classification",
      "node",
      "sf_entrypoint",
      "package_json",
      "package_name",
      "package_version",
      "permission_warnings",
      "enrolled_at",
      "attestation_digest",
    ],
    [
      "schema_version",
      "classification",
      "node",
      "sf_entrypoint",
      "package_json",
      "package_name",
      "package_version",
      "permission_warnings",
      "enrolled_at",
      "attestation_digest",
    ],
    "sf_runtime_attestation",
  );
  if (manifest.schema_version !== CONTRACTS.sfRuntimeAttestation
    || manifest.classification !== "confidential"
    || manifest.package_name !== "@salesforce/cli"
    || !SEMVER.test(manifest.package_version)
    || !Array.isArray(manifest.permission_warnings)
    || manifest.permission_warnings.some((warning) => !PERMISSION_WARNINGS.has(warning))
    || new Set(manifest.permission_warnings).size !== manifest.permission_warnings.length
    || !SHA256.test(manifest.attestation_digest)
    || !Number.isFinite(new Date(manifest.enrolled_at).getTime())
    || new Date(manifest.enrolled_at).toISOString() !== manifest.enrolled_at) {
    throw new SafetyError("INVALID_SF_RUNTIME", "Salesforce CLI runtime attestation metadata is invalid");
  }
  validateFileFingerprint(manifest.node, "sf_runtime_attestation.node");
  validateFileFingerprint(manifest.sf_entrypoint, "sf_runtime_attestation.sf_entrypoint");
  validateFileFingerprint(manifest.package_json, "sf_runtime_attestation.package_json");
  const core = Object.fromEntries(
    Object.entries(manifest).filter(([key]) => key !== "attestation_digest"),
  );
  if (digest(core) !== manifest.attestation_digest) {
    throw new SafetyError("INVALID_SF_RUNTIME", "Salesforce CLI runtime attestation digest is invalid");
  }
  return manifest;
}

export async function discoverSfRuntime({
  pathEnv = process.env.PATH ?? "",
  nodePath = process.execPath,
  now = new Date(),
} = {}) {
  const canonicalNode = await realpath(nodePath);
  const canonicalEntrypoint = await findSfEntrypoint(pathEnv);
  const [node, sfEntrypoint, packageJson] = await Promise.all([
    fingerprintExecutable(canonicalNode),
    fingerprintExecutable(canonicalEntrypoint),
    findPackageJson(canonicalEntrypoint),
  ]);
  if (!/^#![^\r\n]*\bnode\b/u.test(sfEntrypoint.prefix)) {
    throw new SafetyError("INVALID_SF_RUNTIME", "Salesforce CLI entrypoint is not an attested Node launcher");
  }
  if (!SEMVER.test(packageJson.parsed.version ?? "")) {
    throw new SafetyError("INVALID_SF_RUNTIME", "Salesforce CLI package version is invalid");
  }
  const permissionWarnings = [
    ...(node.fingerprint.mode & 0o020 ? ["NODE_GROUP_WRITABLE"] : []),
    ...(sfEntrypoint.fingerprint.mode & 0o020 ? ["SF_ENTRYPOINT_GROUP_WRITABLE"] : []),
    ...(packageJson.fingerprint.mode & 0o020 ? ["PACKAGE_METADATA_GROUP_WRITABLE"] : []),
  ];
  const core = {
    schema_version: CONTRACTS.sfRuntimeAttestation,
    classification: "confidential",
    node: node.fingerprint,
    sf_entrypoint: sfEntrypoint.fingerprint,
    package_json: packageJson.fingerprint,
    package_name: packageJson.parsed.name,
    package_version: packageJson.parsed.version,
    permission_warnings: permissionWarnings,
    enrolled_at: (now instanceof Date ? now : new Date(now)).toISOString(),
  };
  return validateSfRuntimeManifest({ ...core, attestation_digest: digest(core) });
}

async function verifyFingerprint(expected, { executable }) {
  if (await realpath(expected.canonical_path) !== expected.canonical_path) {
    throw new SafetyError("SF_EXECUTABLE_REATTESTATION_REQUIRED", "Salesforce CLI runtime path changed after enrollment");
  }
  const current = executable
    ? (await fingerprintExecutable(expected.canonical_path)).fingerprint
    : (await fingerprintPackageJson(expected.canonical_path)).fingerprint;
  if (canonicalJson(current) !== canonicalJson(expected)) {
    throw new SafetyError("SF_EXECUTABLE_REATTESTATION_REQUIRED", "Salesforce CLI runtime changed after enrollment");
  }
}

export async function verifySfRuntimeManifest(manifest) {
  validateSfRuntimeManifest(manifest);
  await verifyFingerprint(manifest.node, { executable: true });
  await verifyFingerprint(manifest.sf_entrypoint, { executable: true });
  const packageResult = await fingerprintPackageJson(manifest.package_json.canonical_path);
  if (canonicalJson(packageResult.fingerprint) !== canonicalJson(manifest.package_json)
    || packageResult.parsed.name !== manifest.package_name
    || packageResult.parsed.version !== manifest.package_version) {
    throw new SafetyError("SF_EXECUTABLE_REATTESTATION_REQUIRED", "Salesforce CLI package metadata changed after enrollment");
  }
  return {
    executable: manifest.node.canonical_path,
    fixedArgs: ["--no-deprecation", manifest.sf_entrypoint.canonical_path],
    attestationDigest: manifest.attestation_digest,
  };
}

export async function verifySfRuntimeMetadata(manifest) {
  validateSfRuntimeManifest(manifest);
  for (const expected of [manifest.node, manifest.sf_entrypoint, manifest.package_json]) {
    if (await realpath(expected.canonical_path) !== expected.canonical_path) {
      throw new SafetyError("SF_EXECUTABLE_REATTESTATION_REQUIRED", "Salesforce CLI runtime path changed after enrollment");
    }
    const metadata = await statRegularFileNoFollow(expected.canonical_path, {
      forbidGroupOtherWrite: false,
    });
    validateExecutableOwnership(metadata);
    const current = fileFingerprint(expected.canonical_path, expected.sha256, metadata);
    if (canonicalJson(current) !== canonicalJson(expected)) {
      throw new SafetyError("SF_EXECUTABLE_REATTESTATION_REQUIRED", "Salesforce CLI runtime metadata changed after enrollment");
    }
  }
  return {
    executable: manifest.node.canonical_path,
    fixedArgs: ["--no-deprecation", manifest.sf_entrypoint.canonical_path],
    attestationDigest: manifest.attestation_digest,
  };
}

export function defaultSfRuntimeManifestPath() {
  const codexHome = process.env.CODEX_HOME
    ? resolve(process.env.CODEX_HOME)
    : join(homedir(), ".codex");
  return join(codexHome, "state", "salesforce-account-profile", "sf-runtime.json");
}

export async function loadVerifiedSfRuntime(path = defaultSfRuntimeManifestPath()) {
  let bytes;
  try {
    ({ bytes } = await readStableRegularFile(path, {
      maximumBytes: CAPS.runtimeManifestBytes,
      requiredMode: 0o600,
    }));
  } catch (error) {
    if (error instanceof SafetyError) {
      throw new SafetyError(
        "SF_RUNTIME_NOT_ENROLLED",
        "Run the conversational doctor setup before Salesforce access",
      );
    }
    throw error;
  }
  let manifest;
  try {
    manifest = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new SafetyError("INVALID_SF_RUNTIME", "Salesforce CLI runtime attestation is malformed");
  }
  const command = await verifySfRuntimeManifest(manifest);
  return { manifest, command };
}

export async function writeSfRuntimeManifest(path, manifest) {
  validateSfRuntimeManifest(manifest);
  await writeFile(path, `${canonicalJson(manifest)}\n`, {
    mode: 0o600,
    flag: "wx",
  });
}
