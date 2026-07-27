const ACTIONS = Object.freeze({
  cancel: "cancel",
  narrowQuery: "narrow_query",
  reauthenticate: "reauthenticate",
  requestPermissions: "request_permissions",
});

const makeRecovery = (nextAction, narrowingOptions = []) => Object.freeze({
  next_action: nextAction,
  narrowing_options: Object.freeze([...narrowingOptions]),
});

const CANCEL = makeRecovery(ACTIONS.cancel);
const REAUTHENTICATE = makeRecovery(ACTIONS.reauthenticate);
const REQUEST_PERMISSIONS = makeRecovery(ACTIONS.requestPermissions);

const CAP_RECOVERY = new Map([
  ["CANDIDATE_CAP_EXCEEDED", makeRecovery(ACTIONS.narrowQuery, ["account_selector"])],
  ["FAMILY_ACCOUNT_CAP_EXCEEDED", makeRecovery(ACTIONS.narrowQuery, ["selected_account"])],
  ["OPPORTUNITY_CAP_EXCEEDED", makeRecovery(ACTIONS.narrowQuery, [
    "selected_account",
    "open_only",
    "close_date_window",
    "stage",
  ])],
  ["LINE_ITEM_CAP_EXCEEDED", makeRecovery(ACTIONS.narrowQuery, [
    "selected_account",
    "open_only",
    "close_date_window",
    "stage",
    "remove_line_items",
  ])],
  ["USER_CAP_EXCEEDED", makeRecovery(ACTIONS.narrowQuery, [
    "selected_account",
    "remove_team",
  ])],
  ["QUERY_CAP_EXCEEDED", makeRecovery(ACTIONS.narrowQuery, [
    "selected_account",
    "remove_line_items",
    "remove_team",
    "reduce_sections",
  ])],
  ["FAMILY_DISCOVERY_INCOMPLETE", makeRecovery(ACTIONS.narrowQuery, ["selected_account"])],
  ["FAMILY_CYCLE_DETECTED", makeRecovery(ACTIONS.narrowQuery, ["selected_account"])],
  ["FAMILY_DEPTH_LIMIT_REACHED", makeRecovery(ACTIONS.narrowQuery, ["selected_account"])],
  ["INVALID_NARROWING", makeRecovery(ACTIONS.narrowQuery, [
    "selected_account",
    "open_only",
    "close_date_window",
    "stage",
    "remove_line_items",
    "remove_team",
  ])],
]);

const AUTHENTICATION_FAILURES = new Set([
  "AUTHENTICATION_FAILURE",
  "AUTH_REQUIRED",
  "INVALID_GRANT",
  "INVALID_SESSION",
  "SESSION_EXPIRED",
  "SF_AUTHENTICATION_FAILED",
]);

const PERMISSION_FAILURES = new Set([
  "FIELD_PERMISSION_DENIED",
  "INSUFFICIENT_ACCESS",
  "NOT_AUTHORIZED",
  "OBJECT_PERMISSION_DENIED",
  "PERMISSION_DENIED",
]);

/**
 * Convert a fail-closed error code to the small recovery vocabulary consumed by
 * the Phase 3 user experience. No source error details are returned.
 */
export function recoveryForError(errorOrCode) {
  const code = typeof errorOrCode === "string"
    ? errorOrCode
    : errorOrCode && typeof errorOrCode.code === "string"
      ? errorOrCode.code
      : "";

  if (CAP_RECOVERY.has(code)) return CAP_RECOVERY.get(code);
  if (AUTHENTICATION_FAILURES.has(code)) return REAUTHENTICATE;
  if (PERMISSION_FAILURES.has(code)) return REQUEST_PERMISSIONS;
  return CANCEL;
}
