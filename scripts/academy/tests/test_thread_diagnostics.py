"""Bounded current-profile stack projections; synthetic files/Python child only."""
import copy,hashlib,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import thread_diagnostics as diag
from collect_evidence import collect
from run_official import capture,small_logs
STACK=b'"AWT-EventQueue-0" priority=6\n java.lang.Thread.State: WAITING (parking)\n\tat java.base@21/java.lang.Thread.sleep(Native Method)\n\tat com.intellij.openapi.application.ApplicationImpl.runWriteAction(ApplicationImpl.java:10)\n'
class ThreadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'run'
        (self.root/'evidence').mkdir(parents=True);self.directory=self.root/'validate-profile/log/bg-wa';self.directory.mkdir(parents=True)
        values={'summary.json':{'run_id':'123','run_attempt':'1','commit':'a'*40},'source-ci.json':{'status':'PASS','sha':'a'*40,'commit_tree':'b'*40},'generation.json':{'status':'PASS','full_manifest_sha256':'c'*64},'archive.json':{'status':'PASS','archive_sha256':'d'*64}}
        for name,value in values.items():(self.root/'evidence'/name).write_text(json.dumps(value))
    def add(self,ident,mtime=1,raw=STACK):
        p=self.directory/f'thread-dump-{ident}.txt';p.write_bytes(raw);os.utime(p,ns=(mtime,mtime));return p
    def read(self):return json.loads((self.root/'evidence'/diag.NAME).read_bytes())
    def test_numeric_suffix_is_only_tiebreaker_not_time(self):
        self.add(9,1);self.add(1,9);self.add(2,9)
        diag.snapshot(self.root,'BEFORE_TERMINATION');value=self.read()
        self.assertEqual([s['source_id'] for s in value['samples']],[9,2]);self.assertEqual(value['status'],'COLLECTED')
        self.assertEqual(value['context']['archive_sha256'],'d'*64);self.assertEqual(value['context']['source_tree'],'b'*40)
    def test_only_file_hash_and_no_arbitrary_names_or_messages(self):
        raw=b'"PRIVATE_SECRET_COMMAND=/bin/secret"\npassword=SUPER_PRIVATE\nENV={PRIVATE_ENV}\n'+STACK
        self.add(7,raw=raw);diag.snapshot(self.root,'BEFORE_TERMINATION');value=self.read();text=json.dumps(value)
        self.assertNotIn('PRIVATE',text);self.assertEqual(value['samples'][0]['source_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(value['samples'][0]['selection'],'ONLY');self.assertEqual(value['samples'][0]['threads'][0]['role'],'EDT')
    def test_module_version_text_is_dropped_by_projection_and_validation(self):
        secret='ghp_SYNTHETICFIXTURE000000000000'
        raw=('"main"\n\tat '+secret+'/java.lang.Thread.run(Thread.java:1)\n').encode()
        threads,_=diag.project_stacks(raw)
        self.assertEqual(threads[0]['frames'],['java.lang.Thread.run(Thread.java:1)'])
        self.add(1);diag.snapshot(self.root,'BEFORE_TERMINATION');value=self.read()
        value['samples'][0]['threads'][0]['frames']=[secret+'/java.lang.Thread.run(Thread.java:1)']
        result=diag.validate_document(value)
        self.assertNotIn(secret,json.dumps(result));self.assertEqual(result['samples'][0]['threads'][0]['frames'],['java.lang.Thread.run(Thread.java:1)'])
    def test_credential_shaped_retained_components_are_rejected(self):
        fixtures=['ghp_SYNTHETICFIXTURE000000000000','github_pat_SYNTHETICFIXTURE0000','AKIAABCDEFGHIJKLMNOP','AIzaSYNTHETICFIXTURE000000000000','eyJfixture.payload.signature']
        self.add(1);diag.snapshot(self.root,'BEFORE_TERMINATION');original=self.read()
        for secret in fixtures:
            for frame in ['java.lang.'+secret+'.run(Thread.java:1)','java.lang.Thread.'+secret+'(Thread.java:1)','java.lang.Thread.run('+secret+'.java:1)']:
                with self.subTest(frame=frame):
                    with self.assertRaises(ValueError):diag.project_stacks(('"main"\n\tat '+frame+'\n').encode())
                    value=copy.deepcopy(original);value['samples'][0]['threads'][0]['frames']=[frame]
                    with self.assertRaises(ValueError):diag.validate_document(value)
        # The real collector must omit the malformed diagnostic, not publish it.
        value=copy.deepcopy(original);value['samples'][0]['threads'][0]['frames']=['java.lang.ghp_SYNTHETICFIXTURE000000000000.run(Thread.java:1)']
        (self.root/'evidence'/diag.NAME).write_text(json.dumps(value));output=Path(self.tmp.name)/'credential-artifact';collect(self.root,output)
        self.assertFalse((output/diag.NAME).exists());self.assertNotIn('ghp_SYNTHETIC', (output/'collection.json').read_text())
    def test_no_eligible_files_records_failure_proof(self):
        (self.directory/'config.json').write_text('PRIVATE');(self.directory/'nested').mkdir();(self.directory/'nested/thread-dump-1.txt').write_bytes(STACK)
        diag.snapshot(self.root,'BEFORE_TERMINATION');value=self.read();self.assertEqual(value['status'],'NO_ELIGIBLE_FILES');self.assertEqual(value['samples'],[])
    def test_missing_directory_is_unavailable_not_root_cause(self):
        self.directory.rmdir();diag.snapshot(self.root,'FINALIZATION');self.assertEqual(self.read()['status'],'UNAVAILABLE');self.assertIn('DIRECTORY_UNAVAILABLE',self.read()['omissions'])
    def test_filename_limits_and_no_recursive_payload(self):
        for name in ('thread-dump-00.txt','thread-dump-2147483648.txt','thread-dump-'+'9'*100+'.txt','thread-dump--1.txt','thread-dump-secret.txt'):(self.directory/name).write_bytes(STACK)
        self.add(0);diag.snapshot(self.root,'BEFORE_TERMINATION');self.assertEqual([v['source_id'] for v in self.read()['samples']],[0])
    def test_scan_bound_is_visible(self):
        for n in range(260):self.add(n)
        diag.snapshot(self.root,'BEFORE_TERMINATION');value=self.read();self.assertEqual(value['scan']['examined'],256);self.assertTrue(value['scan']['truncated']);self.assertIn('SCAN_LIMIT',value['omissions'])
    def test_scan_time_bound_is_visible(self):
        self.add(1)
        with patch.object(diag.time,'monotonic',side_effect=[0,2]):diag.snapshot(self.root,'BEFORE_TERMINATION')
        self.assertIn('SCAN_DEADLINE',self.read()['omissions']);self.assertFalse(self.read()['samples'])
    def test_leaf_symlink_rejected(self):
        p=self.root/'private.txt';p.write_bytes(STACK+b'PRIVATE');(self.directory/'thread-dump-1.txt').symlink_to(p)
        diag.snapshot(self.root,'BEFORE_TERMINATION');self.assertEqual(self.read()['status'],'UNAVAILABLE');self.assertIn('UNSAFE_FILE',self.read()['omissions'])
    def test_hardlinked_dump_is_not_an_owned_input(self):
        outside=self.root/'outside.txt';outside.write_bytes(STACK);os.link(outside,self.directory/'thread-dump-1.txt')
        diag.snapshot(self.root,'BEFORE_TERMINATION');self.assertIn('UNSAFE_FILE',self.read()['omissions']);self.assertEqual(self.read()['samples'],[])
    def test_negative_timestamp_retains_metadata_failure(self):
        self.add(1,-1);diag.snapshot(self.root,'BEFORE_TERMINATION');self.assertIn('SOURCE_METADATA_INVALID',self.read()['omissions']);self.assertEqual(self.read()['samples'],[])
    def test_no_context_never_claims_complete_binding(self):
        self.add(1);(self.root/'evidence/archive.json').unlink();diag.snapshot(self.root,'BEFORE_TERMINATION');value=self.read();self.assertEqual(value['status'],'PARTIAL');self.assertEqual(value['context']['status'],'UNAVAILABLE');self.assertIn('CONTEXT_UNAVAILABLE',value['omissions'])
    def test_parent_symlink_rejected(self):
        self.directory.rmdir();foreign=self.root/'foreign';foreign.mkdir();(foreign/'thread-dump-1.txt').write_bytes(STACK);self.directory.symlink_to(foreign,target_is_directory=True)
        diag.snapshot(self.root,'BEFORE_TERMINATION');self.assertIn('DIRECTORY_UNAVAILABLE',self.read()['omissions']);self.assertFalse(self.read()['samples'])
    def test_oversize_and_malformed_content_keep_bounded_failure(self):
        self.add(1,raw=b'x'*(diag.MAX_SOURCE+1));self.add(2,raw=b'\xff');self.add(3,raw=b'PRIVATE no stack frames')
        diag.snapshot(self.root,'BEFORE_TERMINATION');value=self.read();self.assertIn('SOURCE_SIZE_LIMIT',value['omissions']);self.assertIn('MALFORMED_UTF8',value['omissions']);self.assertIn('NO_STACK_FRAMES',value['omissions'])
    def test_duplicate_ids_reject_selection_and_preserve_failure_record(self):
        self.add(1)
        original=diag.os.scandir
        class Repeated:
            def __enter__(inner):
                with original(self.directory) as entries:entry=next(entries)
                return iter([entry,entry])
            def __exit__(inner,*args):return False
        with patch.object(diag.os,'scandir',return_value=Repeated()):diag.snapshot(self.root,'BEFORE_TERMINATION')
        value=self.read();self.assertIn('DUPLICATE_SOURCE_ID',value['omissions']);self.assertEqual(value['samples'],[])

    def test_thread_and_frame_limits(self):
        raw=b''.join(b'"main"\n'+b'\tat java.lang.Thread.run(Thread.java:1)\n'*60 for _ in range(70))
        threads,truncated=diag.project_stacks(raw);self.assertTrue(truncated);self.assertLessEqual(len(threads),64);self.assertTrue(all(len(t['frames'])<=48 for t in threads))
    def test_duplicate_nonfinite_and_type_confusion_rejected(self):
        for raw in (b'{"schema_version":1,"schema_version":1}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):diag.strict_json(raw)
        self.add(1);diag.snapshot(self.root,'BEFORE_TERMINATION');original=self.read()
        mutations=[('schema_version',True),('status',{'command':['PRIVATE']}),('at_utc',{}),('samples',{}),('omissions',[{}])]
        for name,value in mutations:
            v=copy.deepcopy(original);v[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):diag.validate_document(v)
        for path,bad in [(('context','run_id'),{'env':'PRIVATE'}),(('scan','examined'),False),(('scan','truncated'),0)]:
            v=copy.deepcopy(original);v[path[0]][path[1]]=bad
            with self.assertRaises(ValueError):diag.validate_document(v)
        for name,bad in [('source_id',True),('source_bytes','5'),('source_sha256',{}),('threads',[{'role':'EDT','state':'RUNNABLE','frames':[{'command':'PRIVATE'}]}])]:
            v=copy.deepcopy(original);v['samples'][0][name]=bad
            with self.assertRaises(ValueError):diag.validate_document(v)
    def test_unknown_nested_fields_are_dropped(self):
        self.add(1);diag.snapshot(self.root,'BEFORE_TERMINATION');v=self.read();v['private']={'command':'PRIVATE'};v['samples'][0]['private']={'environment':'PRIVATE'}
        self.assertNotIn('PRIVATE',json.dumps(diag.validate_document(v)))
    def test_collector_rejects_invalid_projection_keeps_other_logs(self):
        (self.root/'evidence'/diag.NAME).write_text('{"schema_version":true,"private":{"command":"PRIVATE"}}')
        (self.root/'evidence/validate.stderr.log').write_text('SAFE')
        output=Path(self.tmp.name)/'artifact';collect(self.root,output)
        self.assertFalse((output/diag.NAME).exists());self.assertIn('SAFE',(output/'validate.stderr.log').read_text());self.assertIn(diag.NAME,(output/'collection.json').read_text())
    def test_capture_precedes_child_shutdown_and_finalization_does_not_replace(self):
        self.add(5);log=self.root/'validate-profile/log/idea.log';log.write_text('SAFE')
        child=self.root/'child.py';child.write_text('import signal,time,sys\nfrom pathlib import Path\ndef stop(*_):\n Path(sys.argv[1]).write_text("PRIVATE no frames")\n raise SystemExit(0)\nsignal.signal(signal.SIGTERM,stop)\ntime.sleep(20)\n')
        result=capture([sys.executable,str(child),str(self.directory/'thread-dump-5.txt')],os.environ.copy(),self.root,self.root/'evidence/validate.stdout.log',self.root/'evidence/validate.stderr.log',.1,self.root,phase='validate')
        self.assertTrue(result['timed_out']);self.assertEqual(result['pretermination_snapshot']['thread_diagnostics']['status'],'COLLECTED')
        before=(self.root/'evidence'/diag.NAME).read_bytes();small_logs(self.root,self.root/'evidence');self.assertEqual(before,(self.root/'evidence'/diag.NAME).read_bytes());self.assertIn(b'Thread.sleep',before)
if __name__=='__main__':unittest.main()
