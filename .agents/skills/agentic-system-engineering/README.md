# Agentic Systems Engineering Skill + AgentCheck v0.1

A portable Agent Skills folder for **building, testing and improving coding agents and agentic systems**. It combines an opinionated engineering workflow with an executable, standard-library Python verification harness.

**Scope:** Repo-level evidence gates, path-policy checking, requirement mapping, JSON/Markdown reports and baseline comparison. This does not execute an agent autonomously, create tests for you, sandbox untrusted code, or authenticate human approvals.

## Install

Copy the whole `agentic-system-engineering` folder into:

- **Codex:** `.agents/skills/agentic-system-engineering/` (repo-local) or `~/.agents/skills/agentic-system-engineering/` (user-wide).
- **Claude Code:** `.claude/skills/agentic-system-engineering/` (repo-local) or `~/.claude/skills/agentic-system-engineering/` (user-wide).

The skill is portable; install only one copy per client environment. For both clients in one repository, place in `.agents/skills/` and add a symlink from `.claude/skills/agentic-system-engineering` to that folder if your setup supports symlinks, or copy it to both locations.

## Use (macOS / Linux, Python 3.10+)

From the **target project repository**:

```bash
# Set this to wherever you installed the skill.
SKILL_DIR="$HOME/.agents/skills/agentic-system-engineering"
python3 "$SKILL_DIR/scripts/agentcheck.py" init --repo . --preset python
# Edit agentcheck.json and agent-tasks/example.json for your real task.
# Commit the new configs to create a clean baseline before implementation.
python3 "$SKILL_DIR/scripts/agentcheck.py" validate --repo . --task agent-tasks/example.json
# Make implementation changes, create real acceptance tests, then:
python3 "$SKILL_DIR/scripts/agentcheck.py" verify --repo . --task agent-tasks/example.json --base HEAD
```

For non-Python projects choose `--preset custom` and specify `argv` arrays for real tests. The placeholder is intentionally blocked until configured. Do not treat `unittest` output as meaningful unless the suite actually tests task behavior.

Reports: `.agentcheck/runs/<timestamp>-<task>.json` and `.md` (add `.agentcheck/` to the repo `.gitignore`).

Compare two repeated runs for the **same task**:

```bash
python3 "$SKILL_DIR/scripts/agentcheck.py" compare --baseline path/to/old.json --candidate path/to/new.json
```

## Use with an agent

Request: `Use agentic-system-engineering to design, implement and independently test <goal>. Define the acceptance contract first, then run the gates, and report evidence and gaps.`

Use a clean, isolated branch or worktree for changes. Keep approval for deployments, secrets, destructive operations and high-risk changes with humans.

## Self-test the verifier

```bash
cd agentic-system-engineering
python3 -m unittest discover -s tests -v
```

## Why this structure

A skill is appropriate for teaching *how to engineer*. A deterministic verifier is necessary for measuring *whether configured checks passed*. MCP becomes appropriate only when you need a remote service to orchestrate live agents and tools. A full platform is not warranted before these mechanics prove valuable on your own projects.
