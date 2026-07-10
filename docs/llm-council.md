# llm-council

Run a structured five-advisor council for expensive-to-get-wrong decisions.

Last verified: 2026-07-10.

## When To Use

Use this skill when the user explicitly invokes `$llm-council`, asks to "council this," or wants a decision stress-tested from multiple perspectives. Do not use it for simple factual lookups, summaries, routine drafting, or tasks with one correct answer.

## Runtime And Dependencies

- Runtime: Python 3.11 or newer.
- Dependencies: Python standard library only for artifact rendering.
- Primary entrypoint: `llm-council/scripts/render_council_artifacts.py`.
- External writes: none. The renderer writes only local HTML and Markdown artifacts.
- Subagents: used by the skill workflow when available, but not required by the renderer.

## Inputs

- Original decision question.
- Neutral framed question.
- Five required advisor responses:
  - `The Contrarian`
  - `The First Principles Thinker`
  - `The Expansionist`
  - `The Outsider`
  - `The Executor`
- Five peer review responses.
- Decision criteria, disconfirming evidence, review date, confidence, sensitivity, permissions, retention, run/model metadata, advisor/reviewer agent IDs, and input hashes.
- Output folder and optional timestamp slug.

## Versioned Contract

The renderer accepts only `schema_version: "llm-council.session.v1"`.
The published schema is [`session-schema-v1.json`](../llm-council/references/session-schema-v1.json); the standard-library runtime enforces the same operational invariants without a JSON Schema dependency.

The v1 contract is intentionally strict:

- `advisors` must contain exactly the five required advisor names with non-empty responses.
- `peer_reviews` must contain exactly five review objects with non-empty reviewer names and responses.
- `anonymization_mapping` must use exactly `Response A` through `Response E`.
- The `Response A` through `Response E` values must bijectively map to the five advisors.
- `decision_criteria` and `disconfirming_evidence` must be non-empty string lists.
- `review_date` must be an ISO date in `YYYY-MM-DD` format.
- `confidence.level` must be `low`, `medium`, or `high`, with a non-empty rationale.
- `execution_mode` must be `subagents` or `single_agent_fallback`.
- `single_agent_fallback` requires `fallback_reason`; simulated perspectives must not be described as independent.
- `metadata` must include `preparer`, `preparer_seed`, `run_id`, model IDs, input hashes, `created_at`, sensitivity, permissions, and retention.
- True subagent sessions require exactly five unique advisor agent IDs and five disjoint reviewer agent IDs. Fallback sessions require both ID lists to be empty.
- Recorded original/framed-question hashes must match the actual inputs; changed inputs fail closed.

Legacy loose payloads fail closed with migration guidance instead of producing partial artifacts.

## Prompt

```text
Use $llm-council to stress-test this launch decision. Capture five advisor positions, five anonymous peer-review responses, a chairman verdict, decision criteria, disconfirming evidence, confidence, metadata, and report artifacts.
```

## Runnable Example

Run from the repository root:

```bash
tmpdir="$(mktemp -d)"

python3 llm-council/scripts/render_council_artifacts.py \
  --prepare-template \
  --seed "example-20260710" \
  --original-question "Should we launch now?" \
  --framed-question "Decide whether launch should proceed this quarter." \
  > "$tmpdir/session.json"

python3 - "$tmpdir/session.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["chairman_verdict"] = "COUNCIL VERDICT\n\nThe Recommendation\nLaunch only as a narrow pilot.\n\nThe One Thing to Do First\nName the pilot owner and success metric."
payload["decision_criteria"] = ["Customer proof must justify delivery risk."]
payload["disconfirming_evidence"] = ["No named pilot owner or measurable success metric exists."]
payload["confidence"] = {"level": "medium", "rationale": "The decision has enough internal signal but lacks live customer proof."}
payload["review_date"] = "2026-07-10"
payload["execution_mode"] = "single_agent_fallback"
payload["fallback_reason"] = "Runnable local example; no independent subagents were invoked."
payload["metadata"]["model_ids"] = ["local-example-model"]
payload["metadata"]["advisor_agent_ids"] = []
payload["metadata"]["reviewer_agent_ids"] = []
for advisor in payload["advisors"]:
    payload["advisors"][advisor] = f"{advisor} says the launch should be gated by owner, metric, and rollback clarity."
for review in payload["peer_reviews"]:
    review["response"] = "The strongest response focuses on launch gates. The blind spot is customer validation. All responses should consider rollback cost."
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY

python3 llm-council/scripts/render_council_artifacts.py \
  "$tmpdir/session.json" \
  --output-dir "$tmpdir" \
  --timestamp example \
  --sensitivity internal
```

Use `--validate-only` to check a payload without writing artifacts:

```bash
python3 llm-council/scripts/render_council_artifacts.py "$tmpdir/session.json" --validate-only
```

## Outputs

- `council-report-[timestamp].html`
- `council-transcript-[timestamp].md`
- Validate-only result with advisor count, review count, schema version, and session hash.

Rendered artifacts include run/model metadata, input hashes, sensitivity, permissions, retention, decision criteria, disconfirming evidence, confidence, fallback disclosure when applicable, and SHA-256 content hashes. New output directories use mode `0700`; report and transcript files are written atomically with mode `0600` on POSIX filesystems.

## Collision And Overwrite Handling

The renderer refuses to overwrite an existing report or transcript for the same timestamp. If replacement is intentional, rerun with `--overwrite` after checking the existing files.

## Safety

- Do not use this skill for one-correct-answer tasks or routine content generation.
- Do not pretend single-agent fallback is independent multi-agent review.
- Do not render legacy or partial payloads; migrate them to the strict v1 contract.
- Do not send confidential details to tools, agents, connectors, or models that lack access approval.
- Keep durable artifacts local unless the user explicitly asks for a different destination.

## Recovery

- Missing or unsupported `schema_version`: migrate to `llm-council.session.v1`; do not render the legacy payload.
- Wrong advisor or review count: rerun the missing advisor or reviewer step, or mark the session as `single_agent_fallback` with a truthful `fallback_reason`.
- Broken anonymization mapping: regenerate the template with a stable `--seed` and preserve the resulting `Response A` through `Response E` mapping.
- Artifact collision: choose a new timestamp or use `--overwrite` only after confirming replacement is intended.
- Sensitive data concern: delete local artifacts and rerun with tighter `metadata.permissions` and `metadata.retention`.
- Changed question/hash mismatch: regenerate the seeded session shell; do not copy old input hashes onto new prompts.

## Classification And Retention

Set `metadata.sensitivity` to one of `public`, `internal`, `confidential`, or `restricted`. Use the least permissive classification that fits the source material. `metadata.permissions` must state who or what environment can access the artifact. `metadata.retention` must say how long to keep the local report and transcript.

## Limitations

- The renderer validates and renders a session payload; it does not call models or create advisor content.
- Single-agent fallback is weaker than independent subagents and must be labeled.
- The council is judgment support, not factual authority.
- Concrete child model IDs may not be exposed by every orchestration tool. Record that limitation literally in `model_ids`; do not invent model provenance.

## Certification

Certified for the offline council workflow, not production decision quality. The hardening gate on 2026-07-10 covers the published strict schema, input-hash and agent-ID validation, seeded anonymization, collision refusal, deterministic atomic `0600` rendering, sensitivity override, and truthful fallback. A fresh synthetic run used five distinct advisor agents followed by five distinct anonymous reviewer agents, producing a validated council and a separately labeled fallback. Scores were 5/5 decision utility, 5/5 independence, 5/5 auditability, and 4/5 operational actionability; real decision data, concrete model provenance, and production telemetry remain uncertified.

## Validation

```bash
python3 -m unittest discover -s llm-council/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
