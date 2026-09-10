# Bundled Salesforce fact layer

This internal layer makes `enrich-day2-dashboard` independently installable. It conservatively seeds schema `1.4` dashboard JSON from one Salesforce Account before contextual evidence and clarification are considered.

Its command surface is intentionally limited to:

- `sf org display`
- `sf sobject describe`
- `sf data query`

It contains no Salesforce create, update, delete, upsert, bulk, Apex, or browser-automation path. The parent skill treats its mapping report and provenance block as the deterministic base receipt.

## Workflow

Create and inspect a confidential proposal:

```bash
node enrich-day2-dashboard/salesforce-layer/scripts/enrich-day2.mjs preview \
  --account <001-id-or-account-lightning-url> \
  --target-org <approved-org>
```

Build the Salesforce-seeded dashboard and its mapping report:

```bash
node enrich-day2-dashboard/salesforce-layer/scripts/enrich-day2.mjs build \
  --preview <salesforce-preview.json>
```

After the parent skill creates its final contextual preview, re-query the same recorded org:

```bash
node enrich-day2-dashboard/salesforce-layer/scripts/enrich-day2.mjs revalidate \
  --report <exact-unmoved-mapping-report.json> \
  --output <salesforce-revalidation.json>
```

`revalidate` is the required final Salesforce checkpoint, not a mapping-report refresh. It runs only the same read-only CLI commands, verifies the exact field-map digest and accepted Account field/value digest, checks purchased-Asset candidates, and writes a confidential [`salesforce-day2-revalidation/v1`](references/salesforce-revalidation.schema.json) receipt. Any mismatch fails closed and requires new Salesforce and contextual previews.

Previews, mapping reports, and revalidation receipts must be regular non-symlink `0600` files in a `0700` directory. JSON reads are capped at 25 MiB. The paired dashboard/report commit requires same-directory hard-link support; use a private local filesystem.

Run the bundled synthetic certification with:

```bash
node enrich-day2-dashboard/salesforce-layer/scripts/enrich-day2.mjs self-test
```

The field map is versioned in `references/field-map.json`; the blank schema `1.4` dashboard is in `assets/blank-dashboard-v1.4.json`.
