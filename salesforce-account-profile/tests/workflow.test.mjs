import assert from "node:assert/strict";
import test from "node:test";

import { CAPS, CONTRACTS, WARNING_ANNUALIZATION } from "../scripts/constants.mjs";
import { buildRenderResult } from "../scripts/render.mjs";
import { profile, render, resolve } from "../scripts/workflow.mjs";
import { DESCRIBE, IDS, MockClient, describeMap, orgDigestFor, receiptFor } from "./helpers.mjs";

const account = {
  Id: IDS.account1,
  Name: "Example",
  ParentId: null,
  OwnerId: IDS.user1,
  Ultimate_Parent_name__c: "Example Family",
};
const secondAccount = {
  Id: IDS.account2,
  Name: "Example Division",
  ParentId: IDS.account1,
  OwnerId: IDS.user2,
  Ultimate_Parent_name__c: "Example Family",
};

function resolveRequest(client, selector) {
  return {
    schema_version: CONTRACTS.resolveRequest,
    target_org: "synthetic",
    confirmed_org_digest: orgDigestFor(client),
    selector,
  };
}

function profileRequest(client, overrides = {}) {
  return {
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic",
    confirmed_org_digest: orgDigestFor(client),
    account_receipt: receiptFor(client, { Id: account.Id, Name: account.Name }),
    ...overrides,
  };
}

test("exact resolution selects exactly one Account", async () => {
  const client = new MockClient({ query: () => [account] });
  const result = await resolve(resolveRequest(client, { mode: "exact_name", value: "Example" }), { client });
  assert.equal(result.status, "selected");
  assert.equal(result.selected_account.Id, account.Id);
});

test("exact and prefix name binding follow Salesforce case-insensitive semantics", async () => {
  const exactClient = new MockClient({ query: () => [account] });
  const exact = await resolve(resolveRequest(exactClient, { mode: "exact_name", value: "example" }), { client: exactClient });
  assert.equal(exact.status, "selected");
  const prefixClient = new MockClient({ query: () => [account] });
  const prefix = await resolve(resolveRequest(prefixClient, { mode: "prefix", value: "EXA" }), { client: prefixClient });
  assert.equal(prefix.status, "chooser");
});

test("exact resolution returns no_match without fallback", async () => {
  const client = new MockClient({ query: () => [] });
  const result = await resolve(resolveRequest(client, { mode: "exact_name", value: "Missing" }), { client });
  assert.equal(result.status, "no_match");
  assert.deepEqual(result.candidates, []);
});

test("exact resolution returns ambiguous chooser data", async () => {
  const client = new MockClient({ query: () => [
    { ...account, Name: "Repeated" },
    { ...secondAccount, Name: "Repeated" },
  ] });
  const result = await resolve(resolveRequest(client, { mode: "exact_name", value: "Repeated" }), { client });
  assert.equal(result.status, "ambiguous");
  assert.equal(result.candidates.length, 2);
});

test("resolve rejects rows that do not bind to the requested predicate", async () => {
  const idClient = new MockClient({ query: () => [secondAccount] });
  await assert.rejects(
    () => resolve(resolveRequest(idClient, { mode: "id", value: account.Id }), { client: idClient }),
    { code: "PREDICATE_BINDING_FAILED" },
  );
  const nameClient = new MockClient({ query: () => [secondAccount] });
  await assert.rejects(
    () => resolve(resolveRequest(nameClient, { mode: "exact_name", value: "Example" }), { client: nameClient }),
    { code: "PREDICATE_BINDING_FAILED" },
  );
});

test("prefix resolution always returns a chooser even for one candidate", async () => {
  const client = new MockClient({ query: () => [account] });
  const result = await resolve(resolveRequest(client, { mode: "prefix", value: "Ex" }), { client });
  assert.equal(result.status, "chooser");
  assert.equal(result.account_receipt, undefined);
});

test("candidate cap fails instead of truncating", async () => {
  const records = Array.from({ length: CAPS.candidates + 1 }, (_, index) => ({
    ...account,
    Id: `001${String(index).padStart(12, "0")}AAA`,
  }));
  const client = new MockClient({ query: () => records });
  await assert.rejects(
    () => resolve(resolveRequest(client, { mode: "prefix", value: "E" }), { client }),
    { code: "CANDIDATE_CAP_EXCEEDED" },
  );
});

test("org mismatch fails before account query", async () => {
  const client = new MockClient();
  await assert.rejects(
    () => resolve({
      ...resolveRequest(client, { mode: "id", value: account.Id }),
      confirmed_org_digest: "0".repeat(64),
    }, { client }),
    { code: "ORG_IDENTITY_MISMATCH" },
  );
  assert.equal(client.queryCount, 0);
});

test("selected Account row must match the receipt ID", async () => {
  const client = new MockClient({ query: () => [secondAccount] });
  await assert.rejects(() => profile(profileRequest(client), { client }), { code: "RELATIONSHIP_INCONSISTENCY" });
});

test("prefix resolution escapes percent and underscore literally", async () => {
  let observed;
  const client = new MockClient({ query: (soql) => {
    observed = soql;
    return [];
  } });
  await resolve(resolveRequest(client, { mode: "prefix", value: "A%_B" }), { client });
  assert(observed.includes("Name LIKE 'A\\%\\_B%'"));
});

test("required-field drift fails closed", async () => {
  const client = new MockClient({
    describes: { ...DESCRIBE, Account: ["Id", "ParentId", "OwnerId"] },
    query: () => [account],
  });
  await assert.rejects(
    () => profile(profileRequest(client), { client }),
    { code: "SCHEMA_FAILURE" },
  );
});

test("present custom fields with incompatible semantics fail closed", async () => {
  const client = new MockClient({ query: () => [account] });
  client.describe = async (objectName) => {
    const fields = describeMap(DESCRIBE[objectName] ?? []);
    if (objectName === "Account") {
      fields.set("Ultimate_Parent_name__c", {
        ...fields.get("Ultimate_Parent_name__c"),
        type: "currency",
      });
    }
    return fields;
  };
  await assert.rejects(
    () => profile(profileRequest(client, { sections: ["family"] }), { client }),
    { code: "SCHEMA_FAILURE" },
  );
});

test("missing custom fields warn and do not invent values", async () => {
  const client = new MockClient({
    describes: { ...DESCRIBE, Account: ["Id", "Name", "ParentId", "OwnerId"] },
    query: () => [account],
  });
  const result = await profile(profileRequest(client), { client });
  assert.equal(result.status, "complete");
  assert.equal("Support_Status__c" in result.selected_account, false);
  assert(result.warnings.includes("OPTIONAL_FIELD_UNAVAILABLE:Account.Support_Status__c"));
  assert(result.warnings.includes("OPTIONAL_FIELD_UNAVAILABLE:Account.PreSales__c"));
});

test("products-only Account query reads core fields and no overview optionals", async () => {
  const accountQueries = [];
  const opportunityQueries = [];
  const opportunity = { Id: IDS.opportunity1, Name: "A", AccountId: IDS.account1, OwnerId: IDS.user1, StageName: "Open", Amount: 100, CloseDate: "2030-01-01", IsClosed: false, IsWon: false, CurrencyIsoCode: "USD", HasOpportunityLineItem: false };
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM Account")) {
        accountQueries.push(soql);
        return [account];
      }
      if (soql.includes("FROM OpportunityLineItem")) return [];
      if (soql.includes("FROM Opportunity")) {
        opportunityQueries.push(soql);
        return [opportunity];
      }
      return [];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["products"] }), { client });
  assert.equal(accountQueries.length, 1);
  assert(!accountQueries[0].includes("Billed_ARR_YTD__c"));
  assert(!accountQueries[0].includes("Support_Status__c"));
  assert(!accountQueries[0].includes("CSM__c"));
  assert(!result.warnings.some((warning) => warning.includes("Support_Status__c")));
  assert.equal(opportunityQueries.length, 1);
  assert(!opportunityQueries[0].includes("Amount"));
  assert(!opportunityQueries[0].includes("OwnerId"));
  assert(!opportunityQueries[0].includes("StageName"));
  assert(!opportunityQueries[0].includes("CloseDate"));
  assert(!opportunityQueries[0].includes("Deal_Type__c"));
  assert(opportunityQueries[0].includes("ORDER BY Id"));
});

test("generic Account overview never emits an unlabeled ARR amount", async () => {
  const client = new MockClient({ query: () => [{ ...account, Billed_ARR_YTD__c: 999 }] });
  const result = await profile(profileRequest(client), { client });
  assert.equal("Billed_ARR_YTD__c" in result.selected_account, false);
  const rendered = buildRenderResult(result);
  assert(!rendered.markdown.includes("Billed ARR"));
  assert(!rendered.markdown.includes("999"));
});

test("family-only Account queries use the family key but not overview optionals", async () => {
  const accountQueries = [];
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM Account")) accountQueries.push(soql);
      return soql.includes("Ultimate_Parent_name__c =") ? [account, secondAccount] : [account];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["family"] }), { client });
  assert(accountQueries.every((soql) => !soql.includes("Billed_ARR_YTD__c")));
  assert(accountQueries.every((soql) => !soql.includes("Support_Status__c")));
  assert(accountQueries.some((soql) => soql.includes("Ultimate_Parent_name__c")));
  assert.equal("Ultimate_Parent_name__c" in result.accounts[0], false);
});

test("overview plus family keeps overview custom fields out of family discovery", async () => {
  const accountQueries = [];
  const overviewAccount = { ...account, Region__c: "Synthetic Region" };
  const client = new MockClient({
    describes: { ...DESCRIBE, Account: [...DESCRIBE.Account, "Region__c", "Support_Status__c"] },
    query: (soql) => {
      if (soql.includes("FROM Account")) accountQueries.push(soql);
      return soql.includes("Ultimate_Parent_name__c =") ? [account, secondAccount] : [overviewAccount];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["overview", "family"] }), { client });
  assert.equal(result.selected_account.Region__c, "Synthetic Region");
  assert(accountQueries[0].includes("Region__c"));
  assert(!accountQueries[1].includes("Region__c"));
  assert(!accountQueries[1].includes("Support_Status__c"));
});

test("empty configured family key validates ParentId fallback and warns distinctly", async () => {
  const emptyFamily = { ...account, Ultimate_Parent_name__c: null };
  const client = new MockClient({
    query: (soql) => soql.includes("ParentId IN") ? [] : [emptyFamily],
  });
  const result = await profile(profileRequest(client, { sections: ["family"] }), { client });
  assert(result.warnings.includes("ULTIMATE_PARENT_FIELD_EMPTY_USING_PARENT_TRAVERSAL"));
  assert(!result.warnings.includes("ULTIMATE_PARENT_FIELD_UNAVAILABLE_USING_PARENT_TRAVERSAL"));
});

test("corporate-family queries require confirmation of the exact ID set", async () => {
  const client = new MockClient({
    query: (soql) => soql.includes("Ultimate_Parent_name__c =") ? [account, secondAccount] : [account],
  });
  const result = await profile(profileRequest(client, {
    sections: ["family", "opportunities"],
    scope: "corporate_family",
  }), { client });
  assert.equal(result.status, "family_confirmation_required");
  assert.deepEqual(result.family_confirmation.account_ids, [IDS.account1, IDS.account2]);
  assert.deepEqual(result.opportunities, []);
});

test("family confirmation minimizes data when family details were not requested", async () => {
  const client = new MockClient({
    query: (soql) => soql.includes("Ultimate_Parent_name__c =") ? [account, secondAccount] : [account],
  });
  const result = await profile(profileRequest(client, {
    sections: ["products"],
    scope: "corporate_family",
  }), { client });
  assert.equal(result.status, "family_confirmation_required");
  assert.deepEqual(result.accounts, []);
  assert.deepEqual(result.opportunities, []);
  assert.deepEqual(result.products, []);
  assert.deepEqual(result.family_confirmation.account_ids, [IDS.account1, IDS.account2]);
  assert.equal("Ultimate_Parent_name__c" in result.selected_account, false);
});

test("family confirmation mismatch fails when supplied set changes", async () => {
  const client = new MockClient({
    query: (soql) => soql.includes("Ultimate_Parent_name__c =") ? [account, secondAccount] : [account],
  });
  await assert.rejects(() => profile(profileRequest(client, {
    sections: ["family"],
    scope: "corporate_family",
    confirmed_family_digest: "f".repeat(64),
  }), { client }), { code: "FAMILY_CONFIRMATION_MISMATCH" });
});

test("ParentId traversal detects cycles and warns explicitly", async () => {
  const cyclic = { ...account, ParentId: account.Id };
  const client = new MockClient({
    describes: { ...DESCRIBE, Account: ["Id", "Name", "ParentId", "OwnerId"] },
    query: (soql) => soql.includes("ParentId IN") ? [] : [cyclic],
  });
  const result = await profile(profileRequest(client, { sections: ["family"] }), { client });
  assert(result.warnings.includes("FAMILY_CYCLE_DETECTED"));
  assert(result.warnings.includes("ULTIMATE_PARENT_FIELD_UNAVAILABLE_USING_PARENT_TRAVERSAL"));
});

test("ParentId traversal expands a deep selected path without inventing a cycle", async () => {
  const grandparentId = "001000000000003AAA";
  const siblingId = "001000000000004AAA";
  const descendantId = "001000000000005AAA";
  const child = { ...account, ParentId: IDS.account2 };
  const parent = { ...secondAccount, Name: "Parent", ParentId: grandparentId };
  const root = { ...secondAccount, Id: grandparentId, Name: "Root", ParentId: null };
  const sibling = { ...secondAccount, Id: siblingId, Name: "Sibling", ParentId: IDS.account2 };
  const descendant = { ...secondAccount, Id: descendantId, Name: "Descendant", ParentId: IDS.account1 };
  const client = new MockClient({
    describes: { ...DESCRIBE, Account: ["Id", "Name", "ParentId", "OwnerId"] },
    query: (soql) => {
      if (soql.includes(`WHERE Id = '${IDS.account1}'`)) return [child];
      if (soql.includes(`WHERE Id = '${IDS.account2}'`)) return [parent];
      if (soql.includes(`WHERE Id = '${grandparentId}'`)) return [root];
      if (soql.includes(`ParentId IN ('${grandparentId}')`)) return [parent];
      if (soql.includes(`ParentId IN ('${IDS.account2}')`)) return [child, sibling];
      if (soql.includes(IDS.account1) && soql.includes(siblingId)) return [descendant];
      if (soql.includes(`ParentId IN ('${descendantId}')`)) return [];
      return [];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["family"] }), { client });
  assert.deepEqual(result.accounts.map((item) => item.Id), [
    IDS.account1, IDS.account2, grandparentId, siblingId, descendantId,
  ]);
  assert(!result.warnings.includes("FAMILY_CYCLE_DETECTED"));
});

test("custom family discovery rejects duplicate IDs and mismatched family keys", async () => {
  const duplicateClient = new MockClient({
    query: (soql) => soql.includes("Ultimate_Parent_name__c =") ? [account, account] : [account],
  });
  await assert.rejects(
    () => profile(profileRequest(duplicateClient, { sections: ["family"] }), { client: duplicateClient }),
    { code: "FAMILY_INCONSISTENCY" },
  );
  const mismatchedClient = new MockClient({
    query: (soql) => soql.includes("Ultimate_Parent_name__c =")
      ? [account, { ...secondAccount, Ultimate_Parent_name__c: "Other Family" }]
      : [account],
  });
  await assert.rejects(
    () => profile(profileRequest(mismatchedClient, { sections: ["family"] }), { client: mismatchedClient }),
    { code: "FAMILY_INCONSISTENCY" },
  );
});

test("ParentId traversal reports the deterministic depth boundary", async () => {
  const ids = Array.from({ length: 12 }, (_, index) => `001${String(index + 1).padStart(12, "0")}AAA`);
  ids[0] = IDS.account1;
  const nodes = new Map(ids.map((id, index) => [id, {
    Id: id,
    Name: `Node ${index}`,
    ParentId: ids[index + 1] ?? null,
    OwnerId: IDS.user1,
  }]));
  nodes.get(IDS.account1).Name = "Example";
  const client = new MockClient({
    describes: { ...DESCRIBE, Account: ["Id", "Name", "ParentId", "OwnerId"] },
    query: (soql) => {
      if (soql.includes("ParentId IN")) return [];
      const id = [...nodes.keys()].find((candidate) => soql.includes(candidate));
      return id ? [nodes.get(id)] : [];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["family"] }), { client });
  assert(result.warnings.includes("FAMILY_DEPTH_LIMIT_REACHED"));
});

test("manager traversal detects cycles", async () => {
  const user1 = { Id: IDS.user1, Name: "Owner", Title: "AE", ManagerId: IDS.user2 };
  const user2 = { Id: IDS.user2, Name: "Manager", Title: "VP", ManagerId: IDS.user1 };
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM Account")) return [account];
      if (soql.includes(IDS.user1) && !soql.includes(IDS.user2)) return [user1];
      if (soql.includes(IDS.user2)) return [user2];
      return [];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["overview", "team"] }), { client });
  assert(result.warnings.includes("MANAGER_CYCLE_DETECTED"));
  assert.equal(result.team.length, 2);
});

test("multiple team seeds with a shared hierarchy do not invent a manager cycle", async () => {
  const user1 = { Id: IDS.user1, Name: "Owner", Title: "AE", ManagerId: IDS.user2 };
  const user2 = { Id: IDS.user2, Name: "Manager", Title: "VP", ManagerId: null };
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("Ultimate_Parent_name__c =")) return [account, secondAccount];
      if (soql.includes("FROM Account")) return [account];
      if (soql.includes("FROM User")) return [user1, user2];
      return [];
    },
  });
  const first = await profile(profileRequest(client, {
    sections: ["family", "team"],
    scope: "corporate_family",
  }), { client });
  assert(!first.warnings.includes("MANAGER_CYCLE_DETECTED"));
});

test("sf row type violations fail atomically before a complete profile can escape", async () => {
  const badResolveClient = new MockClient({ query: () => [{ ...account, Name: 42 }] });
  await assert.rejects(
    () => resolve(resolveRequest(badResolveClient, { mode: "id", value: account.Id }), { client: badResolveClient }),
    { code: "INVALID_FIELD_TYPE" },
  );

  const badOpportunity = {
    Id: IDS.opportunity1, Name: "Deal", AccountId: IDS.account1, OwnerId: IDS.user1,
    StageName: "Open", Amount: "100", CloseDate: "2030-01-01",
    IsClosed: false, IsWon: false, CurrencyIsoCode: "USD", HasOpportunityLineItem: false,
  };
  const badProfileClient = new MockClient({
    query: (soql) => soql.includes("FROM Opportunity") ? [badOpportunity] : [account],
  });
  await assert.rejects(
    () => profile(profileRequest(badProfileClient, { sections: ["opportunities"] }), { client: badProfileClient }),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );

  const badLineItem = {
    Id: "00k000000000001AAA", OpportunityId: IDS.opportunity1, Quantity: 1,
    UnitPrice: "100", TotalPrice: 100, CurrencyIsoCode: "USD",
    PricebookEntryId: "01u000000000001AAA",
    PricebookEntry: {
      Product2Id: "01t000000000001AAA",
      Product2: { Name: "Synthetic Product" },
    },
  };
  const validLink = {
    Id: IDS.opportunity1, AccountId: IDS.account1,
    IsClosed: false, IsWon: false, CurrencyIsoCode: "USD",
  };
  const badProductClient = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM OpportunityLineItem")) return [badLineItem];
      if (soql.includes("FROM Opportunity")) return [validLink];
      return [account];
    },
  });
  await assert.rejects(
    () => profile(profileRequest(badProductClient, { sections: ["products"] }), { client: badProductClient }),
    { code: "INVALID_PROFILE_RESULT" },
  );
});

test("manager traversal fails when a requested frontier User is missing", async () => {
  const client = new MockClient({
    query: (soql) => soql.includes("FROM User") ? [] : [account],
  });
  await assert.rejects(
    () => profile(profileRequest(client, { sections: ["team"] }), { client }),
    { code: "USER_FRONTIER_INCOMPLETE" },
  );
});

test("manager traversal reports the deterministic depth boundary", async () => {
  const ids = Array.from({ length: 12 }, (_, index) => `005${String(index + 1).padStart(12, "0")}AAA`);
  ids[0] = IDS.user1;
  const users = new Map(ids.map((id, index) => [id, {
    Id: id,
    Name: `User ${index}`,
    Title: "Synthetic",
    ManagerId: ids[index + 1] ?? null,
  }]));
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM Account")) return [account];
      const id = [...users.keys()].find((candidate) => soql.includes(candidate));
      return id ? [users.get(id)] : [];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["overview", "team"] }), { client });
  assert(result.warnings.includes("MANAGER_DEPTH_LIMIT_REACHED"));
  assert.equal(result.team.length, 10);
});

test("selected-account team scope does not widen when family display is requested", async () => {
  const userQueries = [];
  const owner = { Id: IDS.user1, Name: "Owner", Title: "AE", ManagerId: null };
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("Ultimate_Parent_name__c =")) return [account, secondAccount];
      if (soql.includes("FROM User")) {
        userQueries.push(soql);
        return [owner];
      }
      return [account];
    },
  });
  const result = await profile(profileRequest(client, {
    sections: ["family", "team"],
    scope: "selected_account",
  }), { client });
  assert.equal(result.team.length, 1);
  assert.equal(userQueries.length, 1);
  assert(userQueries[0].includes(IDS.user1));
  assert(!userQueries[0].includes(IDS.user2));
});

test("family Account cap fails without a truncated set", async () => {
  const family = Array.from({ length: CAPS.familyAccounts + 1 }, (_, index) => ({
    ...account,
    Id: `001${String(index + 1).padStart(12, "0")}AAA`,
  }));
  family[0] = account;
  const client = new MockClient({
    query: (soql) => soql.includes("Ultimate_Parent_name__c =") ? family : [account],
  });
  await assert.rejects(() => profile(profileRequest(client, { sections: ["family"] }), { client }), {
    code: "FAMILY_ACCOUNT_CAP_EXCEEDED",
  });
});

test("Opportunity cap fails without a partial result", async () => {
  const opportunities = Array.from({ length: CAPS.opportunities + 1 }, (_, index) => ({
    Id: `006${String(index + 1).padStart(12, "0")}AAA`,
    Name: `Opportunity ${index}`,
    AccountId: IDS.account1,
    OwnerId: IDS.user1,
    StageName: "Open",
    Amount: index,
    CloseDate: "2030-01-01",
    IsClosed: false,
    IsWon: false,
    CurrencyIsoCode: "USD",
    HasOpportunityLineItem: false,
  }));
  const client = new MockClient({
    query: (soql) => soql.includes("FROM Opportunity") ? opportunities : [account],
  });
  await assert.rejects(() => profile(profileRequest(client, { sections: ["overview", "opportunities"] }), { client }), {
    code: "OPPORTUNITY_CAP_EXCEEDED",
  });
});

test("Opportunity scope and duplicate predicates bind atomically", async () => {
  const closedOpportunity = {
    Id: IDS.opportunity1, Name: "Closed", AccountId: IDS.account1, OwnerId: IDS.user1,
    StageName: "Closed", Amount: 100, CloseDate: "2030-01-01",
    IsClosed: true, IsWon: true, CurrencyIsoCode: "USD", HasOpportunityLineItem: false,
  };
  const wrongScopeClient = new MockClient({
    query: (soql) => soql.includes("FROM Opportunity") ? [closedOpportunity] : [account],
  });
  await assert.rejects(
    () => profile(profileRequest(wrongScopeClient, { sections: ["opportunities"], opportunity_scope: "open" }), { client: wrongScopeClient }),
    { code: "PREDICATE_BINDING_FAILED" },
  );

  const duplicateClient = new MockClient({
    query: (soql) => soql.includes("FROM Opportunity")
      ? [{ ...closedOpportunity, IsClosed: false }, { ...closedOpportunity, IsClosed: false }]
      : [account],
  });
  await assert.rejects(
    () => profile(profileRequest(duplicateClient, { sections: ["opportunities"] }), { client: duplicateClient }),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
});

test("line-item cap fails without a partial result", async () => {
  const opportunity = { Id: IDS.opportunity1, Name: "A", AccountId: IDS.account1, OwnerId: IDS.user1, StageName: "Open", Amount: 100, CloseDate: "2030-01-01", IsClosed: false, IsWon: false, CurrencyIsoCode: "USD", HasOpportunityLineItem: true };
  const items = Array.from({ length: CAPS.lineItems + 1 }, (_, index) => ({
    Id: `00k${String(index + 1).padStart(12, "0")}AAA`,
    OpportunityId: IDS.opportunity1,
    Quantity: 1,
    UnitPrice: 1,
    TotalPrice: 1,
    CurrencyIsoCode: "USD",
    PricebookEntryId: `01u${String(index + 1).padStart(12, "0")}AAA`,
    PricebookEntry: { Product2Id: "01t000000000001AAA", Product2: { Name: "Synthetic" } },
  }));
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM OpportunityLineItem")) return items;
      if (soql.includes("FROM Opportunity")) return [opportunity];
      return [account];
    },
  });
  await assert.rejects(() => profile(profileRequest(client, { sections: ["overview", "products"] }), { client }), {
    code: "LINE_ITEM_CAP_EXCEEDED",
  });
});

test("duplicate line-item IDs fail without a partial product result", async () => {
  const opportunity = {
    Id: IDS.opportunity1, AccountId: IDS.account1,
    IsClosed: false, IsWon: false, CurrencyIsoCode: "USD",
  };
  const item = {
    Id: "00k000000000001AAA", OpportunityId: IDS.opportunity1, Quantity: 1,
    UnitPrice: 100, TotalPrice: 100, CurrencyIsoCode: "USD",
    PricebookEntryId: "01u000000000001AAA",
    PricebookEntry: {
      Product2Id: "01t000000000001AAA",
      Product2: { Name: "Synthetic Product" },
    },
  };
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM OpportunityLineItem")) return [item, item];
      if (soql.includes("FROM Opportunity")) return [opportunity];
      return [account];
    },
  });
  await assert.rejects(
    () => profile(profileRequest(client, { sections: ["products"] }), { client }),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
});

test("User cap fails without a partial hierarchy", async () => {
  const users = Array.from({ length: CAPS.users + 1 }, (_, index) => ({
    Id: `005${String(index + 1).padStart(12, "0")}AAA`,
    Name: `User ${index}`,
    Title: "Synthetic",
    ManagerId: null,
  }));
  users[0].Id = IDS.user1;
  const family = users.map((user, index) => ({
    ...account,
    Id: `001${String(index + 1).padStart(12, "0")}AAA`,
    Name: `Account ${index}`,
    OwnerId: user.Id,
  }));
  family[0] = account;
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM User")) return users.filter((user) => soql.includes(user.Id));
      if (soql.includes("Ultimate_Parent_name__c =")) return family;
      return [account];
    },
  });
  await assert.rejects(() => profile(profileRequest(client, {
    sections: ["family", "team"],
    scope: "corporate_family",
  }), { client }), {
    code: "USER_CAP_EXCEEDED",
  });
});

test("multicurrency profile preserves currencies and does not aggregate", async () => {
  const opportunities = [
    { Id: IDS.opportunity1, Name: "A", AccountId: IDS.account1, OwnerId: IDS.user1, StageName: "Open", Amount: 100, CloseDate: "2030-01-01", IsClosed: false, IsWon: false, CurrencyIsoCode: "USD", HasOpportunityLineItem: false },
    { Id: IDS.opportunity2, Name: "B", AccountId: IDS.account1, OwnerId: IDS.user1, StageName: "Open", Amount: 100, CloseDate: "2030-01-02", IsClosed: false, IsWon: false, CurrencyIsoCode: "EUR", HasOpportunityLineItem: false },
  ];
  const client = new MockClient({
    query: (soql) => soql.includes("FROM Opportunity") ? opportunities : [account],
  });
  const result = await profile(profileRequest(client, { sections: ["overview", "opportunities"] }), { client });
  assert.deepEqual(result.currencies, ["EUR", "USD"]);
  assert(result.warnings.includes("MULTICURRENCY_NO_AGGREGATION"));
  assert.equal("total_amount" in result, false);
});

test("products retain raw prices and annualization stays disabled", async () => {
  const opportunity = { Id: IDS.opportunity1, Name: "A", AccountId: IDS.account1, OwnerId: IDS.user1, StageName: "Open", Amount: 100, CloseDate: "2030-01-01", IsClosed: false, IsWon: false, CurrencyIsoCode: "USD", HasOpportunityLineItem: true };
  const line = { Id: "00k000000000001AAA", OpportunityId: IDS.opportunity1, Quantity: 2, UnitPrice: 50, TotalPrice: 100, CurrencyIsoCode: "USD", PricebookEntryId: "01u000000000001AAA", PricebookEntry: { Product2Id: "01t000000000001AAA", Product2: { Name: "Synthetic" } } };
  const client = new MockClient({
    query: (soql) => {
      if (soql.includes("FROM OpportunityLineItem")) return [line];
      if (soql.includes("FROM Opportunity")) return [opportunity];
      return [account];
    },
  });
  const result = await profile(profileRequest(client, { sections: ["overview", "products"] }), { client });
  assert.equal(result.products[0].UnitPrice, 50);
  assert.equal(result.products[0].TotalPrice, 100);
  assert.equal(result.products[0].Product2Id, "01t000000000001AAA");
  assert.equal("AnnualizedPrice" in result.products[0], false);
  assert(result.warnings.includes(WARNING_ANNUALIZATION));
  assert.deepEqual(result.opportunities, []);
});

test("later-batch failure produces no partial profile result", async () => {
  const family = Array.from({ length: 201 }, (_, index) => ({
    ...account,
    Id: `001${String(index + 1).padStart(12, "0")}AAA`,
    Name: `Synthetic ${index + 1}`,
  }));
  family[0] = account;
  const confirmationClient = new MockClient({
    query: (soql) => soql.includes("Ultimate_Parent_name__c =") ? family : [account],
  });
  const staged = await profile(profileRequest(confirmationClient, {
    sections: ["family", "opportunities"],
    scope: "corporate_family",
  }), { client: confirmationClient });
  let opportunityBatch = 0;
  const failureClient = new MockClient({
    query: (soql) => {
      if (soql.includes("Ultimate_Parent_name__c =")) return family;
      if (soql.includes("FROM Opportunity")) {
        opportunityBatch += 1;
        if (opportunityBatch === 2) throw Object.assign(new Error("synthetic later batch failure"), { code: "SF_COMMAND_FAILED" });
        return [{
          Id: IDS.opportunity1, Name: "A", AccountId: family[0].Id, OwnerId: IDS.user1,
          StageName: "Open", Amount: 1, CloseDate: "2030-01-01", IsClosed: false,
          IsWon: false, CurrencyIsoCode: "USD", HasOpportunityLineItem: false,
        }];
      }
      return [account];
    },
  });
  let result;
  await assert.rejects(async () => {
    result = await profile(profileRequest(failureClient, {
      sections: ["family", "opportunities"],
      scope: "corporate_family",
      confirmed_family_digest: staged.family_confirmation.family_digest,
    }), { client: failureClient });
  });
  assert.equal(result, undefined);
});

test("deterministic renderer sanitizes adversarial CRM text", () => {
  const result = buildRenderResult({
    schema_version: CONTRACTS.profileResult,
    classification: "confidential",
    selected_account: { Id: IDS.account1, Name: "**bad**\u202e\u001b[31m" },
    scope: "selected_account",
    accounts: [{ ...account, Name: "| table\n# heading" }],
    opportunities: [],
    products: [],
    team: [],
    warnings: [],
  });
  assert(!result.markdown.includes("\u202e"));
  assert(!result.markdown.includes("\u001b"));
  assert(result.markdown.includes("\\*\\*bad\\*\\*"));
  assert.equal(result.classification, "confidential");
});

test("complete render includes optional overview and required relationship IDs", async () => {
  const rendered = await render({
    schema_version: CONTRACTS.renderRequest,
    profile: {
      schema_version: CONTRACTS.profileResult,
      classification: "confidential",
      status: "complete",
      selected_account: { ...account, Region__c: "Synthetic Region", Support_Status__c: "Synthetic Status" },
      scope: "corporate_family",
      opportunity_scope: "all",
      accounts: [account, secondAccount],
      family_confirmation: { account_ids: [IDS.account1, IDS.account2], family_digest: "a".repeat(64) },
      opportunities: [{
        Id: IDS.opportunity1, Name: "Synthetic Opportunity", AccountId: IDS.account1,
        OwnerId: IDS.user1, StageName: "Open", Amount: 100, CloseDate: "2030-01-01",
        IsClosed: false, IsWon: false, CurrencyIsoCode: "USD", HasOpportunityLineItem: true,
      }],
      products: [{
        Id: "00k000000000001AAA", OpportunityId: IDS.opportunity1, Quantity: 2,
        UnitPrice: 50, TotalPrice: 100, CurrencyIsoCode: "USD",
        PricebookEntryId: "01u000000000001AAA", Product2Id: "01t000000000001AAA",
        ProductName: "Synthetic Product",
      }],
      team: [{ Id: IDS.user1, Name: "Synthetic Owner", Title: "AE", ManagerId: null }],
      currencies: ["USD"],
      warnings: [WARNING_ANNUALIZATION],
      query_count: 4,
    },
  });
  assert(rendered.markdown.includes("## Account Overview"));
  assert(rendered.markdown.includes("Synthetic Region"));
  assert(rendered.markdown.includes("## Corporate-Family Accounts"));
  assert(rendered.markdown.includes(IDS.user1));
  assert(rendered.markdown.includes("01u000000000001AAA"));
  assert(rendered.markdown.includes("01t000000000001AAA"));
});

test("render rejects partial family-confirmation results", async () => {
  await assert.rejects(() => render({
    schema_version: CONTRACTS.renderRequest,
    profile: {
      schema_version: CONTRACTS.profileResult,
      classification: "confidential",
      status: "family_confirmation_required",
      selected_account: account,
      scope: "corporate_family",
      opportunity_scope: "open",
      accounts: [],
      family_confirmation: { account_ids: [IDS.account1], family_digest: "a".repeat(64) },
      opportunities: [],
      products: [],
      team: [],
      currencies: [],
      warnings: [],
      query_count: 1,
    },
  }), { code: "PROFILE_NOT_COMPLETE" });
});
