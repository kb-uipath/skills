---
name: llm-council
description: Run a structured multi-perspective council for high-stakes decisions using five independent advisor subagents, anonymous peer review, and a chairman verdict with report artifacts. Use when the user explicitly invokes $llm-council, says "council this", asks to run a council or multi-agent advisor panel, or wants to stress-test a pivot, pricing, positioning, hiring, launch, strategy, or other expensive-to-get-wrong choice. Do not use for factual lookups, simple content generation, summaries, or tasks with one correct answer.
---

# LLM Council

## Fit Check

Use this only when the user is asking for judgment under uncertainty and being wrong is costly. If the request has one correct answer, answer directly. If the request is mainly to create copy, summarize text, or execute an already chosen plan, do that work instead of convening a council.

If the decision is too vague to evaluate, ask exactly one clarifying question, then proceed.

Treat explicit invocations such as `$llm-council`, "council this", "run a council", or "use advisor subagents" as permission to use subagents for this workflow. If subagents are unavailable in the current environment, say so directly and offer a weaker single-agent council simulation. Do not pretend simulated perspectives are independent.

## Workflow

### 1. Frame the Question

Spend no more than 30 seconds gathering task-local context before framing:

- User-referenced files or attachments
- `AGENTS.md`, `README*`, `docs/`, `memory/`, or similar project context files
- Recent `council-transcript-*.md` files if the same decision has been discussed before
- Small, directly relevant data files such as pricing notes, launch results, or positioning docs

Rewrite the user's request as a neutral framed question for the advisors. Include:

- Core decision or choice
- Key constraints, numbers, audience, timing, and stakes
- Relevant context from files
- What outcome the user needs

Do not insert your own recommendation into the framed question.

### 2. Convene Five Advisors in Parallel

Spawn all five advisor subagents at the same time. Do not run them sequentially; earlier opinions must not bleed into later prompts.

Advisors:

- `The Contrarian`: finds fatal flaws, weak assumptions, and downside.
- `The First Principles Thinker`: strips the problem to fundamentals and rebuilds the decision logic.
- `The Expansionist`: finds upside, optionality, and adjacent opportunities.
- `The Outsider`: evaluates only what is visible, as a fresh skeptical reader would.
- `The Executor`: tests feasibility and identifies the fastest practical path.

Use this prompt shape for each advisor:

```text
You are [Advisor Name] on an LLM Council.
Your thinking style: [advisor description]

A user has brought this question to the council:

[framed question]

Respond from your perspective. Be direct and specific. Do not hedge or try to be balanced.
Lean fully into your assigned angle. The other advisors will cover the angles you are not covering.
Keep your response between 150 and 300 words. No preamble.
```

### 3. Run Anonymous Peer Review

Randomize and anonymize the five advisor responses as `Response A` through `Response E`. Keep the mapping private until the transcript.

Spawn five reviewer subagents in parallel. Each reviewer sees the framed question and all anonymized responses, then answers:

```text
You are reviewing the outputs of an LLM Council. Five advisors independently answered this question:

[framed question]

Here are their anonymized responses:
Response A: [response]
Response B: [response]
Response C: [response]
Response D: [response]
Response E: [response]

Answer these three questions. Be specific. Reference responses by letter.
1. Which response is the strongest? Why?
2. Which response has the biggest blind spot? What is it missing?
3. What did all five responses miss that the council should consider?

Keep your review under 200 words. Be direct.
```

### 4. Synthesize the Chairman Verdict

Synthesize locally unless the user explicitly asks for a separate chairman subagent. Use the original question, framed question, de-anonymized advisor responses, peer reviews, and anonymization mapping.

The chairman can disagree with the majority. Strong reasoning beats vote count.

Use this exact structure:

```text
COUNCIL VERDICT

Where the Council Agrees
[Points multiple advisors converged on independently. High-confidence signals.]

Where the Council Clashes
[Genuine disagreements. Present both sides. Explain why reasonable advisors disagree.]

Blind Spots the Council Caught
[Things that emerged through peer review or cross-reading.]

The Recommendation
[A clear direct recommendation. Not "it depends."]

The One Thing to Do First
[A single concrete next step. Not a list.]
```

### 5. Generate Artifacts

Every council session produces two files in the working directory unless the user specifies another output folder:

```text
council-report-[timestamp].html
council-transcript-[timestamp].md
```

Use `scripts/render_council_artifacts.py` to create both files from a JSON payload. Build the JSON payload after synthesis in a temporary file or delete it after rendering; the durable council artifacts should be only the report and transcript.

```bash
tmpdir="$(mktemp -d)"
session_json="$tmpdir/council-session.json"
# Write the session JSON to "$session_json", then render:
python3 <skill-dir>/scripts/render_council_artifacts.py "$session_json" --output-dir .
rm "$session_json"
rmdir "$tmpdir"
```

Expected JSON fields:

```json
{
  "original_question": "User's raw request",
  "framed_question": "Neutral prompt sent to advisors",
  "chairman_verdict": "COUNCIL VERDICT...",
  "advisors": {
    "The Contrarian": "Advisor response",
    "The First Principles Thinker": "Advisor response",
    "The Expansionist": "Advisor response",
    "The Outsider": "Advisor response",
    "The Executor": "Advisor response"
  },
  "peer_reviews": [
    {"reviewer": "Reviewer 1", "response": "Review text"}
  ],
  "anonymization_mapping": {
    "Response A": "The Outsider",
    "Response B": "The Contrarian",
    "Response C": "The Executor",
    "Response D": "The Expansionist",
    "Response E": "The First Principles Thinker"
  },
  "advisor_positions": [
    {"advisor": "The Contrarian", "position": "Do not launch yet", "stance": "negative"},
    {"advisor": "The Executor", "position": "Launch a narrow pilot", "stance": "positive"}
  ]
}
```

`advisor_positions` is optional, but include it whenever possible because the HTML report uses it as the agreement/disagreement visual. Valid `stance` values are `positive`, `negative`, `mixed`, and `neutral`.

The renderer validates required session fields and the five required advisor responses before writing artifacts. Treat validation failure as a workflow defect; repair the session payload instead of creating a partial report.

Use `--validate-only` when checking a saved session payload in CI or before handoff without creating HTML or Markdown artifacts.

After generating the files, surface the HTML report path to the user. If the environment supports opening local files and doing so is appropriate, open the HTML report.

## Output Style

In the chat response, lead with the recommendation and the one next step. Link the HTML report and transcript. Do not paste all advisor responses into chat unless the user asks; the artifacts are the detailed record.

## Critical Rules

- Run advisor subagents in parallel.
- Run reviewer subagents in parallel.
- Anonymize before peer review.
- Do not council trivial questions.
- Do not let consensus override better reasoning.
- Create both artifacts for every completed council session.
