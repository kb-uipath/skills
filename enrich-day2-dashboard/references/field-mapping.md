# Evidence → field mapping (schema 1.10)

**`llm.md` at the deployed route is the source of truth** for field semantics, enums,
and formats. This table only maps *kinds of evidence* to the fields they may fill, per
tab. When this table and `llm.md` disagree, `llm.md` wins.

## Background tab

| Field | Evidence that may fill it |
| --- | --- |
| `accountTeam.*`, `background.region` | Org announcements, intro emails/messages naming the role holder ("X is your new CSM"), signatures, the SFDC account team |
| `renewalDate`, `renewalEconomics.currentArrUsd`, `supportTier`, `deploymentType` | Contract documents, renewal-confirmation messages, deal-desk threads |
| `background.metricCheckpoints[]` (`label`, `arrUsd`, `arrIncrementalUsd`, `consumptionValue`, `consumptionIncrementalUsd`) | Dated ARR/consumption snapshots from QBR decks, telemetry exports, or a stated figure — never interpolated between two points |
| `background.partners`, `background.competitor`, `background.threatOfCompetition` | Explicit team statements naming the partner/competitor and assessing the threat; never inferred from a competitor merely being mentioned |
| `background.investmentsToDate` (`cs`/`ps`/`fde`/`other`, `unit`) | Statements of hours or dollars actually invested by team/category; `unit` must match what was stated (`Hours` vs `USD`), never assumed |
| `goals[]` (`text`, `target`, `owner`), `background.growthGoalActions[]` | Stated growth goals and the concrete actions committed to reach them |
| `risks[]` (`risk`, `mitigation`, `askForLeadership`, `owner`, `targetDate`) | Named risks and dated, agreed-or-taken mitigation actions (not aspirations) |
| `risks[].severity`, `risks[].status` | Judgment fields — explicit team ranking/status statement only, never derived from tone |
| `background.accountStrategy` | Not fillable by this skill — human-authored only; leave it exactly as found in the baseline |
| `functionalNeeds[]` (renders as "Asks") | Named cross-functional asks with function, accountable owner, due date |
| `background.coreMotions[]` (`label`, `active`) | Explicit statements of which named motions are actively pursued for this account |
| `bottomLineStatus` | Judgment field — explicit team statement only ("Watch"/"At risk"/"Healthy"), never inferred |

## Sales Plan tab

| Field | Evidence that may fill it |
| --- | --- |
| `pipelineOpportunities[]`: `name`, `businessProblem`, `motionLabel`, `stage`, `personaTarget` | Named pursuits in team channels/notes/SFDC: the deal name, the customer problem it solves, its motion, sales stage, and buyer persona |
| `pipelineOpportunities[].estimatedIarrUsd` | Contract/validated statements or SFDC amount only — never derived from hours-saved claims |
| `pipelineOpportunities[].key`, `.status`, `.owner`, `.motions[]`, `.consumptionRowIds[]`, `.nextGate`/`.nextGateDate` | 1.8-era governance fields, still present behind a disclosure — same sourcing rules as before: `key` unique per pursuit, `motions[]` from `M1`/`M2`/`M3` only when explicitly mapped, `consumptionRowIds[]` only for rows the pursuit actually references |
| `relationships[].roleCategory` | A named person's stated role, mapped into one of the deck's five groups (Economic Buyer, Executive Sponsor, Champion, Technical Decision Maker, Blocker or Detractor) only when the evidence supports that categorization — leave unmapped rather than guess |
| `salesPlan.executionPlan` (`day30`/`day60`/`day90`), `salesPlan.notes` | Team-stated execution plan bullets and general notes; these are near-term commitments, not aspirations |
| `salesPlan.nextExecutiveMove`, `salesPlan.signOff.owner`/`.by` | Not fillable by this skill — human-authored only; leave exactly as found in the baseline |

## Consumption Plan tab

| Field | Evidence that may fill it |
| --- | --- |
| `consumptionPlan.groups[].rows[]`: `offering`, `unit`, `soldQuantity` | Entitlement docs, license-count statements from the platform owner |
| `soldArrUsd`, `actualConsumed`, `forecastUnits.q1`–`.q4`, `renewalArrUsd` | Telemetry, contract, or validated statements only — never derived from hours. Consumed ARR/% and the Q+1–4 percentages are the app's own derived figures; supply only the raw quantities |
| `renewalEconomics.assurance` | Judgment field — explicit team statement only (`High`/`Medium`/`Low`) |
| `consumptionPlan.businessValue` (`realizedUsd`, `realizedOwner`, `forecastedUsd`) | Stated realized/forecasted value figures and the named owner accountable for them; dollar figures only from contract or validated statements |
| `consumptionPlan.primaryUseCases[]` (`category`, `useCases`, `arrConsumedUsd`, `customerValue`) | Named use cases actually in flight, their production status, and stated customer value (paraphrased) |

New rows/use cases get fresh UUIDs; never renumber or reuse existing ids.

## Stakeholders & Actions tab

| Field | Evidence that may fill it |
| --- | --- |
| `cadenceGoals[]` (`label`, `owner`, `target`, `date`, `status`) | Stated goals with an owner, a next-milestone description, a date, and an explicit G/Y/R status — status is a judgment field |
| `stakeholdersActions.relationshipMap[].uipathRoleBand`/`.customerRoleBand` | Team statements describing who typically sits in each of the four fixed tiers (Executive/Sponsor/Business Owner/Project Team) for this account; `customerPeople[]` names are not fillable by this skill — human-authored only |
| `relationships[]` new entries | A named person with a stated role — identity-confirmed |
| `caresAbout` | Their stated priorities (paraphrased) |
| `cadence` | Calendar evidence: actual recurring meetings |
| `relationshipStatus` | Judgment field — explicit team statement only |
| `nextStep` | Committed next actions from messages/notes |
| `stakeholderGaps` | Team statements about missing/unengaged levels; new-arrival intros |

Patch existing `relationships[]` entries by matching `customerName`, keeping the existing
`id`. Patch existing `risks[]` entries by matching `risk`, keeping the existing `id`; a
risk with no new evidence keeps its previous state.

## Fields with no tab today

`workstreams`, `timeline`, `programClock`, `consumptionHeadline`, `consumptionDrivers`,
`keyActivities`, `customerSignals`, `health`, and `statusSummary` are preserved through
import/export but render on no schema-1.10 tab. Do not spend a sweep pass filling them —
if evidence for one surfaces incidentally, note it in the findings file as "no current
home" rather than writing it, so nothing is silently lost if a future tab adopts it.
