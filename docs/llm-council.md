# llm-council

Run a structured five-advisor council for expensive-to-get-wrong decisions.

## When To Use

Use this skill when the user explicitly invokes `$llm-council`, asks to "council this," or wants a decision stress-tested from multiple perspectives. Do not use it for simple factual lookups or tasks with one correct answer.

## Inputs

- Original decision question.
- Constraints, facts, goals, risks, and options.
- Any required output format.
- Whether subagents are available; if not, the main agent must state the fallback and produce a single-agent structured council.

## Prompt

```text
Use $llm-council to stress-test this launch decision. Capture five advisor positions, anonymous peer-review themes, a chairman verdict, and report artifacts.
```

## Outputs

- Five named advisor responses.
- Agreement/disagreement summary.
- Peer-review highlights.
- Chairman synthesis.
- HTML report and Markdown transcript when artifact rendering is requested.

## Safety

- Do not outsource confidential details to tools or agents that lack access approval.
- Make uncertainty and dissent visible; a council report that hides disagreement is theater, not analysis.
- If subagents are unavailable, say so and continue with a deterministic single-agent fallback.
- Clean up temporary session JSON files unless the user asks to keep them.

## Validation

```bash
python3 -m unittest discover -s llm-council/tests -p 'test_*.py'
python3 tools/validate_repo.py
```
