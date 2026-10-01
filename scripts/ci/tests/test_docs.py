from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_docs import anchors, links, validate


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


if __name__ == '__main__':
    unittest.main()
