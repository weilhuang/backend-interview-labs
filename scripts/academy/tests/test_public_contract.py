"""Synthetic 100-task contract regressions; these do not execute Academy or Java."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gates import (GateError, canonical_manifest, sha, validate_report,
                   verify_public_build, expected_task_count)
from native_handoff import check_native
from test_gates import contract as legacy_contract, fixture as legacy_report
from test_environment_acceptance import native_fixture


def hundred():
    contract = legacy_contract(); report = legacy_report()
    rows = report['children'][0]['children'][0]['children'][0]['children']
    for i in range(84, 100):
        task = copy.deepcopy(contract['tasks'][0])
        task['path'] = f'section/lesson/task-{i}'
        task['suite'][-1] = f'练习 {i}'
        contract['tasks'].append(task)
        node = copy.deepcopy(rows[0]); node['name'] = task['suite'][-1]; rows.append(node)
    contract['counts'].update(tasks=100, placeholders=100)
    return contract, report


def source_stage(contract, digest='c'*64):
    return {'status':'PASS','counts':contract['counts'],'sha256':digest,
            'tasks':[{'path':t['path'],'expected_link_urls':t['expected_link_urls']} for t in contract['tasks']]}


class NativeContractCountsTests(unittest.TestCase):
    def test_exact_hundred_native_cases_and_links(self):
        contract, report = hundred(); value = validate_report(report, contract)
        self.assertEqual(value['status'], 'PASS')
        self.assertEqual(value['native_tests']['expected'], 100)
        self.assertEqual(value['native_tests']['observed'], 100)
        self.assertEqual(value['description_links']['observed_tasks'], 100)
        native = native_fixture(); native['stages']['source_contract'] = source_stage(contract)
        native['stages']['native_validation'] = value
        check_native(native, contract, 'c'*64)

    def test_old_eighty_four_cannot_pass_hundred(self):
        contract, _ = hundred()
        result = validate_report(legacy_report(), contract)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(len(result['native_tests']['missing']), 16)
        native = native_fixture(); native['stages']['source_contract'] = source_stage(contract)
        with self.assertRaises(GateError): check_native(native, contract, 'c'*64)

    def test_declared_count_missing_bool_or_wrong_fails(self):
        for count in (None, True, 0, 84, 101):
            contract, report = hundred(); contract['counts']['tasks'] = count
            with self.subTest(count=count), self.assertRaises(GateError): validate_report(report, contract)

    def test_duplicate_expected_task_path_fails(self):
        contract, _ = hundred(); contract['tasks'][-1]['path'] = contract['tasks'][0]['path']
        with self.assertRaises(GateError): expected_task_count(contract)

    def test_duplicate_link_cannot_fill_missing_link(self):
        contract, report = hundred(); rows = report['children'][0]['children'][0]['children'][0]['children']
        links = rows[0]['children'][1]['children']; links.append(copy.deepcopy(links[0]))
        with self.assertRaises(GateError): validate_report(report, contract)

    def test_unexpected_success_link_fails(self):
        contract, report = hundred(); rows = report['children'][0]['children'][0]['children'][0]['children']
        rows[0]['children'][1]['children'].append({'type':'case','name':'https://unreviewed.invalid/','result':{'type':'success'}})
        result=validate_report(report, contract)
        self.assertEqual(result['status'], 'FAIL'); self.assertTrue(result['description_links']['unexpected'])

    def native(self):
        contract, report = hundred(); native=native_fixture()
        native['stages']['source_contract']=source_stage(contract)
        native['stages']['native_validation']=validate_report(report,contract)
        return contract,native

    def test_handoff_duplicate_or_wrong_task_case_fails(self):
        for field in ('native_tests', 'description_links'):
            contract,native=self.native();cases=native['stages']['native_validation'][field]['cases']
            cases[-1]=copy.deepcopy(cases[0])
            with self.subTest(field=field),self.assertRaises(GateError): check_native(native,contract,'c'*64)

    def test_handoff_ignored_failure_or_missing_link_case_fails(self):
        for field in ('native_tests', 'description_links'):
            for result in ('ignored', 'failed'):
                contract,native=self.native();native['stages']['native_validation'][field]['cases'][0]['result']=result
                with self.subTest(field=field,result=result),self.assertRaises(GateError): check_native(native,contract,'c'*64)

    def test_handoff_wrong_source_bytes_or_inventory_fails(self):
        contract,native=self.native()
        with self.assertRaises(GateError):check_native(native,contract,'d'*64)
        native['stages']['source_contract']['tasks'][0]['expected_link_urls']=['https://different.invalid/']
        with self.assertRaises(GateError):check_native(native,contract,'c'*64)

    def test_hundred_native_and_v1_environment_pass_still_blocks_final_release(self):
        from test_environment_acceptance import evidence_fixture
        from release_gate import evaluate,prepare_release
        contract,report=hundred();environment,native,identity=evidence_fixture()
        native['stages']['source_contract']=source_stage(contract)
        native['stages']['native_validation']=validate_report(report,contract)
        native['native_ui_check_reset']='NOT_RUN'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'handoff').mkdir();archive=root/'handoff/synthetic.zip';archive.write_bytes(b'SYNTHETIC NOT A COURSE ARCHIVE')
            digest=sha(archive.read_bytes());native['stages']['archive'].update(archive_sha256=digest,bytes=archive.stat().st_size)
            environment['archive_sha256']=digest;identity['archive_sha256']=digest
            result=evaluate(native,environment,identity,archive)
            self.assertEqual(result['status'],'BLOCKED');self.assertFalse(result['archive_upload_allowed'])
            with self.assertRaises(GateError):prepare_release(native,environment,identity,archive,root/'release')
            self.assertFalse((root/'release').exists())

    def test_runner_uses_only_reproducible_builder(self):
        source=(Path(__file__).resolve().parents[1]/'run_official.py').read_text()
        self.assertIn("repo/'scripts/build_unified_course.py'",source)
        self.assertNotIn("repo/'scripts/unify_course.py'",source)
        self.assertNotIn("repo/'scripts/validate_unified_course.py'",source)
        self.assertIn('build_contract(author,generation)',source)


class SealedGenerationTests(unittest.TestCase):
    def prepare(self,root):
        (root/'authoring').mkdir()
        (root/'authoring/course-map.json').write_text('{"tasks": []}\n')
        (root/'course-info.yaml').write_text('title: synthetic-only\n')
        files={p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
        counts={'courses':1,'sections':15,'tasks':100,'placeholders':159}
        public={'schema_version':1,'counts':counts,'course_map_sha256':files['authoring/course-map.json'],
                'source_manifest_sha256':sha(canonical_manifest(files))}
        path=root/'authoring/public-build-contract.json';path.write_text(json.dumps(public))
        files['authoring/public-build-contract.json']=sha(path.read_bytes())
        report={'status':'PASS','kind':'static-only',**counts,'counts':counts,
                'source_manifest_sha256':public['source_manifest_sha256'],
                'course_map_sha256':public['course_map_sha256'],
                'public_contract_sha256':files['authoring/public-build-contract.json'],
                'full_manifest_sha256':sha(canonical_manifest(files))}
        return report

    def test_rehash_seal_before_export(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);report=self.prepare(root)
            self.assertEqual(verify_public_build(root,report),report['counts'])

    def test_missing_or_modified_source_map_contract_fails(self):
        for name in ('course-info.yaml','authoring/course-map.json','authoring/public-build-contract.json'):
            for action in ('mutate','remove'):
                with self.subTest(name=name,action=action),tempfile.TemporaryDirectory() as d:
                    root=Path(d);report=self.prepare(root);path=root/name
                    if action=='mutate':path.write_bytes(path.read_bytes()+b'\n')
                    else:path.unlink()
                    with self.assertRaises((GateError,FileNotFoundError)):verify_public_build(root,report)

    def test_false_static_status_and_count_drift_fail(self):
        for field,value in [('status','FAIL'),('kind','runtime'),('tasks',84),('counts',{'tasks':100}),('full_manifest_sha256','0'*64),('public_contract_sha256','0'*64)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                root=Path(d);report=self.prepare(root);report[field]=value
                with self.assertRaises(GateError):verify_public_build(root,report)

    def test_added_file_and_symlink_rejected(self):
        for symlink in (False,True):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);report=self.prepare(root)
                if symlink:(root/'extra').symlink_to(root/'course-info.yaml')
                else:(root/'extra').write_text('unreviewed')
                with self.assertRaises(GateError):verify_public_build(root,report)

if __name__=='__main__':unittest.main()
