import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CAPS,
  CONTRACTS,
  FIELD_MAP_VERSION,
} from "./constants.mjs";
import {
  digest,
  readStableRegularFile,
  SafetyError,
} from "./security.mjs";

const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const CRITICAL_FILES = Object.freeze([
  "../references/field-map.v1.json",
  "account-profile.mjs",
  "advanced-execution.mjs",
  "approval-trust.mjs",
  "certification-contracts.mjs",
  "certification-evidence.mjs",
  "certification.mjs",
  "constants.mjs",
  "contracts.mjs",
  "conversational-contracts.mjs",
  "metadata-compatibility.mjs",
  "orchestrator.mjs",
  "org-registry.mjs",
  "package-attestation.mjs",
  "profile-hydration.mjs",
  "profile-view.mjs",
  "read-plan.mjs",
  "recovery.mjs",
  "render.mjs",
  "resolution-choice.mjs",
  "security.mjs",
  "sf-client.mjs",
  "sf-runtime.mjs",
  "state-store.mjs",
  "workflow.mjs",
]);

function fileHash(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

export async function attestCertificationPackage() {
  const files = [];
  for (const relativePath of CRITICAL_FILES) {
    const absolutePath = join(SCRIPT_DIRECTORY, relativePath);
    const { bytes } = await readStableRegularFile(absolutePath, {
      maximumBytes: CAPS.inputBytes,
      forbidGroupOtherWrite: true,
    });
    files.push({
      path: relativePath,
      sha256: fileHash(bytes),
      bytes: bytes.length,
    });
  }
  if (files.some((item, index) =>
    index > 0 && item.path <= files[index - 1].path)) {
    throw new SafetyError(
      "INVALID_PACKAGE_ATTESTATION",
      "Certification-critical package files are not in canonical order",
    );
  }
  const core = {
    schema_version: CONTRACTS.packageAttestation,
    field_map_version: FIELD_MAP_VERSION,
    files,
  };
  return {
    ...core,
    package_digest: digest(core),
  };
}

export const packageAttestationInternals = Object.freeze({
  CRITICAL_FILES,
  fileHash,
});
