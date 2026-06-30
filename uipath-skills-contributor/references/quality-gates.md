# Quality Gates

## Universal Checks

Run before committing:

```bash
git diff --check
```

For changed skill descriptions:

```bash
bash hooks/validate-skill-descriptions.sh skills/<skill>/SKILL.md
```

For changed Markdown files:

```bash
for f in $(git diff --name-only -- '*.md'); do
  awk 'BEGIN{c=0} /^[[:space:]>]*```/{c++} END{if (c%2) {print FILENAME ": unbalanced fences (" c ")"; exit 1}}' "$f" || exit 1
done
```

For stale-command or malformed-snippet cleanup:

```bash
rg -n '<stale-pattern>|<malformed-pattern>' <changed-paths>
```

The `rg` command should exit with no matches when the goal is removal.

## CLI Documentation Checks

When docs mention a current CLI command, validate against help output:

```bash
npx -y @uipath/cli@latest <command> --help --output json
```

Use direct command help rather than only parent help; some commands may be hidden from parent listings but still have help endpoints.

## PR-Side Checks

After creating the PR:

```bash
gh pr view <number> --repo UiPath/skills --json number,title,url,state,isDraft,labels,mergeStateStatus,reviewDecision,statusCheckRollup
gh pr checks <number> --repo UiPath/skills
gh run list --repo UiPath/skills --branch <branch> --limit 10 --json name,status,conclusion,event,url
```

Confirm:

- `isDraft` matches the user's request
- `labels` is empty unless labels were requested
- PR body has summary and validation
- related issues are linked honestly
- Socket or visible checks pass
- fork workflow `action_required` is noted as an approval gate, not treated as a local failure
