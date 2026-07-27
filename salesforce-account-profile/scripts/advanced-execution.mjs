import {
  validateProfileRequest,
  validateResolveRequest,
} from "./contracts.mjs";
import {
  assertRegistryReadiness,
  downgradeRegistryReadiness,
  emptyOrgRegistry,
  registryReadinessDigest,
  resolveRegistryEntry,
  validateOrgRegistry,
  verifyRegistryIdentity,
} from "./org-registry.mjs";
import { inspectMetadataCompatibility } from "./metadata-compatibility.mjs";
import { attestCertificationPackage } from "./package-attestation.mjs";
import { digest, SafetyError } from "./security.mjs";
import { createProductionSfClient } from "./sf-client.mjs";
import { createStateStore } from "./state-store.mjs";
import { execute } from "./workflow.mjs";

const ADVANCED_DATA_COMMANDS = new Set(["resolve", "profile"]);
const SHA256 = /^[a-f0-9]{64}$/u;
const RUNTIME_DRIFT_CODES = new Set([
  "INVALID_SF_RUNTIME",
  "SF_EXECUTABLE_REATTESTATION_REQUIRED",
  "SF_RUNTIME_NOT_ENROLLED",
  "UNSUPPORTED_RUNTIME",
]);
const PERSISTED_READINESS_DOWNGRADES = new WeakSet();

function clockFor(dependencies) {
  return () => {
    const value = typeof dependencies.now === "function"
      ? dependencies.now()
      : dependencies.now ?? new Date();
    const instant = value instanceof Date
      ? new Date(value.getTime())
      : new Date(value);
    if (!Number.isFinite(instant.getTime())) {
      throw new SafetyError(
        "INVALID_CLOCK",
        "Advanced execution clock is invalid",
      );
    }
    return instant;
  };
}

function stateStoreFor(dependencies) {
  return dependencies.stateStore ?? createStateStore({
    stateRoot: dependencies.stateRoot,
    now: clockFor(dependencies),
  });
}

async function clientFor(targetOrg, dependencies) {
  const client = typeof dependencies.clientFactory === "function"
    ? await dependencies.clientFactory(targetOrg)
    : await createProductionSfClient({
      targetOrg,
      runtimeManifestPath: dependencies.runtimeManifestPath,
    });
  if (!client
    || typeof client.orgDisplay !== "function"
    || typeof client.describe !== "function"
    || typeof client.query !== "function"
    || !SHA256.test(client.attestationDigest ?? "")
    || client.queryCount !== 0) {
    throw new SafetyError(
      "INVALID_SF_CLIENT",
      "Advanced Salesforce execution requires a fresh verified client",
    );
  }
  return client;
}

async function assertPackageAttestation(entry, client) {
  const evidence = entry.certification_evidence;
  let currentPackage;
  try {
    currentPackage = await attestCertificationPackage();
  } catch {
    throw new SafetyError(
      "CERTIFICATION_DRIFT",
      "Certification-critical package could not be re-attested",
    );
  }
  if (!evidence
    || evidence.runtime_attestation_digest !== client.attestationDigest
    || evidence.package_digest !== currentPackage.package_digest) {
    throw new SafetyError(
      "CERTIFICATION_DRIFT",
      "Salesforce runtime or certification-critical package changed after org certification",
    );
  }
}

async function assertMetadataAttestation(entry, client) {
  let metadata;
  try {
    metadata = await inspectMetadataCompatibility(client);
  } catch {
    throw new SafetyError(
      "CERTIFICATION_DRIFT",
      "Salesforce metadata can no longer be attested",
    );
  }
  if (entry.certification_evidence?.metadata_compatibility_digest
      !== digest(metadata)) {
    throw new SafetyError(
      "CERTIFICATION_DRIFT",
      "Salesforce metadata changed after org certification",
    );
  }
}

async function persistReadinessDowngrade(store, entry) {
  await store.updateOrgRegistry((current) =>
    downgradeRegistryReadiness(current, entry));
}

function requiresReadinessDowngrade(error) {
  return RUNTIME_DRIFT_CODES.has(error?.code)
    || error?.code === "CERTIFICATION_DRIFT"
    || error?.code === "ORG_IDENTITY_MISMATCH";
}

async function withReadinessDowngradeOnFailure(
  store,
  entry,
  operation,
) {
  try {
    return await operation();
  } catch (error) {
    if (requiresReadinessDowngrade(error)) {
      await persistReadinessDowngrade(store, entry);
      if (error && typeof error === "object") {
        PERSISTED_READINESS_DOWNGRADES.add(error);
      }
    }
    throw error;
  }
}

async function assertClientIdentity(store, entry, identity) {
  return await withReadinessDowngradeOnFailure(
    store,
    entry,
    async () => {
      verifyRegistryIdentity(entry, identity);
      return identity;
    },
  );
}

function validateCommandInput(command, input) {
  if (command === "resolve") return validateResolveRequest(input);
  if (command === "profile") return validateProfileRequest(input);
  throw new SafetyError(
    "UNKNOWN_COMMAND",
    "Advanced data execution accepts only resolve or profile",
  );
}

async function guardedClient(input, dependencies) {
  const store = stateStoreFor(dependencies);
  if (!store
    || typeof store.initialize !== "function"
    || typeof store.readOrgRegistry !== "function"
    || typeof store.updateOrgRegistry !== "function"
    || typeof store.withOrgRegistryReadiness !== "function") {
    throw new SafetyError(
      "INVALID_STATE_STORE",
      "Advanced Salesforce execution requires a guarded org registry",
    );
  }
  await store.initialize();
  const registry = validateOrgRegistry(
    await store.readOrgRegistry() ?? emptyOrgRegistry(),
  );
  const entry = resolveRegistryEntry(registry, input.target_org);
  if (entry.alias !== input.target_org) {
    throw new SafetyError(
      "ORG_ALIAS_REQUIRED",
      "Advanced Salesforce commands require the enrolled target-org alias",
    );
  }
  assertRegistryReadiness(entry);

  const { client } = await withReadinessDowngradeOnFailure(
    store,
    entry,
    async () => {
      const currentClient = await clientFor(entry.alias, dependencies);
      const identity = await currentClient.orgDisplay();
      verifyRegistryIdentity(entry, identity);
      await assertPackageAttestation(entry, currentClient);
      await assertMetadataAttestation(entry, currentClient);
      return { client: currentClient };
    },
  );
  const orgDisplay = client.orgDisplay.bind(client);
  client.orgDisplay = async () => await withReadinessDowngradeOnFailure(
    store,
    entry,
    async () => {
      const currentIdentity = await orgDisplay();
      verifyRegistryIdentity(entry, currentIdentity);
      return currentIdentity;
    },
  );
  const expectedReadinessDigest = registryReadinessDigest(entry);
  const query = client.query.bind(client);
  client.query = async (soql) =>
    await store.withOrgRegistryReadiness(
      async (currentDocument, lease) => {
        if (!lease || typeof lease.issueQuery !== "function") {
          throw new SafetyError(
            "INVALID_STATE_STORE",
            "Org readiness guard did not provide a query-issuance lease",
          );
        }
        const currentRegistry = validateOrgRegistry(
          currentDocument ?? emptyOrgRegistry(),
        );
        const currentEntry = resolveRegistryEntry(
          currentRegistry,
          entry.alias,
        );
        assertRegistryReadiness(currentEntry);
        if (registryReadinessDigest(currentEntry)
            !== expectedReadinessDigest) {
          throw new SafetyError(
            "CERTIFICATION_DRIFT",
            "Org certification changed before the next Salesforce data query",
          );
        }
        try {
          await assertPackageAttestation(currentEntry, client);
        } catch (error) {
          if (error?.code === "CERTIFICATION_DRIFT") {
            if (typeof lease.updateRegistry !== "function") {
              throw new SafetyError(
                "INVALID_STATE_STORE",
                "Org readiness lease cannot persist certification drift",
              );
            }
            await lease.updateRegistry((current) =>
              downgradeRegistryReadiness(current, currentEntry));
            if (error && typeof error === "object") {
              PERSISTED_READINESS_DOWNGRADES.add(error);
            }
          }
          throw error;
        }
        try {
          return await lease.issueQuery(() => query(soql));
        } catch (error) {
          if (RUNTIME_DRIFT_CODES.has(error?.code)) {
            if (typeof lease.updateRegistry !== "function") {
              throw new SafetyError(
                "INVALID_STATE_STORE",
                "Org readiness lease cannot persist runtime drift",
              );
            }
            await lease.updateRegistry((current) =>
              downgradeRegistryReadiness(current, currentEntry));
            if (error && typeof error === "object") {
              PERSISTED_READINESS_DOWNGRADES.add(error);
            }
          }
          throw error;
        }
      },
    );
  return { client, entry, store };
}

export async function executeAdvancedPublic(
  command,
  input,
  dependencies = {},
) {
  if (!ADVANCED_DATA_COMMANDS.has(command)) {
    throw new SafetyError(
      "UNKNOWN_COMMAND",
      "Advanced data execution accepts only resolve or profile",
    );
  }
  validateCommandInput(command, input);
  const context = await guardedClient(input, dependencies);
  try {
    return await execute(command, input, {
      client: context.client,
    });
  } catch (error) {
    if (error?.code === "SCHEMA_FAILURE"
      || (RUNTIME_DRIFT_CODES.has(error?.code)
        && !PERSISTED_READINESS_DOWNGRADES.has(error))) {
      await persistReadinessDowngrade(
        context.store,
        context.entry,
      );
    }
    throw error;
  }
}

export const advancedExecutionInternals = Object.freeze({
  ADVANCED_DATA_COMMANDS,
  RUNTIME_DRIFT_CODES,
  assertClientIdentity,
  assertMetadataAttestation,
  assertPackageAttestation,
  persistReadinessDowngrade,
});
