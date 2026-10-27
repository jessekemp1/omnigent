# Agent architecture review checklist

1. **Task boundary:** measurable goal, input data, expected outputs, dependencies, timeout, retry budget, cancellation conditions, human approval points.
2. **Runtime:** explicit state transitions: queued → running → evaluating → completed / failed / needs-approval; idempotency for replay; safe resume after a crash.
3. **Context engineering:** curated sources, provenance, per-role context, bounded history, compaction without dropping acceptance criteria; mark all external text untrusted.
4. **Memory:** use typed memories (facts, procedures, failure patterns). Assign scope, source, confidence, TTL, revision, revocation; never let agent-generated memory silently override system policy.
5. **Tools:** typed inputs/outputs, least-privilege credentials, deadline, dry-run support, allowlisted side effects, sanitized returns and auditable tool usage.
6. **Orchestration:** start single agent. Parallelize only separable tasks or independent verification. Give each subagent bounded token/time budgets and isolated working trees; require explicit integration and final test window.
7. **Verification:** independent oracle where possible; mapped requirements to tests; negative and boundary cases; reproducible fixtures; integration and regression tests; invariant and security tests; mutation or seeded fault checks for important tasks.
8. **Observability:** traces with task IDs, provenance, exact tool results, errors, checkpoints, hashes, costs where available, outcome and unresolved unknowns. Never log secrets or unfiltered sensitive user data.
9. **Change control:** humans authorize irreversible actions, external deployments, permission changes, billing, secrets and destructive operations. Task JSON alone cannot establish authorization.
10. **Evolution:** accept new skills or policies only with independent held-out evaluation, rollback path, counterfactual failure checks and versioned release process.

## Decision heuristic
- **Deterministic workflow first** if the sequence is known and the tools can be called directly.
- **Single agent** when dynamic reasoning/tool selection is needed but work shares state.
- **Temporary subagents** for independently specifiable research, implementation and review tasks.
- **Persistent multi-agent platform** only after measured benefit over simpler execution and an operational need for retries, queues, state, tracing, rate-limit control, multi-tenant permissions, and deployment.

## Research motivation
- TestSuiteBench (2026): code-generating agents produced test suites with weak mutation scores; passing tests are not enough.
- When Sub-Agents Work in Parallel (2026): parallelism can reduce success and increase cost in many conditions.
- SWE-CC (2026): passing functional tests does not imply repository policy compliance.
- TrustProbe (2026): third-party skills can break trust boundaries.

Use the source papers for context, but validate their reported methods and applicability before making operational claims.
