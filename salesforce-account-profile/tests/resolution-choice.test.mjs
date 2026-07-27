import assert from "node:assert/strict";
import test from "node:test";

import { CAPS } from "../scripts/constants.mjs";
import { buildResolutionChoices } from "../scripts/resolution-choice.mjs";
import { DESCRIBE, IDS, MockClient } from "./helpers.mjs";

const PARENT_ID = "001000000000003AAA";
const EXTRA_ACCOUNT_ID = "001000000000004AAA";
const EXTRA_USER_ID = "005000000000003AAA";
const CHOICE_DESCRIBE = Object.freeze({
  ...DESCRIBE,
  Account: Object.freeze([
    "Id",
    "Name",
    "ParentId",
    "OwnerId",
    "Type",
    "BillingCity",
    "BillingState",
    "BillingCountry",
  ]),
  User: Object.freeze(["Id", "Name", "Title"]),
});

const candidates = Object.freeze([
  Object.freeze({
    Id: IDS.account2,
    Name: "Repeated **Name**",
    ParentId: null,
    OwnerId: IDS.user2,
  }),
  Object.freeze({
    Id: IDS.account1,
    Name: "Repeated **Name**",
    ParentId: PARENT_ID,
    OwnerId: IDS.user1,
  }),
]);

const accountRows = Object.freeze([
  Object.freeze({
    Id: IDS.account1,
    Name: "Repeated **Name**\u202e",
    ParentId: PARENT_ID,
    OwnerId: IDS.user1,
    Type: "Customer",
    BillingCity: "New | York\u001b[31m",
    BillingState: "NY",
    BillingCountry: "United States",
  }),
  Object.freeze({
    Id: IDS.account2,
    Name: "Repeated **Name**",
    ParentId: null,
    OwnerId: IDS.user2,
    Type: "Prospect",
    BillingCity: "Arlington",
    BillingState: "VA",
    BillingCountry: "United States",
  }),
  Object.freeze({
    Id: PARENT_ID,
    Name: "Parent **HQ**\u001b[31m",
    ParentId: null,
    OwnerId: IDS.user1,
    Type: null,
    BillingCity: null,
    BillingState: null,
    BillingCountry: null,
  }),
]);

const userRows = Object.freeze([
  Object.freeze({
    Id: IDS.user1,
    Name: "Alex | Owner\u202e",
    Title: "Account **Executive**",
  }),
  Object.freeze({
    Id: IDS.user2,
    Name: "Bearer abcdefghijklmnop",
    Title: null,
  }),
]);

function exactQueryClient({
  describes = CHOICE_DESCRIBE,
  accounts = accountRows,
  users = userRows,
} = {}) {
  const queries = [];
  const describeCalls = [];
  const client = new MockClient({
    describes,
    query: (soql) => {
      queries.push(soql);
      const records = soql.includes("FROM Account") ? accounts : users;
      return records.filter((record) => soql.includes(`'${record.Id}'`)).reverse();
    },
  });
  const describe = client.describe.bind(client);
  client.describe = async (objectName) => {
    describeCalls.push(objectName);
    return await describe(objectName);
  };
  return { client, queries, describeCalls };
}

test("builds deterministic display-only rows with exact Account, parent, and owner identities", async () => {
  const { client, queries, describeCalls } = exactQueryClient();

  const result = await buildResolutionChoices({ candidates, client });

  assert.deepEqual(describeCalls.sort(), ["Account", "User"]);
  assert.equal(queries.length, 2);
  assert.match(queries[0], /^SELECT Id, Name, ParentId, OwnerId, Type, BillingCity, BillingState, BillingCountry FROM Account WHERE Id IN \(.+\) ORDER BY Id LIMIT 4$/u);
  assert(queries[0].includes(`'${IDS.account1}'`));
  assert(queries[0].includes(`'${IDS.account2}'`));
  assert(queries[0].includes(`'${PARENT_ID}'`));
  assert(!queries[0].includes("LIKE"));
  assert(!queries[0].includes("Repeated"));
  assert.match(queries[1], /^SELECT Id, Name, Title FROM User WHERE Id IN \(.+\) ORDER BY Id LIMIT 3$/u);
  assert(queries[1].includes(`'${IDS.user1}'`));
  assert(queries[1].includes(`'${IDS.user2}'`));

  assert.deepEqual(result, {
    rows: [
      {
        Id: IDS.account1,
        Name: "Repeated **Name**",
        Type: "Customer",
        BillingCity: "New | York",
        BillingState: "NY",
        BillingCountry: "United States",
        ParentId: PARENT_ID,
        ParentName: "Parent **HQ**",
        OwnerId: IDS.user1,
        OwnerName: "Alex | Owner",
        OwnerTitle: "Account **Executive**",
      },
      {
        Id: IDS.account2,
        Name: "Repeated **Name**",
        Type: "Prospect",
        BillingCity: "Arlington",
        BillingState: "VA",
        BillingCountry: "United States",
        ParentId: null,
        ParentName: null,
        OwnerId: IDS.user2,
        OwnerName: "[REDACTED]",
        OwnerTitle: null,
      },
    ],
    warnings: [],
  });
});

test("missing optional schema and values become null with stable warnings", async () => {
  const source = [candidates[0]];
  const accounts = [{
    Id: IDS.account2,
    Name: source[0].Name,
    ParentId: null,
    OwnerId: IDS.user2,
    BillingCity: null,
  }];
  const { client, queries } = exactQueryClient({
    describes: {
      ...DESCRIBE,
      Account: ["Id", "Name", "ParentId", "OwnerId", "BillingCity"],
      User: ["Id", "Name", "Title"],
    },
    accounts,
    users: [userRows[1]],
  });

  const result = await buildResolutionChoices({ candidates: source, client });

  assert.equal(queries.length, 2);
  assert.match(queries[0], /^SELECT Id, Name, ParentId, OwnerId, BillingCity FROM Account /u);
  assert.deepEqual(result.rows[0], {
    Id: IDS.account2,
    Name: source[0].Name,
    Type: null,
    BillingCity: null,
    BillingState: null,
    BillingCountry: null,
    ParentId: null,
    ParentName: null,
    OwnerId: IDS.user2,
    OwnerName: "[REDACTED]",
    OwnerTitle: null,
  });
  assert.deepEqual(result.warnings, [
    "OPTIONAL_FIELD_UNAVAILABLE:Account.BillingCountry",
    "OPTIONAL_FIELD_UNAVAILABLE:Account.BillingState",
    "OPTIONAL_FIELD_UNAVAILABLE:Account.Type",
    "OPTIONAL_VALUE_MISSING:Account.BillingCity",
  ]);
});

test("empty candidates return without metadata or data access", async () => {
  const { client, queries, describeCalls } = exactQueryClient();

  assert.deepEqual(await buildResolutionChoices({ candidates: [], client }), {
    rows: [],
    warnings: [],
  });
  assert.deepEqual(describeCalls, []);
  assert.deepEqual(queries, []);
});

test("duplicate and over-cap candidate sets fail before Salesforce access", async (t) => {
  await t.test("duplicate", async () => {
    const { client, queries, describeCalls } = exactQueryClient();
    await assert.rejects(
      () => buildResolutionChoices({ candidates: [candidates[0], candidates[0]], client }),
      { code: "INVALID_CANDIDATE_SET" },
    );
    assert.deepEqual(describeCalls, []);
    assert.deepEqual(queries, []);
  });

  await t.test("over cap", async () => {
    const oversized = Array.from({ length: CAPS.candidates + 1 }, (_, index) => ({
      Id: `001${String(index).padStart(12, "0")}AAA`,
      Name: `Candidate ${index}`,
      ParentId: null,
      OwnerId: IDS.user1,
    }));
    const { client, queries, describeCalls } = exactQueryClient();
    await assert.rejects(
      () => buildResolutionChoices({ candidates: oversized, client }),
      { code: "CANDIDATE_CAP_EXCEEDED" },
    );
    assert.deepEqual(describeCalls, []);
    assert.deepEqual(queries, []);
  });
});

test("all runtime metadata is validated before any data query", async (t) => {
  await t.test("required User field missing", async () => {
    const { client, queries } = exactQueryClient({
      describes: {
        ...CHOICE_DESCRIBE,
        User: ["Id", "Title"],
      },
    });
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "SCHEMA_FAILURE" },
    );
    assert.deepEqual(queries, []);
  });

  await t.test("optional Account field has incompatible type", async () => {
    const { client, queries } = exactQueryClient();
    const describe = client.describe.bind(client);
    client.describe = async (objectName) => {
      const fields = await describe(objectName);
      if (objectName === "Account") {
        fields.set("Type", { ...fields.get("Type"), type: "currency" });
      }
      return fields;
    };
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "SCHEMA_FAILURE" },
    );
    assert.deepEqual(queries, []);
  });
});

test("candidate identity and relationship drift fails before owner enrichment", async () => {
  const drifted = accountRows.map((record) => record.Id === IDS.account1
    ? { ...record, OwnerId: IDS.user2 }
    : record);
  const { client, queries } = exactQueryClient({ accounts: drifted });

  await assert.rejects(
    () => buildResolutionChoices({ candidates, client }),
    { code: "CANDIDATE_REVALIDATION_FAILED" },
  );
  assert.equal(queries.length, 1);
});

test("missing, duplicate, and extra enrichment rows fail atomically", async (t) => {
  await t.test("missing parent", async () => {
    const { client, queries } = exactQueryClient({
      accounts: accountRows.filter((record) => record.Id !== PARENT_ID),
    });
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "ACCOUNT_ENRICHMENT_INCOMPLETE" },
    );
    assert.equal(queries.length, 1);
  });

  await t.test("duplicate Account", async () => {
    const { client, queries } = exactQueryClient({
      accounts: [...accountRows, accountRows[0]],
    });
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "ACCOUNT_ENRICHMENT_INCOMPLETE" },
    );
    assert.equal(queries.length, 1);
  });

  await t.test("extra Account", async () => {
    const { client, queries } = exactQueryClient({
      accounts: [
        ...accountRows,
        {
          ...accountRows[0],
          Id: EXTRA_ACCOUNT_ID,
        },
      ],
    });
    client.queryHandler = (soql) => {
      queries.push(soql);
      if (soql.includes("FROM Account")) {
        return [
          ...accountRows,
          { ...accountRows[0], Id: EXTRA_ACCOUNT_ID },
        ];
      }
      return userRows;
    };
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "ACCOUNT_ENRICHMENT_INCOMPLETE" },
    );
    assert.equal(queries.length, 1);
  });

  await t.test("missing owner", async () => {
    const { client, queries } = exactQueryClient({
      users: userRows.filter((record) => record.Id !== IDS.user1),
    });
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "OWNER_IDENTITY_INCOMPLETE" },
    );
    assert.equal(queries.length, 2);
  });

  await t.test("extra owner", async () => {
    const { client, queries } = exactQueryClient();
    client.queryHandler = (soql) => {
      queries.push(soql);
      if (soql.includes("FROM Account")) return accountRows;
      return [...userRows, { Id: EXTRA_USER_ID, Name: "Extra", Title: "Extra" }];
    };
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "OWNER_IDENTITY_INCOMPLETE" },
    );
    assert.equal(queries.length, 2);
  });
});

test("present rows with missing parent or owner names fail rather than inferring identity", async (t) => {
  await t.test("parent name", async () => {
    const { client } = exactQueryClient({
      accounts: accountRows.map((record) => record.Id === PARENT_ID
        ? { ...record, Name: null }
        : record),
    });
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "PARENT_IDENTITY_INCOMPLETE" },
    );
  });

  await t.test("owner name", async () => {
    const { client } = exactQueryClient({
      users: userRows.map((record) => record.Id === IDS.user1
        ? { ...record, Name: null }
        : record),
    });
    await assert.rejects(
      () => buildResolutionChoices({ candidates, client }),
      { code: "OWNER_IDENTITY_INCOMPLETE" },
    );
  });
});

test("twenty candidates sharing references use two deduplicated bounded queries", async () => {
  const source = Array.from({ length: CAPS.candidates }, (_, index) => ({
    Id: `001${String(index + 10).padStart(12, "0")}AAA`,
    Name: `Candidate ${String(index).padStart(2, "0")}`,
    ParentId: PARENT_ID,
    OwnerId: IDS.user1,
  }));
  const accounts = [
    ...source.map((candidate) => ({
      ...candidate,
      Type: "Customer",
      BillingCity: "City",
      BillingState: "ST",
      BillingCountry: "Country",
    })),
    {
      Id: PARENT_ID,
      Name: "Shared Parent",
      ParentId: null,
      OwnerId: IDS.user1,
      Type: null,
      BillingCity: null,
      BillingState: null,
      BillingCountry: null,
    },
  ];
  const { client, queries } = exactQueryClient({
    accounts,
    users: [userRows[0]],
  });

  const result = await buildResolutionChoices({ candidates: source, client });

  assert.equal(result.rows.length, CAPS.candidates);
  assert.equal(queries.length, 2);
  assert.match(queries[0], /LIMIT 22$/u);
  assert.match(queries[1], /LIMIT 2$/u);
  assert.equal(queries[1].split(IDS.user1).length - 1, 1);
});
