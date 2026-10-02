"""Regression for the observed validateCourse graphics-startup failure."""
import ast
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]


class DisplayRoutingTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((ROOT / '.github/workflows/academy-official.yml').read_text())
        self.job = self.workflow['jobs']['package']
        self.steps = self.job['steps']
        self.native = next(s for s in self.steps if s.get('id') == 'official')
        self.expression = self.native['env']['DISPLAY_MODE']

    def route(self, event, ref, display=''):
        # Evaluate only this tiny reviewed boolean-expression grammar, with no
        # arbitrary calls, attributes or identifiers permitted.
        expr = self.expression.removeprefix('${{').removesuffix('}}').strip()
        for key, value in [('github.event_name', event), ('github.ref', ref), ('inputs.display', display)]:
            expr = expr.replace(key, repr(value))
        expr = expr.replace('&&', ' and ').replace('||', ' or ')
        node = ast.parse(expr, mode='eval')
        self.assertTrue(all(isinstance(n, (ast.Expression, ast.BoolOp, ast.And, ast.Or,
                                          ast.Compare, ast.Eq, ast.Constant)) for n in ast.walk(node)))
        return eval(compile(node, '<display-routing>', 'eval'), {'__builtins__': {}})

    def test_only_temporary_full_push_defaults_to_xvfb(self):
        self.assertEqual(self.route('push', 'refs/heads/academy-validation/full'), 'xvfb')
        for ref in ['refs/heads/academy-validation/smoke', 'refs/heads/main', 'refs/heads/other']:
            self.assertEqual(self.route('push', ref), 'headless')

    def test_manual_explicit_display_remains_authoritative(self):
        for ref in ['refs/heads/main', 'refs/heads/academy-validation/full']:
            for display in ['headless', 'xvfb']:
                self.assertEqual(self.route('workflow_dispatch', ref, display), display)

    def test_xvfb_preflight_matches_full_push_and_manual_choice(self):
        run = next(s['run'] for s in self.steps if s.get('name') == '标准 runner 容量与 Docker 预检')
        self.assertIn("(github.event_name == 'push' && github.ref == 'refs/heads/academy-validation/full') || inputs.display == 'xvfb'", run)
        self.assertIn('then command -v xvfb-run; fi', run)

    def test_existing_budget_source_gate_and_release_gate_remain(self):
        self.assertEqual(self.job['runs-on'], 'ubuntu-24.04')
        self.assertIn('&& 85 || 30', self.job['timeout-minutes'])
        self.assertIn('&& 60 || 8', self.native['timeout-minutes'])
        self.assertTrue(any('check_source_ci.py' in s.get('run', '') for s in self.steps))
        environment = self.workflow['jobs']['environment']
        self.assertEqual(environment['needs'], 'package')
        self.assertEqual(environment['runs-on'], 'ubuntu-24.04')
        self.assertEqual(environment['timeout-minutes'], 65)
        self.assertTrue(environment['if'].startswith('success() &&'))
        self.assertTrue(any(s.get('id') == 'release_gate' and 'release_gate.py' in s.get('run', '') for s in environment['steps']))
        upload = environment['steps'][-1]
        self.assertEqual(upload['if'], "success() && steps.environment.outcome == 'success' && steps.release_gate.outcome == 'success'")
        self.assertEqual(upload['with']['path'].splitlines(), ['${{ env.ENV_RUN }}/release/backend-interview-academy.zip', '${{ env.ENV_RUN }}/release/SHA256SUMS'])

    def test_uses_existing_official_xvfb_path_with_all_tests_and_links(self):
        source = (ROOT / 'scripts/academy/run_official.py').read_text()
        self.assertEqual(source.count("if a.display=='xvfb':command=['xvfb-run','-a','--server-args=-screen 0 1280x900x24',*command]"), 2)
        self.assertIn("'--tests','true','--links','true'", source)
        self.assertIn("if a.phase=='export-import-smoke':", source)


if __name__ == '__main__':
    unittest.main()
