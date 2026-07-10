# Security

Do not commit live secrets, personal auth files, tenant dumps, customer data, or generated local backups to this repository.

Before pushing updates, run a secret-oriented scan and inspect any hits manually. Placeholder credentials in examples should be obviously fake.

## Reporting A Vulnerability

Use a GitHub private advisory for security-sensitive reports, credential exposure, or customer-data exposure. Do not open a public issue with exploit details, live credentials, tenant identifiers, customer exports, or connector payloads.

If a private advisory is not available, contact the repository owner privately and include only the minimum reproduction detail needed to triage. Redact secrets and customer data before sharing.

## Supported Versions

Only the current `main` branch is treated as supported for security fixes. Historical worktrees and local exports are not supported release lines.

Last verified: 2026-07-10
