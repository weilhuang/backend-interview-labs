"""Exact title adapter replies and bounded converter outputs; no X server or JVM."""
import copy
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import modal_window as modal


class TitleAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter=modal._X11.__new__(modal._X11)
        self.adapter.connection=1;self.adapter.deadline=20;self.adapter.x=Mock();self.adapter.sync=Mock()
        self.atoms={b'WM_NAME':10,b'_NET_WM_NAME':11,b'STRING':31,b'UTF8_STRING':40,b'COMPOUND_TEXT':41,b'CARDINAL':6}
        self.props={};self.buffers=[];self.reads=[];self.conversions=[]
        self.adapter.x.XInternAtom.side_effect=lambda _,name,only:self.atoms.get(name,0)
        self.adapter.x.XGetWindowProperty.side_effect=self.get_property
        self.adapter.x.Xutf8TextPropertyToTextList.side_effect=self.convert
        self.convert_status=0;self.convert_count=1;self.convert_value='中文'.encode();self.convert_list=True;self.convert_pointer=True
        self.clock=patch.object(modal.time,'monotonic',return_value=10);self.clock.start();self.addCleanup(self.clock.stop)

    def get_property(self,connection,window,atom,offset,length,delete,requested,actual,fmt,count,remaining,data):
        self.assertEqual((offset,length,delete,requested),(0,256,False,0))
        name=next(k for k,v in self.atoms.items() if v==atom);self.reads.append(name)
        row=self.props.get(name)
        if row is None:
            actual._obj.value=0;fmt._obj.value=0;count._obj.value=0;remaining._obj.value=0;data._obj.value=None
        else:
            encoding,format_value,raw,rest,nitems=row
            actual._obj.value=self.atoms.get(encoding,999);fmt._obj.value=format_value
            count._obj.value=len(raw) if nitems is None else nitems;remaining._obj.value=rest
            buffer=C.create_string_buffer(raw);self.buffers.append(buffer);data._obj.value=C.cast(buffer,C.c_void_p).value
        return 0

    def put(self,name,encoding,raw,fmt=8,remaining=0,count=None):
        self.props[name]=(encoding,fmt,raw,remaining,count)

    def convert(self,connection,prop,out,count):
        p=prop._obj;self.conversions.append((p.encoding,p.format,C.string_at(p.value,p.nitems)))
        count._obj.value=self.convert_count
        if self.convert_list:
            raw=C.create_string_buffer(self.convert_value);array=(C.c_void_p*1)(C.cast(raw,C.c_void_p).value if self.convert_pointer else None)
            self.buffers.extend([raw,array]);C.cast(out,C.POINTER(C.POINTER(C.c_void_p)))[0]=C.cast(array,C.POINTER(C.c_void_p))
        return self.convert_status

    def test_modern_preference_and_deliberately_ignored_legacy_mutation(self):
        self.put(b'_NET_WM_NAME',b'UTF8_STRING','课程'.encode());self.put(b'WM_NAME',b'STRING',b'legacy')
        first=self.adapter.title(56);self.put(b'WM_NAME',b'STRING',b'different legacy')
        self.assertEqual(first,self.adapter.title(56));self.assertEqual(self.reads,[b'_NET_WM_NAME']*2)
        self.assertEqual(first,modal._title_digest(b'_NET_WM_NAME',b'UTF8_STRING','课程'.encode()))

    def test_modern_empty_is_selected_not_absent(self):
        self.put(b'_NET_WM_NAME',b'UTF8_STRING',b'');self.put(b'WM_NAME',b'STRING',b'legacy')
        self.assertEqual(self.adapter.title(56),modal._title_digest(b'_NET_WM_NAME',b'UTF8_STRING',b''))
        self.assertEqual(self.reads,[b'_NET_WM_NAME'])

    def test_absent_modern_all_three_supported_legacy_encodings(self):
        for encoding,raw in [(b'STRING',b'caf\xe9\t\n'),(b'UTF8_STRING','课程'.encode()),(b'COMPOUND_TEXT',b'\x1b$(Bsynthetic')]:
            with self.subTest(encoding=encoding):
                self.put(b'WM_NAME',encoding,raw)
                self.assertEqual(self.adapter.title(56),modal._title_digest(b'WM_NAME',encoding,raw))
        self.assertEqual(self.conversions,[(41,8,b'\x1b$(Bsynthetic')]);self.adapter.x.XFreeStringList.assert_called_once()

    def test_both_absent_and_globally_absent_atom(self):
        self.assertIsNone(self.adapter.title(56))
        self.atoms.pop(b'_NET_WM_NAME');self.assertIsNone(self.adapter.title(56))

    def test_modern_wrong_type_invalid_utf8_and_controls_never_fall_back(self):
        self.put(b'WM_NAME',b'STRING',b'usable legacy')
        for encoding,raw in [(b'STRING',b'title'),(b'COMPOUND_TEXT',b'title'),(b'PRIVATE_ATOM',b'PRIVATE_TITLE'),
            (b'UTF8_STRING',b'\xff'),(b'UTF8_STRING',b'\xed\xa0\x80'),(b'UTF8_STRING',b'a\0b'),(b'UTF8_STRING',b'\x1b')]:
            self.reads=[];self.put(b'_NET_WM_NAME',encoding,raw)
            with self.subTest(encoding=encoding,raw=raw),self.assertRaises(modal.ProofError) as raised:self.adapter.title(56)
            self.assertEqual(self.reads,[b'_NET_WM_NAME']);self.assertNotIn('PRIVATE',json.dumps(modal.failure_from_exception(raised.exception)))

    def test_legacy_wrong_atom_format_truncation_and_oversize_rejected(self):
        for encoding,fmt,raw,rest,count in [(b'CARDINAL',8,b'a',0,None),(b'PRIVATE_ATOM',8,b'a',0,None),
            (b'STRING',16,b'a',0,None),(b'STRING',8,b'a',1,None),(b'STRING',8,b'a',0,1025),
            (b'UTF8_STRING',8,b'\xff',0,None),(b'STRING',8,b'a\0b',0,None)]:
            self.put(b'WM_NAME',encoding,raw,fmt,rest,count)
            with self.subTest(encoding=encoding,fmt=fmt,rest=rest,count=count),self.assertRaises(modal.ProofError):self.adapter.title(56)

    def test_string_controls_and_all_graphic_latin1_boundaries(self):
        for raw in [b'\t\n !~\xa0\xff',b'']:
            self.put(b'WM_NAME',b'STRING',raw);self.adapter.title(56)
        for number in [0,1,8,11,13,27,31,127,128,159]:
            self.put(b'WM_NAME',b'STRING',bytes([number]))
            with self.subTest(number=number),self.assertRaises(modal.ProofError):self.adapter.title(56)

    def test_property_encoding_and_original_bytes_are_framed_without_normalization(self):
        values=[modal._title_digest(n,e,r) for n,e,r in [(b'WM_NAME',b'STRING',b'title'),
            (b'WM_NAME',b'UTF8_STRING',b'title'),(b'_NET_WM_NAME',b'UTF8_STRING',b'title'),
            (b'_NET_WM_NAME',b'UTF8_STRING','é'.encode()),(b'_NET_WM_NAME',b'UTF8_STRING','e\u0301'.encode())]]
        self.assertEqual(len(set(values)),len(values))
        raw=b'title';expected=modal.TITLE_DOMAIN+struct.pack('>H',7)+b'WM_NAME'+struct.pack('>H',6)+b'STRING'+struct.pack('>I',len(raw))+raw
        self.assertEqual(values[0],hashlib.sha256(expected).hexdigest())
        self.put(b'_NET_WM_NAME',b'UTF8_STRING',b'title');self.put(b'WM_NAME',b'UTF8_STRING',b'title')
        first=self.adapter.title(56);self.props.pop(b'_NET_WM_NAME');self.assertNotEqual(first,self.adapter.title(56))

    def test_converter_exact_success_one_pointer_and_every_rejection_frees_output(self):
        self.put(b'WM_NAME',b'COMPOUND_TEXT',b'fixture')
        for field,value in [('convert_status',-1),('convert_status',-2),('convert_status',-3),('convert_status',1),
            ('convert_count',0),('convert_count',2),('convert_pointer',False),('convert_value',b'\xff'),('convert_value',b'\x1b'),('convert_value',b'\xc2\x80')]:
            old=getattr(self,field);setattr(self,field,value);self.adapter.x.XFreeStringList.reset_mock()
            with self.subTest(field=field,value=value),self.assertRaises(modal.ProofError):self.adapter.title(56)
            self.adapter.x.XFreeStringList.assert_called_once();setattr(self,field,old)

    def test_converter_null_list_no_unsafe_copy(self):
        self.put(b'WM_NAME',b'COMPOUND_TEXT',b'fixture');self.convert_list=False
        with self.assertRaises(modal.ProofError):self.adapter.title(56)
        self.adapter.x.XFreeStringList.assert_not_called()

    def test_converter_nul_scan_bound_before_copy(self):
        self.put(b'WM_NAME',b'COMPOUND_TEXT',b'fixture');self.convert_value=b'x'*4095
        self.adapter.title(56)
        self.convert_value=b'x'*4096
        with self.assertRaises(modal.ProofError) as raised:self.adapter.title(56)
        self.assertEqual(raised.exception.call_site,'TITLE_CONVERTED_LIMIT')
        self.assertEqual(raised.exception.facts,{'converted_bytes':4096})

    def test_empty_compound_is_explicit_and_does_not_call_converter(self):
        self.put(b'WM_NAME',b'COMPOUND_TEXT',b'')
        self.assertEqual(self.adapter.title(56),modal._title_digest(b'WM_NAME',b'COMPOUND_TEXT',b''))
        self.adapter.x.Xutf8TextPropertyToTextList.assert_not_called()

    def test_escape_inputs_are_not_claimed_to_have_a_complete_custom_parser(self):
        # Modeled converter replies: the input is passed unchanged. Unknown/truncated
        # escapes left as output controls are rejected even when conversion says Success.
        for raw in (b'\x1b',b'\x1b$',b'\x1bQunknown'):
            self.put(b'WM_NAME',b'COMPOUND_TEXT',raw);self.convert_value=raw
            with self.subTest(raw=raw),self.assertRaises(modal.ProofError) as raised:self.adapter.title(56)
            self.assertEqual(raised.exception.call_site,'TITLE_CONTROLS');self.assertEqual(self.conversions[-1][2],raw)

    def test_cancel_and_deadline_during_converter_free_returned_list(self):
        def cancelled(*args):self.convert(*args);raise InterruptedError('PRIVATE')
        self.adapter.x.Xutf8TextPropertyToTextList.side_effect=cancelled
        with self.assertRaises(InterruptedError):self.adapter._compound_text(b'fixture',41)
        self.adapter.x.XFreeStringList.assert_called_once()
        self.adapter.x.Xutf8TextPropertyToTextList.side_effect=self.convert;self.adapter.x.XFreeStringList.reset_mock()
        with patch.object(modal.time,'monotonic',side_effect=[10,21]),self.assertRaises(modal.ProofError):self.adapter._compound_text(b'fixture',41)
        self.adapter.x.XFreeStringList.assert_called_once()

    def test_known_numeric_atom_categories_without_raw_names_or_ids(self):
        for encoding,category in [(b'STRING',1),(b'COMPOUND_TEXT',3),(b'CARDINAL',4),(b'PRIVATE_ATOM',5)]:
            self.put(b'_NET_WM_NAME',encoding,b'PRIVATE_TITLE')
            with self.assertRaises(modal.ProofError) as raised:self.adapter.title(56)
            doc=modal.failure_from_exception(raised.exception)
            self.assertEqual(doc['facts']['actual_type'],category);self.assertEqual(doc['facts']['property_name'],2)
            self.assertNotIn('PRIVATE',json.dumps(doc))
            for key,value in [('actual_type',True),('actual_type',6),('property_name',3),('raw_atom','PRIVATE')]:
                bad=copy.deepcopy(doc);bad['facts'][key]=value
                with self.assertRaises(ValueError):modal.failure_document(bad)

class AwtArtifactBoundary(unittest.TestCase):
    def report(self):
        import awt_title_fixture as fixture
        base=Path(modal.__file__).parent
        paths={'toolchain_sha256':base/'toolchain.json','fixture_sha256':base/'awt_title_fixture.py',
            'helper_sha256':base/'probes/AwtTitleFixture.java','selector_sha256':base/'modal_window.py'}
        hashes={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in paths.items()}
        hashes.update({key:'a'*64 for key in fixture.HASH_NAMES if key not in hashes})
        return {'schema':1,'status':'PASS','kind':fixture.KIND,'cases':[
            {'case':name,'status':'REJECTED' if i==4 else 'PASS',
             'title_sha256':fixture.MODERN_HASHES[i] if i<2 else None if i==4 else 'b'*64,
             'title_encoding':'UTF8_STRING' if i<2 else None if i==4 else 'STRING' if i==2 else 'COMPOUND_TEXT'}
            for i,name in enumerate(fixture.CASE_NAMES)],'cleanup':{'jvm':'REAPED','xvfb':'REAPED'},'exit_codes':{'jvm':-15,'xvfb':0},
            'error':None,'diagnosis':None,'runtime':{'idea_version':fixture.IDEA_VERSION,'idea_build':fixture.IDEA_BUILD,
                'idea_archive_sha256':fixture.IDEA_ARCHIVE_SHA256,'java_runtime_version':fixture.RUNTIME_VERSION,'hashes':hashes},
            'run_id':'123','run_attempt':'1','tested_sha':'a'*40,'elapsed_milliseconds':100}

    def collected(self,report):
        from collect_evidence import collect
        import awt_title_fixture as fixture
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);run=root/'run';(run/'evidence').mkdir(parents=True);bootstrap=root/'bootstrap';bootstrap.mkdir()
        (run/'evidence/validate.stderr.log').write_text('safe existing log\n')
        (bootstrap/fixture.NAME).write_text(json.dumps(report))
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'a'*40}):
            collect(run,root/'out',bootstrap=bootstrap,job_status='failure')
        return root/'out'

    def test_exact_typed_fixture_and_current_source_hashes_collect(self):
        import awt_title_fixture as fixture
        out=self.collected(self.report());self.assertTrue((out/fixture.NAME).exists())
        self.assertEqual(json.loads((out/fixture.NAME).read_text())['status'],'PASS')

    def test_stale_source_run_or_helper_hash_is_omitted(self):
        import awt_title_fixture as fixture
        for change in ('run_attempt','tested_sha','helper_sha256'):
            report=self.report()
            if change=='helper_sha256':report['runtime']['hashes'][change]='c'*64
            else:report[change]='2' if change=='run_attempt' else 'c'*40
            out=self.collected(report);self.assertFalse((out/fixture.NAME).exists())
            self.assertTrue((out/'validate.stderr.log').exists())

    def test_malformed_private_fixture_payload_never_enters_artifact(self):
        import awt_title_fixture as fixture
        for change in ({'diagnosis':{'title':'PRIVATE_TITLE'}},{'runtime':{'environment':'PRIVATE_ENV'}},
            {'elapsed_milliseconds':True},{'extra':'PRIVATE_COMMAND'},{'cases':['PRIVATE'*3000]}):
            out=self.collected({**self.report(),**change});self.assertFalse((out/fixture.NAME).exists())
            for path in out.iterdir():self.assertNotIn(b'PRIVATE',path.read_bytes())

    def test_failure_without_runtime_is_retained_without_inventing_identity(self):
        import awt_title_fixture as fixture
        report=self.report();report.update(status='FAIL',cases=[],runtime=None,error='PRECHECK_UNAVAILABLE',cleanup={'jvm':'NOT_STARTED','xvfb':'NOT_STARTED'},exit_codes={'jvm':None,'xvfb':None})
        out=self.collected(report);value=json.loads((out/fixture.NAME).read_text())
        self.assertIsNone(value['runtime']);self.assertEqual(value['status'],'FAIL')

    def test_genuine_fixture_uses_existing_install_budget_before_official_ide(self):
        import yaml
        root=Path(modal.__file__).parents[2];job=yaml.safe_load((root/'.github/workflows/academy-official.yml').read_text())['jobs']['package']
        steps=job['steps'];install=next(i for i,s in enumerate(steps) if 'install_toolchain.sh "$TOOLCHAIN_DIR"' in s.get('run',''))
        step=steps[install];self.assertEqual(step['timeout-minutes'],7)
        self.assertIn('awt_title_fixture.py --toolchain-root "$TOOLCHAIN_DIR"',step['run'])
        self.assertLess(step['run'].index('install_toolchain.sh'),step['run'].index('awt_title_fixture.py'))
        self.assertLess(install,next(i for i,s in enumerate(steps) if s.get('id')=='official'))
        self.assertIn("inputs.phase == 'full-validation'",step['run']);self.assertIn("refs/heads/academy-validation/full",step['run'])
        self.assertNotIn('continue-on-error',step);self.assertNotIn('sudo',step['run'])

if __name__=='__main__':unittest.main()
