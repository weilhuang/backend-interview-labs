import io,json,os,sys,tarfile,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collect_evidence import collect,sanitize_value
from extract_toolchain import validate_members,extract_tar,extract_zip
from safe_io import read_regular,write_new
from run_official import capture
import check_source_ci as source
import urllib.error

class DiagnosticTests(unittest.TestCase):
    def test_truncated_json_preserves_other_failure_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'run/evidence').mkdir(parents=True);(p/'run/evidence/summary.json').write_text('{"status":"FAIL"}');(p/'run/evidence/official-validation.json').write_text('{"name":')
            collect(p/'run',p/'artifact');c=json.loads((p/'artifact/collection.json').read_text())
            self.assertEqual(c['status'],'PARTIAL');self.assertTrue((p/'artifact/summary.json').exists());self.assertEqual(c['omitted'][0]['name'],'official-validation.json');self.assertIn('original_sha256',c['omitted'][0])
    def test_partial_jsonl_preserves_other_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'run/evidence').mkdir(parents=True);(p/'run/evidence/gradle-jvm.jsonl').write_text('{"java_version":"21"}\n{')
            collect(p/'run',p/'artifact');self.assertEqual(json.loads((p/'artifact/collection.json').read_text())['status'],'PARTIAL')
    def test_sensitive_json_keys_redacted(self):
        value=sanitize_value({'Authorization':'Bearer SENTINEL','password':'SENTINEL','nested':{'api_key':'SENTINEL'}})
        self.assertNotIn('SENTINEL',str(value))
    def test_read_rejects_parent_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'real').mkdir();(p/'real/report').write_text('SENSITIVE');(p/'link').symlink_to(p/'real',target_is_directory=True)
            with self.assertRaises(OSError):read_regular(p/'link/report')
    def test_exclusive_stdout_rejects_collision_before_spawn(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'victim').write_text('ORIGINAL');(p/'stdout').symlink_to(p/'victim')
            with patch('run_official.subprocess.Popen') as start:
                with self.assertRaises(FileExistsError):capture(['never-run'],{},p,p/'stdout',p/'stderr',1,p)
                start.assert_not_called()
            self.assertEqual((p/'victim').read_text(),'ORIGINAL')
    def test_exclusive_archive_destination_rejects_collision(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'archive.zip';p.write_bytes(b'old')
            with self.assertRaises(FileExistsError):write_new(p,b'new')
            self.assertEqual(p.read_bytes(),b'old')

class ExtractorTests(unittest.TestCase):
    def test_internal_legal_symlink_valid(self):
        validate_members([('root/jbr/legal/java.base/LICENSE','file',2,''),('root/jbr/legal/other/LICENSE','symlink',0,'../java.base/LICENSE')],'root',10)
    def test_symlink_escape_rejected(self):
        with self.assertRaises(ValueError):validate_members([('root/link','symlink',0,'../../foreign')],'root',10)
    def test_member_below_symlink_rejected(self):
        with self.assertRaises(ValueError):validate_members([('root/link','symlink',0,'target'),('root/link/file','file',1,'')],'root',10)
    def test_duplicate_special_and_size_rejected(self):
        for rows in ([('root/a','file',1,''),('root/a','file',1,'')],[('root/a','other',1,'')],[('root/a','file',11,'')]):
            with self.assertRaises(ValueError):validate_members(rows,'root',10)
    def test_tar_extraction_preserves_valid_internal_link(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);root='idea-IU-261.27258.48';src=p/'idea.tar.gz';dest=p/'out';dest.mkdir()
            with tarfile.open(src,'w:gz') as tar:
                f=tarfile.TarInfo(root+'/jbr/legal/java.base/LICENSE');f.size=2;tar.addfile(f,io.BytesIO(b'ok'))
                link=tarfile.TarInfo(root+'/jbr/legal/other/LICENSE');link.type=tarfile.SYMTYPE;link.linkname='../java.base/LICENSE';tar.addfile(link)
            extract_tar(src,dest);self.assertEqual((dest/'jbr/legal/other/LICENSE').read_bytes(),b'ok')
    def test_plugin_extraction_no_symlink_or_escape(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'plugin.zip';out=p/'out';out.mkdir()
            with zipfile.ZipFile(src,'w') as z:z.writestr('JetBrainsAcademy/lib/test.jar',b'data')
            extract_zip(src,out);self.assertEqual((out/'JetBrainsAcademy/lib/test.jar').read_bytes(),b'data')
    def test_source_archive_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'real.zip';out=p/'out';out.mkdir()
            with zipfile.ZipFile(src,'w') as z:z.writestr('JetBrainsAcademy/a',b'data')
            (p/'linked.zip').symlink_to(src)
            with self.assertRaises(OSError):extract_zip(p/'linked.zip',out)

class RedirectTests(unittest.TestCase):
    def test_bearer_never_follows_signed_redirect(self):
        seen=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'zipbytes'
        class Opener:
            def open(self,request,**kwargs):
                seen.append(request)
                if len(seen)==1:raise urllib.error.HTTPError(request.full_url,302,'redirect',{'Location':'https://example.blob.core.windows.net/a?sig=PRIVATE'},None)
                return Response()
        with patch.dict(os.environ,{'GH_TOKEN':'BEARER_SECRET'}),patch.object(source.urllib.request,'build_opener',lambda *a:Opener()):
            self.assertEqual(source.api('actions/artifacts/1/zip',raw=True),b'zipbytes')
        self.assertEqual(seen[0].get_header('Authorization'),'Bearer BEARER_SECRET');self.assertIsNone(seen[1].get_header('Authorization'))

if __name__=='__main__':unittest.main()
