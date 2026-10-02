import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gates import GateError, read_json, read_yaml, validate_report, learner_content, safe_name
from run_official import fresh_target, cli_environment, prepare_gradle_evidence, inspect_gradle_evidence
from collect_evidence import collect

FIXTURES=Path(__file__).parent/'fixtures'

def fixture():
    return json.loads((FIXTURES/'validation-success-84.json').read_text())

def contract():
    value=json.loads((FIXTURES/'expected-suites-84.json').read_text())
    value['counts']={'courses':1,'sections':1,'tasks':84,'placeholders':84}
    return value

def first_task(report):return report['children'][0]['children'][0]['children'][0]['children'][0]

class ValidationTests(unittest.TestCase):
    def test_source_shaped_full_success(self):
        result=validate_report(fixture(),contract())
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['native_tests']['observed'],84)
        self.assertEqual(result['native_ui_check_reset'],'NOT_RUN')
    def test_exit_zero_does_not_make_failed_case_pass(self):
        report=fixture();first_task(report)['children'][0]['result']={'type':'failed','message':'compiler failed'}
        self.assertEqual(validate_report(report,contract())['native_tests']['status'],'FAIL')
    def test_ignored_case_is_failure(self):
        report=fixture();first_task(report)['children'][0]['result']={'type':'ignored','message':'no test run'}
        self.assertEqual(validate_report(report,contract())['status'],'FAIL')
    def test_missing_task_is_failure(self):
        report=fixture();report['children'][0]['children'][0]['children'][0]['children'].pop()
        self.assertEqual(validate_report(report,contract())['native_tests']['observed'],83)
        self.assertEqual(validate_report(report,contract())['status'],'FAIL')
    def test_missing_tests_case_is_failure(self):
        report=fixture();first_task(report)['children'].pop(0)
        self.assertEqual(validate_report(report,contract())['status'],'FAIL')
    def test_duplicate_tests_case_rejected(self):
        report=fixture();first_task(report)['children'].append(copy.deepcopy(first_task(report)['children'][0]))
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_duplicate_task_suite_rejected(self):
        report=fixture();report['children'][0]['children'][0]['children'][0]['children'].append(copy.deepcopy(first_task(report)))
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_unexpected_task_rejected(self):
        report=fixture();first_task(report)['name']='unexpected'
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_ascii_dir_instead_of_presentable_name_rejected(self):
        report=fixture();first_task(report)['name']='lab'
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_wrong_course_rejected(self):
        report=fixture();report['children'][0]['name']='wrong course'
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_unknown_result_rejected(self):
        report=fixture();first_task(report)['children'][0]['result']={'type':'passed'}
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_unknown_node_schema_rejected(self):
        report=fixture();first_task(report)['children'][0]['status']='success'
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_root_has_no_polymorphic_discriminator(self):
        report=fixture();report['type']='suite'
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_success_message_is_unexpected_schema(self):
        report=fixture();first_task(report)['children'][0]['result']['message']='hidden error'
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_unexpected_case_cannot_fill_coverage(self):
        report=fixture();first_task(report)['children'][0]['name']='Tests (skipped)'
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_failed_link_is_separate_from_tests(self):
        report=fixture();first_task(report)['children'][1]['children'][0]['result']={'type':'failed','message':'HTTP 404'}
        result=validate_report(report,contract())
        self.assertEqual(result['native_tests']['status'],'PASS');self.assertEqual(result['description_links']['status'],'FAIL');self.assertEqual(result['status'],'FAIL')
    def test_ignored_link_fails(self):
        report=fixture();first_task(report)['children'][1]['children'][0]['result']={'type':'ignored','message':'offline'}
        self.assertEqual(validate_report(report,contract())['status'],'FAIL')
    def test_absent_all_links_is_not_pass(self):
        report=fixture()
        for task in report['children'][0]['children'][0]['children'][0]['children']:task['children'].pop()
        self.assertEqual(validate_report(report,contract())['description_links']['status'],'FAIL')
    def test_ambiguous_expected_paths_rejected(self):
        c=contract();c['tasks'][-1]=copy.deepcopy(c['tasks'][0])
        with self.assertRaises(GateError):validate_report(fixture(),c)
    def test_empty_suite_rejected(self):
        report=fixture();first_task(report)['children']=[]
        with self.assertRaises(GateError):validate_report(report,contract())
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.json';p.write_text('{"name":"a","name":"b"}')
            with self.assertRaises(GateError):read_json(p)
    def test_truncated_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.json';p.write_text('{"name":')
            with self.assertRaises(json.JSONDecodeError):read_json(p)
    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.json';p.write_text('{"x":NaN}')
            with self.assertRaises(GateError):read_json(p)
    def test_duplicate_yaml_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bad.yaml';p.write_text('title: a\ntitle: b\n')
            with self.assertRaises(GateError):read_yaml(p)

class SafetyTests(unittest.TestCase):
    def test_utf16_offsets_and_shifted_multiple_regions(self):
        raw='😀xANSWERtailYY'.encode(); learner,parts=learner_content(raw,[
            {'offset':3,'length':6,'placeholder_text':'TODO'}, {'offset':13,'length':2,'placeholder_text':'?'}])
        self.assertEqual(learner.decode(),'😀xTODOtail?');self.assertEqual([p['offset'] for p in parts],[3,11])
    def test_overlapping_regions_rejected(self):
        with self.assertRaises(GateError):learner_content(b'abcde',[{'offset':1,'length':3,'placeholder_text':'x'},{'offset':2,'length':1,'placeholder_text':'y'}])
    def test_source_and_target_ancestor_both_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(GateError):fresh_target(root/'source',root,[root/'source'/'child'])
            with self.assertRaises(GateError):fresh_target(root/'source'/'child',root,[root/'source'])
    def test_existing_target_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/'existing';target.mkdir()
            with self.assertRaises(GateError):fresh_target(target,root,[])
    def test_run_root_and_outside_target_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(GateError):fresh_target(root,root,[])
            with self.assertRaises(GateError):fresh_target(root.parent/'outside',root,[])
    def test_safe_fresh_sibling_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.assertEqual(fresh_target(root/'student',root,[root/'author']),root/'student')
    def test_unsafe_archive_paths_rejected(self):
        for name in ('../a','/a','a/../b','a\\b','a//b','C:/a','a/./b'):
            with self.subTest(name=name),self.assertRaises(GateError):safe_name(name)
    def test_evidence_never_copies_archive_or_profile(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'run';(run/'evidence').mkdir(parents=True)
            (run/'evidence/archive.zip').write_bytes(b'NO');(run/'evidence/summary.json').write_text('{}')
            (run/'evidence/idea.properties').write_text('private');collect(run,root/'collected')
            self.assertEqual({p.name for p in (root/'collected').iterdir()},{'summary.json','collection.json'})
    def test_evidence_exists_when_native_command_never_started(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);collect(root/'missing',root/'collected')
            self.assertEqual(read_json(root/'collected/summary.json')['status'],'NOT_RUN')
    def test_profile_has_no_acceptance_or_trust_switches(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);idea=root/'idea';(idea/'bin').mkdir(parents=True);(idea/'bin/idea64.vmoptions').write_text('-Xmx2048m\n-ea\n')
            jdk=root/'jdk';(jdk/'bin').mkdir(parents=True);(jdk/'bin/java').write_text('');(jdk/'release').write_text('JAVA_VERSION="21.0.12"\n')
            with patch.dict(os.environ,{'GH_TOKEN':'secret','JAVA_TOOL_OPTIONS':'bad','JAVA_HOME':str(jdk)}):env,profile=cli_environment(idea,root/'plugins',root,'export')
            self.assertNotIn('GH_TOKEN',env);self.assertNotIn('JAVA_TOOL_OPTIONS',env)
            options=Path(env['IDEA_VM_OPTIONS']).read_text();self.assertIn('-Djava.io.tmpdir=',options);self.assertNotIn('-Xmx2048m',options)
            self.assertNotIn('accept',options);self.assertNotIn('trust',options)
            self.assertIn('-Dproject.jdk='+str(jdk),options);self.assertIn('-Dproject.jdk.name=academy-ci-jdk21',options)

class WorkflowTests(unittest.TestCase):
    def workflow(self):
        return yaml.load((Path(__file__).resolve().parents[3]/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
    def test_manual_standard_runner_read_only(self):
        w=self.workflow();self.assertEqual(set(w['on']),{'workflow_dispatch','push'});self.assertEqual(w['on']['push']['branches'],['academy-validation/smoke','academy-validation/full'])
        self.assertEqual(w['permissions'],{'contents':'read','actions':'read'})
        self.assertEqual(w['jobs']['package']['runs-on'],'ubuntu-24.04')
        self.assertEqual(w['on']['workflow_dispatch']['inputs']['phase']['default'],'export-import-smoke')
    def test_final_artifact_has_all_gates_and_short_retention(self):
        workflow=self.workflow();package=workflow['jobs']['package'];environment=workflow['jobs']['environment']
        all_uploads=[s for s in package['steps'] if s.get('uses')=='actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02']
        ui=[s for s in all_uploads if s['with']['name'].startswith('academy-ui-')]
        uploads=[s for s in all_uploads if not s['with']['name'].startswith('academy-ui-')]
        self.assertEqual(len(uploads),2)
        self.assertEqual(len(ui),4)
        for step in ui:
            self.assertIn("inputs.phase == 'full-validation'",step['if'])
            self.assertEqual(step['with']['retention-days'],'1')
            for path in step['with']['path'].splitlines():
                self.assertTrue(path.startswith('${{ env.UI_RUN }}/stage-'))
                for forbidden in ('profile','token','.zip','/home/'):
                    self.assertNotIn(forbidden,path.lower())
        self.assertEqual({x['with']['name'].split('${{')[0] for x in ui},
                         {'academy-ui-stage-1-','academy-ui-stage-2-','academy-ui-stage-3-','academy-ui-receipts-'})
        self.assertEqual(uploads[0]['if'],"always() && steps.evidence.outputs.collected == 'true'")
        self.assertIn("steps.handoff.outcome == 'success'",uploads[1]['if'])
        self.assertEqual(uploads[1]['with']['retention-days'],'1');self.assertIn('NOT-A-RELEASE',uploads[1]['with']['name'])
        final=environment['steps'][-1]
        self.assertEqual(environment['needs'],'package');self.assertIn("inputs.phase == 'full-validation'",environment['if'])
        self.assertIn("steps.environment.outcome == 'success'",final['if']);self.assertIn("steps.release_gate.outcome == 'success'",final['if'])
        self.assertEqual(final['with']['retention-days'],'7');self.assertEqual(final['with']['if-no-files-found'],'error')
    def test_no_cache_schedule_or_paid_runner(self):
        w=self.workflow();self.assertNotIn('schedule',w['on']);self.assertEqual(w['on']['push']['branches'],['academy-validation/smoke','academy-validation/full'])
        self.assertFalse(any('cache' in s.get('uses','') for s in w['jobs']['package']['steps']))


class JvmEvidenceTests(unittest.TestCase):
    def test_missing_jvm_observation_fails(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(GateError):inspect_gradle_evidence(Path(d),[Path(d)/'student'])
    def test_wrong_actual_jvm_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'evidence').mkdir();(root/'evidence/gradle-jvm.jsonl').write_text(json.dumps({'java_version':'25.0.4','gradle_version':'8.10.2','root':str(root/'student')})+'\n')
            with self.assertRaises(GateError):inspect_gradle_evidence(root,[root/'student'])
    def test_no_validation_root_evidence_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'evidence').mkdir();(root/'evidence/gradle-jvm.jsonl').write_text(json.dumps({'java_version':'21.0.12','gradle_version':'8.10.2','root':str(root/'student')})+'\n')
            with self.assertRaises(GateError):inspect_gradle_evidence(root,[root/'student',root/'validation'])
    def test_observer_generated_outside_course(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);prepare_gradle_evidence(root)
            text=(root/'gradle-home/init.d/academy-ci-jvm-evidence.gradle').read_text()
            self.assertIn("System.getProperty('java.version')",text)
            self.assertIn('JavaVersion.VERSION_21',text);self.assertIn('gradle.beforeSettings',text)
            self.assertFalse((root/'author').exists())

class ArchiveTests(unittest.TestCase):
    def inputs(self):
        import base64
        from gates import sha
        source=b'answer';learner=b'TODO';answer={'offset':0,'length':4,'placeholder_text':'TODO','answer':'answer','answer_sha256':sha(source)}
        f={'author_sha256':sha(source),'learner_sha256':sha(learner),'placeholders':[answer],'visible':True,'binary':False}
        contract={'counts':{'courses':1,'sections':1,'tasks':1,'placeholders':1},'title':'Synthetic parser fixture','sections':['section'],'containers':{'section':'章节','section/lesson':'一课'},
                  'tasks':[{'path':'section/lesson/task','custom_name':'练习','description_sha256':sha(b'task\n'),'files':{'src/F.java':f}}],
                  'files':{'section/lesson/task/src/F.java':f},'additional_files':[]}
        meta={'version':23,'edu_plugin_version':'pin','title':contract['title'],'programming_language_id':'JAVA','language':'zh',
              'environment_settings':{'jvm_language_level':'JDK_21'},'additional_files':[],
              'items':[{'id':1,'title':'section','custom_name':'章节','items':[{'id':2,'title':'lesson','custom_name':'一课',
              'task_list':[{'id':3,'name':'task','custom_name':'练习','task_type':'edu','description_format':'MD','description_text':'task\n',
              'files':{'src/F.java':{'name':'src/F.java','is_visible':True,'placeholders':[{'offset':0,'length':4,'placeholder_text':'TODO','possible_answer':base64.b64encode(b'X'*16).decode()}]}}}]}]}]}
        return contract,meta,{'academy':{'archive_schema_version':23,'version':'pin'}}
    def archive(self,root,meta,extra=None,content=b'X'*16):
        import zipfile
        p=root/'synthetic-parser-fixture.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('course.json',json.dumps(meta));z.writestr('contents/section/lesson/task/src/F.java',content)
            if extra:z.writestr(extra,b'bad')
        return p
    def test_archive_reader_does_not_rewrite_bytes(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();path=self.archive(Path(d),m);before=path.read_bytes()
            self.assertEqual(inspect_archive(path,c,pins)['status'],'PASS');self.assertEqual(path.read_bytes(),before)
    def test_extra_stale_member_fails(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();path=self.archive(Path(d),m,'stale-release.zip')
            with self.assertRaises(GateError):inspect_archive(path,c,pins)
    def test_path_traversal_fails(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();path=self.archive(Path(d),m,'../outside')
            with self.assertRaises(GateError):inspect_archive(path,c,pins)
    def test_unknown_exporter_fails(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();m['edu_plugin_version']='unknown';path=self.archive(Path(d),m)
            with self.assertRaises(GateError):inspect_archive(path,c,pins)
    def test_wrong_jdk_metadata_fails(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();m['environment_settings']['jvm_language_level']='JDK_25';path=self.archive(Path(d),m)
            with self.assertRaises(GateError):inspect_archive(path,c,pins)
    def test_duplicate_study_ids_fail(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();m['items'][0]['items'][0]['id']=1;path=self.archive(Path(d),m)
            with self.assertRaises(GateError):inspect_archive(path,c,pins)
    def test_plaintext_possible_answer_fails(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();m['items'][0]['items'][0]['task_list'][0]['files']['src/F.java']['placeholders'][0]['possible_answer']='answer';path=self.archive(Path(d),m)
            with self.assertRaises(GateError):inspect_archive(path,c,pins)
    def test_omitted_additional_asset_fails(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();c['additional_files']=['build.gradle'];path=self.archive(Path(d),m)
            with self.assertRaises(GateError):inspect_archive(path,c,pins)
    def test_plaintext_payload_fails(self):
        from gates import inspect_archive
        with tempfile.TemporaryDirectory() as d:
            c,m,pins=self.inputs();path=self.archive(Path(d),m,content=b'answer')
            with self.assertRaises(GateError):inspect_archive(path,c,pins)


class ImportTests(unittest.TestCase):
    def fixture(self,root):
        from gates import sha
        for path in ('section/lesson/task/src','section/lesson/task/test'): (root/path).mkdir(parents=True,exist_ok=True)
        (root/'course-info.yaml').write_text('type: marketplace\ntitle: Synthetic\nlanguage: Chinese\nprogramming_language: Java\nenvironment_settings: {jvm_language_level: JDK_21}\ncontent: [section]\n')
        (root/'section/section-info.yaml').write_text('custom_name: 章节\ncontent: [lesson]\n')
        (root/'section/lesson/lesson-info.yaml').write_text('custom_name: 课程\ncontent: [task]\n')
        (root/'section/lesson/task/src/F.java').write_bytes(b'TODO')
        (root/'section/lesson/task/test/FTest.java').write_bytes(b'test')
        (root/'section/lesson/task/task.md').write_bytes(b'task\n')
        f={'author_sha256':sha(b'answer'),'learner_sha256':sha(b'TODO'),'visible':True,'binary':False,'placeholders':[{'offset':0,'length':4,'placeholder_text':'TODO','author_offset':0,'author_length':6}]}
        support={'author_sha256':sha(b'test'),'learner_sha256':sha(b'test'),'visible':True,'binary':False,'placeholders':[]}
        tm={'type':'edu','custom_name':'练习','status':'Unchecked','files':[{'name':'src/F.java','visible':True,'placeholders':[{'offset':0,'length':4,'placeholder_text':'TODO','status':'Unchecked','initial_state':{'offset':0,'length':4}}]},{'name':'test/FTest.java','visible':True}]}
        (root/'section/lesson/task/task-info.yaml').write_text(yaml.safe_dump(tm,allow_unicode=True))
        c={'counts':{'courses':1,'sections':1,'tasks':1,'placeholders':1},'course_metadata':{'type':'marketplace','language':'Chinese','programming_language':'Java'},'title':'Synthetic','sections':['section'],'containers':{'section':'章节','section/lesson':'课程'},
           'container_contents':{'section':['lesson'],'section/lesson':['task']},
           'files':{'section/lesson/task/src/F.java':f,'section/lesson/task/test/FTest.java':support},
           'tasks':[{'path':'section/lesson/task','suite':['root_node','Synthetic','section','lesson','练习'],'expected_link_urls':['https://example.com/source'],'custom_name':'练习','description_sha256':sha(b'task\n'),'files':{'src/F.java':f,'test/FTest.java':support}}]}
        return c
    def test_fresh_student_plaintext_and_metadata(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.fixture(root);self.assertEqual(inspect_import(root,c,'student')['status'],'PASS')
    def test_reference_solution_is_not_student_state(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.fixture(root);(root/'section/lesson/task/src/F.java').write_bytes(b'answer')
            with self.assertRaises(GateError):inspect_import(root,c,'student')
    def test_missing_test_file_fails(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.fixture(root);(root/'section/lesson/task/test/FTest.java').unlink()
            with self.assertRaises(GateError):inspect_import(root,c,'student')
    def test_false_solved_metadata_fails(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.fixture(root);p=root/'section/lesson/task/task-info.yaml';p.write_text(p.read_text().replace('Unchecked','Solved'))
            with self.assertRaises(GateError):inspect_import(root,c,'student')
    def test_container_names_cannot_change(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.fixture(root);(root/'section/section-info.yaml').write_text('custom_name: Wrong\ncontent: [lesson]\n')
            with self.assertRaises(GateError):inspect_import(root,c,'student')
    def test_orphan_task_fails(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.fixture(root);(root/'section/extra').mkdir();(root/'section/extra/task-info.yaml').write_text('type: edu\n')
            with self.assertRaises(GateError):inspect_import(root,c,'student')
    def test_educator_must_restore_reference(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.fixture(root)
            with self.assertRaises(GateError):inspect_import(root,c,'educator')
            (root/'section/lesson/task/src/F.java').write_bytes(b'answer')
            p=root/'section/lesson/task/task-info.yaml';tm=yaml.safe_load(p.read_text());tm['files'][0]['placeholders'][0]['length']=6;p.write_text(yaml.safe_dump(tm))
            self.assertEqual(inspect_import(root,c,'educator')['status'],'PASS')



class ReviewRegressionTests(unittest.TestCase):
    def mutate_import(self,change,educator=False):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);contract=ImportTests().fixture(root)
            if educator:(root/'section/lesson/task/src/F.java').write_bytes(b'answer')
            p=root/'section/lesson/task/task-info.yaml';tm=yaml.safe_load(p.read_text());change(tm);p.write_text(yaml.safe_dump(tm))
            with self.assertRaises(GateError):inspect_import(root,contract,'educator' if educator else 'student')
    def test_choice_type_rejected(self):self.mutate_import(lambda m:m.update(type='choice'))
    def test_duplicate_declared_source_rejected(self):self.mutate_import(lambda m:m['files'].append(copy.deepcopy(m['files'][0])))
    def test_hidden_source_rejected(self):self.mutate_import(lambda m:m['files'][0].update(visible=False))
    def test_educator_offsets_rejected(self):self.mutate_import(lambda m:m['files'][0]['placeholders'][0].update(offset=99999,length=99),True)
    def test_jdk25_metadata_rejected(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=ImportTests().fixture(root);p=root/'course-info.yaml';m=yaml.safe_load(p.read_text());m['environment_settings']['jvm_language_level']='JDK_25';p.write_text(yaml.safe_dump(m))
            with self.assertRaises(GateError):inspect_import(root,c,'student')
    def test_missing_task_instructions_rejected(self):
        from gates import inspect_import
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=ImportTests().fixture(root);(root/'section/lesson/task/task.md').unlink()
            with self.assertRaises(GateError):inspect_import(root,c,'student')
    def test_one_arbitrary_link_cannot_cover_84_tasks(self):
        report=fixture();tasks=report['children'][0]['children'][0]['children'][0]['children']
        for task in tasks:task['children']=task['children'][:1]
        tasks[0]['children'].append({'type':'suite','name':'Task description links','children':[{'type':'case','name':'https://unrelated.invalid','result':{'type':'success'}}]})
        result=validate_report(report,contract());self.assertEqual(result['status'],'FAIL');self.assertEqual(len(result['description_links']['missing']),84)
    def test_evidence_parent_symlink_never_read(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'foreign').mkdir();(p/'foreign/summary.json').write_text('SENSITIVE');(p/'run').mkdir();(p/'run/evidence').symlink_to(p/'foreign',target_is_directory=True)
            with self.assertRaises(OSError):collect(p/'run',p/'collected')
            self.assertFalse((p/'collected').exists())
    def test_existing_artifact_destination_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'run/evidence').mkdir(parents=True);(p/'run/evidence/summary.json').write_text('{}');(p/'victim').write_text('ORIGINAL');(p/'collected').mkdir();(p/'collected/summary.json').symlink_to(p/'victim')
            with self.assertRaises(FileExistsError):collect(p/'run',p/'collected')
            self.assertEqual((p/'victim').read_text(),'ORIGINAL')
    def test_log_symlink_never_read(self):
        from run_official import small_logs
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'export-profile/log').mkdir(parents=True);(p/'evidence').mkdir();(p/'foreign').write_text('SENSITIVE');(p/'export-profile/log/idea.log').symlink_to(p/'foreign')
            with self.assertRaises(OSError):small_logs(p,p/'evidence')
            self.assertFalse((p/'evidence/export-idea.log').exists())
    def test_dangling_target_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'student').symlink_to(p/'missing')
            with self.assertRaises(GateError):fresh_target(p/'student',p,[])
    def test_target_symlink_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'real').mkdir();(p/'link').symlink_to(p/'real',target_is_directory=True)
            with self.assertRaises(OSError):fresh_target(p/'link/student',p,[])
    def test_generator_and_cli_share_minimal_child_env(self):
        from run_official import sanitized_environment
        with patch.dict(os.environ,{'GH_TOKEN':'a','GITHUB_TOKEN':'b','ACTIONS_RUNTIME_TOKEN':'c','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'d','JAVA_TOOL_OPTIONS':'e','AWS_ACCESS_KEY_ID':'f'}):
            env=sanitized_environment()
        for key in ('GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','ACTIONS_ID_TOKEN_REQUEST_TOKEN','JAVA_TOOL_OPTIONS','AWS_ACCESS_KEY_ID'):self.assertNotIn(key,env)
        source=Path(__file__).resolve().parents[1]/'run_official.py';self.assertIn('subprocess.run(command,cwd=repo,env=sanitized_environment()',source.read_text())
    def test_complete_authorization_and_url_credentials_redacted(self):
        from collect_evidence import sanitize_text,sanitize_value
        original='Authorization: Bearer credential_one\nProxy-Authorization: Basic credential_two\nhttps://user:credential_three@example.com/path?token=credential_four'
        result=sanitize_text(original)
        for value in ('credential_one','credential_two','credential_three','credential_four'):self.assertNotIn(value,result)
        nested=sanitize_value({'error':'Authorization: Bearer abc','details':{'diff':['https://u:p@host']}})
        self.assertNotIn('abc',str(nested));self.assertNotIn('u:p',str(nested))
    def test_source_report_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'foreign').mkdir();(p/'foreign/report.json').write_text('{}');(p/'link').symlink_to(p/'foreign',target_is_directory=True)
            with self.assertRaises(OSError):read_json(p/'link/report.json')



class ReleaseBoundaryTests(unittest.TestCase):
    def test_native_positive_pass_cannot_claim_unified_environment(self):
        from release_gate import evaluate
        result=evaluate({'status':'PASS','native_archive_verified':True})
        self.assertEqual(result['status'],'BLOCKED');self.assertFalse(result['archive_upload_allowed']);self.assertEqual(result['unified_environment_runtime'],'NOT_RUN')
    def test_partial_native_never_release(self):
        from release_gate import evaluate
        with self.assertRaises(GateError):evaluate({'status':'SMOKE_PASS_NOT_RELEASE'})
    def test_job_has_explicit_evidence_margin(self):
        w=WorkflowTests().workflow();steps=w['jobs']['package']['steps'];full=0;smoke=0
        first=next(i for i,step in enumerate(steps) if step.get('id')=='official')
        last=next(i for i,step in enumerate(steps) if step.get('run')=='python scripts/academy/ui_session.py finish --root "$UI_RUN"')
        group=steps[first:last+1]
        self.assertEqual(len(group),9)
        self.assertIn('ui_session.py launch --root "$UI_RUN"',group[0]['run'])
        self.assertEqual(sum('ui_control.py' in x.get('run','') for x in group),3)
        self.assertEqual(sum(x.get('uses')=='actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02' for x in group),4)
        for step in group[1:]:self.assertIn("inputs.phase == 'full-validation'",step['if'])
        # 三阶段共享同一已启动进程的kernel-start绝对截止，不按每个等待步骤重新发放60分钟。
        source=(Path(__file__).resolve().parents[1]/'ui_session.py').read_text()
        control=(Path(__file__).resolve().parents[1]/'ui_control.py').read_text()
        self.assertEqual(source.count("put(root/'state.json',budget_record(owner,3600))"),1)
        self.assertIn("deadline=read_outer_deadline(root)",source)
        self.assertIn("int(owner['start_time'])/os.sysconf('SC_CLK_TCK')+seconds",control)
        self.assertIn("if record['monotonic_deadline']!=deadline",control)
        self.assertIn("record=budget_record(ide_meta,UI_BUDGET_SECONDS)",source)
        self.assertIn("ui_session.py cleanup --root",steps[last+2]['run'])
        for index,step in enumerate(steps):
            if index==first:full+=60;smoke+=8;continue
            if first<index<=last:continue
            full+=int(step['timeout-minutes'])
            if step.get('id')=='handoff' or step.get('name','').startswith('传递验收'):continue
            smoke+=int(step['timeout-minutes'])
        self.assertLessEqual(full,83);self.assertLessEqual(smoke,29)
    def test_final_upload_requires_release_gate(self):
        upload=WorkflowTests().workflow()['jobs']['environment']['steps'][-1]
        self.assertIn("steps.release_gate.outcome == 'success'",upload['if'])

if __name__=='__main__':unittest.main()
