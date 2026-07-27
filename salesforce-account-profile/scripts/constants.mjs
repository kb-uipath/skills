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
export const PROFILE_SECTIONS = Object.freeze([
  "overview",
  "family",
  "opportunities",
  "products",
  "team",
]);
export const OPPORTUNITY_SCOPES = Object.freeze(["open", "closed", "all"]);
export const OUTPUT_TYPES = Object.freeze(["rendered", "json"]);
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
