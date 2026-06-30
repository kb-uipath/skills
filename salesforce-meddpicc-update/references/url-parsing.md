# Salesforce Opportunity ID Parsing

Accept:

- Lightning URLs such as `https://uipath.lightning.force.com/lightning/r/Opportunity/006Pa00000TNhhtIAD/view`
- Related or edit Lightning URLs containing `/Opportunity/{id}`
- Classic or bare-path URLs containing a `006...` ID
- Bare 15-character or 18-character Opportunity IDs
- Sentences containing one valid Opportunity ID

Reject:

- IDs that do not start with `006`
- Account IDs (`001...`), Contact IDs (`003...`), Lead IDs (`00Q...`), and any non-Opportunity object
- IDs shorter than 15 or longer than 18 alphanumeric characters

Use the helper instead of rewriting regexes:

```bash
node scripts/meddpicc.mjs parse-id --input payload.json
```

Input:

```json
{"input":"Update MEDDPICC on https://uipath.lightning.force.com/lightning/r/Opportunity/006Pa00000TNhhtIAD/view"}
```

Output:

```json
{"opportunityId":"006Pa00000TNhhtIAD","valid":true,"source":"embedded"}
```
