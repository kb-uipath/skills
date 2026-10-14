# Evidence → field mapping (schema 1.11)

**The field instructions JSON (`llm-guide/day2-dashboard-field-instructions-v1.11.json`) is
the source of truth** for field semantics, enums, formats and — above all — who may write
each field (`writePolicy`). `llm.md` narrates it. This table only maps *kinds of evidence*
to the fields they may fill, per tab. Where this table and the instructions disagree, the
instructions win. Run `scripts/gap-inventory.mjs` for the live, per-field answer; do not
rely on a remembered list.

Write policies, as the apply script enforces them:

| `writePolicy` | What the skill does |
| --- | --- |
| `evidence_required` | Fills from a dated source (locator + as-of date) |
| `attestation_allowed` | Fills only from a named person's explicit statement; records who |
| `human_only` | Never writes. Offers a suggestion in the report; writes only what the user authors in chat |
| `system_managed`, `preserve_only`, `constant` | Leaves exactly as found (ids are minted by the script for new records) |

`requirement: not_used` means "no publication requirement", not "never rendered". The slides
draw, and the UI edits, `goals` and `cadenceGoals` (the Growth Goals table and the Goals and
Next Actions table), but their instructions allow only approved or verified legacy content, so
the skill proposes entries in the report and writes them only when the owner approves them.
The one `not_used` field the UI edits without that limit is `relationships`, which stays fillable.

## Background tab

| Field | Policy | Evidence that may fill it |
| --- | --- | --- |
| `accountTeam.*`, `background.region` | evidence | **The SFDC account team first — system of record.** Only where SFDC is silent: org announcements, intro emails/messages naming the role holder ("X is your new CSM"), signatures |
| `renewalDate`, `renewalEconomics.currentArrUsd`, `supportTier`, `deploymentType` | evidence | Contract documents, renewal-confirmation messages, deal-desk threads, Salesforce contract and renewal opportunity |
| `renewalEconomics.usageOnlyEstimateUsd` / `…EvidenceId` | evidence + an approved ledger record | Only a stated usage-only estimate; the evidence record's `approved` flag is `human_only`, so publication needs the account team |
| `background.metricCheckpoints[]` (`label`, `arrUsd`, `arrIncrementalUsd`, `consumptionValue`, `consumptionIncrementalUsd`) | evidence | Dated ARR/consumption snapshots from QBR decks, telemetry exports, or a stated figure — never interpolated between two points |
| `background.partners`, `background.competitor` | evidence | Explicit team statements naming the partner/competitor |
| `background.threatOfCompetition` | attest | An explicit statement assessing the threat; never inferred from a competitor merely being mentioned |
| `background.investmentsToDate` (`cs`/`ps`/`fde`/`other`, `unit`) | evidence | Statements of hours or dollars actually invested by team/category; `unit` must match what was stated (`Hours` vs `USD`), never assumed |
| `background.growthGoalActions[]` | evidence | The concrete actions committed to reach a stated growth goal |
| `goals[]` | human (approval) | "Use only approved legacy goal content": propose in the report, write on the owner's approval |
| `risks[]` (`risk`, `mitigation`, `owner`, `targetDate`) | evidence | Named risks and dated, agreed-or-taken mitigation actions (not aspirations) |
| `risks[].severity`, `.status`, `.askForLeadership` | attest | Explicit team ranking/status statement only, never derived from tone or from a deck an assistant drafted |
| `background.accountStrategy` | human | Human-authored only; leave it exactly as found |
| `functionalNeeds[]` (renders as "Asks") | evidence for `need`/`whyItMatters`; **`function`, `accountableOwner`, `dueDate` are `human_only`; `status` is attest** | A need is only publishable once a person supplies the human-only fields, so add one only when the user authors them |
| `background.coreMotions[]` (`label`, `active`) | attest | Explicit statements of which named motions are actively pursued for this account |
| `bottomLineStatus` | attest | Judgment field — explicit team statement only ("Watch"/"At risk"/"Healthy") |
| `health.*` (nine fixed keys) | `evidence` text is evidence; `status`, `owner`, `mitigation` are `human_only` | Renders on no schema-1.11 tab; leave alone |

## Sales Plan tab

| Field | Policy | Evidence that may fill it |
| --- | --- | --- |
| `pipelineOpportunities[]`: `name`, `businessProblem`, `motionLabel`, `stage`, `personaTarget` | evidence | Named pursuits in team channels/notes/SFDC: the deal name, the customer problem it solves, its motion, sales stage, and buyer persona |
| `pipelineOpportunities[].estimatedIarrUsd` | evidence | SFDC amount first (check `getObjectSchema`'s admin guidance for which amount field the org treats as authoritative, e.g. `Calculated_ACV__c` over `Amount`), else contract/validated statements — never derived from hours-saved claims |
| `pipelineOpportunities[].key`, `.status`, `.products`, `.consumptionRowIds[]` | evidence | `key` unique per pursuit; `consumptionRowIds[]` only for rows the pursuit actually references |
| `pipelineOpportunities[].owner`, `.motions[]`, `.nextGate`, `.nextGateDate` | **human** | `human_only`, and each present opportunity needs them to publish. Offer the SFDC owner and close date as suggestions in the report; the account team writes them |
| `relationships[].roleCategory` | evidence | A named person's stated role, mapped into one of the deck's five groups (Economic Buyer, Executive Sponsor, Champion, Technical Decision Maker, Blocker or Detractor) only when the evidence supports that categorization — leave unmapped rather than guess |
| `salesPlan.executionPlan` (`day30`/`day60`/`day90`), `salesPlan.notes` | evidence | Team-stated execution plan bullets and general notes; these are near-term commitments, not aspirations |
| `salesPlan.nextExecutiveMove`, `salesPlan.signOff.owner`/`.by` | human | Human-authored only; leave exactly as found |

## Consumption Plan tab

Owned by `consumption-plan`. When the baseline already carries a filled
`consumptionPlan`, an enrichment run does not write to it. For a blank plan, use that skill.

| Field | Policy | Evidence that may fill it |
| --- | --- | --- |
| `consumptionPlan.groups[].rows[]`: `offering`, `unit`, `soldQuantity` | evidence | Entitlement docs, `SBQQ__Subscription__c`, license-count statements from the platform owner |
| `soldArrUsd`, `actualConsumed`, `renewalArrUsd` | evidence | Telemetry, contract, or validated statements only — never derived from hours. Consumed ARR/% and the Q+1–4 percentages are the app's own derived figures |
| `forecastUnits.q1`–`.q4` | attest | A named person's forecast; an unstated quarter stays null |
| `renewalEconomics.assurance` | **human** | `human_only`; High/Medium/Low only when the account team writes it |
| `consumptionPlan.businessValue` (`realizedUsd`, `realizedOwner`, `forecastedUsd`) | evidence | Stated realized/forecasted value figures and the named owner accountable for them; dollar figures only from contract or validated statements |
| `consumptionPlan.primaryUseCases[]` (`category`, `useCases`, `arrConsumedUsd`, `customerValue`) | evidence | Named use cases actually in flight, their production status, and stated customer value in the customer's own terms |

New rows/use cases get fresh UUIDs; never renumber or reuse existing ids.

## Stakeholders & Actions tab

| Field | Policy | Evidence that may fill it |
| --- | --- | --- |
| `cadenceGoals[]` | human (approval) | "Use only verified legacy plan content": propose goal, next milestone and date in the report, write on the owner's approval; `owner` is `human_only` and `status` is the owner's call |
| `stakeholdersActions.relationshipMap[].uipathRoleBand`/`.customerRoleBand` | evidence | Team statements describing who typically sits in each of the four fixed tiers (Executive/Sponsor/Business Owner/Project Team). `customerPeople[]` is human-authored |
| `relationships[]` new entries | evidence | A named person with a stated role — identity-confirmed |
| `relationships[].caresAbout`, `.cadence`, `.nextStep` | evidence | Their stated priorities (paraphrased); calendar evidence of an actual recurring meeting; committed next actions |
| `relationships[].relationshipStatus` | attest | Explicit team statement only |
| `stakeholderGaps` | evidence | Team statements about missing/unengaged levels; new-arrival intros |

Patch existing `relationships[]` entries by matching `customerName`, keeping the existing
`id`. Patch existing `risks[]` entries by matching `risk`, keeping the existing `id`; a
risk with no new evidence keeps its previous state. The apply script does both.

## Fields with no tab today

`workstreams`, `timeline`, `programClock`, `consumptionHeadline`, `consumptionDrivers`,
`keyActivities`, `customerSignals`, `health`, `statusSummary`, `segment`, `useCases`,
`deliveryModel`, `discountRatePercent` and `annualizedValueToDateUsd` are preserved
through import/export but render on no schema-1.11 tab (the app's slide code never reads
`consumptionHeadline` or `consumptionDrivers`). Do not spend a sweep pass filling them —
if evidence for one surfaces incidentally, note it in the findings file as "no current
home" rather than writing it, so nothing is silently lost if a future tab adopts it.
