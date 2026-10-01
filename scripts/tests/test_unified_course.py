import importlib.util,json,os,shutil,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
COURSE=None
PROFILES=None
def load(name):
 p=ROOT/'scripts'/f'{name}.py';s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
u=load('unify_course');v=load('validate_unified_course')


def setUpModule():
    """Plain discovery builds its own fixture; no Java or pre-existing output needed."""
    global COURSE, PROFILES
    original_path = sys.path[:]
    missing = object()
    original_modules = {name: sys.modules.get(name, missing)
                        for name in ('academy_gate', 'process_runner')}

    def restore_imports():
        sys.path[:] = original_path
        for name, module in original_modules.items():
            if module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    unittest.addModuleCleanup(restore_imports)
    requested = os.environ.get('UNIFIED_COURSE_ROOT')
    if requested is not None:
        if not requested.strip():
            raise ValueError('UNIFIED_COURSE_ROOT 必须指向已有完整课程，不能留空')
        COURSE = Path(requested).resolve()
        if not COURSE.is_dir():
            raise ValueError('UNIFIED_COURSE_ROOT 课程目录不存在：' + str(COURSE))
    else:
        temporary = tempfile.TemporaryDirectory(prefix='unified-course-tests-')
        # Register immediately so partial generation failures also clean only our directory.
        unittest.addModuleCleanup(temporary.cleanup)
        COURSE = Path(temporary.name) / 'course'
        u.build(ROOT, COURSE)
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(COURSE / 'authoring/quality'))
    # Load this fixture's profile map by exact path, never by ambient PYTHONPATH/cache.
    PROFILES = u.load_module(COURSE / 'scripts/environment_profiles.py',
                             'unified_test_environment_profiles').PROFILES
    v.validate(COURSE, repo=ROOT)

class UnifiedCourseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)/'course'
  shutil.copytree(COURSE,cls.root,ignore=shutil.ignore_patterns('build','.gradle','__pycache__'))
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_complete_static_contract(self):
  r=v.validate(self.root);self.assertEqual((r['tasks'],r['placeholders']),(84,136))
 def test_framework_process_script_retains_reviewed_source(self):
  path='materials/java-frameworks/scripts/course.sh'
  source=ROOT/'courses/java-frameworks/scripts/course.sh'
  self.assertEqual((self.root/path).read_bytes(),source.read_bytes())
  files=json.loads((self.root/'authoring/source-provenance.json').read_text())['files']
  entry=next(item for item in files if item['path']==path)
  self.assertEqual(entry['transformation'],'identity')
  self.assertEqual(entry['source_sha256'],u.digest(source.read_bytes()))
  self.assertEqual(entry['sha256'],entry['source_sha256'])
 def test_generated_framework_startup_regression(self):
  import subprocess
  environment=dict(os.environ,FRAMEWORK_STARTUP_SCRIPT=str(self.root/'materials/java-frameworks/scripts/course.sh'))
  result=subprocess.run([sys.executable,str(ROOT/'scripts/tests/test_framework_startup.py'),
    'FrameworkStartupTests.test_delayed_same_child_exec_then_separate_http_check'],
    env=environment,capture_output=True,text=True,timeout=30)
  self.assertEqual(result.returncode,0,(result.stdout,result.stderr))
 def test_generated_framework_http_identity_regressions(self):
  import subprocess
  environment=dict(os.environ,FRAMEWORK_STARTUP_SCRIPT=str(self.root/'materials/java-frameworks/scripts/course.sh'))
  result=subprocess.run([sys.executable,str(ROOT/'scripts/tests/test_framework_http_identity.py')],
    env=environment,capture_output=True,text=True,timeout=15)
  self.assertEqual(result.returncode,0,(result.stdout,result.stderr))
 def test_official_module_names(self):
  m=json.loads((self.root/'authoring/course-map.json').read_text())
  self.assertEqual(len({t['gradle_project'] for t in m['tasks']}),84)
  for t in m['tasks']:self.assertEqual(t['gradle_project'],':'+t['path'].replace('/','-'))
 def test_redis_wrapped_without_nested_section(self):
  self.assertTrue((self.root/'redis-course/section-info.yaml').is_file())
  self.assertTrue((self.root/'redis-course/redis/lesson-info.yaml').is_file())
 def test_mapping_drift_rejected(self):
  p=self.root/'authoring/course-map.json';old=p.read_bytes();m=json.loads(old);m['tasks'][0]['gradle_project']=':wrong';p.write_text(json.dumps(m))
  try:
   with self.assertRaisesRegex(ValueError,'命名'):v.validate(self.root)
  finally:p.write_bytes(old)
 def test_java_tampering_rejected(self):
  p=next((self.root/'c00').rglob('*.java'));old=p.read_bytes();p.write_bytes(old+b'\n// changed\n')
  try:
   with self.assertRaisesRegex(ValueError,'保护文件'):v.validate(self.root)
  finally:p.write_bytes(old)
 def test_second_ledger_rejected(self):
  p=self.root/'materials/versions.env';p.write_text('MYSQL_IMAGE=mysql:8.4.7\n')
  try:
   with self.assertRaisesRegex(ValueError,'台账必须唯一'):v.validate(self.root)
  finally:p.unlink()
 def test_no_pilot_no_generated_build_outputs(self):
  self.assertFalse(any('java-pilot' in p.parts for p in self.root.rglob('*')))
  self.assertFalse(any(p.name=='course-info.yaml' and p.parent!=self.root for p in self.root.rglob('course-info.yaml')))
 def test_single_wrapper_single_jdk_entry(self):
  self.assertEqual(len(list(self.root.rglob('gradlew'))),1)
  self.assertEqual(len(list(self.root.rglob('gradle-wrapper.jar'))),1)
  self.assertIn('org.gradle.workers.max=1',(self.root/'gradle.properties').read_text())
 def test_c10_full_native_grading_preserved(self):
  b=(self.root/'materials/distributed-systems/course.gradle').read_text()
  self.assertIn('sourceSets.test.output.classesDirs + sourceSets.integrationTest.output.classesDirs',b)
  self.assertIn("['06-transactions', '07-outbox-cache']",b)
 def test_c14_reference_dirs_preserved(self):
  b=(self.root/'materials/backend-capstone/course.gradle').read_text()
  self.assertIn("it != originalNames[project.path]",b)
  self.assertIn('courseFile("reference/${it}/src")',b)
 def test_support_project_paths_isolated(self):
  b='\n'.join(p.read_text() for p in self.root.glob('materials/*/course.gradle'))
  self.assertNotIn("project(':support')",b);self.assertNotIn("project(':common')",b)
 def test_materializer_retains_reference_answers(self):
  from academy_gate import inspect_course,replace_placeholders
  m=inspect_course(self.root)
  for name,ph in m['placeholders'].items():
   original=(self.root/name).read_text();learner,answers=replace_placeholders(original,ph)
   self.assertNotEqual(original,learner);self.assertEqual(len(answers),len(ph))
 def test_unknown_project_reference_fails_closed(self):
  mapping=json.loads((self.root/'authoring/course-map.json').read_text())
  with self.assertRaisesRegex(ValueError,'未映射'):
   u.gradle_adapter("plugins { id 'base' }\nsubprojects { implementation project(':unknown') }",'java-foundations',mapping,{})
 def test_output_refuses_existing_directory(self):
  with self.assertRaisesRegex(ValueError,'目标必须不存在'):u.build(Path('/not-used'),self.root)


class SupportTestAggregationTests(unittest.TestCase):
 def test_generated_support_test_capabilities_are_explicit(self):
  mapping=json.loads((COURSE/'authoring/course-map.json').read_text())
  actual={item['gradle_project']:item['test_tasks'] for item in mapping['support_projects']}
  self.assertEqual(actual,{
   ':java-foundations-common':{'test':'test','unitTest':'test'},
   ':java-foundations-benchmark':{},
   ':redis-engineering-support':{'test':'test','unitTest':'unitTest'},
   ':distributed-systems-support':{'test':'test','unitTest':'unitTest'},
   ':messaging-support':{'test':'test','unitTest':'test'},
  })
  self.assertEqual(len(mapping['tasks']),84)
  for aggregate in ('test','unitTest'):
   support_targets=[item['gradle_project']+':'+item['test_tasks'][aggregate]
                    for item in mapping['support_projects'] if item['test_tasks']]
   self.assertEqual(len(support_targets),4)
   self.assertFalse(any('benchmark' in target for target in support_targets))
 def test_generated_root_aggregates_keep_course_and_support_dependencies(self):
  build=(COURSE/'build.gradle').read_text()
  self.assertIn('def taskProjects = courseMap.tasks.collect { project(it.gradle_project) }',build)
  for aggregate,course_dependency in (
   ('test',"dependsOn taskProjects.collect { it.tasks.named('test') }"),
   ('unitTest',"dependsOn taskProjects.collect { it.tasks.findByName('unitTest') ?: it.tasks.named('test') }"),
  ):
   body=build.split("tasks.register('"+aggregate+"') {",1)[1].split('\n}',1)[0]
   self.assertIn(course_dependency,body)
   self.assertIn("dependsOn supportTestTasks('"+aggregate+"')",body)
 def test_support_task_resolution_fails_closed_and_never_schedules_jmh(self):
  build=(COURSE/'build.gradle').read_text()
  body=build.split('def supportTestTasks = { String aggregate ->',1)[1].split('\n}',1)[0]
  self.assertIn("courseMap.support_projects.findAll { it.original_module != 'benchmark' }",body)
  self.assertIn('def target = item.test_tasks[aggregate]',body)
  self.assertIn('if (!target) throw new GradleException(',body)
  self.assertIn('project(item.gradle_project).tasks.named(target)',body)
  for silent_fallback in ('findProject','findByName','?:','catch','withJmh'):
   self.assertNotIn(silent_fallback,body)
 def test_new_support_project_requires_a_declared_test_contract(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)/'java-concurrency';(root/'common').mkdir(parents=True)
   with self.assertRaisesRegex(ValueError,'缺少支撑项目聚合测试合同'):
    u.mapping([(root,{'tasks':[]},{'content':[]})])


class WrapperPropertyNormalizationTests(unittest.TestCase):
 # Captured pinned Academy WrapperInit + official Gradle 8.10.2 / JDK21
 # minimal preflight. These are not bytes recovered from the Actions import.
 BEFORE = b'distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\ndistributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\ndistributionSha256Sum=31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26\nnetworkTimeout=10000\nvalidateDistributionUrl=true\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n'
 AFTER = b'distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\ndistributionSha256Sum=31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26\ndistributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\nnetworkTimeout=10000\nvalidateDistributionUrl=true\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n'
 def test_matches_fixed_sdk_preflight_exact_bytes(self):
  self.assertEqual(u.digest(self.BEFORE),'1de17d500d4671816e3ee230e897e8722157da899c534850aa8ab5cce9577da0')
  self.assertEqual(u.digest(self.AFTER),'09debb2fbd9878414d0632cc40a7e285966bfd0625c0d430bfa11e3cab173335')
  self.assertEqual(u.normalize_wrapper_properties(self.BEFORE),self.AFTER)
  self.assertEqual(u.normalize_wrapper_properties(self.AFTER),self.AFTER)
 def test_preserves_every_value_and_escape(self):
  actual=u.normalize_wrapper_properties(self.BEFORE)
  self.assertEqual(dict(line.split(b'=',1) for line in actual.splitlines()),
                   dict(line.split(b'=',1) for line in self.BEFORE.splitlines()))
  self.assertEqual(sorted(actual.splitlines(keepends=True)),sorted(self.BEFORE.splitlines(keepends=True)))
 def test_unknown_duplicate_missing_and_unfamiliar_format_rejected(self):
  invalid=[self.BEFORE+b'unknown=value\n',self.BEFORE+b'networkTimeout=10000\n',
           self.BEFORE.replace(b'networkTimeout=10000\n',b''),
           self.BEFORE.replace(b'\n',b'\r\n'),self.BEFORE.rstrip(b'\n'),
           b'# comment\n'+self.BEFORE,self.BEFORE+b'\n',
           self.BEFORE.replace(b'networkTimeout=10000',b'networkTimeout=10000\\'),
           self.BEFORE.replace(b'distributionBase=',b'distributionBase : ')]
  for data in invalid:
   with self.subTest(data=data):
    with self.assertRaisesRegex(ValueError,'Wrapper properties:'):u.normalize_wrapper_properties(data)
 def test_generated_wrapper_and_provenance(self):
  path='gradle/wrapper/gradle-wrapper.properties'
  self.assertEqual((COURSE/path).read_bytes(),self.AFTER)
  entries=json.loads((COURSE/'authoring/source-provenance.json').read_text())['files']
  entry=next(x for x in entries if x['path']==path)
  self.assertEqual(entry,{'source':'courses/java-foundations/'+path,'path':path,
                        'source_sha256':u.digest(self.BEFORE),'sha256':u.digest(self.AFTER),
                        'transformation':'gradle-8.10.2-wrapper-property-line-order'})
 def test_generation_leaves_nine_source_courses_unchanged(self):
  def snapshot():
   return {p.relative_to(ROOT).as_posix():u.digest(p.read_bytes())
           for name in u.COURSES for p in (ROOT/'courses'/name).rglob('*')
           if p.is_file() and not u.IGNORE.intersection(p.parts)}
  before=snapshot()
  with tempfile.TemporaryDirectory() as directory:u.build(ROOT,Path(directory)/'course')
  self.assertEqual(snapshot(),before)

class OutputSafetyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.repo=Path(self.temp.name)/'repo';self.repo.mkdir()
  (self.repo/'courses/java-foundations').mkdir(parents=True)
  (self.repo/'scripts/unified-environment').mkdir(parents=True)
  (self.repo/'scripts/unified-dependency-locks').mkdir()
 def tearDown(self):self.temp.cleanup()
 def test_generator_rejects_author_descendant(self):
  with self.assertRaisesRegex(ValueError,'互不包含'):u.validate_destinations(self.repo,self.repo/'courses/java-foundations/new')
 def test_generator_rejects_template_descendant(self):
  with self.assertRaisesRegex(ValueError,'互不包含'):u.validate_destinations(self.repo,self.repo/'scripts/unified-environment/new')
 def test_generator_rejects_lock_descendant(self):
  with self.assertRaisesRegex(ValueError,'互不包含'):u.validate_destinations(self.repo,self.repo/'scripts/unified-dependency-locks/new')
 def test_generator_rejects_input_ancestor(self):
  with self.assertRaisesRegex(ValueError,'目标必须不存在'):u.validate_destinations(self.repo,self.repo/'courses')
 def test_generator_resolves_symlink_into_input(self):
  link=Path(self.temp.name)/'alias';link.symlink_to(self.repo/'courses/java-foundations',target_is_directory=True)
  with self.assertRaisesRegex(ValueError,'互不包含'):u.validate_destinations(self.repo,link/'new')
 def test_report_cannot_overwrite_source(self):
  report=self.repo/'README.md';report.write_text('keep')
  with self.assertRaisesRegex(ValueError,'拒绝覆盖'):u.validate_destinations(self.repo,self.repo/'build/course',report=report)
  self.assertEqual(report.read_text(),'keep')
 def test_report_cannot_be_generated_asset(self):
  with self.assertRaisesRegex(ValueError,'生成课程资产'):u.validate_destinations(self.repo,self.repo/'build/course',report=self.repo/'build/course/build.gradle')
 def test_report_cannot_be_input_asset(self):
  with self.assertRaisesRegex(ValueError,'输入目录'):u.validate_destinations(self.repo,self.repo/'build/course',report=self.repo/'courses/java-foundations/report.json')
 def test_new_build_output_and_sibling_report_allowed(self):
  u.validate_destinations(self.repo,self.repo/'build/course',report=self.repo/'build/report.json')
 def test_materialize_rejects_child_before_copy(self):
  import subprocess,sys
  course=COURSE;dest=course/'should-not-create'
  result=subprocess.run([sys.executable,str(course/'authoring/materialize_learner.py'),str(dest)],capture_output=True,text=True)
  self.assertNotEqual(result.returncode,0);self.assertFalse(dest.exists());self.assertIn('互不包含',result.stderr)
 def test_materialize_rejects_ancestor_before_copy(self):
  import subprocess,sys
  course=COURSE
  result=subprocess.run([sys.executable,str(course/'authoring/materialize_learner.py'),str(course.parent)],capture_output=True,text=True)
  self.assertNotEqual(result.returncode,0);self.assertIn('互不包含',result.stderr)


class TeachingMigrationTests(unittest.TestCase):
 def test_gradle_namespace_and_java_example_are_separate(self):
  from unified_markdown import migrate
  mapping=json.loads((COURSE/'authoring/course-map.json').read_text())
  original="./gradlew :06-transactions:test\n```java\nSystem.out.println(\"./gradlew :06-transactions:test\");\n```\n"
  result=migrate(original,'distributed-systems',COURSE/'materials/distributed-systems',mapping,'distributed-course/services/06-transactions/task.md')
  self.assertTrue(result.startswith('bash scripts/gradle.sh :distributed-course-services-06-transactions:test'))
  self.assertIn('System.out.println(\"./gradlew :06-transactions:test\");',result)
 def test_current_teaching_commands_are_mapped(self):
  from unified_markdown import command_inventory
  mapping=json.loads((COURSE/'authoring/course-map.json').read_text());known={t['gradle_project'] for t in mapping['tasks']+mapping['support_projects']}
  for task in mapping['tasks']:
   for page in (COURSE/task['path']).rglob('*.md'):
    for command in command_inventory(page.read_text()):self.assertIn(command.rsplit(':',1)[0],known)
 def test_capstone_current_fault_commands(self):
  s=(COURSE/'capstone/stages/04-recovery/task.md').read_text()
  self.assertIn('bash scripts/lab.sh pause-service capstone --service mysql',s)
  self.assertIn('bash scripts/lab.sh recover-service capstone --service delivery',s)
  self.assertNotIn('scripts/course.sh',s)
 def test_diagnostic_paths_reach_actual_sections(self):
  self.assertIn("R.parents[1]/'jvm'",(COURSE/'materials/java-jvm/scripts/lab.py').read_text())
  self.assertIn("ROOT.parents[1]/'juc/",(COURSE/'materials/java-concurrency/scripts/diagnose.py').read_text())
  self.assertIn("R.parents[1]/'c01/",(COURSE/'materials/java-foundations/scripts/trace_hashmap.py').read_text())
 def test_active_lock_tampering_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'course';shutil.copytree(COURSE,root,ignore=shutil.ignore_patterns('build','.gradle','__pycache__'))
   lock=next((root/'dependency-locks').glob('*.lockfile'));lock.write_text(lock.read_text()+'# drift\n')
   with self.assertRaisesRegex(ValueError,'锁已漂移'):v.validate(root)


class FinalInstructionTests(unittest.TestCase):
 def test_inline_url_does_not_hide_stage_instruction(self):
  from unified_markdown import migrate
  mapping=json.loads((COURSE/'authoring/course-map.json').read_text())
  text='打开 `http://127.0.0.1:8088`。默认使用05-defense；练第二节时设置 `CAPSTONE_STAGE=02-reliability` 再start。'
  changed=migrate(text,'backend-capstone',COURSE/'materials/backend-capstone',mapping,'README.md')
  self.assertNotIn('CAPSTONE_STAGE=02-reliability',changed)
  self.assertIn('bash scripts/lab.sh start capstone --stage 02-reliability',changed)
 def test_readme_materializer_uses_sibling(self):
  for name in ('java-foundations','java-jvm','redis-engineering'):
   text=(COURSE/'materials'/name/'README.md').read_text()
   self.assertNotRegex(text,r'authoring/materialize_learner.py\s+build/')
 def test_original_author_commands_cannot_be_copied_as_current_shell(self):
  import re
  for p in (COURSE/'materials').rglob('*.md'):
   for line in p.read_text().splitlines():
    self.assertFalse(re.match(r'^\s*python3?\s+authoring/(?!materialize_learner\.py)[\w.-]+\.py',line),(p,line))
 def test_legacy_service_verbs_absent(self):
  for name in ('mysql-engineering','redis-engineering'):
   text=(COURSE/'materials'/name/'README.md').read_text()
   self.assertNotRegex(text,r'scripts/lab.sh\s+(up|down)\b')
   self.assertNotRegex(text,r'scripts/lab.sh\s+check\s+(core|mysql|redis)(?![/\w-])')
 def test_unified_ledger_does_not_advertise_ancestor_override(self):
  text=(COURSE/'shared/README.md').read_text()
  self.assertIn('不会向父仓库查找',text)
  self.assertNotIn('LAB_SHARED_VERSIONS=',text)

class EnvironmentInstructionTests(unittest.TestCase):
 def test_all_documented_environment_commands_use_known_actions_and_targets(self):
  import re
  from unified_markdown import sections
  paths={t['path'] for t in json.loads((COURSE/'authoring/course-map.json').read_text())['tasks']}
  actions={'verify','doctor','profiles','images','start','stop','status','logs','health','resources','check','workbench-check','pause-service','recover-service','crash-service'}
  for page in COURSE.rglob('*.md'):
   if {'build','.gradle'}.intersection(page.relative_to(COURSE).parts):continue
   for protected,text in sections(page.read_text()):
    if protected:continue
    for match in re.finditer(r'scripts/lab\.sh\s+([a-z-]+)(?:[ \t]+([A-Za-z0-9/_-]+))?',text):
     action,scope=match[1],match[2];self.assertIn(action,actions,(page,match[0]))
     if scope and not scope.startswith('--') and action not in ('check','verify','profiles','images','resources'):self.assertIn(scope,set(PROFILES)|{'all'},(page,match[0]))
     if action=='check' and scope:self.assertIn(scope,paths,(page,match[0]))


class GradleLauncherInstructionsTests(unittest.TestCase):
 def test_active_gradle_commands_use_surviving_launcher(self):
  import re
  from unified_markdown import sections
  for page in COURSE.rglob('*.md'):
   if {'build','.gradle'}.intersection(page.relative_to(COURSE).parts):continue
   for protected,text in sections(page.read_text()):
    if protected:continue
    self.assertFalse(re.search(r'(?:^|[ `])(?:bash\s+)?\./gradlew(?:\.bat)?\s+[:A-Za-z-]',text,re.M),(page,text[:100]))
 def test_launcher_is_explicitly_registered(self):
  import yaml
  names={f['name'] for f in yaml.safe_load((COURSE/'course-info.yaml').read_text())['additional_files']}
  self.assertIn('scripts/gradle.sh',names);self.assertIn('scripts/gradle_launcher.py',names)
  self.assertIn('gradle/wrapper/gradle-wrapper.properties',names)


if __name__ == '__main__':
    unittest.main()
