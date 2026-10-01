"""Prevent the authoring generator from restoring the old masked-timeout test."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


class ConcurrencySourceTests(unittest.TestCase):
    def test_bounded_buffer_generator_matches_public_test(self):
        course = ROOT / 'courses/java-concurrency'
        tree = ast.parse((course / 'authoring/build_course.py').read_text())
        payload = next(ast.literal_eval(node.value.args[4]) for node in tree.body
                       if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                       and isinstance(node.value.func, ast.Name) and node.value.func.id == 'task'
                       and ast.literal_eval(node.value.args[0]) == '03-bounded-buffer')
        public = (course / 'juc/03-bounded-buffer/lab/test/BoundedBuffersTest.java').read_text()
        self.assertEqual(payload.strip(), public.strip())
        self.assertIn('ExecutorCompletionService<Set<Integer>>', public)
        self.assertIn('primary.addSuppressed(cleanup)', public)
        self.assertNotIn('first.get(3, TimeUnit.SECONDS)', public)


if __name__ == '__main__':
    unittest.main()
