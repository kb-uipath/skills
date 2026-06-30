# kb-uipath skills

This repository contains Keith Born's personal Codex skills from `~/.codex/skills`, packaged for public GitHub use.

The skills are copied as top-level directories so they can be installed or synced directly into a Codex skills folder. The `docs/` folder contains usage notes, required inputs, and example prompts for each skill.

## What is included

- 40 top-level personal Codex skills from `~/.codex/skills`.
- Per-skill `SKILL.md` files plus bundled references, scripts, assets, and templates.
- Generated documentation in `docs/` with use cases, required inputs, and prompt examples.
- Hidden backups, `.DS_Store` files, and local zip artifacts are intentionally excluded.

## Install

Clone the repository and copy the skill directories you want into your Codex skills directory.

```bash
git clone https://github.com/kb-uipath/skills.git
cd skills
mkdir -p ~/.codex/skills
cp -R <skill-name> ~/.codex/skills/
```

To sync every skill:

```bash
rsync -a --exclude docs --exclude .git --exclude README.md --exclude SECURITY.md ./ ~/.codex/skills/
```

## Use

Invoke a skill by name in a Codex prompt, usually with a `$` prefix, then provide the concrete inputs listed in the matching doc page.

```text
Use $uipath-review to audit this UiPath solution read-only. Prioritize structural, reliability, security, and deployment issues with file references and rule IDs where available.
```

## Skill index

### Consumption planning

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [estimate-du-units](./estimate-du-units/SKILL.md) | Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer automation descriptions, especially messy natural-language descriptions involving scanned documents, forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document routing. | Estimate annual UiPath Document Understanding AI Unit or Platform Unit consumption from customer automation descriptions, especially messy natural-language descriptions involving scanned documents, forms, OCR, classification, extraction, indexing, manual queues, batches, faxes, PDFs, or document routing. Use when Codex needs to decide whether DU applies, infer documents and page volume, source or annualize workload counts, calculate low/base/high consumption, explain assumptions, or produce a planning estimate for a UiPath customer. | [docs](./docs/estimate-du-units.md) |

### Customer operations

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [account-meeting-availability](./account-meeting-availability/SKILL.md) | Source, validate, store, edit, and review account meeting contacts for both customer contacts and UiPath team members from a CSV or direct user-provided contact details. | Source, validate, store, edit, and review account meeting contacts for both customer contacts and UiPath team members from a CSV or direct user-provided contact details. Use when the user provides or references an account/contact CSV, asks to add or edit customer or UiPath contacts, asks Codex to maintain an account contact book, fill missing email addresses, verify account contacts, prepare meeting attendees, or identify likely emails from Outlook Email/Calendar evidence without sending messages automatically. | [docs](./docs/account-meeting-availability.md) |

### Decision support

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [llm-council](./llm-council/SKILL.md) | Run a structured multi-perspective council for high-stakes decisions using five independent advisor subagents, anonymous peer review, and a chairman verdict with report artifacts. | Run a structured multi-perspective council for high-stakes decisions using five independent advisor subagents, anonymous peer review, and a chairman verdict with report artifacts. Use when the user explicitly invokes $llm-council, says "council this", asks to run a council or multi-agent advisor panel, or wants to stress-test a pivot, pricing, positioning, hiring, launch, strategy, or other expensive-to-get-wrong choice. Do not use for factual lookups, simple content generation, summaries, or tasks with one correct answer. | [docs](./docs/llm-council.md) |

### Delivery handoff

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [usecasehandoff](./usecasehandoff/SKILL.md) | Capture, verify, synthesize, package, and route customer or internal automation use case handoffs. | Capture, verify, synthesize, package, and route customer or internal automation use case handoffs. Use when Codex needs to gather known information from chats, email, Slack, Teams, SharePoint, Drive, local files, or web sources; produce executive framing, cited metrics, business impact, solution workflow, delivery plan, enterprise hardening recommendations, AI/UiPath AI Unit consumption opportunities, risk register, next steps, and downloadable artifacts for a professional services or automation delivery team. | [docs](./docs/usecasehandoff.md) |

### Engineering quality

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [repo-hardening-sprint](./repo-hardening-sprint/SKILL.md) | Run safe, repository-agnostic cleanup and production-hardening sprints. | Run safe, repository-agnostic cleanup and production-hardening sprints. Use when Codex is asked to review, clean up, refactor, harden, reorganize docs, improve tests, add smoke checks, prepare a repo for commit, or verify that a change can be safely pushed to main without breaking public behavior. | [docs](./docs/repo-hardening-sprint.md) |

### GTM and executive proposals

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [act-2-customer-expansion-proposals](./act-2-customer-expansion-proposals/SKILL.md) | Create Act 2 customer expansion proposal cards from a customer-provided use case or automation idea inventory. | Create Act 2 customer expansion proposal cards from a customer-provided use case or automation idea inventory. Use when Codex is asked to analyze an existing UiPath customer, agency, public-sector entity, enterprise account, or department; identify strategic objectives from public sources; cross-reference those objectives against an uploaded spreadsheet/CSV/table of automation ideas; prioritize expansion-ready agentic use cases; estimate planning value; validate UiPath Automation Cloud capability fit; and produce a concise .docx Word executive briefing as the final artifact. | [docs](./docs/act-2-customer-expansion-proposals.md) |
| [gtm-org-proposal-generator](./gtm-org-proposal-generator/SKILL.md) | Build executive-level UiPath automation proposal cards from public organizational research. | Build executive-level UiPath automation proposal cards from public organizational research. Use when Codex is asked to research an organization, agency, department, public company, healthcare system, university, or other institution; analyze budgets, strategic goals, administrative burden, or cost drivers; identify automation use cases; and produce cited GTM, sales, C-suite, public sector, or federal proposal content aligned to a specified industry vertical and UiPath deployment type. | [docs](./docs/gtm-org-proposal-generator.md) |
| [uipath-agentic-expansion-planner](./uipath-agentic-expansion-planner/SKILL.md) | analyze detailed customer automation or use-case inventories to produce evidence-backed uipath act 2 expansion plans, agentic automation portfolios, top 5 high-impact recommendations, top 3 low-friction poc candidates, and a final verified executive .docx Word brief every run. | analyze detailed customer automation or use-case inventories to produce evidence-backed uipath act 2 expansion plans, agentic automation portfolios, top 5 high-impact recommendations, top 3 low-friction poc candidates, and a final verified executive .docx Word brief every run. use when the user provides or references a customer inventory spreadsheet, asks for agentic expansion ideas, asks to prioritize uipath opportunities, or needs a customer-ready proposal grounded in inventory data, public strategy evidence, deployment-aware validation, and Word-ready executive packaging. | [docs](./docs/uipath-agentic-expansion-planner.md) |

### Public-sector account research

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [pubsec-big-rocks-row-research](./pubsec-big-rocks-row-research/SKILL.md) | Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks spreadsheet. | Research and synthesize evidence for one account row in the PubSec CS Portfolio Big Rocks spreadsheet. Use when Codex is asked to fill, review, validate, or provide organized content for a single account/row/record in the PUBSEC Big Rocks workbook, especially columns for utilization, cloud status, AI Units, Agent Units, Test/IXP/Agentic status, FY27 Big Rocks, value tracking, churn/risk, and notes using SharePoint, Slack, OneNote, migration, TAC, Gov SFDC, Wingman/license, and workbook tabs. | [docs](./docs/pubsec-big-rocks-row-research.md) |

### Sales operations

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [salesforce-meddpicc-update](./salesforce-meddpicc-update/SKILL.md) | Update MEDDPICC qualification fields and Next Steps on UiPath Salesforce Opportunities through the UiPath Integration Service Salesforce connector. | Update MEDDPICC qualification fields and Next Steps on UiPath Salesforce Opportunities through the UiPath Integration Service Salesforce connector. Use when the user provides or references a Salesforce Opportunity URL or ID and asks to update MEDDPICC, qualification, Metrics, Economic Buyer, Decision Criteria, Decision Process, Paper Process, Identified Pain, Champion, Competition, Compelling Event, or Next Steps. Requires read-before-write, schema describe validation, explicit user confirmation, append-with-date behavior for narrative fields, read-after-write verification, prompt-injection guardrail, fuzzy near-duplicate detection, force-duplicate override, and privacy-safe telemetry logging. | [docs](./docs/salesforce-meddpicc-update.md) |

### Skill maintenance

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-rpa-skill-hardening](./uipath-rpa-skill-hardening/SKILL.md) | Use when Codex needs to improve, review, or repair UiPath/skills RPA skill content for agent reliability: `skills/uipath-rpa`, RPA discovery docs, XAML/UIA guidance, CLI snippets, project-context instructions, activity docs, validation guidance, or RPA-related PRs and issues. | Use when Codex needs to improve, review, or repair UiPath/skills RPA skill content for agent reliability: `skills/uipath-rpa`, RPA discovery docs, XAML/UIA guidance, CLI snippets, project-context instructions, activity docs, validation guidance, or RPA-related PRs and issues. | [docs](./docs/uipath-rpa-skill-hardening.md) |
| [uipath-skills-contributor](./uipath-skills-contributor/SKILL.md) | Use when Codex needs to contribute to the UiPath/skills repository end to end: analyze open issues and PRs, prioritize high-impact low-effort fixes or enhancements, implement clean external-contributor patches, validate repo requirements, push branches, create ready pull requests, and review or repair submitted PRs without Codex branding or inappropriate labels. | Use when Codex needs to contribute to the UiPath/skills repository end to end: analyze open issues and PRs, prioritize high-impact low-effort fixes or enhancements, implement clean external-contributor patches, validate repo requirements, push branches, create ready pull requests, and review or repair submitted PRs without Codex branding or inappropriate labels. | [docs](./docs/uipath-skills-contributor.md) |

### UiPath UI interaction

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-interact](./uipath-interact/SKILL.md) | UiPath UI interaction (`uip rpa uia`) - drive live desktop/browser apps: click, type, read values, screenshot, inspect UI state, verify behavior, fill forms, navigate menus, extract table data from running applications. | User wants to drive or inspect a live running app (Windows desktop or browser) - 'click the button', 'fill this form', 'read the value from the screen', 'screenshot the dialog', 'extract this table', 'verify the UI shows X', 'walk through this app'. Live execution only - NOT for authoring XAML/coded selectors at design time (use uipath-rpa). | [docs](./docs/uipath-interact.md) |

### UiPath build

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-agents](./uipath-agents/SKILL.md) | End-to-end work with UiPath Agents of all types: build, integrate with UiPath Products (e.g., Orchestrator, Flow, Maestro), design with UiPath Tools (e.g., Agent Builder/Studio Web), and deploy. | Must use when user mentions or implies any Agent lifecycle phase - e.g., auth, design, scaffold, Studio Web sync, flow integration, editing, pack/deploy/version bump, eval, tracing, guardrails, memory spaces, bindings, attachments. Example requests: 'create/build a UiPath agent', 'build a low-code / Agent Builder agent', 'add agent memory spaces', 'build a coded / Python agent (LangGraph / LlamaIndex / OpenAI Agents)', 'scaffold an agent project', 'run / evaluate / deploy my agent'. | [docs](./docs/uipath-agents.md) |
| [uipath-api-workflow](./uipath-api-workflow/SKILL.md) | UiPath API Workflow assistant - author, run, package, publish JSON workflows executed by `uip api-workflow run`. Covers logical/hierarchical structure (Sequence, Assign, JavaScript, If with #Wrapper/#Then/#Else, ForEach, DoWhile, Break, TryCatch, Wait, Response - including nested patterns) AND HTTP / Integration Service connector activities (Gmail, Outlook, GitHub, Slack, etc.) authored via `uip api-workflow registry resolve` + `stub`. Triggers on prompts about UiPath API workflows, project type \"Api\", JSON workflow files containing `document.dsl`/`do[]`, any of those activity types, or fetching data from a public/vendor API. Uses `uip api-workflow run` for local execution and `uip solution pack`/`publish` for deployment. | UiPath API Workflow assistant - author, run, package, publish JSON workflows executed by `uip api-workflow run`. Covers logical/hierarchical structure (Sequence, Assign, JavaScript, If with #Wrapper/#Then/#Else, ForEach, DoWhile, Break, TryCatch, Wait, Response - including nested patterns) AND HTTP / Integration Service connector activities (Gmail, Outlook, GitHub, Slack, etc.) authored via `uip api-workflow registry resolve` + `stub`. Triggers on prompts about UiPath API workflows, project type \"Api\", JSON workflow files containing `document.dsl`/`do[]`, any of those activity types, or fetching data from a public/vendor API. Uses `uip api-workflow run` for local execution and `uip solution pack`/`publish` for deployment. For .flow Maestro->uipath-maestro-flow. For .xaml/coded RPA->uipath-rpa. For coded agents->uipath-agents. For Coded Apps->uipath-coded-apps. | [docs](./docs/uipath-api-workflow.md) |
| [uipath-coded-apps](./uipath-coded-apps/SKILL.md) | Always invoke for `app.config.json` or `action-schema.json` files. UiPath Coded Web Apps & Coded Action Apps via `uip codedapp` and `@uipath/uipath-typescript` SDK. Scaffold, build, debug, deploy. | Always invoke for `app.config.json` or `action-schema.json` files. UiPath Coded Web Apps & Coded Action Apps via `uip codedapp` and `@uipath/uipath-typescript` SDK. Scaffold, build, debug, deploy. For .cs/XAML->uipath-rpa, Python->uipath-agents. | [docs](./docs/uipath-coded-apps.md) |
| [uipath-human-in-the-loop](./uipath-human-in-the-loop/SKILL.md) | UiPath Human-in-the-Loop / HITL node authoring - building approval gates, escalations, write-back validation, and data enrichment checkpoints in Flow, Maestro, or Coded Agents. NOT for managing, reassigning, or monitoring tasks at runtime (use uipath-tasks for that). | UiPath Human-in-the-Loop / HITL node authoring - building approval gates, escalations, write-back validation, and data enrichment checkpoints in Flow, Maestro, or Coded Agents. NOT for managing, reassigning, or monitoring tasks at runtime (use uipath-tasks for that). | [docs](./docs/uipath-human-in-the-loop.md) |
| [uipath-maestro-bpmn](./uipath-maestro-bpmn/SKILL.md) | Always invoke for `.bpmn`, `project.uiproj`, `entry-points.json`, `operate.json`, `bindings_v2.json`, or `package-descriptor.json` files. UiPath Maestro BPMN / Process Orchestration - author, inspect, validate, package, operate, diagnose. Model writes BPMN skeleton + non-IS UiPath XML; CLI owns Integration Service nodes/templates and generated package files. | Always invoke for `.bpmn`, `project.uiproj`, `entry-points.json`, `operate.json`, `bindings_v2.json`, or `package-descriptor.json` files. UiPath Maestro BPMN / Process Orchestration - author, inspect, validate, package, operate, diagnose. Model writes BPMN skeleton + non-IS UiPath XML; CLI owns Integration Service nodes/templates and generated package files. For .flow JSON->uipath-maestro-flow. For XAML/coded workflows->uipath-rpa. For Python agents->uipath-agents. For Case plans->uipath-maestro-case. | [docs](./docs/uipath-maestro-bpmn.md) |
| [uipath-maestro-case](./uipath-maestro-case/SKILL.md) | Always invoke for `caseplan.json` files. UiPath Case Management authoring (caseplan.json) from sdd.md, or via lightweight interview if sdd.md absent. Produces tasks.md plan, writes caseplan.json via per-plugin JSON recipes. | Always invoke for `caseplan.json` files. UiPath Case Management authoring (caseplan.json) from sdd.md, or via lightweight interview if sdd.md absent. Produces tasks.md plan, writes caseplan.json via per-plugin JSON recipes. For .xaml->uipath-rpa, .flow->uipath-maestro-flow, .bpmn->uipath-maestro-bpmn. For PDD->SDD or complex/multi-product->uipath-design. | [docs](./docs/uipath-maestro-case.md) |
| [uipath-maestro-flow](./uipath-maestro-flow/SKILL.md) | TRIGGER for `.flow` files, UiPath Flow / Maestro Flow build or edit requests, adding IxP/document-extraction nodes to a flow, or asking what IxP / document-extraction models are available in Maestro. UiPath Maestro Flow (.flow) - build, edit, run, debug, fix, evaluate. Create, connect nodes; connector, approval, script, subflow, ixp; list IxP / document-extraction models for a flow through `uip maestro flow registry search \"uipath.ixp\"`; triggers, schedules; validate. Upload, publish, manage runs, instances. Diagnose errors, incidents, traces. Design eval sets, evaluators, run Studio Web evals via `uip maestro flow eval`. `uip maestro flow` CLI. DO NOT TRIGGER for raw IxP project labelling/prediction review/prompt tuning outside Flow->uipath-ixp; C#/XAML->uipath-rpa; standalone agents->uipath-agents. | TRIGGER for `.flow` files, UiPath Flow / Maestro Flow build or edit requests, adding IxP/document-extraction nodes to a flow, or asking what IxP / document-extraction models are available in Maestro. UiPath Maestro Flow (.flow) - build, edit, run, debug, fix, evaluate. Create, connect nodes; connector, approval, script, subflow, ixp; list IxP / document-extraction models for a flow through `uip maestro flow registry search \"uipath.ixp\"`; triggers, schedules; validate. Upload, publish, manage runs, instances. Diagnose errors, incidents, traces. Design eval sets, evaluators, run Studio Web evals via `uip maestro flow eval`. `uip maestro flow` CLI. DO NOT TRIGGER for raw IxP project labelling/prediction review/prompt tuning outside Flow->uipath-ixp; C#/XAML->uipath-rpa; standalone agents->uipath-agents. | [docs](./docs/uipath-maestro-flow.md) |
| [uipath-mcp-servers](./uipath-mcp-servers/SKILL.md) | UiPath AgentHub MCP server registration + tool authoring via `uip agenthub mcp` (six server types: uipath / coded / command / remote / platform / swagger) and `uip agenthub mcp-tools` (three tool kinds: is-activity / resource / raw on `uipath`-type servers). | UiPath AgentHub MCP server registration + tool authoring via `uip agenthub mcp` (six server types: uipath / coded / command / remote / platform / swagger) and `uip agenthub mcp-tools` (three tool kinds: is-activity / resource / raw on `uipath`-type servers). For Integration Service activity authoring->load `references/is-activity-workflow.md`. For Python MCP servers / coded-agent integration->uipath-agents. For raw IS CLI->uipath-platform. | [docs](./docs/uipath-mcp-servers.md) |
| [uipath-rpa](./uipath-rpa/SKILL.md) | Always invoke for `.xaml` or `.cs` workflow files. UiPath RPA - create, edit, build, run, debug `.cs` coded workflows and `.xaml` workflows. UI automation with Object Repository selectors, test case authoring, Integration Service connector calls. Live desktop/browser UI exploration and control. Deploy via `.uipx`->uipath-solution. Non-solution Orchestrator ops->uipath-platform. Test reports->uipath-test. Agents->uipath-agents. | User wants to create, edit, debug, or run a UiPath automation - '.cs' coded workflows or '.xaml' files. Triggers: 'build a workflow', 'automate Excel/email/web/PDF/queue items', 'add a try-catch', 'fix this XAML error', 'scrape this site', 'process invoices', 'create a test case', or project.json shows UiPath dependencies. NOT for '.flow' files (->uipath-maestro-flow), Python agents (->uipath-agents). | [docs](./docs/uipath-rpa.md) |
| [uipath-rpa-legacy](./uipath-rpa-legacy/SKILL.md) | Always invoke when `project.json` has `targetFramework: Legacy` or the user mentions legacy XAML / .NET 4.6.1. UiPath legacy RPA (.NET Framework 4.6.1, XAML) via `uip rpa-legacy`. | Always invoke when `project.json` has `targetFramework: Legacy` or the user mentions legacy XAML / .NET 4.6.1. UiPath legacy RPA (.NET Framework 4.6.1, XAML) via `uip rpa-legacy`. For Windows/cross-platform->uipath-rpa. | [docs](./docs/uipath-rpa-legacy.md) |

### UiPath deploy

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-solution](./uipath-solution/SKILL.md) | Always invoke for `.uipx` files. UiPath Solution lifecycle via the `uip solution` CLI: init/pack/publish/deploy/activate/upload, project add|import|remove, resource refresh|add|remove|edit. Bundles multiple automation projects (RPA/Flow/Case/Agents/API Workflows) into one deployable `.uipx`. | User mentions .uipx / 'uip solution' / 'pack the solution' / 'publish the solution' / 'deploy the solution' / 'activate' / multi-project / Solution scope / Solution Folder. Fires for 'create a new solution', 'add project/resource to solution', 'add a queue/asset/bucket/connection to the solution', 'import a cloud queue/asset', 'edit/remove a resource', 'change a queue/asset field', 'set an asset value in the solution'. Load BEFORE editing .uipx or running uip solution commands. For PDD->SDD design->uipath-design; for an 'architect then deploy' two-phase request, run uipath-design first, then return here to pack/deploy. | [docs](./docs/uipath-solution.md) |
| [uipcodedappdeploy](./uipcodedappdeploy/SKILL.md) | Deploy UiPath coded app projects with the native UiPath CLI. | Deploy UiPath coded app projects with the native UiPath CLI. Use when Codex needs to increment a coded app package version, validate the project, build the app dist, pack it, publish it, and deploy it to UiPath Automation Cloud alpha using `uip codedapp pack`, `uip codedapp publish`, and `uip codedapp deploy`. | [docs](./docs/uipcodedappdeploy.md) |

### UiPath design

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-design](./uipath-design/SKILL.md) | Always invoke for `sdd.md` / `pdd.md` files. UiPath Solution Design Document (SDD) authoring from Process Design Documents (PDDs). Selects scope (single product or multi-project SDD scope: RPA/Flow/Case/Agents/Apps/API Workflows), writes implementation-ready SDD. | User mentions sdd.md / pdd.md / Process Design Document / Solution Design Document / SDD / PDD / multi-project / Solution scope. Fires for 'design this automation', 'architect the solution', 'generate SDD', 'analyze this PDD', 'turn this PDD into code', 'design from this PDD'. Load BEFORE authoring an SDD. For running `uip solution` commands or editing `.uipx`->uipath-solution. | [docs](./docs/uipath-design.md) |
| [uipath-solution-design](./uipath-solution-design/SKILL.md) | Always invoke for `sdd.md`, `pdd.md`, or PDD/SDD documents. UiPath PDD->SDD: analyze PDDs (PDF/docx/md), pick scope (single product or multi-project Solution: RPA/Flow/Case/Agents/Apps/API Workflows), write implementation-ready SDD. | Always invoke for `sdd.md`, `pdd.md`, or PDD/SDD documents. UiPath PDD->SDD: analyze PDDs (PDF/docx/md), pick scope (single product or multi-project Solution: RPA/Flow/Case/Agents/Apps/API Workflows), write implementation-ready SDD. For task plans->uipath-planner. For project setup->uipath-platform. | [docs](./docs/uipath-solution-design.md) |

### UiPath document understanding

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-ixp](./uipath-ixp/SKILL.md) | UiPath IXP (Document Understanding) - review IXP predictions with Claude, confirm valid fields, improve prompts, publish models. | UiPath IXP (Document Understanding) - review IXP predictions with Claude, confirm valid fields, improve prompts, publish models. | [docs](./docs/uipath-ixp.md) |

### UiPath feedback

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-feedback](./uipath-feedback/SKILL.md) | UiPath bug reports and improvement suggestions via `uip feedback send`. Use for 'report issue', 'send feedback', 'file a bug', or the /uipath-feedback command. | User says 'this is broken', 'this isn't working', 'report a bug', 'send feedback', 'something is wrong', 'file an issue', 'this crashed', 'wrong result' about a UiPath product, CLI, or skill. Also fires on the /uipath-feedback slash command. | [docs](./docs/uipath-feedback.md) |

### UiPath operations

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-tasks](./uipath-tasks/SKILL.md) | UiPath Action Center human-in-the-loop tasks via `uip tasks` - list, assign, complete approval/validation tasks. | User says 'approve task', 'pending approval', 'pending action item', 'review action', 'list my tasks', 'reassign task' in an Orchestrator/Action Center context. NOT for TaskCreate/TaskUpdate (general session-task tracking) or Document Understanding validation. | [docs](./docs/uipath-tasks.md) |

### UiPath planning

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-planner](./uipath-planner/SKILL.md) | UiPath task planner - reads SDDs from uipath-design or elicits non-PDD requests, derives multi-skill task lists, emits live TaskCreate calls. Detects project type (.cs, .xaml, .flow, .bpmn, .py). | User makes a non-trivial UiPath request that spans SEPARATE buildable projects - e.g. 'build a UiPath solution for X', 'set up a process from scratch', a Flow that orchestrates standalone RPA processes or agents - OR provides an SDD path. Skip when the request targets a SINGLE project, even a Flow/Agent/RPA project with inline HITL, script, or connector nodes wrapped in its own solution (e.g. a Flow with an inline approval step is one uipath-maestro-flow task, not a plan) - invoke that specialist directly. | [docs](./docs/uipath-planner.md) |

### UiPath platform

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-admin](./uipath-admin/SKILL.md) | UiPath Admin via `uip admin` - Identity Server (users, groups, robot accounts, external OAuth2 apps, secrets), Authorization (custom roles, role assignments, permission catalog, effective-access via check-access PDP), OMS (org read/update, tenant lifecycle, service provisioning, regions, async operation polling), IP Restriction (allowlist, enforcement switch, bypass rules, lockout safety), Audit (event sources, paginated queries, ZIP exports - login history, compliance dumps, who-did-what-when-where on a resource). | UiPath Admin via `uip admin` - Identity Server (users, groups, robot accounts, external OAuth2 apps, secrets), Authorization (custom roles, role assignments, permission catalog, effective-access via check-access PDP), OMS (org read/update, tenant lifecycle, service provisioning, regions, async operation polling), IP Restriction (allowlist, enforcement switch, bypass rules, lockout safety), Audit (event sources, paginated queries, ZIP exports - login history, compliance dumps, who-did-what-when-where on a resource). For Orchestrator-specific roles/permissions/folders/jobs->uipath-platform. For RPA workflows->uipath-rpa. | [docs](./docs/uipath-admin.md) |
| [uipath-data-fabric](./uipath-data-fabric/SKILL.md) | UiPath Data Fabric entity/record CRUD via `uip df`. Create entities, insert/query/update/delete records, CSV import, file attachments. | UiPath Data Fabric entity/record CRUD via `uip df`. Create entities, insert/query/update/delete records, CSV import, file attachments. For Flow connector nodes (query/create/update/delete/get-by-id inside a `.flow`)->uipath-maestro-flow. For Orchestrator->uipath-platform. For Integration Service->uipath-platform. | [docs](./docs/uipath-data-fabric.md) |
| [uipath-governance](./uipath-governance/SKILL.md) | UiPath governance via `uip gov` - author and deploy policies on two layers. AOps product policies (`uip gov aops-policy`): block/restrict/enforce features in Studio, StudioX, Assistant, Robot, AI Trust Layer, Agent Builder; deploy to user/group/tenant. Access ToolUsePolicy (`uip gov access-policy`): allow/deny when one workflow invokes another as a tool (Agent->Agent/Maestro/Flow/RPA/API/Case), gated by tag, caller, or actor (User/Group). Skill classifies product-layer vs resource/tool-use intent before authoring. | UiPath governance via `uip gov` - author and deploy policies on two layers. AOps product policies (`uip gov aops-policy`): block/restrict/enforce features in Studio, StudioX, Assistant, Robot, AI Trust Layer, Agent Builder; deploy to user/group/tenant. Access ToolUsePolicy (`uip gov access-policy`): allow/deny when one workflow invokes another as a tool (Agent->Agent/Maestro/Flow/RPA/API/Case), gated by tag, caller, or actor (User/Group). Skill classifies product-layer vs resource/tool-use intent before authoring. For platform ops->uipath-platform. | [docs](./docs/uipath-governance.md) |
| [uipath-llm-configuration-byo-connections](./uipath-llm-configuration-byo-connections/SKILL.md) | UiPath BYO LLM product configurations in the LLM Gateway via `uip llm-configuration byo-connections` - list, get, create, update, delete, list-product-configs. Register tenant-owned OpenAI / Azure OpenAI / AWS Bedrock / Anthropic / Google Vertex / Mistral keys against UiPath products (agents, agenthub, jarvis, IXP, agent builder). Wraps product-level llm-configurations endpoints. | UiPath BYO LLM product configurations in the LLM Gateway via `uip llm-configuration byo-connections` - list, get, create, update, delete, list-product-configs. Register tenant-owned OpenAI / Azure OpenAI / AWS Bedrock / Anthropic / Google Vertex / Mistral keys against UiPath products (agents, agenthub, jarvis, IXP, agent builder). Wraps product-level llm-configurations endpoints. For tenant-wide AI governance (allowed providers, blocked models)->uipath-governance. | [docs](./docs/uipath-llm-configuration-byo-connections.md) |
| [uipath-platform](./uipath-platform/SKILL.md) | UiPath platform ops via the uip CLI - use this skill for ANY task hitting UiPath Cloud / Orchestrator / Studio Web / Integration Service / LLM Gateway. Load BEFORE writing any code that calls a UiPath API. Covers auth, folders, assets, queues, storage buckets, bucket files, libraries, webhooks, triggers, processes, jobs, machines, users, roles, sessions, calendars, IS connectors/connections/activities, BYO LLM product configurations (`uip llm-configuration byo-connections` - register / audit / re-probe / troubleshoot tenant-owned OpenAI / Azure OpenAI / Bedrock / Vertex / Anthropic keys against UiPath products), traces, licensing. | User mentions UiPath / Orchestrator / Studio Web / Integration Service / LLM Gateway / 'uip' CLI / asset / queue / bucket / library / webhook / trigger / connector / connection / tenant / folder / robot / package / BYO LLM. Also 'upload to UiPath', 'create asset', 'start job', 'list queues', 'deploy a single package to Orchestrator', 'OAuth2 token', 'register my own LLM key', 'configure a model substitution', 'my BYO LLM key stopped working / returns errors', 're-probe / audit a BYO configuration', 'uipath.com REST'. Load BEFORE composing any HTTP request - most UiPath tasks have a `uip` command. For `uip solution` ops or `.uipx` deploys->uipath-solution. | [docs](./docs/uipath-platform.md) |

### UiPath quality

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-review](./uipath-review/SKILL.md) | UiPath read-only reviewer - audit structure, quality, best practices for RPA (.xaml/.cs), agents (.py/agent.json), flows (.flow), BPMN (.bpmn), coded apps, solutions (.uipx). Does NOT edit files. | UiPath read-only reviewer - audit structure, quality, best practices for RPA (.xaml/.cs), agents (.py/agent.json), flows (.flow), BPMN (.bpmn), coded apps, solutions (.uipx). Does NOT edit files. For building/editing->domain skills. | [docs](./docs/uipath-review.md) |

### UiPath testing

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-test](./uipath-test/SKILL.md) | UiPath Test Manager - manage test projects, cases, sets, executions; generate reports. | UiPath Test Manager - manage test projects, cases, sets, executions; generate reports. For Orchestrator->uipath-platform. For test automation->uipath-rpa. | [docs](./docs/uipath-test.md) |

### UiPath troubleshooting

| Skill | What it does | When to use it | Docs |
| --- | --- | --- | --- |
| [uipath-diagnostics](./uipath-diagnostics/SKILL.md) | UiPath cross-platform diagnostics - failed or stuck Orchestrator jobs, faulted queue items, publish errors, selector failures, healing agent issues, permission problems. | UiPath cross-platform diagnostics - failed or stuck Orchestrator jobs, faulted queue items, publish errors, selector failures, healing agent issues, permission problems. For .flow run diagnosis->uipath-maestro-flow. For .bpmn run diagnosis->uipath-maestro-bpmn. For .xaml/.cs workflow debug->uipath-rpa. For platform ops->uipath-platform. | [docs](./docs/uipath-diagnostics.md) |
| [uipath-troubleshoot](./uipath-troubleshoot/SKILL.md) | UiPath troubleshooting, diagnostics, and root-cause investigations across any UiPath product, feature, runtime, or artifact. Investigates errors, failures, faults, exceptions, regressions, performance problems, unexpected behavior, and silent malfunctions - answers why something failed, broke, stopped, hung, slowed down, returned wrong results, lost access, or stopped working after a change. Walks the available evidence (logs, traces, incidents, status fields, configuration, history) to identify the originating fault and explain what changed. | User asks why something failed, broke, stopped, hung, was stuck, returns wrong results, or behaves unexpectedly in any UiPath system. Triggers: 'why did X fail', 'find the cause', 'find why', 'what changed', 'investigate', 'diagnose', 'debug this', 'triage', 'help me figure out', 'what's wrong', 'root cause', 'fix this error', 'inspect this trace / incident / log / job / instance', 'X worked yesterday but now …'. Also fires on raw error messages, exception stacks, error codes, job / queue IDs, or 'stuck / orphan / zombie' state descriptions. | [docs](./docs/uipath-troubleshoot.md) |

## Public repository safety notes

This repo is intended to contain reusable skill instructions and reference material, not live credentials or customer data. Before pushing updates, scan for tokens, secrets, tenant-specific dumps, customer files, and hidden backup directories.

A quick local scan before committing:

```bash
rg -n --hidden -i "(api[_-]?key|secret|password|token|bearer|authorization|client[_-]?secret|private[_-]?key)" .
```
