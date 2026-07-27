export const CONTRACTS = Object.freeze({
  preflightRequest: "salesforce-account-profile-preflight-request/v1",
  preflightResult: "salesforce-account-profile-preflight-result/v1",
  resolveRequest: "salesforce-account-profile-resolve-request/v1",
  resolveResult: "salesforce-account-profile-resolve-result/v1",
  accountReceipt: "salesforce-account-profile-account-receipt/v1",
  profileRequest: "salesforce-account-profile-profile-request/v1",
  profileResult: "salesforce-account-profile-profile-result/v1",
  renderRequest: "salesforce-account-profile-render-request/v1",
  renderResult: "salesforce-account-profile-render-result/v1",
  readPlan: "salesforce-account-profile-read-plan/v2",
  approvalReceipt: "salesforce-account-profile-approval-receipt/v2",
  profileView: "salesforce-account-profile-view/v2",
  orgRegistryLegacy: "salesforce-account-profile-org-registry/v1",
  orgRegistryUnsigned: "salesforce-account-profile-org-registry/v2",
  orgRegistry: "salesforce-account-profile-org-registry/v3",
  session: "salesforce-account-profile-session/v2",
  doctorRequest: "salesforce-account-profile-doctor-request/v2",
  doctorResult: "salesforce-account-profile-doctor-result/v2",
  startRequest: "salesforce-account-profile-start-request/v2",
  startResult: "salesforce-account-profile-start-result/v2",
  continueRequest: "salesforce-account-profile-continue-request/v2",
  continueResult: "salesforce-account-profile-continue-result/v2",
  statusRequest: "salesforce-account-profile-status-request/v2",
  statusResult: "salesforce-account-profile-status-result/v2",
  abortRequest: "salesforce-account-profile-abort-request/v2",
  abortResult: "salesforce-account-profile-abort-result/v2",
  sandboxCertificationScopeRequest: "salesforce-account-profile-sandbox-certification-scope-request/v1",
  sandboxCertificationScopeResult: "salesforce-account-profile-sandbox-certification-scope-result/v1",
  sandboxCertificationRequest: "salesforce-account-profile-sandbox-certification-request/v1",
  sandboxCertificationScope: "salesforce-account-profile-sandbox-certification-scope/v1",
  sandboxFixtureManifest: "salesforce-account-profile-sandbox-fixtures/v1",
  sandboxCertificationEvidence: "salesforce-account-profile-sandbox-certification-evidence/v1",
  sandboxCertificationResult: "salesforce-account-profile-sandbox-certification-result/v1",
  productionApprovalScopeRequest: "salesforce-account-profile-production-approval-scope-request/v1",
  productionApprovalScopeResult: "salesforce-account-profile-production-approval-scope-result/v1",
  productionApprovalScope: "salesforce-account-profile-production-approval-scope/v1",
  productionApprovalRequest: "salesforce-account-profile-production-approval-request/v1",
  productionApprovalEvidence: "salesforce-account-profile-production-approval-evidence/v1",
  productionApprovalResult: "salesforce-account-profile-production-approval-result/v1",
  approvalTrust: "salesforce-account-profile-approval-trust/v1",
  approvalAssertion: "salesforce-account-profile-approval-assertion/v1",
  packageAttestation: "salesforce-account-profile-package-attestation/v1",
  sfRuntimeAttestation: "salesforce-account-profile-sf-runtime-attestation/v1",
  error: "salesforce-account-profile-error/v1",
});

export const CAPS = Object.freeze({
  inputBytes: 1_048_576,
  candidates: 20,
  familyAccounts: 500,
  opportunities: 2_000,
  lineItems: 5_000,
  users: 100,
  idsPerBatch: 200,
  managerDepth: 10,
  queries: 30,
  familyDepth: 10,
  runtimeManifestBytes: 65_536,
  executableBytes: 512 * 1024 * 1024,
  packageMetadataBytes: 1_048_576,
  authorizedOrgs: 200,
  approvalTrustBytes: 65_536,
  approvalTrustKeys: 32,
  approvalAssertionsPerOrg: 64,
});

export const ACCOUNT_ID = /^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
export const ORG_ID = /^00D[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
export const OPPORTUNITY_ID = /^006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
export const USER_ID = /^005[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
export const LINE_ITEM_ID = /^00k[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/i;
export const PRODUCT_ID = /^01t[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/i;
export const PRICEBOOK_ENTRY_ID = /^01u[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/i;
export const CLASSIFICATION = "confidential";
export const WARNING_ANNUALIZATION = "ANNUALIZATION_NOT_CERTIFIED";
export const FIELD_MAP_VERSION = "salesforce-account-profile-field-map/v1";
export const SESSION_TTL_MS = 30 * 60 * 1_000;
export const CERTIFICATION_SCOPE_TTL_MS = 30 * 60 * 1_000;
export const CERTIFICATION_APPROVAL_AUDIENCE =
  "salesforce-account-profile-certification/v1";
export const CERTIFICATION_APPROVAL_ROLES = Object.freeze({
  sandbox: "sandbox_certifier",
  productionAdministrator: "production_administrator",
  productionRiskOwner: "production_risk_owner",
});
export const SANDBOX_SUITE_VERSION =
  "salesforce-account-profile-sandbox-suite/v1";
export const SANDBOX_SCENARIO_IDS = Object.freeze([
  "org_identity",
  "metadata_compatibility",
  "unique_pipeline",
  "ambiguous_chooser",
  "literal_prefix",
  "family_exact_scope",
  "multicurrency",
  "annualization_disabled",
  "session_cleanup",
]);
export const PROFILE_SECTIONS = Object.freeze([
  "overview",
  "family",
  "opportunities",
  "products",
  "team",
]);
export const OPPORTUNITY_SCOPES = Object.freeze(["open", "closed", "all"]);
export const OUTPUT_TYPES = Object.freeze(["rendered", "json"]);
export const CERTIFICATION_STATES = Object.freeze([
  "offline_validated",
  "sandbox_read_certified",
  "production_read_approved",
]);
export const PRESETS = Object.freeze({
  snapshot: Object.freeze({
    sections: Object.freeze(["overview"]),
    scope: "selected_account",
    opportunity_scope: "open",
  }),
  pipeline: Object.freeze({
    sections: Object.freeze(["overview", "opportunities", "team"]),
    scope: "selected_account",
    opportunity_scope: "open",
  }),
  team: Object.freeze({
    sections: Object.freeze(["overview", "team"]),
    scope: "selected_account",
    opportunity_scope: "open",
  }),
  family_map: Object.freeze({
    sections: Object.freeze(["overview", "family"]),
    scope: "corporate_family",
    opportunity_scope: "open",
  }),
  full_selected: Object.freeze({
    sections: Object.freeze(["overview", "opportunities", "products", "team"]),
    scope: "selected_account",
    opportunity_scope: "open",
  }),
});
