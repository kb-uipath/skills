---
name: usecasehandoff
description: Capture, verify, synthesize, package, and route customer or internal automation use case handoffs. Use when Codex needs to gather known information from chats, email, Slack, Teams, SharePoint, Drive, local files, or web sources; produce executive framing, cited metrics, business impact, solution workflow, delivery plan, enterprise hardening recommendations, AI/UiPath AI Unit consumption opportunities, risk register, next steps, and downloadable artifacts for a professional services or automation delivery team.
---

# Use Case Handoff

## Operating Standard

Build an evidence-backed handoff package, not a polished guess. Treat uncited metrics, vague ownership, and missing source links as defects. If a stakeholder could challenge a number or a delivery team could not act on a recommendation, tighten the evidence or label the assumption.

Use `references/report-package-outline.md` when creating the final artifact set.

## Workflow

1. Scope the use case.
   Identify the customer or internal team, sponsor, originating stakeholder, process name, automation name, platform, environment, current maturity, and intended audience. Preserve user-supplied names and terminology, but normalize the final narrative so an executive and delivery lead can both understand it.

2. Gather all source material.
   Search the current chat, local workspace, connected mail, Slack, Teams, SharePoint, Google Drive, and relevant public or vendor documentation when available. Prefer exact source artifacts over memory. Capture source titles, authors or systems, dates, URLs or relative local paths, SHA-256 for local sources, and the facts each source supports.

3. Build an evidence ledger before writing.
   Track every metric, claim, constraint, integration, system name, stakeholder, and business outcome with citation coverage. Mark each item as `Source-backed`, `Derived`, `Estimate`, or `Open`. Do not blend these categories.

4. Synthesize the story.
   Produce a concise executive narrative first: business problem, why now, operational impact, high-level solution workflow, quantified value, and what must happen next. Keep it useful for sales, account leadership, and delivery leadership.

5. Convert the story into delivery work.
   Translate the use case into actionable implementation guidance: current state, target state, architecture, integrations, queue/data model, exception handling, security, audit, monitoring, deployment path, testing approach, acceptance criteria, backlog, risks, and owners.

6. Highlight AI and UiPath consumption opportunities.
   Separate deterministic automation from AI-assisted work. Identify Document Understanding, GenAI, Communications Mining/IXP, Semantic Activities, classifiers, extractors, summarizers, or human-in-the-loop review only where they improve reliability, throughput, or resilience. If estimating AI Units, use the available `estimate-du-units` skill when applicable and clearly state assumptions.

7. Package artifacts.
   Create a dated artifact folder with the stable nine-file package contract, reference links, source citations, and a ZIP only when useful and authorized. Include a `README.md` that tells the recipient what to read first and what each file is for.
   Use `scripts/create_handoff_package.py` for deterministic local scaffolding before writing the final evidence ledger and delivery plan.

8. Route or upload only when authorized.
   If the user asks to send, post, upload, or share the package, use the relevant connector or desktop workflow and verify the destination afterward. Follow confirmation policy for messages, uploads, sensitive data, permission changes, or deletions. Return the verified link or exact blocker.

## Required Outputs

For a full handoff, produce these sections:

- Executive summary: concise business problem, impact, solution workflow, and decision ask.
- Evidence and citations: metrics mapped to sources; public/vendor docs separated from internal sources.
- Use case analysis: current process, pain points, systems, users, volumes, constraints, and value drivers.
- Delivery plan: enterprise-ready target workflow, architecture, backlog, phases, acceptance criteria, and test strategy.
- AI consumption opportunities: candidate AI features, why each matters, assumptions, and estimated consumption if requested.
- Risks and gaps: missing facts, weak metrics, dependencies, policy concerns, and owner decisions required.
- Reference links: local paths, SharePoint/Drive/Slack/Teams/mail/web links that the team can open or download.
- Cover message: short stakeholder-ready message explaining what is attached and what action is needed.

## Helper Script

Create a deterministic local package scaffold without connector writes:

```bash
python3 scripts/create_handoff_package.py --title "Permit Intake Automation" --account "Fixture Agency" --output-dir outputs --date 2026-07-01
```

The scaffolder creates the schema `usecasehandoff.package` version `1.0.0` with nine stable files: `README.md`, `executive-summary.md`, `analysis.md`, `evidence-ledger.md`, `delivery-plan.md`, `risk-register.md`, `references.md`, `cover-message.md`, and `manifest.json`. It refuses to overwrite an existing package unless `--force` is passed.

`manifest.json` records status, classification, retention, package time, last verification time, file hashes, and the no-send boundary. New packages start at `scaffold` status, not `ready`.

Validate scaffold shape while filling the package:

```bash
python3 scripts/create_handoff_package.py --validate outputs/2026-07-01-permit-intake-automation --level scaffold
```

Before routing, refresh hashes, set `ready`, and run default ready validation:

```bash
python3 scripts/create_handoff_package.py --refresh-manifest outputs/2026-07-01-permit-intake-automation --status ready
python3 scripts/create_handoff_package.py --validate outputs/2026-07-01-permit-intake-automation
```

Migrate older six-file packages before validation:

```bash
python3 scripts/create_handoff_package.py --migrate outputs/legacy-handoff-package
```

Ready validation fails closed when placeholders, uncited non-open claims, undefined reference claims, missing or hash-mismatched local sources, ownerless work, empty acceptance criteria, empty test strategy, missing first sprint backlog, missing next action, stale package hashes, or non-ready manifest status remain.

## Evidence Rules

- Never present a metric as fact without a source or an explicit estimate label.
- Prefer internal source names and dates for customer-specific claims.
- Prefer public agency, vendor, or official documentation for external facts.
- Preserve source URLs and portable relative local paths in `references.md`; record and verify local-source SHA-256 values.
- State calculations in plain language, including numerator, denominator, annualization, and any haircut.
- Separate what the current citizen developer automation does from what the enterprise hardened version should do.

## Quality Bar

The final package should let a delivery team start intake without re-reading the entire source thread. If the team still has to ask “what exactly are we building?”, “where did that number come from?”, “what systems are involved?”, or “what is the first sprint?”, the handoff is not finished.
