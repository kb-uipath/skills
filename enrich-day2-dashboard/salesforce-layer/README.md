# Bundled Salesforce fact layer

This internal layer makes `enrich-day2-dashboard` independently installable. It conservatively seeds schema `1.4` dashboard JSON from one Salesforce Account before contextual evidence and clarification are considered.

Its command surface is intentionally limited to:

- `sf org display`
- `sf sobject describe`
- `sf data query`

It contains no Salesforce create, update, delete, upsert, bulk, Apex, or browser-automation path. The parent skill treats its mapping report and provenance block as the deterministic base receipt.

Run the bundled synthetic certification with:

```bash
node enrich-day2-dashboard/salesforce-layer/scripts/enrich-day2.mjs self-test
```

The field map is versioned in `references/field-map.json`; the blank schema `1.4` dashboard is in `assets/blank-dashboard-v1.4.json`.
