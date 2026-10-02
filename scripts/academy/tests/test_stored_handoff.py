"""Ordinary synthetic producer/consumer regressions, not archive security tests."""
import copy
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gates import GateError, sha
from native_handoff import pack, unpack, MAX_CONTAINER, MAX_FILES, MAX_TOTAL
import test_environment_acceptance as legacy


class StoredHandoffTests(unittest.TestCase):
    def prepare(self, root):
        return legacy.HandoffFixture().prepare(root)

    def rewrite_normal(self, path, transform):
        # Only valid ZIP_STORED files with ordinary content/mode differences.
        with zipfile.ZipFile(path) as source:
            rows=[(copy.copy(info), source.read(info)) for info in source.infolist()]
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as target:
            for info, data in rows:
                data=transform(info, data)
                target.writestr(info, data)

    def test_normal_roundtrip_bytes_identity_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run,expected=self.prepare(root)
            for folder in ('student','validation'):
                (run/folder/'scripts/gradle.sh').chmod(0o755)
            path=root/'handoff.stored.zip';proof=pack(run,path)
            identity,native,contract,imports=unpack(path,root/'out',expected)
            self.assertEqual(identity['handoff_sha256'],proof['handoff_sha256'])
            self.assertEqual(identity['archive_sha256'],sha((run/'dist/backend-interview-academy.zip').read_bytes()))
            self.assertEqual((root/'out/backend-interview-academy.zip').read_bytes(),(run/'dist/backend-interview-academy.zip').read_bytes())
            for mode in ('student','educator'):
                self.assertEqual(imports[mode]['status'],'PASS')
                self.assertEqual(stat.S_IMODE((root/'out'/mode/'scripts/gradle.sh').stat().st_mode),0o755)
                self.assertEqual(stat.S_IMODE((root/'out'/mode/'shared/versions.env').stat().st_mode),0o644)
            with zipfile.ZipFile(path) as archive:
                self.assertTrue(all(info.compress_type==zipfile.ZIP_STORED for info in archive.infolist()))
                self.assertLessEqual(len(archive.infolist()),MAX_FILES)
                self.assertLessEqual(sum(info.file_size for info in archive.infolist()),MAX_TOTAL)
                self.assertLessEqual(path.stat().st_size,MAX_CONTAINER)

    def test_normal_identity_mismatch_rejected(self):
        for key in ('repository','commit','run_id','run_attempt'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);run,expected=self.prepare(root);path=root/'handoff.stored.zip';pack(run,path)
                expected[key]='different'
                with self.assertRaises(GateError):unpack(path,root/'out',expected)
                self.assertFalse((root/'out').exists())

    def test_accidental_member_content_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run,expected=self.prepare(root);path=root/'handoff.stored.zip';pack(run,path)
            self.rewrite_normal(path,lambda info,data:data+b'ordinary edit' if info.filename=='student/shared/versions.env' else data)
            with self.assertRaises(GateError):unpack(path,root/'out',expected)
            self.assertFalse((root/'out').exists())

    def test_lost_execute_mode_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run,expected=self.prepare(root)
            (run/'validation/scripts/gradle.sh').chmod(0o755)
            path=root/'handoff.stored.zip';pack(run,path)
            def lose_mode(info,data):
                if info.filename=='educator/scripts/gradle.sh':info.external_attr=(stat.S_IFREG|0o644)<<16
                return data
            self.rewrite_normal(path,lose_mode)
            with self.assertRaises(GateError):unpack(path,root/'out',expected)
            self.assertFalse((root/'out').exists())

    def test_changed_import_plaintext_rejected_before_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run,expected=self.prepare(root)
            (run/'validation/section/lesson/task/src/F.java').write_bytes(b'accidental edit')
            with self.assertRaises(GateError):pack(run,root/'handoff.stored.zip')
            self.assertFalse((root/'handoff.stored.zip').exists())

    def test_existing_owned_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run,expected=self.prepare(root);path=root/'handoff.stored.zip';pack(run,path)
            output=root/'out';output.mkdir();(output/'keep.txt').write_text('keep')
            with self.assertRaises(FileExistsError):unpack(path,output,expected)
            self.assertEqual((output/'keep.txt').read_text(),'keep')

if __name__=='__main__':unittest.main()
