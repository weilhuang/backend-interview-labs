import unittest,json,re,yaml
from pathlib import Path
R=Path(__file__).resolve().parents[1];LESSONS=json.loads((R/'manifest/lessons.json').read_text())
def slices(t):
 y=yaml.safe_load((t/'task-info.yaml').read_text());h=y['files'][0]['placeholders'][0];s=(t/'go/exercise.go').read_text();b=s.encode('utf-16-le')
 return y,h,s,b[:h['offset']*2].decode('utf-16-le'),b[(h['offset']+h['length'])*2:].decode('utf-16-le')
class StaticTests(unittest.TestCase):
 def test_exact_three_new_tasks(self):
  self.assertEqual([l['id'] for l in LESSONS],['C13-01','C13-02','C13-03']);self.assertEqual(len(list((R/'overlay').rglob('task-info.yaml'))),3)
 def test_utf16_projection_and_region_only(self):
  for l in LESSONS:
   with self.subTest(l['id']):
    t=R/'overlay/go-course/core'/l['slug'];y,h,s,pre,post=slices(t);self.assertNotEqual(len(pre),h['offset'])
    self.assertEqual((R/'learner-static/go-course/core'/l['slug']/'go/exercise.go').read_text(),pre+h['placeholder_text']+post)
    answers=list((t/'go/answers').glob('*.txt'));self.assertGreaterEqual(len(answers),2)
    for a in answers:self.assertTrue(a.read_text().startswith(pre) and a.read_text().endswith(post),str(a))
 def test_visible_inventory_complete(self):
  for l in LESSONS:
   t=R/'overlay/go-course/core'/l['slug'];y,*_=slices(t);self.assertTrue(all(f['visible'] for f in y['files']))
   names=[f['name'] for f in y['files']];self.assertEqual(len(names),len(set(names)));self.assertEqual(set(names),{str(p.relative_to(t)) for p in t.rglob('*') if p.is_file() and p.name not in ['task.md','task-info.yaml']})
 def test_go_bridge_pins_expected_tests(self):
  for l in LESSONS:
   t=R/'overlay/go-course/core'/l['slug'];bridge=(t/'src/GoTestBridge.java').read_text()
   for name in l['required_tests']+l['cases']:self.assertIn('"'+name+'"',bridge)
   self.assertRegex(bridge,r'version.exitCode\(\)\s*!=\s*0');self.assertRegex(bridge,r'result.exitCode\(\)\s*!=\s*0');self.assertIn('"1.27.1"',bridge);self.assertIn('GO_EXECUTABLE',(t/'test/GoContractTest.java').read_text())
 def test_docs_have_executable_learner_paths(self):
  for l in LESSONS:
   t=R/'overlay/go-course/core'/l['slug'];text=(t/'task.md').read_text()
   for needle in ['H1','H2','H3','H4','Java对照','标准答案','INVALID_ENV','NOT_RUN','GO_EXECUTABLE','分步练习与迁移观察']:self.assertIn(needle,text)
   self.assertFalse(re.search(r'(?m)^\s*/[A-Za-z0-9_-]+/',text));self.assertNotIn('model.go',text)
   for path in re.findall(r'!\[[^]]*\]\(([^)]+)\)',text):self.assertTrue((t/path).is_file(),path)
 def test_all_local_markdown_links_in_both_views(self):
  for view in ['overlay','learner-static']:
   for task in (R/view/'go-course/core').iterdir():
    for path in re.findall(r'!?\[[^]]*\]\(([^)]+)\)',(task/'task.md').read_text()):
     self.assertFalse(path.startswith(('http:','https:','file:')))
     self.assertTrue((task/path).is_file(),str(task/path))
    if view=='learner-static':
     self.assertIn('../../../../overlay/go-course/core/'+task.name+'/task-info.yaml',(task/'task.md').read_text())
 def test_no_sdk_or_external_go_dependencies(self):
  for l in LESSONS:
   t=R/'overlay/go-course/core'/l['slug'];mod=(t/'go/go.mod').read_text();self.assertIn('go 1.27.1',mod);self.assertNotIn('require ',mod)
  self.assertFalse(any(p.name in ['go','java','javac'] and p.is_file() for p in (R/'overlay').rglob('*')))
 def test_count_proposal_preserves_baselines(self):
  p=json.loads((R/'manifest/overlay-proposal.json').read_text());self.assertEqual((p['base_v1']['tasks'],p['base_v1']['placeholders']),(84,136));self.assertEqual((p['base_v2_first_slice']['tasks'],p['base_v2_first_slice']['placeholders']),(92,144));self.assertEqual((p['additional_tasks'],p['additional_placeholders']),(3,3));self.assertFalse(p['canonical_modified']);self.assertFalse(p['frozen_eight_modified'])
 def test_repaired_error_priority_retained(self):
  t=R/'overlay/go-course/core/order-total';text=(t/'go/contract_test.go').read_text();bridge=(t/'src/GoTestBridge.java').read_text()
  for name in ['乘溢出先于后行非法','加溢出先于后行非法','非法先于后行溢出']:self.assertIn(name,text);self.assertIn(name,bridge)
  self.assertTrue((t/'go/wrong-solutions/prevalidate-all-first.go.txt').is_file())
if __name__=='__main__':unittest.main(verbosity=2)
