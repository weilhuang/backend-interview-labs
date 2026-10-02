from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_docs import anchors, links, validate, validate_repository


class DocsTests(unittest.TestCase):
    def test_code_examples_are_not_links(self):
        self.assertEqual(links('```md\n[x](missing)\n```\n`[x](also-missing)`\n[x](README.md)'), ['README.md'])

    def test_chinese_anchors_and_duplicates(self):
        self.assertEqual(anchors('# 中文 标题\n## 中文 标题\n## API：`test()`\n<a id="custom"></a>'), {'中文-标题','中文-标题-1','apitest','custom'})

    def test_link_path_anchor_reference_and_external_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'target.md').write_text('# 中文标题\n')
            good = '[x](target.md#中文标题)\n[ref]: target.md\n[x](https://example.com)'
            (root/'README.md').write_text(good)
            result=validate(root,['README.md','target.md'])
            self.assertEqual(result['errors'],[])
            self.assertEqual(result['external_http_reachability'],'NOT_RUN')
            (root/'README.md').write_text(good+'\n[x](target.md#wrong)\n[x](missing.md)\n[x](../escape)')
            self.assertEqual(len(validate(root,['README.md','target.md'])['errors']),3)

    def test_generated_untracked_target_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'README.md').write_text('[x](untracked.txt)')
            (root/'untracked.txt').write_text('generated')
            self.assertEqual(len(validate(root,['README.md'])['errors']),1)


    def test_exact_template_links_require_tracked_author_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = 'scripts/unified-environment/docs/统一环境.md'
            doc = root / name
            doc.parent.mkdir(parents=True)
            doc.write_text('[ledger](../shared/versions.env)\n[frontend](../materials/backend-capstone/docs/前端使用.md)')
            sources = ['infra/versions.env', 'courses/backend-capstone/docs/前端使用.md']
            for source in sources:
                target = root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('# 页面\n')
            self.assertEqual(validate(root, [name] + sources)['errors'], [])
            self.assertEqual(len(validate(root, [name])['errors']), 2)
            ledger = root / sources[0]
            ledger.unlink()
            self.assertEqual(len(validate(root, [name] + sources)['errors']), 1)
            with tempfile.TemporaryDirectory() as outside:
                other = Path(outside) / 'versions.env'
                other.write_text('external')
                ledger.symlink_to(other)
                self.assertEqual(len(validate(root, [name] + sources)['errors']), 1)
            ledger.unlink()
            ledger.write_text('restored')
            doc.write_text('[wrong](../shared/other.env)')
            self.assertEqual(len(validate(root, [name] + sources)['errors']), 1)

    def test_generated_course_links_are_checked_without_source_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'docs/统一环境.md').write_text('[ledger](../shared/versions.env)')
            self.assertEqual(len(validate(root, ['docs/统一环境.md'])['errors']), 1)
            (root / 'shared').mkdir()
            (root / 'shared/versions.env').write_text('MYSQL_IMAGE=mysql:fixed')
            self.assertEqual(validate(root, ['docs/统一环境.md', 'shared/versions.env'])['errors'], [])


    def test_partial_overlay_cannot_skip_sealed_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'authoring/unified-course/overlay/task.md';path.parent.mkdir(parents=True);path.write_text('[generated target](../missing.md)')
            result=validate_repository(root,[path.relative_to(root).as_posix()])
            self.assertEqual(result['status'],'failed')
            self.assertIn('sealed manifest',result['errors'][0])

    def test_overlay_generation_error_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);overlay=root/'authoring/unified-course/overlay/task.md';overlay.parent.mkdir(parents=True);overlay.write_text('draft')
            (root/'authoring/unified-course/manifest.json').write_text('{}')
            script=root/'scripts/build_unified_course.py';script.parent.mkdir();script.write_text("def build(*args): raise ValueError('changed overlay')")
            files=[p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()]
            result=validate_repository(root,files)
            self.assertEqual(result['status'],'failed');self.assertIn('changed overlay',result['errors'][0])

    def test_repository_without_overlay_keeps_normal_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'README.md').write_text('[missing](absent.md)')
            self.assertEqual(validate_repository(root,['README.md']),validate(root,['README.md']))


if __name__ == '__main__':
    unittest.main()
