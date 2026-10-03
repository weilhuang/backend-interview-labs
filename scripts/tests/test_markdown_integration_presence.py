"""Integration command selection uses real Java source, not workspace empty dirs."""
from pathlib import Path
import tempfile, unittest, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unified_markdown import migrate
class IntegrationPresenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.addCleanup(self.tmp.cleanup)
 def render(self,cid='distributed-systems'):
  tasks=[{'source_course':cid,'source_task':'tasks/'+s,'original_module':s,'gradle_project':':course-'+s} for s in ['first','second']]
  return migrate('./gradlew integrationTest compileIntegrationTestJava\n',cid,self.root,{'tasks':tasks,'support_projects':[]},'README.md')
 def test_empty_directory_does_not_select_module(self):
  before=self.render();(self.root/'tasks/first/integration-test/nested').mkdir(parents=True);self.assertEqual(before,self.render())
 def test_non_java_file_does_not_select_module(self):
  p=self.root/'tasks/first/integration-test/README.md';p.parent.mkdir(parents=True);p.write_text('not Java source');self.assertNotIn(':course-first:',self.render())
 def test_real_java_source_selects_both_goals(self):
  p=self.root/'tasks/second/integration-test/labs/Test.java';p.parent.mkdir(parents=True);p.write_text('class Test {}');s=self.render();self.assertIn(':course-second:integrationTest',s);self.assertIn(':course-second:compileIntegrationTestJava',s);self.assertNotIn(':course-first:',s)
 def test_directory_named_java_is_not_source(self):
  (self.root/'tasks/first/integration-test/NotAFile.java').mkdir(parents=True);self.assertNotIn(':course-first:',self.render())
 def test_redis_registered_shared_source_behavior_preserved(self):
  s=self.render('redis-engineering');self.assertIn(':course-first:integrationTest',s);self.assertIn(':course-second:compileIntegrationTestJava',s)
if __name__=='__main__':unittest.main()
