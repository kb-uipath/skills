import assert from "node:assert/strict";
import test from "node:test";

import { recoveryForError } from "../scripts/recovery.mjs";

const ALLOWED_ACTIONS = new Set([
  "narrow_query",
  "reauthenticate",
  "request_permissions",
  "cancel",
]);

const ALLOWED_NARROWING_OPTIONS = new Set([
  "account_selector",
  "selected_account",
  "open_only",
  "close_date_window",
  "stage",
  "remove_line_items",
  "remove_team",
  "reduce_sections",
]);

test("maps each cap to deterministic, relevant narrowing options", () => {
  assert.deepEqual(recoveryForError("CANDIDATE_CAP_EXCEEDED"), {
    next_action: "narrow_query",
    narrowing_options: ["account_selector"],
  });
  assert.deepEqual(recoveryForError("FAMILY_ACCOUNT_CAP_EXCEEDED"), {
    next_action: "narrow_query",
    narrowing_options: ["selected_account"],
  });
  assert.deepEqual(recoveryForError("OPPORTUNITY_CAP_EXCEEDED"), {
    next_action: "narrow_query",
    narrowing_options: ["selected_account", "open_only", "close_date_window", "stage"],
  });
  assert.deepEqual(recoveryForError("LINE_ITEM_CAP_EXCEEDED"), {
    next_action: "narrow_query",
    narrowing_options: [
      "selected_account",
      "open_only",
      "close_date_window",
      "stage",
      "remove_line_items",
    ],
  });
  assert.deepEqual(recoveryForError("USER_CAP_EXCEEDED"), {
    next_action: "narrow_query",
    narrowing_options: ["selected_account", "remove_team"],
  });
  assert.deepEqual(recoveryForError("QUERY_CAP_EXCEEDED"), {
    next_action: "narrow_query",
    narrowing_options: [
      "selected_account",
      "remove_line_items",
      "remove_team",
      "reduce_sections",
    ],
  });
});

test("maps bounded family traversal failures to account narrowing", () => {
  for (const code of [
    "FAMILY_DISCOVERY_INCOMPLETE",
    "FAMILY_CYCLE_DETECTED",
    "FAMILY_DEPTH_LIMIT_REACHED",
  ]) {
    assert.deepEqual(recoveryForError(code), {
      next_action: "narrow_query",
      narrowing_options: ["selected_account"],
    });
  }
});

test("maps explicit authentication failures to reauthentication", () => {
  for (const code of [
    "AUTHENTICATION_FAILURE",
    "AUTH_REQUIRED",
    "INVALID_GRANT",
    "INVALID_SESSION",
    "SESSION_EXPIRED",
    "SF_AUTHENTICATION_FAILED",
  ]) {
    assert.deepEqual(recoveryForError(code), {
      next_action: "reauthenticate",
      narrowing_options: [],
    });
  }
});

test("maps explicit authorization failures to permission requests", () => {
  for (const code of [
    "FIELD_PERMISSION_DENIED",
    "INSUFFICIENT_ACCESS",
    "NOT_AUTHORIZED",
    "OBJECT_PERMISSION_DENIED",
    "PERMISSION_DENIED",
  ]) {
    assert.deepEqual(recoveryForError(code), {
      next_action: "request_permissions",
      narrowing_options: [],
    });
  }
});

test("ambiguous, security-sensitive, and unknown failures cancel without retries", () => {
  for (const code of [
    "SCHEMA_OR_AUTHORIZATION_FAILURE",
    "SCHEMA_FAILURE",
    "ORG_IDENTITY_MISMATCH",
    "ACCOUNT_RECEIPT_MISMATCH",
    "FAMILY_CONFIRMATION_MISMATCH",
    "PREDICATE_BINDING_FAILED",
    "RELATIONSHIP_INCONSISTENCY",
    "UNTRUSTED_SF_EXECUTABLE",
    "SF_EXECUTABLE_REATTESTATION_REQUIRED",
    "SF_RUNTIME_NOT_ENROLLED",
    "SF_COMMAND_NOT_ALLOWED",
    "TRUNCATED_QUERY_RESULT",
    "INPUT_CHANGED",
    "UNSAFE_INPUT_PATH",
    "SOME_FUTURE_FAILURE",
    "",
  ]) {
    assert.deepEqual(recoveryForError(code), {
      next_action: "cancel",
      narrowing_options: [],
    });
  }
});

test("ignores records, identifiers, messages, and partial data on error objects", () => {
  const secretId = "001000000000001AAA";
  const recovery = recoveryForError({
    code: "OPPORTUNITY_CAP_EXCEEDED",
    message: `Account ${secretId}`,
    details: {
      records: [{ Id: secretId, Name: "Sensitive account" }],
      partial_data: { owner: "Sensitive owner" },
    },
  });

  assert.deepEqual(recovery, {
    next_action: "narrow_query",
    narrowing_options: ["selected_account", "open_only", "close_date_window", "stage"],
  });
  const serialized = JSON.stringify(recovery);
  assert.doesNotMatch(serialized, /001000000000001AAA|Sensitive|records|partial_data/);
});

test("always returns the fixed recovery schema and allowed vocabulary", () => {
  const codes = [
    "CANDIDATE_CAP_EXCEEDED",
    "FAMILY_ACCOUNT_CAP_EXCEEDED",
    "OPPORTUNITY_CAP_EXCEEDED",
    "LINE_ITEM_CAP_EXCEEDED",
    "USER_CAP_EXCEEDED",
    "QUERY_CAP_EXCEEDED",
    "AUTHENTICATION_FAILURE",
    "INSUFFICIENT_ACCESS",
    "UNKNOWN",
  ];

  for (const code of codes) {
    const recovery = recoveryForError(code);
    assert.deepEqual(Object.keys(recovery), ["next_action", "narrowing_options"]);
    assert.equal(ALLOWED_ACTIONS.has(recovery.next_action), true);
    assert.equal(Array.isArray(recovery.narrowing_options), true);
    assert.equal(
      recovery.narrowing_options.every((option) => ALLOWED_NARROWING_OPTIONS.has(option)),
      true,
    );
    assert.equal(Object.isFrozen(recovery), true);
    assert.equal(Object.isFrozen(recovery.narrowing_options), true);
  }
});
