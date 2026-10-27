#!/usr/bin/env python3
"""AgentCheck: deterministic, fail-closed evidence gate for agent-produced changes.

Stdlib only. It is NOT a sandbox, adversarial test oracle, or autonomous agent runtime.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

SKILL = Path(__file__).resolve().parent.parent
IGNORE_PREFIXES = ('.agentcheck/', '.git/')

class CheckError(Exception):
    pass


def read_json(path: Path) -> dict:
    try:
        with path.open('r', encoding='utf-8') as f:
            result = json.load(f)
    except (OSError, ValueError) as exc:
        raise CheckError(f'Cannot load JSON {path}: {exc}') from exc
    if not isinstance(result, dict):
        raise CheckError(f'Expected JSON object: {path}')
    return result


def local_path(repo: Path, requested: str) -> Path:
    path = (repo / requested).resolve()
    if not path.is_relative_to(repo):
        raise CheckError(f'Path must be inside repo: {requested}')
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_str(v, name):
    if not isinstance(v, str) or not v.strip():
        raise CheckError(f'{name} must be a nonempty string')


def validate(config: dict, task: dict) -> None:
    if config.get('schema_version') != 1 or task.get('schema_version') != 1:
        raise CheckError('schema_version must be 1 in both files')
    gates = config.get('gates')
    if not isinstance(gates, list) or not gates:
        raise CheckError('config.gates must have at least one real executable gate')
    ids = set()
    for g in gates:
        if not isinstance(g, dict):
            raise CheckError('each gate must be a JSON object')
        gid = g.get('id')
        require_str(gid, 'gate.id')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,50}', gid):
            raise CheckError(f'invalid gate id: {gid}')
        if gid in ids:
            raise CheckError(f'duplicate gate id: {gid}')
        ids.add(gid)
        argv = g.get('argv')
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x.strip() for x in argv):
            raise CheckError(f'{gid}: argv must be a nonempty array of strings (no shell)')
        if any('REPLACE_ME' in x for x in argv):
            raise CheckError(f'{gid}: configure a real command before verification')
        timeout = g.get('timeout_seconds', 120)
        if not isinstance(timeout, int) or not 1 <= timeout <= 1800:
            raise CheckError(f'{gid}: timeout_seconds must be 1..1800')
        if not isinstance(g.get('required', True), bool):
            raise CheckError(f'{gid}: required must be boolean')
        if 'evidence_regex' in g:
            require_str(g['evidence_regex'], f'{gid}.evidence_regex')
            try:
                re.compile(g['evidence_regex'])
            except re.error as exc:
                raise CheckError(f'{gid}.evidence_regex is invalid: {exc}') from exc
    require_str(task.get('task_id'), 'task_id')
    require_str(task.get('goal'), 'goal')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', task['task_id']):
        raise CheckError('task_id must be simple alphanumeric, underscores or hyphens')
    if task.get('risk') not in ('low', 'medium', 'high', 'critical'):
        raise CheckError('risk must be low, medium, high, or critical')
    if not isinstance(task.get('require_changes', True), bool):
        raise CheckError('require_changes must be boolean')
    for field in ('allowed_paths', 'denied_paths'):
        paths = task.get(field)
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p.strip() for p in paths):
            raise CheckError(f'{field} must be a nonempty list of glob patterns')
    requirements = task.get('requirements')
    if not isinstance(requirements, list) or not requirements:
        raise CheckError('requirements must be a nonempty array')
    rids = set()
    for r in requirements:
        if not isinstance(r, dict):
            raise CheckError('each requirement must be a JSON object')
        rid = r.get('id')
        require_str(rid, 'requirement.id')
        require_str(r.get('description'), f'{rid}.description')
        if rid in rids:
            raise CheckError(f'duplicate requirement id: {rid}')
        rids.add(rid)
        accepts = r.get('acceptance_gates')
        if not isinstance(accepts, list) or not accepts:
            raise CheckError(f'{rid}: provide at least one acceptance gate')
        for gate in accepts:
            if gate not in ids:
                raise CheckError(f'{rid}: acceptance gate {gate!r} not present in config')
    if task.get('risk') in ('high', 'critical') and task.get('external_actions_allowed', True):
        raise CheckError('high/critical tasks must set external_actions_allowed=false; use explicit human approval outside the tool for external actions')


def matched(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or (pattern.startswith('**/') and fnmatch.fnmatchcase(path, pattern[3:]))


def git_changed(repo: Path, base: str) -> list[str]:
    if base.startswith('-') or '\n' in base:
        raise CheckError('Unsafe git base ref')
    try:
        check = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], cwd=repo, capture_output=True, text=True, timeout=10)
        if check.returncode or check.stdout.strip() != 'true':
            raise CheckError('Repository is not a Git working tree. Initialize Git and commit a baseline first.')
        a = subprocess.run(['git', 'diff', '--name-only', '-z', base, '--'], cwd=repo, capture_output=True, timeout=20)
        b = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=repo, capture_output=True, timeout=20)
        if a.returncode or b.returncode:
            raise CheckError('Git diff failed. Ensure baseline ref exists: ' + a.stderr.decode(errors='replace')[-250:])
        paths = {p.decode('utf-8', errors='replace').replace('\\', '/') for p in (a.stdout + b.stdout).split(b'\0') if p}
        return sorted(p for p in paths if not p.startswith(IGNORE_PREFIXES))
    except FileNotFoundError as exc:
        raise CheckError('Git is required for scope verification') from exc
    except subprocess.TimeoutExpired as exc:
        raise CheckError('Git status timed out') from exc


def run_gate(repo: Path, gate: dict) -> dict:
    t0 = time.monotonic()
    output = {'id': gate['id'], 'argv': gate['argv'], 'required': gate.get('required', True)}
    try:
        # shell=False is deliberate. This still executes project code and does not sandbox it.
        result = subprocess.run(gate['argv'], cwd=repo, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=gate.get('timeout_seconds', 120))
        combined = (result.stdout or '') + '\n' + (result.stderr or '')
        evidence_ok = not gate.get('evidence_regex') or re.search(gate['evidence_regex'], combined) is not None
        output.update({'status': 'PASS' if result.returncode == 0 and evidence_ok else 'FAIL',
                       'exit_code': result.returncode, 'evidence_pattern_found': bool(evidence_ok),
                       'stdout_tail': (result.stdout or '')[-4000:], 'stderr_tail': (result.stderr or '')[-4000:]})
    except subprocess.TimeoutExpired as exc:
        output.update({'status': 'TIMEOUT', 'exit_code': None,
                       'stdout_tail': str(exc.stdout or b'')[-2000:], 'stderr_tail': str(exc.stderr or b'')[-2000:]})
    except OSError as exc:
        output.update({'status': 'ERROR', 'exit_code': None, 'error': str(exc)})
    output['duration_seconds'] = round(time.monotonic() - t0, 3)
    return output


def verify(args) -> int:
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise CheckError('Repository does not exist: ' + str(repo))
    cfg_path = local_path(repo, args.config)
    task_path = local_path(repo, args.task)
    config, task = read_json(cfg_path), read_json(task_path)
    validate(config, task)
    baseline = args.base or task.get('baseline_ref', 'HEAD')
    changed_before = git_changed(repo, baseline)  # fail closed on absent baseline
    gates = []
    for gate in config['gates']:
        outcome = run_gate(repo, gate)
        gates.append(outcome)
        print(f"[{outcome['status']}] {outcome['id']} ({outcome['duration_seconds']:.2f}s)")
    changed = git_changed(repo, baseline)  # detect files modified by test commands too
    allow = task['allowed_paths']
    deny = task['denied_paths']
    violations = [p for p in changed if any(matched(p, d) for d in deny) or not any(matched(p, a) for a in allow)]
    gate_map = {g['id']: g for g in gates}
    requirements = [{'id': r['id'], 'description': r['description'],
                     'acceptance_gates': r['acceptance_gates'],
                     'status': 'PASS' if all(gate_map[k]['status'] == 'PASS' for k in r['acceptance_gates']) else 'FAIL'}
                    for r in task['requirements']]
    required_fail = [g['id'] for g in gates if g['required'] and g['status'] != 'PASS']
    errors = []
    if required_fail:
        errors.append('Required gates failed: ' + ', '.join(required_fail))
    if any(r['status'] != 'PASS' for r in requirements):
        errors.append('One or more requirements lack passing acceptance gates')
    if violations:
        errors.append('Out-of-scope or forbidden changed files: ' + ', '.join(violations))
    if task.get('require_changes', True) and not changed:
        errors.append('No file changes detected versus baseline; a claimed implementation cannot be verified')
    if task['risk'] in ('high', 'critical'):
        errors.append('Human approval required for high-risk task. This CLI does not attest authorization.')
    now = dt.datetime.now(dt.timezone.utc)
    record = {'schema_version': 1, 'task_id': task['task_id'], 'goal': task['goal'], 'risk': task['risk'],
              'timestamp_utc': now.isoformat(), 'baseline_ref': baseline,
              'contract_sha256': digest(task_path), 'config_sha256': digest(cfg_path),
              'changed_before_gates': changed_before, 'changed_after_gates': changed,
              'scope_violations': violations, 'gates': gates, 'requirements': requirements,
              'status': 'PASS' if not errors else 'FAIL', 'errors': errors,
              'disclaimer': 'PASS means only configured gates passed. Not a security certification, comprehensive test oracle, or proof of user intent.'}
    outdir = local_path(repo, args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{task['task_id']}"
    jsonpath, mdpath = outdir / (stem + '.json'), outdir / (stem + '.md')
    jsonpath.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    render_md(record, mdpath)
    print(f"{record['status']}: {task['task_id']} | changed={len(changed)} | scope violations={len(violations)}")
    print(f'Evidence: {jsonpath}\nReport: {mdpath}')
    return 0 if not errors else 1


def render_md(record: dict, dest: Path) -> None:
    lines = [f"# AgentCheck: {record['task_id']}", '', f"**Result:** {record['status']}",
             f"**Goal:** {record['goal']}", f"**Risk:** {record['risk']}",
             f"**UTC:** {record['timestamp_utc']}", f"**Baseline:** `{record['baseline_ref']}`", '',
             '## Acceptance requirements', '', '| ID | Evidence gates | Result |', '|---|---|---|']
    lines += [f"| {r['id']} | {', '.join(r['acceptance_gates'])} | {r['status']} |" for r in record['requirements']]
    lines += ['', '## Executed gates', '', '| Gate | Result | Seconds |', '|---|---|---:|']
    lines += [f"| {g['id']} | {g['status']} | {g['duration_seconds']:.3f} |" for g in record['gates']]
    lines += ['', '## Changed paths', ''] + ['- `' + p + '`' for p in record['changed_after_gates']]
    if record['scope_violations']:
        lines += ['', '## Scope violations', ''] + ['- `' + p + '`' for p in record['scope_violations']]
    if record['errors']:
        lines += ['', '## Blocking findings', ''] + ['- ' + s for s in record['errors']]
    lines += ['', '## Limits', '', record['disclaimer'],
              'Review the sibling JSON for commands, stdout/stderr tails, hashes and exact evidence.']
    dest.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def init(args) -> int:
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise CheckError('Repository directory not found: ' + str(repo))
    config = read_json(SKILL / 'assets' / 'agentcheck.json')
    if args.preset == 'python':
        config['gates'] = [{'id': 'unit_tests', 'argv': ['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                            'timeout_seconds': 180, 'required': True,
                            'evidence_regex': r'Ran [1-9][0-9]* tests?'}]
    task = read_json(SKILL / 'assets' / 'task-contract.json')
    out = [(repo / 'agentcheck.json', config), (repo / 'agent-tasks' / 'example.json', task)]
    existing = [str(p) for p, _ in out if p.exists()]
    if existing:
        raise CheckError('Init would overwrite existing files: ' + ', '.join(existing))
    for path, content in out:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')
        print('Created:', path)
    print('NEXT: configure real gates, set allowed_paths and acceptance requirements, then commit baseline.')
    return 0


def validate_cmd(args) -> int:
    repo = Path(args.repo).expanduser().resolve()
    validate(read_json(local_path(repo, args.config)), read_json(local_path(repo, args.task)))
    print('PASS: config and task contract have valid structure and linked acceptance gates.')
    print('NOTE: validation does not execute tests or prove correctness.')
    return 0


def compare(args) -> int:
    a, b = read_json(Path(args.baseline)), read_json(Path(args.candidate))
    if a.get('task_id') != b.get('task_id'):
        raise CheckError('Compare requires matching task IDs; do not compare unrelated tasks')
    if a.get('contract_sha256') != b.get('contract_sha256'):
        print('WARNING: task contract changed; comparison is not controlled', file=sys.stderr)
    ga = {g['id']: g for g in a.get('gates', [])}
    gb = {g['id']: g for g in b.get('gates', [])}
    print('Task:', a.get('task_id'), '| baseline:', a.get('status'), '| candidate:', b.get('status'))
    print(f"{'Gate':24s} {'Baseline':12s} {'Candidate':12s} {'Δ seconds':>12s}")
    for key in sorted(ga.keys() | gb.keys()):
        x, y = ga.get(key, {}), gb.get(key, {})
        delta = y.get('duration_seconds', 0) - x.get('duration_seconds', 0) if x and y else None
        print(f"{key[:24]:24s} {x.get('status','MISSING'):12s} {y.get('status','MISSING'):12s} {delta if delta is not None else 'n/a':>12}")
    print('Single-run comparison is descriptive. Repeat evaluations before claiming improvement.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ini = sub.add_parser('init', help='create starter contract and test gate configuration')
    ini.add_argument('--repo', default='.')
    ini.add_argument('--preset', choices=['python', 'custom'], default='custom')
    val = sub.add_parser('validate', help='validate config and contract schema/linkage')
    ver = sub.add_parser('verify', help='run gates and produce independent execution evidence')
    for p in (val, ver):
        p.add_argument('--repo', default='.')
        p.add_argument('--config', default='agentcheck.json')
        p.add_argument('--task', default='agent-tasks/example.json')
    ver.add_argument('--base', help='Git baseline commit/ref (defaults to contract baseline_ref)')
    ver.add_argument('--output-dir', default='.agentcheck/runs')
    cmp = sub.add_parser('compare', help='compare two evidence JSON records from the same task')
    cmp.add_argument('--baseline', required=True)
    cmp.add_argument('--candidate', required=True)
    args = parser.parse_args(argv)
    try:
        return {'init': init, 'validate': validate_cmd, 'verify': verify, 'compare': compare}[args.command](args)
    except (CheckError, OSError) as exc:
        print('AGENTCHECK ERROR: ' + str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
