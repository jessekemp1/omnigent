# Verification record | 2026-10-27

## Local checks performed

- `python3 -m unittest discover -s tests -v`: **14 passed**.
- `python3 scripts/agentcheck.py --help`: exit 0.
- Sample Git repo tests exercise real subprocess-based acceptance gates and generation of JSON + Markdown evidence.

## Behaviors covered

- Real change + configured acceptance evidence passes.
- No implementation change fails when `require_changes` is true.
- Forbidden and out-of-scope Git-visible changes fail.
- Nonzero command exit fails.
- Exit zero without required evidence signature fails.
- A zero-test result fails when configured with a test-count evidence regex.
- Changes made as side effects of test commands are rechecked.
- Placeholder gates and nonexistent acceptance references fail validation.
- High-risk tasks cannot silently auto-pass.
- Path traversal in task filenames is rejected.
- Initialization refuses overwrite.
- Two evidence records can be compared for the same task.

## Unvalidated / non-goals

- No verification against actual users' Codex/Claude installations or production repositories.
- No sandbox isolation; gate commands execute locally.
- No automatic independent test authoring, mutation testing, network restriction, privileged action attestation, or secrets redaction from arbitrary project subprocess output.
- Path checks cover Git-visible tracked/untracked (non-ignored) files; they do not detect every possible filesystem side effect or exfiltration.
- A green test means configured gates passed, not that requirements are complete or security has been proved.

Review and tighten project-specific gates before production use.
