import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'scripts' / 'agentcheck.py'


def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, timeout=30)


class AgentCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        for c in [['git', 'init', '-q'], ['git', 'config', 'user.email', 'test@example.invalid'],
                  ['git', 'config', 'user.name', 'Test']]:
            subprocess.run(c, cwd=self.repo, check=True, capture_output=True)
        (self.repo / 'src').mkdir()
        (self.repo / 'src' / 'app.py').write_text('x = 1\n')
        self.config = {'schema_version': 1, 'gates': [{'id': 'acceptance',
            'argv': [sys.executable, '-c', "print('PASS marker')"],
            'required': True, 'timeout_seconds': 8, 'evidence_regex': 'PASS marker'}]}
        self.task = {'schema_version': 1, 'task_id': 'example', 'goal': 'Change behavior',
                     'risk': 'low', 'external_actions_allowed': False,
                     'baseline_ref': 'HEAD', 'require_changes': True,
                     'allowed_paths': ['src/**', 'tests/**'], 'denied_paths': ['.env', '**/.env', '*.pem'],
                     'requirements': [{'id': 'R1', 'description': 'Verify behavior and regression',
                                       'acceptance_gates': ['acceptance']}]}
        self._write()
        subprocess.run(['git', 'add', '.'], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'baseline'], cwd=self.repo, check=True, capture_output=True)

    def _write(self):
        (self.repo / 'agentcheck.json').write_text(json.dumps(self.config))
        (self.repo / 'agent-tasks').mkdir(exist_ok=True)
        (self.repo / 'agent-tasks' / 'example.json').write_text(json.dumps(self.task))

    def _verify(self):
        return run_cli('verify', '--repo', self.repo, '--task', 'agent-tasks/example.json')

    def _record(self):
        results = list((self.repo / '.agentcheck' / 'runs').glob('*.json'))
        self.assertEqual(len(results), 1)
        return json.loads(results[0].read_text())

    def test_passing_change_generates_evidence_and_report(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        p = self._verify()
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        r = self._record()
        self.assertEqual(r['status'], 'PASS')
        self.assertIn('src/app.py', r['changed_after_gates'])
        self.assertEqual(r['requirements'][0]['status'], 'PASS')
        self.assertEqual(len(list((self.repo / '.agentcheck' / 'runs').glob('*.md'))), 1)

    def test_no_changes_is_not_verified(self):
        p = self._verify()
        self.assertEqual(p.returncode, 1)
        self.assertIn('No file changes detected', self._record()['errors'][-1])

    def test_denied_path_blocks_success(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        (self.repo / '.env').write_text('DO_NOT_READ=this_is_test_only\n')
        p = self._verify()
        self.assertEqual(p.returncode, 1)
        self.assertIn('.env', self._record()['scope_violations'])

    def test_outside_allowlist_blocks_success(self):
        (self.repo / 'surprise.txt').write_text('test')
        self.assertEqual(self._verify().returncode, 1)
        self.assertIn('surprise.txt', self._record()['scope_violations'])

    def test_gate_failure_blocks_success(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        self.config['gates'][0]['argv'] = [sys.executable, '-c', 'raise SystemExit(3)']
        self._write()
        self.assertEqual(self._verify().returncode, 1)
        self.assertEqual(self._record()['gates'][0]['exit_code'], 3)

    def test_evidence_pattern_required(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        self.config['gates'][0]['argv'] = [sys.executable, '-c', "print('success but no evidence')"]
        self._write()
        self.assertEqual(self._verify().returncode, 1)
        self.assertFalse(self._record()['gates'][0]['evidence_pattern_found'])

    def test_zero_test_suite_not_allowed(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        self.config['gates'][0]['argv'] = [sys.executable, '-c', "print('Ran 0 tests')"]
        self.config['gates'][0]['evidence_regex'] = r'Ran [1-9][0-9]* tests?'
        self._write()
        self.assertEqual(self._verify().returncode, 1)

    def test_process_side_effects_are_checked_after_gate(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        self.config['gates'][0]['argv'] = [sys.executable, '-c',
            "open('.env','w').write('bad'); print('PASS marker')"]
        self._write()
        self.assertEqual(self._verify().returncode, 1)
        self.assertIn('.env', self._record()['scope_violations'])

    def test_unconfigured_placeholder_fails_closed(self):
        self.config['gates'][0]['argv'] = ['REPLACE_ME_WITH_TEST_COMMAND']
        self._write()
        p = run_cli('validate', '--repo', self.repo)
        self.assertEqual(p.returncode, 2)
        self.assertIn('configure a real command', p.stderr)

    def test_unknown_acceptance_gate_fails_closed(self):
        self.task['requirements'][0]['acceptance_gates'] = ['imaginary']
        self._write()
        p = run_cli('validate', '--repo', self.repo)
        self.assertEqual(p.returncode, 2)
        self.assertIn('not present', p.stderr)

    def test_high_risk_requires_human_approval_and_never_auto_passes(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        self.task['risk'] = 'high'
        self._write()
        self.assertEqual(self._verify().returncode, 1)
        self.assertIn('Human approval required', self._record()['errors'][-1])

    def test_path_traversal_blocked(self):
        p = run_cli('validate', '--repo', self.repo, '--task', '../secret.json')
        self.assertEqual(p.returncode, 2)
        self.assertIn('inside repo', p.stderr)

    def test_init_creates_configs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as other:
            p = run_cli('init', '--repo', other, '--preset', 'python')
            self.assertEqual(p.returncode, 0, p.stderr)
            config = json.loads((Path(other) / 'agentcheck.json').read_text())
            self.assertIn('unittest', config['gates'][0]['argv'])
            self.assertEqual(run_cli('init', '--repo', other).returncode, 2)

    def test_compare_two_reports(self):
        (self.repo / 'src' / 'app.py').write_text('x = 2\n')
        self.assertEqual(self._verify().returncode, 0)
        evidence = list((self.repo / '.agentcheck' / 'runs').glob('*.json'))[0]
        p = run_cli('compare', '--baseline', evidence, '--candidate', evidence)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('Single-run comparison', p.stdout)


if __name__ == '__main__':
    unittest.main()
