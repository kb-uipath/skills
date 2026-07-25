# Runtime Field Map

Map version: `salesforce-account-profile-field-map/v1`
Certification scope: generic and offline only

Read [field-map.v1.json](field-map.v1.json) as the machine-readable source. Runtime `describe`
must confirm every queried standard and custom field. Missing required standard fields stop
the command. Missing optional custom fields produce explicit warnings and no invented values.

## Objects

- `Account`: selected identity, `ParentId`, `OwnerId`, and described optional overview fields.
- `Opportunity`: required Account and owner IDs, stage, amount, close date, `IsClosed`,
  `IsWon`, `CurrencyIsoCode`, and line-item indicator.
- `OpportunityLineItem`: required Opportunity ID, Pricebook Entry ID, quantity, raw
  `UnitPrice`, raw `TotalPrice`, and `CurrencyIsoCode`.
- `PricebookEntry`: `Id` and `Product2Id` are described before their relationship path is used.
- `Product2`: `Id` and `Name` are described before a line-item relationship is used.
- `User`: only validated owner and manager IDs, name, title, and manager ID.

`Ultimate_Parent_name__c` is optional. Use it only when Account describe exposes it and the
selected Account supplies a value. Match that value exactly. Otherwise use bounded
`ParentId` traversal and warn.

The versioned `semantic_expectations` block is also enforced at runtime. Family keys must
be text, dates must be date/datetime fields, status and deal labels must be text/picklists,
and CSM, technical-advisor, and PreSales fields must reference `User` before they can be
rendered as IDs. A present field with an incompatible type fails the requested section.

Support Status, PreSales, product-end fields, and any optional custom field remain absent
when describe or records omit them. Never substitute another field based on a similar label.

Section minimization applies to reads as well as output. A products-only run reads only
Opportunity `Id`, `AccountId`, `IsClosed`, `IsWon`, and `CurrencyIsoCode` to resolve the
bounded line-item dependency. It does not read Opportunity amount, owner, stage, dates, or
optional deal fields unless the Opportunities section is explicit.

## Price Basis

Annualization is disabled. This generic map does not certify price basis, recurring status,
or duration for any org version. Return raw `UnitPrice` and `TotalPrice` and emit
`ANNUALIZATION_NOT_CERTIFIED`.
