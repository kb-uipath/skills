import { CONTRACTS } from "../scripts/constants.mjs";
import { digest } from "../scripts/security.mjs";

export const IDS = Object.freeze({
  account1: "001000000000001AAA",
  account2: "001000000000002AAA",
  opportunity1: "006000000000001AAA",
  opportunity2: "006000000000002AAA",
  user1: "005000000000001AAA",
  user2: "005000000000002AAA",
});

export const DESCRIBE = Object.freeze({
  Account: ["Id", "Name", "ParentId", "OwnerId", "Ultimate_Parent_name__c"],
  Opportunity: ["Id", "Name", "AccountId", "OwnerId", "StageName", "Amount", "CloseDate", "IsClosed", "IsWon", "CurrencyIsoCode", "HasOpportunityLineItem"],
  OpportunityLineItem: ["Id", "OpportunityId", "Quantity", "UnitPrice", "TotalPrice", "CurrencyIsoCode", "PricebookEntryId"],
  PricebookEntry: ["Id", "Product2Id"],
  Product2: ["Id", "Name"],
  User: ["Id", "Name", "Title", "ManagerId"],
});

export function describeMap(fields) {
  const references = {
    ParentId: ["Account"], OwnerId: ["User"], AccountId: ["Account"],
    OpportunityId: ["Opportunity"], PricebookEntryId: ["PricebookEntry"],
    Product2Id: ["Product2"], ManagerId: ["User"], CSM__c: ["User"],
    Support_Technical_Advisor__c: ["User"], PreSales__c: ["User"],
  };
  const relationships = { PricebookEntryId: "PricebookEntry", Product2Id: "Product2" };
  const booleans = new Set(["IsClosed", "IsWon", "HasOpportunityLineItem"]);
  const currencies = new Set(["Amount", "UnitPrice", "TotalPrice"]);
  return new Map(fields.map((name) => [name, {
    name,
    type: name === "Id" ? "id"
      : references[name] ? "reference"
        : booleans.has(name) ? "boolean"
          : currencies.has(name) ? "currency"
            : name === "Quantity" ? "double"
              : name.includes("Date") || name === "ServiceDate" ? "date"
                : name === "CurrencyIsoCode" ? "picklist"
                  : "string",
    filterable: true,
    referenceTo: references[name] ?? [],
    relationshipName: relationships[name] ?? null,
  }]));
}

export class MockClient {
  constructor({ identity, describes = DESCRIBE, query } = {}) {
    this.identity = identity ?? {
      org_id: "00D000000000001AAA",
      username: "synthetic@example.invalid",
      instance_url: "https://synthetic.example.invalid",
      connected_status: "Connected",
    };
    this.describes = describes;
    this.queryHandler = query ?? (() => []);
    this.queryCount = 0;
  }
  async orgDisplay() { return this.identity; }
  async describe(objectName) { return describeMap(this.describes[objectName] ?? []); }
  async query(soql) {
    this.queryCount += 1;
    return await this.queryHandler(soql, this.queryCount);
  }
}

export function orgDigestFor(client, alias = "synthetic") {
  return digest({
    target_org: alias,
    org_id: client.identity.org_id,
    username: client.identity.username,
    instance_url: client.identity.instance_url,
    runtime_attestation_digest: client.attestationDigest ?? null,
  });
}

export function receiptFor(client, account = { Id: IDS.account1, Name: "Example" }, alias = "synthetic") {
  const orgDigest = orgDigestFor(client, alias);
  const core = {
    schema_version: CONTRACTS.accountReceipt,
    classification: "confidential",
    org_digest: orgDigest,
    account,
  };
  return { ...core, receipt_digest: digest(core) };
}
