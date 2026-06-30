# RPA Skill Scan Commands

Run from the `UiPath/skills` repo root.

## Common Stale Or Malformed Patterns

```bash
rg -n 'rpa-tool|--use-studio|--output jsonuip|json```' skills/uipath-rpa agents/uipath-project-discovery-agent.md README.md
```

Use the pattern only when it matches the change intent. Some matches may be valid in historical issue text outside the edited scope.

## Same-Line Fence Hazards

```bash
rg -n '^[[:space:]]*[^`[:space:]>].*```' skills/uipath-rpa
```

Inspect matches manually. The goal is to catch commands such as:

```text
uip rpa get-errors --output json```
```

## Fenced Code Balance

```bash
for f in $(git diff --name-only -- '*.md'); do
  awk 'BEGIN{c=0} /^[[:space:]>]*```/{c++} END{if (c%2) {print FILENAME ": unbalanced fences (" c ")"; exit 1}}' "$f" || exit 1
done
```

## CLI Help Verification

Validate command examples by checking direct help endpoints:

```bash
npx -y @uipath/cli@latest rpa list-instances --help --output json
npx -y @uipath/cli@latest rpa start-studio --help --output json
npx -y @uipath/cli@latest rpa create-project --help --output json
npx -y @uipath/cli@latest rpa get-errors --help --output json
npx -y @uipath/cli@latest rpa run-file --help --output json
npx -y @uipath/cli@latest rpa find-activities --help --output json
npx -y @uipath/cli@latest rpa get-default-activity-xaml --help --output json
npx -y @uipath/cli@latest rpa list-workflow-examples --help --output json
npx -y @uipath/cli@latest rpa inspect-package --help --output json
```

Prefer direct command help because parent help can omit available commands.
