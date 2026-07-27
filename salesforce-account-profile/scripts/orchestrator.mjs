import { randomBytes } from "node:crypto";
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";

import {
  ACCOUNT_ID,
  CAPS,
  CLASSIFICATION,
  CONTRACTS,
  PROFILE_SECTIONS,
} from "./constants.mjs";
import {
  validateAbortRequest,
  validateContinueRequest,
  validateDoctorRequest,
  validateStartRequest,
  validateStatusRequest,
} from "./conversational-contracts.mjs";
import { orgDigest } from "./contracts.mjs";
import { hydrateProfileRelationships } from "./profile-hydration.mjs";
import { buildProfileView } from "./profile-view.mjs";
import { inspectMetadataCompatibility } from "./metadata-compatibility.mjs";
import {
  assertRegistryReadiness,
  buildOfflineRegistryEntry,
  emptyOrgRegistry,
  markMetadataVerified,
  refreshRegistryVerification,
  resolveRegistryEntry,
  upsertRegistryEntry,
  validateOrgRegistry,
  validateRegistryEntry,
  verifyRegistryIdentity,
} from "./org-registry.mjs";
import {
  buildReadPlan,
  issueApprovalReceipt,
  readPlanDigest,
  validateApprovalReceipt,
} from "./read-plan.mjs";
import { recoveryForError } from "./recovery.mjs";
import { buildResolutionChoices } from "./resolution-choice.mjs";
import { renderProfile } from "./render.mjs";
import {
  batchIds,
  createProductionSfClient,
} from "./sf-client.mjs";
import {
  defaultSfRuntimeManifestPath,
  discoverSfRuntime,
  writeSfRuntimeManifest,
} from "./sf-runtime.mjs";
import {
  escapeSoqlLiteral,
  markdownText,
  SafetyError,
  sanitizeText,
} from "./security.mjs";
import { createStateStore } from "./state-store.mjs";
import { execute } from "./workflow.mjs";

const ALLOWED_NEXT_ACTIONS = new Set([
  "confirm_org_and_plan",
  "choose_account",
  "approve_family_scope",
  "narrow_query",
  "reauthenticate",
  "request_permissions",
  "cancel",
]);

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
        "Conversational execution clock is invalid",
      );
    }
    return instant;
  };
}

function storeFor(dependencies, clock) {
  return dependencies.stateStore ?? createStateStore({
    stateRoot: dependencies.stateRoot,
    now: clock,
  });
}

function maskedUsername(value) {
  const safe = sanitizeText(value);
  const separator = safe.lastIndexOf("@");
  if (separator <= 0 || separator === safe.length - 1) {
    return `${safe.slice(0, 1)}***`;
  }
  return `${safe.slice(0, 1)}***@${safe.slice(separator + 1)}`;
}

async function productionClient(targetOrg, dependencies, {
  enrollRuntime = false,
} = {}) {
  const manifestPath = dependencies.runtimeManifestPath
    ?? defaultSfRuntimeManifestPath();
  try {
    return await createProductionSfClient({
      targetOrg,
      runner: dependencies.runner,
      runtimeManifestPath: manifestPath,
    });
  } catch (error) {
    if (!enrollRuntime || error?.code !== "SF_RUNTIME_NOT_ENROLLED") throw error;
  }
  await mkdir(dirname(manifestPath), { recursive: true, mode: 0o700 });
  const manifest = await discoverSfRuntime({
    pathEnv: dependencies.pathEnv ?? process.env.PATH ?? "",
    nodePath: dependencies.nodePath ?? process.execPath,
    now: clockFor(dependencies)(),
  });
  try {
    await writeSfRuntimeManifest(manifestPath, manifest);
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
  }
  return await createProductionSfClient({
    targetOrg,
    runner: dependencies.runner,
    runtimeManifestPath: manifestPath,
  });
}

async function clientFor(targetOrg, dependencies, options = {}) {
  let client;
  if (typeof dependencies.clientFactory === "function") {
    client = await dependencies.clientFactory(targetOrg);
  } else {
    client = await productionClient(targetOrg, dependencies, options);
  }
  if (!client
    || typeof client.orgDisplay !== "function"
    || typeof client.orgList !== "function"
    || typeof client.describe !== "function"
    || typeof client.query !== "function"
    || !/^[a-f0-9]{64}$/u.test(client.attestationDigest)
    || !Number.isInteger(client.queryCount)) {
    throw new SafetyError(
      "INVALID_SF_CLIENT",
      "Conversational execution requires a verified Salesforce client",
    );
  }
  return client;
}

async function readOrgRegistry(store) {
  const document = await store.readOrgRegistry();
  return validateOrgRegistry(document ?? emptyOrgRegistry());
}

function orgTypeFor(authorizedOrg) {
  if (!authorizedOrg?.org_type) {
    throw new SafetyError(
      "ORG_DISCOVERY_MISMATCH",
      "The selected org is absent from the redacted authorized-org discovery",
    );
  }
  return authorizedOrg.org_type;
}

function validateAuthorizedIdentity(authorizedOrg, identity) {
  let instanceHost;
  try {
    instanceHost = new URL(identity.instance_url).hostname
      .toLocaleLowerCase("en-US");
  } catch {
    throw new SafetyError(
      "ORG_DISCOVERY_MISMATCH",
      "Selected-org identity has an invalid instance host",
    );
  }
  if (identity.org_id.slice(-6) !== authorizedOrg.org_id_suffix
    || instanceHost !== authorizedOrg.instance_host
    || maskedUsername(identity.username)
      !== authorizedOrg.masked_username) {
    throw new SafetyError(
      "ORG_DISCOVERY_MISMATCH",
      "Selected-org identity does not match authorized-org discovery",
    );
  }
}

function publicRegistryEntry(entry) {
  return {
    alias: entry.alias,
    friendly_label: entry.friendly_label,
    org_id_suffix: entry.org_id_suffix,
    instance_host: entry.instance_host,
    environment: entry.environment,
    certification_state: entry.certification_state,
    identity_verified_at: entry.identity_verified_at,
    metadata_verified_at: entry.metadata_verified_at,
    certification_verified_at: entry.certification_verified_at,
  };
}

function registryMessage(entry) {
  const label = markdownText(entry.friendly_label);
  if (entry.certification_state === "production_read_approved") {
    return `${label} identity and metadata verification were refreshed; its separate production read approval remains in force.`;
  }
  if (entry.certification_state === "sandbox_read_certified") {
    return `${label} identity and metadata verification were refreshed; its sandbox read certification remains in force.`;
  }
  return `${label} is enrolled for offline validation; live data reads remain blocked until its certification gate passes.`;
}

function result(schemaVersion, fields) {
  if (fields.next_action !== null
    && fields.next_action !== undefined
    && !ALLOWED_NEXT_ACTIONS.has(fields.next_action)) {
    throw new SafetyError(
      "INTERNAL_ERROR",
      "Conversational result used an unsupported next action",
    );
  }
  return {
    schema_version: schemaVersion,
    classification: CLASSIFICATION,
    ...fields,
  };
}

export async function doctor(input, dependencies = {}) {
  const request = validateDoctorRequest(input);
  const clock = clockFor(dependencies);
  const store = storeFor(dependencies, clock);
  await store.initialize();
  const cleanup = await store.cleanupExpiredSessions();
  const activeSessions = await Promise.all(
    (await store.listSessions()).map(async (entry) => {
      const session = await store.readSession(entry.session_id);
      return {
        session_id: session.session_id,
        summary: statusSummary(session),
      };
    }),
  );
  const discoveryClient = await clientFor(null, dependencies, {
    enrollRuntime: true,
  });
  const authorizedOrgs = await discoveryClient.orgList();
  let registry = await readOrgRegistry(store);
  let enrolled = null;
  let metadataCompatibility = null;
  if (request.target_org) {
    const client = await clientFor(request.target_org, dependencies);
    const identity = await client.orgDisplay();
    const authorizedMatches = authorizedOrgs.filter((org) =>
      org.alias === request.target_org);
    if (authorizedMatches.length !== 1) {
      throw new SafetyError(
        "ORG_DISCOVERY_MISMATCH",
        "The selected org must match exactly one redacted authorized-org entry",
      );
    }
    const [authorized] = authorizedMatches;
    validateAuthorizedIdentity(authorized, identity);
    metadataCompatibility = await inspectMetadataCompatibility(client);
    const orgType = orgTypeFor(authorized);
    registry = await store.updateOrgRegistry((current) => {
      const validated = validateOrgRegistry(current);
      const existing = validated.entries.find((entry) =>
        entry.alias === request.target_org);
      if (existing) {
        if (existing.friendly_label !== request.friendly_label) {
          throw new SafetyError(
            "ORG_LABEL_MISMATCH",
            "The enrolled org has a different friendly label",
          );
        }
        enrolled = refreshRegistryVerification(existing, {
          identity,
          orgType,
          environment: request.environment,
          now: clock(),
        });
      } else {
        enrolled = markMetadataVerified(buildOfflineRegistryEntry({
          alias: request.target_org,
          friendlyLabel: request.friendly_label,
          identity,
          orgType,
          environment: request.environment,
          now: clock(),
        }), clock());
      }
      return upsertRegistryEntry(validated, enrolled);
    });
  }
  return result(CONTRACTS.doctorResult, {
    status: "ready",
    next_action: null,
    message: enrolled
      ? registryMessage(enrolled)
      : `Salesforce runtime and local org discovery completed. ${activeSessions.length} private profile session${activeSessions.length === 1 ? " is" : "s are"} available to resume. Live data reads remain governed by each enrolled org's certification state.`,
    authorized_orgs: authorizedOrgs,
    enrolled_orgs: registry.entries.map(publicRegistryEntry),
    metadata_compatibility: metadataCompatibility,
    active_sessions: activeSessions,
    expired_sessions_deleted: cleanup.deleted.length,
  });
}

function buildPlanFromRequest(request, {
  sessionId,
  entry,
  identity,
  runtimeAttestationDigest,
  issuedAt,
}) {
  return buildReadPlan({
    sessionId,
    orgIdentity: {
      target_org: entry.alias,
      org_id: identity.org_id,
      username: identity.username,
      instance_url: identity.instance_url,
      connected_status: identity.connected_status,
    },
    runtimeAttestationDigest,
    accountSelector: request.account_selector,
    preset: request.preset,
    ...(request.preset === "custom" ? {
      sections: request.sections,
      scope: request.scope,
      opportunityScope: request.opportunity_scope,
    } : {}),
    filters: request.filters,
    outputType: request.output_type,
    issuedAt,
  });
}

function rebuildPlan(plan, overrides = {}) {
  const preset = overrides.preset ?? plan.preset;
  const sections = overrides.sections ?? plan.requested_sections;
  const scope = overrides.scope ?? plan.scope;
  const opportunityScope = overrides.opportunityScope
    ?? plan.opportunity_scope;
  return buildReadPlan({
    sessionId: plan.session_id,
    orgIdentity: plan.org_identity,
    runtimeAttestationDigest: plan.runtime_attestation_digest,
    accountSelector: overrides.accountSelector ?? plan.account_selector,
    selectedAccount: overrides.selectedAccount === undefined
      ? plan.selected_account
      : overrides.selectedAccount,
    accountReceiptDigest: overrides.accountReceiptDigest === undefined
      ? plan.account_receipt_digest
      : overrides.accountReceiptDigest,
    familyAccountIds: overrides.familyAccountIds === undefined
      ? plan.family_account_ids
      : overrides.familyAccountIds,
    preset,
    ...(preset === "custom" ? {
      sections,
      scope,
      opportunityScope,
    } : {}),
    filters: overrides.filters ?? plan.filters,
    outputType: plan.output_type,
    issuedAt: plan.issued_at,
    expiresAt: plan.expires_at,
  });
}

function orgConfirmationSummary(entry, request, identity) {
  return {
    friendly_label: entry.friendly_label,
    environment: entry.environment,
    masked_username: maskedUsername(identity.username),
    org_id_suffix: entry.org_id_suffix,
    instance_host: entry.instance_host,
    account: {
      mode: request.account_selector.mode,
      value: request.account_selector.value,
    },
    preset: request.preset,
    scope: request.scope,
    opportunity_scope: request.opportunity_scope,
    filters: request.filters,
  };
}

function confirmationMessage(summary) {
  const opportunityScope = summary.opportunity_scope === "all"
    ? "all Opportunities"
    : `${summary.opportunity_scope} Opportunities`;
  return `Confirm ${markdownText(summary.friendly_label)} (${markdownText(summary.masked_username)}, org …${markdownText(summary.org_id_suffix)}, ${markdownText(summary.instance_host)}) and a ${summary.scope === "corporate_family" ? "corporate-family" : "selected-account"} ${markdownText(summary.preset)} profile for “${markdownText(summary.account.value)}” using ${markdownText(opportunityScope)}.`;
}

export async function start(input, dependencies = {}) {
  const request = validateStartRequest(input);
  const clock = clockFor(dependencies);
  const store = storeFor(dependencies, clock);
  await store.initialize();
  await store.cleanupExpiredSessions();
  const registry = await readOrgRegistry(store);
  const entry = resolveRegistryEntry(registry, request.target_org);
  assertRegistryReadiness(entry, {
    allowOfflineExecution: dependencies.allowOfflineExecution === true,
  });
  const client = await clientFor(entry.alias, dependencies);
  const identity = await client.orgDisplay();
  verifyRegistryIdentity(entry, identity);
  if (client.queryCount !== 0) {
    throw new SafetyError(
      "INVALID_SF_CLIENT",
      "A new conversation must begin with a fresh query budget",
    );
  }
  const issuedAt = clock();
  const sessionId = randomBytes(16).toString("hex");
  const plan = buildPlanFromRequest(request, {
    sessionId,
    entry,
    identity,
    runtimeAttestationDigest: client.attestationDigest,
    issuedAt,
  });
  const summary = orgConfirmationSummary(entry, request, identity);
  await store.createSession({
    session_id: sessionId,
    state: "new",
    target_org: entry.alias,
    friendly_org: {
      friendly_label: entry.friendly_label,
      environment: entry.environment,
      org_id_suffix: entry.org_id_suffix,
      instance_host: entry.instance_host,
      certification_state: entry.certification_state,
    },
    request: { ...request, target_org: entry.alias },
    read_plan: plan,
    org_approval_receipt: null,
    account_receipt: null,
    resolution_choices: null,
    family_manifest: null,
    family_approval_receipt: null,
    query_count: 0,
    pending_action: null,
    recovery: null,
  });
  await store.updateSession(sessionId, {
    state: "org_confirmation",
    pending_action: "confirm_org_and_plan",
  });
  return result(CONTRACTS.startResult, {
    status: "awaiting_decision",
    session_id: sessionId,
    next_action: "confirm_org_and_plan",
    message: confirmationMessage(summary),
    summary,
  });
}

function resolveRequestFor(session, selector) {
  return {
    schema_version: CONTRACTS.resolveRequest,
    target_org: session.target_org,
    confirmed_org_digest: orgDigest(
      session.target_org,
      session.read_plan.org_identity,
      session.read_plan.runtime_attestation_digest,
    ),
    selector,
  };
}

function profileRequestFor(session) {
  return {
    schema_version: CONTRACTS.profileRequest,
    target_org: session.target_org,
    confirmed_org_digest: orgDigest(
      session.target_org,
      session.read_plan.org_identity,
      session.read_plan.runtime_attestation_digest,
    ),
    account_receipt: session.account_receipt,
    sections: [...session.read_plan.requested_sections],
    scope: session.read_plan.scope,
    opportunity_scope: session.read_plan.opportunity_scope,
    ...(session.family_manifest?.family_digest ? {
      confirmed_family_digest: session.family_manifest.family_digest,
    } : {}),
  };
}

async function verifiedSessionClient(session, dependencies, store) {
  const registry = await readOrgRegistry(store);
  const entry = resolveRegistryEntry(registry, session.target_org);
  assertRegistryReadiness(entry, {
    allowOfflineExecution: dependencies.allowOfflineExecution === true,
  });
  const client = await clientFor(entry.alias, dependencies);
  client.queryCount = session.query_count;
  return { client, entry };
}

function candidateMessage(rows) {
  if (!rows.length) {
    return "No Account matched. Approve a literal prefix search or cancel; no likely match will be selected automatically.";
  }
  return rows.length === 1
    ? "Choose the returned Account explicitly; a prefix result is never auto-selected."
    : `Choose one of the ${rows.length} matching Accounts.`;
}

function candidateResult(sessionId, rows, mode) {
  return result(CONTRACTS.continueResult, {
    status: "awaiting_decision",
    session_id: sessionId,
    next_action: "choose_account",
    message: candidateMessage(rows),
    choices: rows,
    chooser_mode: mode,
  });
}

async function storeChooser(
  continuation,
  session,
  client,
  resolved,
) {
  const enriched = await buildResolutionChoices({
    candidates: resolved.candidates,
    client,
  });
  await continuation.update({
    state: "account_choice",
    resolution_choices: {
      mode: resolved.selector_mode,
      rows: enriched.rows,
    },
    query_count: client.queryCount,
    pending_action: "choose_account",
    recovery: null,
  });
  return candidateResult(
    session.session_id,
    enriched.rows,
    resolved.selector_mode,
  );
}

function selectedPlan(plan, resolved, approvedAt) {
  const updated = rebuildPlan(plan, {
    selectedAccount: resolved.selected_account,
    accountReceiptDigest: resolved.account_receipt.receipt_digest,
  });
  return {
    plan: updated,
    orgApprovalReceipt: issueApprovalReceipt(
      updated,
      "org_and_plan",
      approvedAt,
    ),
  };
}

function familyApprovalMessage(manifest) {
  return `Approve the exact corporate-family scope of ${manifest.account_ids.length} Account${manifest.account_ids.length === 1 ? "" : "s"} before any family-wide evidence is completed.`;
}

function familyResult(sessionId, manifest) {
  return result(CONTRACTS.continueResult, {
    status: "awaiting_decision",
    session_id: sessionId,
    next_action: "approve_family_scope",
    message: familyApprovalMessage(manifest),
    corporate_family_accounts: manifest.accounts,
    account_ids: manifest.account_ids,
  });
}

function requireOrgPlanApproval(session, now) {
  return validateApprovalReceipt(
    session.org_approval_receipt,
    session.read_plan,
    "org_and_plan",
    now,
  );
}

function needsFamilyTransactionReceipt(plan) {
  return plan.scope === "corporate_family"
    && ["opportunities", "products", "team"].some((section) =>
      plan.requested_sections.includes(section));
}

async function runProfileKernel(session, client, now, {
  familyApprovalReceipt,
} = {}) {
  requireOrgPlanApproval(session, now);
  const workflowDependencies = {
    client,
    readPlan: session.read_plan,
    now,
  };
  if (needsFamilyTransactionReceipt(session.read_plan)) {
    workflowDependencies.familyApprovalReceipt = familyApprovalReceipt;
  }
  return await execute(
    "profile",
    profileRequestFor(session),
    workflowDependencies,
  );
}

async function hydrateFamilyManifest(client, accountIds) {
  const ids = [...accountIds].sort();
  if (ids.length < 1
    || ids.length > CAPS.familyAccounts
    || ids.some((id) => !ACCOUNT_ID.test(id))) {
    throw new SafetyError(
      "FAMILY_DISCOVERY_INCOMPLETE",
      "Corporate-family Account identities are invalid or over cap",
    );
  }
  const fields = await client.describe("Account");
  if (!(fields instanceof Map)
    || fields.get("Id")?.type !== "id"
    || fields.get("Id")?.filterable !== true
    || fields.get("Name")?.type !== "string") {
    throw new SafetyError(
      "SCHEMA_FAILURE",
      "Account identity metadata is incompatible",
    );
  }
  const batches = batchIds(ids);
  if (client.queryCount + batches.length > CAPS.queries) {
    throw new SafetyError(
      "QUERY_CAP_EXCEEDED",
      "Corporate-family names cannot be completed within the query cap",
      { next_action: ["selected_account"] },
    );
  }
  const rows = new Map();
  for (const batch of batches) {
    const literals = batch.map((id) =>
      `'${escapeSoqlLiteral(id)}'`).join(", ");
    const returned = await client.query(
      `SELECT Id, Name FROM Account WHERE Id IN (${literals}) ORDER BY Id`,
    );
    for (const row of returned) {
      if (!row
        || typeof row.Id !== "string"
        || !batch.includes(row.Id)
        || rows.has(row.Id)
        || typeof row.Name !== "string") {
        throw new SafetyError(
          "FAMILY_DISCOVERY_INCOMPLETE",
          "Corporate-family Account identity hydration was inconsistent",
        );
      }
      rows.set(row.Id, {
        Id: row.Id,
        Name: sanitizeText(row.Name),
      });
    }
  }
  if (rows.size !== ids.length
    || ids.some((id) => !rows.has(id))) {
    throw new SafetyError(
      "FAMILY_DISCOVERY_INCOMPLETE",
      "Corporate-family Account names were incomplete",
    );
  }
  return ids.map((id) => rows.get(id));
}

async function discoverFamily(
  continuation,
  session,
  client,
  now,
) {
  const profile = await runProfileKernel(session, client, now);
  if (!profile.family_confirmation) {
    throw new SafetyError(
      "FAMILY_DISCOVERY_INCOMPLETE",
      "Corporate-family discovery omitted its exact Account set",
    );
  }
  const accountIds = [...profile.family_confirmation.account_ids].sort();
  const accountNames = new Map(profile.accounts.map((account) => [
    account.Id,
    account.Name,
  ]));
  accountNames.set(
    profile.selected_account.Id,
    profile.selected_account.Name,
  );
  const missingNames = accountIds.some((id) => !accountNames.has(id));
  const accounts = missingNames
    ? await hydrateFamilyManifest(client, accountIds)
    : accountIds.map((id) => ({
      Id: id,
      Name: sanitizeText(accountNames.get(id)),
    }));
  const manifest = {
    account_ids: accountIds,
    accounts,
    family_digest: profile.family_confirmation.family_digest,
  };
  const updatedPlan = rebuildPlan(session.read_plan, {
    familyAccountIds: accountIds,
  });
  await continuation.update({
    state: "family_approval",
    read_plan: updatedPlan,
    family_manifest: manifest,
    family_approval_receipt: null,
    query_count: client.queryCount,
    pending_action: "approve_family_scope",
    recovery: null,
  });
  return familyResult(session.session_id, manifest);
}

async function completeProfile(
  continuation,
  session,
  client,
  entry,
  now,
) {
  await continuation.update({
    state: "executing",
    pending_action: null,
    recovery: null,
  });
  const profile = await runProfileKernel(session, client, now, {
    familyApprovalReceipt: session.family_approval_receipt,
  });
  if (profile.status !== "complete") {
    throw new SafetyError(
      "FAMILY_APPROVAL_MISMATCH",
      "The approved corporate-family scope changed before execution",
    );
  }
  const relationshipContext = await hydrateProfileRelationships({
    client,
    profile,
    readPlan: session.read_plan,
    familyApprovalReceipt: session.family_approval_receipt,
    now,
  });
  const view = buildProfileView({
    plan: session.read_plan,
    profile,
    certificationState: entry.certification_state,
    relationshipContext,
    familyApprovalReceipt: session.family_approval_receipt,
  });
  const markdown = renderProfile(view);
  await continuation.complete();
  return result(CONTRACTS.continueResult, {
    status: "complete",
    next_action: null,
    message: markdown,
    ...(session.read_plan.output_type === "json"
      ? { structured_artifact: view }
      : {}),
  });
}

async function runSelectedOrFamily(
  continuation,
  session,
  client,
  entry,
  now,
) {
  if (session.read_plan.scope === "corporate_family"
    && session.read_plan.family_account_ids.length === 0) {
    return await discoverFamily(
      continuation,
      session,
      client,
      now,
    );
  }
  if (session.read_plan.scope === "corporate_family"
    && session.family_approval_receipt === null) {
    return familyResult(session.session_id, session.family_manifest);
  }
  return await completeProfile(
    continuation,
    session,
    client,
    entry,
    now,
  );
}

async function acceptSelectedAccount(
  continuation,
  session,
  client,
  entry,
  resolved,
  now,
) {
  if (resolved.status !== "selected" || !resolved.account_receipt) {
    throw new SafetyError(
      "ACCOUNT_REVALIDATION_FAILED",
      "The chosen Account no longer resolves exactly once",
    );
  }
  const selected = selectedPlan(session.read_plan, resolved, now);
  const updated = await continuation.update({
    state: "executing",
    read_plan: selected.plan,
    org_approval_receipt: selected.orgApprovalReceipt,
    account_receipt: resolved.account_receipt,
    resolution_choices: null,
    family_manifest: null,
    family_approval_receipt: null,
    query_count: client.queryCount,
    pending_action: null,
    recovery: null,
  });
  return await runSelectedOrFamily(
    continuation,
    updated,
    client,
    entry,
    now,
  );
}

async function resolveAccount(
  continuation,
  session,
  client,
  entry,
  selector,
  now,
  expectedChoice = null,
) {
  requireOrgPlanApproval(session, now);
  const resolved = await execute(
    "resolve",
    resolveRequestFor(session, selector),
    { client },
  );
  if (resolved.status === "no_match") {
    await continuation.update({
      state: "account_choice",
      resolution_choices: {
        mode: "no_match",
        rows: [],
      },
      query_count: client.queryCount,
      pending_action: "choose_account",
      recovery: null,
    });
    return candidateResult(session.session_id, [], "no_match");
  }
  if (resolved.status === "ambiguous" || resolved.status === "chooser") {
    return await storeChooser(
      continuation,
      session,
      client,
      resolved,
    );
  }
  if (expectedChoice
    && (resolved.selected_account?.Id !== expectedChoice.Id
      || resolved.selected_account?.Name !== expectedChoice.Name)) {
    throw new SafetyError(
      "ACCOUNT_CHOICE_MISMATCH",
      "Chosen Account identity changed after the chooser was displayed",
    );
  }
  return await acceptSelectedAccount(
    continuation,
    session,
    client,
    entry,
    resolved,
    now,
  );
}

function ensureDecision(session, decision) {
  const expected = session.pending_action;
  if (decision.action === "cancel") return;
  if (decision.action !== expected) {
    throw new SafetyError(
      "UNEXPECTED_DECISION",
      "This decision does not match the conversation's current next action",
    );
  }
}

function narrowedPlan(session, decision) {
  const current = session.read_plan;
  const scope = decision.scope ?? current.scope;
  if (current.scope === "selected_account"
    && scope !== "selected_account") {
    throw new SafetyError(
      "INVALID_NARROWING",
      "Narrowing cannot expand selected-account scope",
    );
  }
  const opportunityScope = decision.opportunity_scope
    ?? current.opportunity_scope;
  if (current.opportunity_scope !== "all"
    && opportunityScope !== current.opportunity_scope) {
    throw new SafetyError(
      "INVALID_NARROWING",
      "Narrowing cannot widen or switch the current Opportunity scope",
    );
  }
  const filters = {
    ...current.filters,
    ...(decision.filters ?? {}),
  };
  if (current.filters.close_date_from
    && filters.close_date_from < current.filters.close_date_from) {
    throw new SafetyError(
      "INVALID_NARROWING",
      "Narrowing cannot relax the opening Close Date",
    );
  }
  if (current.filters.close_date_to
    && filters.close_date_to > current.filters.close_date_to) {
    throw new SafetyError(
      "INVALID_NARROWING",
      "Narrowing cannot relax the closing Close Date",
    );
  }
  if (current.filters.stages.length
    && filters.stages.some((stage) =>
      !current.filters.stages.includes(stage))) {
    throw new SafetyError(
      "INVALID_NARROWING",
      "Narrowing stages must remain a subset of the current stages",
    );
  }
  let sections = current.requested_sections.filter((section) =>
    !(decision.remove_sections ?? []).includes(section));
  if (!sections.length) {
    throw new SafetyError(
      "INVALID_NARROWING",
      "Narrowing must retain at least one profile section",
    );
  }
  const accountChanged = decision.account_selector !== undefined;
  if (!sections.some((section) =>
    ["opportunities", "products"].includes(section))) {
    filters.close_date_from = null;
    filters.close_date_to = null;
    filters.stages = [];
  }
  const plan = rebuildPlan(current, {
    preset: "custom",
    sections,
    scope,
    opportunityScope,
    filters,
    accountSelector: decision.account_selector
      ?? current.account_selector,
    selectedAccount: accountChanged ? null : current.selected_account,
    accountReceiptDigest: accountChanged
      ? null
      : current.account_receipt_digest,
    familyAccountIds: scope === "selected_account"
      || accountChanged
      ? []
      : current.family_account_ids,
  });
  if (readPlanDigest(plan) === readPlanDigest(current)) {
    throw new SafetyError(
      "INVALID_NARROWING",
      "The requested change does not narrow the current plan",
    );
  }
  return { plan, accountChanged };
}

async function resumeAfterRecovery(
  continuation,
  session,
  client,
  entry,
  now,
) {
  const resumeState = session.recovery?.resume_state;
  if (resumeState === "account_resolution") {
    await continuation.update({
      state: "account_resolution",
      pending_action: null,
      recovery: null,
    });
    return await resolveAccount(
      continuation,
      session,
      client,
      entry,
      session.read_plan.account_selector,
      now,
    );
  }
  const updated = await continuation.update({
    state: "executing",
    pending_action: null,
    recovery: null,
  });
  return await runSelectedOrFamily(
    continuation,
    updated,
    client,
    entry,
    now,
  );
}

function recoveryMessage(nextAction) {
  if (nextAction === "narrow_query") {
    return "The requested scope cannot complete atomically within its safety limits. Choose a narrower Account, Opportunity, date, or stage scope.";
  }
  if (nextAction === "reauthenticate") {
    return "Salesforce authentication must be refreshed before this read can continue.";
  }
  if (nextAction === "request_permissions") {
    return "The authorized Salesforce user needs the required object and field read permissions before this read can continue.";
  }
  return "The read stopped safely and the private session was canceled.";
}

function nextActionLabel(nextAction) {
  return {
    confirm_org_and_plan: "friendly-org and profile confirmation",
    choose_account: "Account choice",
    approve_family_scope: "corporate-family approval",
    narrow_query: "query narrowing",
    reauthenticate: "Salesforce reauthentication",
    request_permissions: "Salesforce permission correction",
    cancel: "cancellation",
  }[nextAction] ?? "the current decision";
}

function pendingDecisionResult(session) {
  if (session.pending_action === "choose_account") {
    return candidateResult(
      session.session_id,
      session.resolution_choices?.rows ?? [],
      session.resolution_choices?.mode ?? "chooser",
    );
  }
  if (session.pending_action === "approve_family_scope") {
    return familyResult(session.session_id, session.family_manifest);
  }
  const nextAction = session.pending_action ?? "cancel";
  return result(CONTRACTS.continueResult, {
    status: "awaiting_decision",
    session_id: session.session_id,
    next_action: nextAction,
    message: nextAction === "confirm_org_and_plan"
      ? "This session is still waiting for confirmation of the friendly org and requested profile."
      : recoveryMessage(nextAction),
    ...(nextAction === "narrow_query"
      ? {
        narrowing_options: [
          ...(session.recovery?.narrowing_options ?? []),
        ],
      }
      : {}),
  });
}

async function recoverConversation(
  continuation,
  session,
  client,
  error,
) {
  const recovery = recoveryForError(error);
  if (recovery.next_action === "cancel") {
    await continuation.abort();
    return result(CONTRACTS.continueResult, {
      status: "canceled",
      next_action: "cancel",
      message: recoveryMessage("cancel"),
    });
  }
  await continuation.update({
    query_count: Math.min(client?.queryCount ?? session.query_count, 30),
    pending_action: recovery.next_action,
    recovery: {
      resume_state: session.state,
      narrowing_options: [...recovery.narrowing_options],
    },
  });
  return result(CONTRACTS.continueResult, {
    status: "awaiting_decision",
    session_id: session.session_id,
    next_action: recovery.next_action,
    message: recoveryMessage(recovery.next_action),
    ...(recovery.next_action === "narrow_query"
      ? { narrowing_options: [...recovery.narrowing_options] }
      : {}),
  });
}

export async function continueConversation(input, dependencies = {}) {
  const request = validateContinueRequest(input);
  const clock = clockFor(dependencies);
  const store = storeFor(dependencies, clock);
  await store.initialize();
  await store.cleanupExpiredSessions();
  return await store.withSessionLock(
    request.session_id,
    async (continuation) => {
      let session = continuation.session;
      let client;
      try {
        ensureDecision(session, request.decision);
        if (request.decision.action === "cancel") {
          await continuation.abort();
          return result(CONTRACTS.continueResult, {
            status: "canceled",
            next_action: "cancel",
            message: "The private Salesforce profile session was canceled and deleted.",
          });
        }
        const verified = await verifiedSessionClient(
          session,
          dependencies,
          store,
        );
        client = verified.client;
        const entry = verified.entry;
        const now = clock();

        if (request.decision.action === "confirm_org_and_plan") {
          const receipt = issueApprovalReceipt(
            session.read_plan,
            "org_and_plan",
            now,
          );
          session = await continuation.update({
            state: "account_resolution",
            org_approval_receipt: receipt,
            pending_action: null,
            recovery: null,
          });
          return await resolveAccount(
            continuation,
            session,
            client,
            entry,
            session.read_plan.account_selector,
            now,
          );
        }

        if (request.decision.action === "choose_account") {
          if (request.decision.literal_prefix) {
            const prefixPlan = rebuildPlan(session.read_plan, {
              accountSelector: {
                mode: "prefix",
                value: request.decision.literal_prefix,
              },
              selectedAccount: null,
              accountReceiptDigest: null,
              familyAccountIds: [],
            });
            session = await continuation.update({
              state: "account_resolution",
              read_plan: prefixPlan,
              org_approval_receipt: issueApprovalReceipt(
                prefixPlan,
                "org_and_plan",
                now,
              ),
              request: {
                ...session.request,
                account_selector: prefixPlan.account_selector,
              },
              resolution_choices: null,
              pending_action: null,
              recovery: null,
            });
            return await resolveAccount(
              continuation,
              session,
              client,
              entry,
              prefixPlan.account_selector,
              now,
            );
          }
          const choices = session.resolution_choices?.rows ?? [];
          const expectedChoice = choices.find((choice) =>
            choice.Id === request.decision.account_id);
          if (!expectedChoice) {
            throw new SafetyError(
              "INVALID_ACCOUNT_CHOICE",
              "Chosen Account is not in the current exact chooser",
            );
          }
          session = await continuation.update({
            state: "account_resolution",
            pending_action: null,
            recovery: null,
          });
          return await resolveAccount(
            continuation,
            session,
            client,
            entry,
            {
              mode: "id",
              value: request.decision.account_id,
            },
            now,
            expectedChoice,
          );
        }

        if (request.decision.action === "approve_family_scope") {
          if (!session.family_manifest
            || session.read_plan.family_account_ids.length === 0) {
            throw new SafetyError(
              "FAMILY_APPROVAL_MISMATCH",
              "No exact corporate-family Account set is awaiting approval",
            );
          }
          const receipt = issueApprovalReceipt(
            session.read_plan,
            "family_scope",
            now,
          );
          session = await continuation.update({
            state: "executing",
            org_approval_receipt: issueApprovalReceipt(
              session.read_plan,
              "org_and_plan",
              now,
            ),
            family_approval_receipt: receipt,
            pending_action: null,
            recovery: null,
          });
          return await completeProfile(
            continuation,
            session,
            client,
            entry,
            now,
          );
        }

        if (request.decision.action === "narrow_query") {
          const narrowed = narrowedPlan(session, request.decision);
          const plan = narrowed.plan;
          session = await continuation.update({
            state: narrowed.accountChanged
              ? "account_resolution"
              : "executing",
            read_plan: plan,
            org_approval_receipt: issueApprovalReceipt(
              plan,
              "org_and_plan",
              now,
            ),
            family_manifest: plan.scope === "selected_account"
              || narrowed.accountChanged
              ? null
              : session.family_manifest,
            family_approval_receipt: null,
            account_receipt: narrowed.accountChanged
              ? null
              : session.account_receipt,
            resolution_choices: narrowed.accountChanged
              ? null
              : session.resolution_choices,
            pending_action: null,
            recovery: null,
          });
          if (narrowed.accountChanged) {
            return await resolveAccount(
              continuation,
              session,
              client,
              entry,
              plan.account_selector,
              now,
            );
          }
          if (plan.scope === "corporate_family"
            && plan.family_account_ids.length) {
            session = await continuation.update({
              state: "family_approval",
              pending_action: "approve_family_scope",
            });
            return familyResult(
              session.session_id,
              session.family_manifest,
            );
          }
          return await runSelectedOrFamily(
            continuation,
            session,
            client,
            entry,
            now,
          );
        }

        return await resumeAfterRecovery(
          continuation,
          session,
          client,
          entry,
          now,
        );
      } catch (error) {
        if (!(error instanceof SafetyError)) throw error;
        if (["UNEXPECTED_DECISION", "INVALID_ACCOUNT_CHOICE"].includes(
          error.code,
        )) {
          return pendingDecisionResult(session);
        }
        if (typeof dependencies.onInternalError === "function") {
          dependencies.onInternalError(error);
        }
        return await recoverConversation(
          continuation,
          session,
          client,
          error,
        );
      }
    },
  );
}

function statusSummary(session) {
  return {
    state: session.state,
    next_action: session.pending_action,
    org: {
      friendly_label: session.friendly_org.friendly_label,
      environment: session.friendly_org.environment,
      org_id_suffix: session.friendly_org.org_id_suffix,
      instance_host: session.friendly_org.instance_host,
    },
    account: session.read_plan.selected_account
      ?? {
        mode: session.read_plan.account_selector.mode,
        value: session.read_plan.account_selector.value,
      },
    preset: session.read_plan.preset,
    requested_sections: [...session.read_plan.requested_sections],
    scope: session.read_plan.scope,
    opportunity_scope: session.read_plan.opportunity_scope,
    expires_at: session.expires_at,
  };
}

export async function status(input, dependencies = {}) {
  const request = validateStatusRequest(input);
  const clock = clockFor(dependencies);
  const store = storeFor(dependencies, clock);
  await store.initialize();
  await store.cleanupExpiredSessions();
  if (!request.session_id) {
    const activeSessions = await Promise.all(
      (await store.listSessions()).map(async (entry) => {
        const session = await store.readSession(entry.session_id);
        return {
          session_id: session.session_id,
          summary: statusSummary(session),
        };
      }),
    );
    return result(CONTRACTS.statusResult, {
      status: activeSessions.length ? "active" : "idle",
      next_action: null,
      message: activeSessions.length
        ? `${activeSessions.length} private Salesforce profile session${activeSessions.length === 1 ? " is" : "s are"} available to resume.`
        : "No private Salesforce profile session is active.",
      active_sessions: activeSessions,
    });
  }
  const session = await store.readSession(request.session_id);
  return result(CONTRACTS.statusResult, {
    status: "active",
    session_id: session.session_id,
    next_action: session.pending_action,
    message: `The ${markdownText(session.friendly_org.friendly_label)} profile session can resume at ${nextActionLabel(session.pending_action)}.`,
    summary: statusSummary(session),
  });
}

export async function abort(input, dependencies = {}) {
  const request = validateAbortRequest(input);
  const clock = clockFor(dependencies);
  const store = storeFor(dependencies, clock);
  await store.initialize();
  await store.cleanupExpiredSessions();
  let deleted = false;
  try {
    deleted = await store.deleteSession(request.session_id, "abort");
  } catch (error) {
    if (error?.code !== "SESSION_NOT_FOUND") throw error;
  }
  return result(CONTRACTS.abortResult, {
    status: "canceled",
    next_action: "cancel",
    message: deleted
      ? "The private Salesforce profile session was canceled and deleted."
      : "No active Salesforce profile session remained to delete.",
  });
}

export async function executeConversational(
  command,
  input,
  dependencies = {},
) {
  if (command === "doctor") return await doctor(input, dependencies);
  if (command === "start") return await start(input, dependencies);
  if (command === "continue") {
    return await continueConversation(input, dependencies);
  }
  if (command === "status") return await status(input, dependencies);
  if (command === "abort") return await abort(input, dependencies);
  throw new SafetyError(
    "UNKNOWN_COMMAND",
    "Command must be doctor, start, continue, status, or abort",
  );
}

export const orchestratorInternals = Object.freeze({
  ALLOWED_NEXT_ACTIONS,
  rebuildPlan,
  needsFamilyTransactionReceipt,
});
