# Agent engineering evaluation playbook

## Evaluation modes

**1. Functional acceptance (required).** Tie every user requirement to at least one executable test gate. Include failures / negative cases that fail on plausible wrong implementations. Keep checkers independent of developer-provided acceptance claims.

**2. Integration / workflow.** Exercise the real tool chain with deterministic fixtures or mocked side-effect endpoints; assert actual postconditions rather than model-written summaries.

**3. Regression.** Re-run known failures and prior released behavior. Hold out an evaluation set not shown to implementation agents.

**4. Security / process.** Check permissions, prompt injection isolation, file-change policy, credential scoping, allowed endpoints, logging redaction, unsafe irreversible tool actions. For untrusted repositories use a sandbox. AgentCheck cannot enforce runtime network or filesystem isolation.

**5. Mutation / challenge.** Seed small plausible defects in a disposable copy and confirm the tests catch them. If tests accept broken versions, tighten acceptance before shipping.

**6. Reliability / efficiency.** Repeat identical tasks on identical inputs and compare success probability, wall clock, token/tool usage (if collected externally), human interventions and cost per verified success. Single runs are not meaningful improvement estimates.

## Concrete operating loop

1. Create or update contract: goals, risk, scope, requirements and mapped acceptance gates.
2. Ensure baseline is committed; record its Git SHA. Scope to edited source/test/document paths.
3. Run `validate`, then let builder execute implementation on isolated branch/worktree.
4. Keep evaluator independent of builder context when possible. Run gates after implementation.
5. Read JSON results. If fail, classify: missing behavior, weak oracle, wrong context, tool error, orchestration, unsafe action, timeout or cost overrun.
6. Repair. Re-run **all** acceptance gates. Do not cherry-pick a passing partial run.
7. Compare new versus old evidence only when task contract and scenario are stable. Treat any difference in contract hashes as a confounder.
8. Version useful recipes. Never auto-promote an evolving skill without held-out tests, security review and rollback.

## Good acceptance gate examples

Python unittest:

```json
{"id":"unit_tests","argv":["python3","-m","unittest","discover","-s","tests","-v"],"required":true,"timeout_seconds":180,"evidence_regex":"Ran [1-9][0-9]* tests?"}
```

Node (project specific script):

```json
{"id":"test","argv":["npm","test"],"required":true,"timeout_seconds":180}
```

Independent integration test:

```json
{"id":"integration","argv":["python3","-m","pytest","tests/integration","-q"],"required":true,"timeout_seconds":300}
```

Configure gates according to the actual project; none of these commands implies test coverage if no adequate tests exist.

## Metrics
- verified-completion-rate = tasks passing independent configured gates / tasks attempted
- cost-per-verified-task = aggregate measurable tool/model cost / verified completions
- rework-rate = failed verification cycles / attempted tasks
- repeat-failure-rate = repeat incidents of previously classified failures / tasks attempted
- policy-compliance-rate = applicable enforced policy checks passed / total applicable checks

Define denominators, task sampling, and uncertainty before comparing agents. Record execution budgets and model/harness versions.
