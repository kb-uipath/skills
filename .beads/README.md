# Beads - AI-Native Issue Tracking

Welcome to Beads! This repository uses **Beads** for issue tracking - a modern, AI-native tool designed to live directly in your codebase alongside your code.

## Repository Persistence Model

This repository publishes Beads in two complementary forms:

- `refs/dolt/data` in the same GitHub repository is the complete, authoritative
  Dolt database. It preserves all issue, event, label, dependency, and comment
  history and is the recovery source.
- `.beads/issues.jsonl` is the current-state interchange snapshot.
- `.beads/history.jsonl` is a deterministic, deduplicated projection of
  issue-table snapshots for review in normal GitHub diffs.
- `.beads/history-manifest.json` records the native Dolt head and exact SHA-256
  hashes of the tracked snapshot and projection.

The projection is intentionally not described as full Beads history:
`bd history` omits relational tables and reports unchanged issue rows at
unrelated commits. The generator collapses those duplicates. Use the native
Dolt ref whenever fidelity or recovery matters.

Everything entered into Beads, including prior values, names, work email
addresses, notes, comments, labels, and dependency metadata, is public in this
repository. Never enter secrets, credentials, customer-confidential material,
tokens, private keys, or machine-local paths. Removing a value from the current
issue does not remove it from history.

## What is Beads?

Beads is issue tracking that lives in your repo, making it perfect for AI coding agents and developers who want their issues close to their code. No web UI required - everything works through the CLI and integrates seamlessly with git.

**Learn more:** [github.com/gastownhall/beads](https://github.com/gastownhall/beads)

## Fresh Clone Setup

Do not run plain `bd init`; with an existing tracked snapshot it can create an
empty database and remove the snapshot from the worktree. Bootstrap from
GitHub's native Dolt ref instead:

```bash
chmod 700 .beads
bd bootstrap --yes
git config beads.role maintainer
bd hooks install --beads
bd dolt remote list
bd history skills-ra5
```

`bd bootstrap --yes` detects `refs/dolt/data` on Git origin before considering
the JSONL fallback. If native history is unavailable, stop rather than
publishing a history export from an imported one-snapshot database.

## Maintainer Sync And Publication

Pull both stores before editing:

```bash
git pull --rebase
bd dolt pull
bd ready --json
```

After Beads changes, refresh and validate the public artifacts from the
authoritative local database:

```bash
make beads-history-export
git add .beads/issues.jsonl .beads/history.jsonl .beads/history-manifest.json
git commit
bd dolt push
git push
git status
```

Never use `bd dolt push --force`. Pull and resolve a divergence so concurrent
history is preserved. `make beads-history-export` also runs the repository's
local-path and secret gates. CI runs `make beads-history-check` without
regenerating the projection.

## Quick Start

### Essential Commands

```bash
# Create new issues
bd create "Add user authentication"

# View all issues
bd list

# View issue details
bd show <issue-id>

# Update issue status
bd update <issue-id> --claim
bd update <issue-id> --status done

# Explicitly sync complete history with the Dolt remote
bd dolt pull
bd dolt push
```

### Working with Issues

Issues in Beads are:
- **Git-native**: Stored in Dolt database with version control and branching
- **AI-friendly**: CLI-first design works perfectly with AI coding agents
- **Branch-aware**: Issues can follow your branch workflow
- **Always in sync**: Auto-syncs with your commits

## Why Beads?

✨ **AI-Native Design**
- Built specifically for AI-assisted development workflows
- CLI-first interface works seamlessly with AI coding agents
- No context switching to web UIs

🚀 **Developer Focused**
- Issues live in your repo, right next to your code
- Works offline, syncs when you push
- Fast, lightweight, and stays out of your way

🔧 **Git Integration**
- Automatic sync with git commits
- Branch-aware issue tracking
- Dolt-native three-way merge resolution

## Get Started with Beads

Try Beads in your own projects:

```bash
# Install Beads
curl -sSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash

# Safely bootstrap this existing repository
bd bootstrap --yes

# Create your first issue
bd create "Try out Beads"
```

## Learn More

- **Documentation**: [github.com/gastownhall/beads/docs](https://github.com/gastownhall/beads/tree/main/docs)
- **Quick Start Guide**: Run `bd quickstart`
- **Examples**: [github.com/steveyegge/beads/examples](https://github.com/steveyegge/beads/tree/main/examples)

---

*Beads: Issue tracking that moves at the speed of thought* ⚡
