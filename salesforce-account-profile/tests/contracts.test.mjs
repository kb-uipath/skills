import assert from "node:assert/strict";
import test from "node:test";

import { CONTRACTS } from "../scripts/constants.mjs";
import {
  orgDigest,
  validatePreflightRequest,
  validateProfileRequest,
  validateResolveRequest,
} from "../scripts/contracts.mjs";
import { IDS, MockClient, orgDigestFor, receiptFor } from "./helpers.mjs";

test("preflight requires an explicit target-org alias", () => {
  assert.throws(() => validatePreflightRequest({ schema_version: CONTRACTS.preflightRequest }), { code: "MISSING_INPUT_FIELD" });
});

test("contracts reject unknown input fields", () => {
  assert.throws(() => validatePreflightRequest({
    schema_version: CONTRACTS.preflightRequest,
    target_org: "synthetic",
    account_name: "not allowed",
  }), { code: "UNKNOWN_INPUT_FIELD" });
});

test("public contracts reject executable-path injection", () => {
  assert.throws(() => validatePreflightRequest({
    schema_version: CONTRACTS.preflightRequest,
    target_org: "synthetic",
    sf_path: "arbitrary-executable",
  }), { code: "UNKNOWN_INPUT_FIELD" });
});

test("resolve rejects substring mode", () => {
  const client = new MockClient();
  assert.throws(() => validateResolveRequest({
    schema_version: CONTRACTS.resolveRequest,
    target_org: "synthetic",
    confirmed_org_digest: orgDigestFor(client),
    selector: { mode: "substring", value: "amp" },
  }), { code: "INVALID_SELECTOR" });
});

test("resolve accepts only validated Account IDs", () => {
  const client = new MockClient();
  assert.throws(() => validateResolveRequest({
    schema_version: CONTRACTS.resolveRequest,
    target_org: "synthetic",
    confirmed_org_digest: orgDigestFor(client),
    selector: { mode: "id", value: "006000000000001AAA" },
  }), { code: "INVALID_ACCOUNT_ID" });
});

test("profile defaults to overview, selected account, and open opportunities", () => {
  const client = new MockClient();
  const result = validateProfileRequest({
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic",
    confirmed_org_digest: orgDigestFor(client),
    account_receipt: receiptFor(client, { Id: IDS.account1, Name: "Example" }),
  });
  assert.deepEqual(result.sections, ["overview"]);
  assert.equal(result.scope, "selected_account");
  assert.equal(result.opportunity_scope, "open");
});

test("profile rejects duplicate or unknown sections", () => {
  const client = new MockClient();
  const base = {
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic",
    confirmed_org_digest: orgDigestFor(client),
    account_receipt: receiptFor(client),
  };
  assert.throws(() => validateProfileRequest({ ...base, sections: ["family", "family"] }), { code: "INVALID_SECTIONS" });
  assert.throws(() => validateProfileRequest({ ...base, sections: ["legal_subsidiaries"] }), { code: "INVALID_SECTIONS" });
});

test("nested account receipt rejects unknown fields and invalid name types", () => {
  const client = new MockClient();
  const base = {
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic",
    confirmed_org_digest: orgDigestFor(client),
  };
  assert.throws(() => validateProfileRequest({
    ...base,
    account_receipt: {
      ...receiptFor(client),
      account: { ...receiptFor(client).account, injected: true },
    },
  }), { code: "UNKNOWN_INPUT_FIELD" });
  assert.throws(() => validateProfileRequest({
    ...base,
    account_receipt: {
      ...receiptFor(client),
      account: { Id: IDS.account1, Name: 42 },
    },
  }), { code: "INVALID_ACCOUNT_RECEIPT" });
});

test("org consistency digest binds the pinned Salesforce runtime", () => {
  const identity = new MockClient().identity;
  assert.notEqual(
    orgDigest("synthetic", identity, "a".repeat(64)),
    orgDigest("synthetic", identity, "b".repeat(64)),
  );
});
