import assert from "node:assert/strict";
import test from "node:test";

import {
  validateAbortRequest,
  validateContinueRequest,
  validateDoctorRequest,
  validateStartRequest,
  validateStatusRequest,
} from "../scripts/conversational-contracts.mjs";
import { CONTRACTS } from "../scripts/constants.mjs";

const sessionId = "0123456789abcdef0123456789abcdef";
const accountId = "001000000000001AAA";

function start(overrides = {}) {
  return {
    schema_version: CONTRACTS.startRequest,
    target_org: "Production",
    account_selector: {
      mode: "exact_name",
      value: "Example Account",
    },
    ...overrides,
  };
}

function continuation(decision, overrides = {}) {
  return {
    schema_version: CONTRACTS.continueRequest,
    session_id: sessionId,
    decision,
    ...overrides,
  };
}

test("doctor accepts inspection or a complete safe enrollment request", () => {
  assert.deepEqual(
    validateDoctorRequest({ schema_version: CONTRACTS.doctorRequest }),
    { schema_version: CONTRACTS.doctorRequest },
  );
  assert.equal(validateDoctorRequest({
    schema_version: CONTRACTS.doctorRequest,
    target_org: "synthetic",
    friendly_label: "UAT",
    environment: "sandbox",
  }).friendly_label, "UAT");
  assert.throws(() => validateDoctorRequest({
    schema_version: CONTRACTS.doctorRequest,
    target_org: "synthetic",
  }), { code: "INVALID_DOCTOR_REQUEST" });
  assert.throws(() => validateDoctorRequest({
    schema_version: CONTRACTS.doctorRequest,
    target_org: "synthetic",
    friendly_label: "UAT",
    environment: "customer",
  }), { code: "INVALID_DOCTOR_REQUEST" });
});

test("doctor rejects paths, digests, and other unknown transport fields", () => {
  for (const forbidden of ["input_path", "output_path", "org_digest", "sf_path"]) {
    assert.throws(() => validateDoctorRequest({
      schema_version: CONTRACTS.doctorRequest,
      [forbidden]: "not allowed",
    }), { code: "UNKNOWN_INPUT_FIELD" });
  }
});

test("start defaults to the selected-account pipeline and rendered output", () => {
  const result = validateStartRequest(start());
  assert.deepEqual(result, {
    schema_version: CONTRACTS.startRequest,
    target_org: "Production",
    account_selector: {
      mode: "exact_name",
      value: "Example Account",
    },
    preset: "pipeline",
    sections: ["overview", "opportunities", "team"],
    scope: "selected_account",
    opportunity_scope: "open",
    filters: {
      close_date_from: null,
      close_date_to: null,
      stages: [],
    },
    output_type: "rendered",
  });
});

test("start supports every fixed preset without allowing preset drift", () => {
  const expected = {
    snapshot: [["overview"], "selected_account"],
    pipeline: [["overview", "opportunities", "team"], "selected_account"],
    team: [["overview", "team"], "selected_account"],
    family_map: [["overview", "family"], "corporate_family"],
    full_selected: [
      ["overview", "opportunities", "products", "team"],
      "selected_account",
    ],
  };
  for (const [preset, [sections, scope]] of Object.entries(expected)) {
    const result = validateStartRequest(start({ preset }));
    assert.deepEqual(result.sections, sections);
    assert.equal(result.scope, scope);
  }
  assert.throws(() => validateStartRequest(start({
    preset: "pipeline",
    scope: "corporate_family",
  })), { code: "INVALID_START_REQUEST" });
});

test("custom start accepts canonical business scope, filters, and JSON output", () => {
  const result = validateStartRequest(start({
    preset: "custom",
    sections: ["overview", "family", "opportunities", "products", "team"],
    scope: "corporate_family",
    opportunity_scope: "closed",
    filters: {
      close_date_from: "2029-01-01",
      close_date_to: "2030-12-31",
      stages: ["Closed Won", "Negotiation"],
    },
    output_type: "json",
  }));
  assert.equal(result.output_type, "json");
  assert.deepEqual(result.filters.stages, ["Closed Won", "Negotiation"]);
  assert.throws(() => validateStartRequest(start({ preset: "custom" })), {
    code: "INVALID_START_REQUEST",
  });
});

test("start validates real ordered dates and canonical unique sections and stages", () => {
  const custom = {
    preset: "custom",
    sections: ["overview", "opportunities"],
    scope: "selected_account",
    opportunity_scope: "all",
  };
  assert.throws(() => validateStartRequest(start({
    ...custom,
    filters: { close_date_from: "2030-02-30" },
  })), { code: "INVALID_START_REQUEST" });
  assert.throws(() => validateStartRequest(start({
    ...custom,
    filters: {
      close_date_from: "2031-01-01",
      close_date_to: "2030-01-01",
    },
  })), { code: "INVALID_START_REQUEST" });
  assert.throws(() => validateStartRequest(start({
    ...custom,
    sections: ["opportunities", "overview"],
  })), { code: "INVALID_START_REQUEST" });
  assert.throws(() => validateStartRequest(start({
    ...custom,
    filters: { stages: ["Negotiation", "Discovery"] },
  })), { code: "INVALID_START_REQUEST" });
  assert.throws(() => validateStartRequest(start({
    ...custom,
    filters: { stages: ["Discovery", "Discovery"] },
  })), { code: "INVALID_START_REQUEST" });
});

test("start allows adversarial literal names only as inert safe data", () => {
  const value = "O'Brien $(touch relative-nope); SELECT * FROM Account";
  assert.equal(
    validateStartRequest(start({
      account_selector: { mode: "exact_name", value },
    })).account_selector.value,
    value,
  );
  assert.throws(() => validateStartRequest(start({
    account_selector: {
      mode: "exact_name",
      value: "Unsafe\u001b[31m",
    },
  })), { code: "INVALID_START_REQUEST" });
  assert.throws(() => validateStartRequest(start({
    account_selector: {
      mode: "prefix",
      value: "Example",
    },
  })), { code: "INVALID_START_REQUEST" });
});

test("user-facing Account ID selection requires an 18-character Account ID", () => {
  assert.equal(validateStartRequest(start({
    account_selector: { mode: "id", value: accountId },
  })).account_selector.value, accountId);
  assert.throws(() => validateStartRequest(start({
    account_selector: { mode: "id", value: "001000000000001" },
  })), { code: "INVALID_START_REQUEST" });

  assert.equal(validateContinueRequest(continuation({
    action: "choose_account",
    account_id: accountId,
  })).decision.account_id, accountId);
  for (const invalid of ["001000000000001", "006000000000001AAA", "001-unsafe"]) {
    assert.throws(() => validateContinueRequest(continuation({
      action: "choose_account",
      account_id: invalid,
    })), { code: "INVALID_CONTINUE_REQUEST" });
  }
});

test("choose_account accepts exactly one Account ID or explicit literal prefix", () => {
  assert.equal(validateContinueRequest(continuation({
    action: "choose_account",
    literal_prefix: "Example O'Brien %_",
  })).decision.literal_prefix, "Example O'Brien %_");
  assert.throws(() => validateContinueRequest(continuation({
    action: "choose_account",
  })), { code: "INVALID_CONTINUE_REQUEST" });
  assert.throws(() => validateContinueRequest(continuation({
    action: "choose_account",
    account_id: accountId,
    literal_prefix: "Example",
  })), { code: "INVALID_CONTINUE_REQUEST" });
});

test("continue accepts fieldless decisions and rejects nested drift", () => {
  for (const action of [
    "confirm_org_and_plan",
    "approve_family_scope",
    "reauthenticate",
    "request_permissions",
    "cancel",
  ]) {
    assert.deepEqual(
      validateContinueRequest(continuation({ action })).decision,
      { action },
    );
  }
  assert.throws(() => validateContinueRequest(continuation({
    action: "confirm_org_and_plan",
    confirmed_digest: "a".repeat(64),
  })), { code: "UNKNOWN_INPUT_FIELD" });
  assert.throws(() => validateContinueRequest(continuation({
    action: "run_arbitrary_query",
  })), { code: "INVALID_CONTINUE_REQUEST" });
});

test("narrow_query accepts only bounded business narrowing", () => {
  assert.deepEqual(validateContinueRequest(continuation({
    action: "narrow_query",
    scope: "selected_account",
    opportunity_scope: "open",
    filters: {
      close_date_from: "2030-01-01",
      stages: ["Discovery", "Negotiation"],
    },
  })).decision, {
    action: "narrow_query",
    scope: "selected_account",
    opportunity_scope: "open",
    filters: {
      close_date_from: "2030-01-01",
      stages: ["Discovery", "Negotiation"],
    },
  });
  assert.deepEqual(validateContinueRequest(continuation({
    action: "narrow_query",
    account_selector: {
      mode: "id",
      value: "001000000000001AAA",
    },
    remove_sections: ["products", "team"],
  })).decision, {
    action: "narrow_query",
    account_selector: {
      mode: "id",
      value: "001000000000001AAA",
    },
    remove_sections: ["products", "team"],
  });
  assert.throws(() => validateContinueRequest(continuation({
    action: "narrow_query",
  })), { code: "INVALID_CONTINUE_REQUEST" });
  assert.throws(() => validateContinueRequest(continuation({
    action: "narrow_query",
    scope: "corporate_family",
  })), { code: "INVALID_CONTINUE_REQUEST" });
  assert.throws(() => validateContinueRequest(continuation({
    action: "narrow_query",
    filters: {},
  })), { code: "INVALID_CONTINUE_REQUEST" });
  assert.throws(() => validateContinueRequest(continuation({
    action: "narrow_query",
    filters: { stages: [] },
  })), { code: "INVALID_CONTINUE_REQUEST" });
  assert.throws(() => validateContinueRequest(continuation({
    action: "narrow_query",
    remove_sections: ["overview"],
  })), { code: "INVALID_CONTINUE_REQUEST" });
});

test("continue, status, and abort strictly validate the session transport", () => {
  for (const validator of [validateStatusRequest, validateAbortRequest]) {
    const schema = validator === validateStatusRequest
      ? CONTRACTS.statusRequest
      : CONTRACTS.abortRequest;
    assert.equal(validator({
      schema_version: schema,
      session_id: sessionId,
    }).session_id, sessionId);
    assert.throws(() => validator({
      schema_version: schema,
      session_id: `${sessionId}../`,
    }), { code: "INVALID_SESSION_ID" });
    assert.throws(() => validator({
      schema_version: schema,
      session_id: sessionId,
      output_path: "synthetic-profile.json",
    }), { code: "UNKNOWN_INPUT_FIELD" });
  }
  assert.deepEqual(validateStatusRequest({
    schema_version: CONTRACTS.statusRequest,
  }), {
    schema_version: CONTRACTS.statusRequest,
  });
  assert.throws(() => validateContinueRequest(continuation(
    { action: "cancel" },
    { org_digest: "a".repeat(64) },
  )), { code: "UNKNOWN_INPUT_FIELD" });
});

test("all conversational validators reject contract-version drift", () => {
  assert.throws(() => validateDoctorRequest({
    schema_version: "wrong",
  }), { code: "CONTRACT_VERSION_MISMATCH" });
  assert.throws(() => validateStartRequest({
    ...start(),
    schema_version: "wrong",
  }), { code: "CONTRACT_VERSION_MISMATCH" });
  assert.throws(() => validateContinueRequest({
    ...continuation({ action: "cancel" }),
    schema_version: "wrong",
  }), { code: "CONTRACT_VERSION_MISMATCH" });
});
