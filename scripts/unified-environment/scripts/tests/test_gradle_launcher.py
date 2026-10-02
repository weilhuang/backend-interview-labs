"""固定发行启动器的离线模拟测试；不运行Java，不下载软件。"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('gradle_launcher', SCRIPTS/'gradle_launcher.py')
launcher=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Gradle 可信缓存 测试-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.course=self.base/'course';self.course.mkdir()
        self.cache=self.base/'cache';self.zip=self.base/'gradle.zip'
        with zipfile.ZipFile(self.zip, 'w') as archive:
            archive.writestr('gradle-8.10.2/bin/gradle', '#!/bin/sh\n# fixture never executed\n')
            archive.writestr('gradle-8.10.2/lib/fixture.jar', b'fixture, not a real jar')
        self.spec={'version':'8.10.2','url':launcher.OFFICIAL_URL,'sha256':hashlib.sha256(self.zip.read_bytes()).hexdigest()}
        self.patchroot=patch.object(launcher,'ROOT',self.course);self.patchroot.start();self.addCleanup(self.patchroot.stop)
        self.patchenv=patch.dict(os.environ, {'LAB_GRADLE_CACHE':str(self.cache), 'LAB_GRADLE_BIN':''});self.patchenv.start();self.addCleanup(self.patchenv.stop)
        (self.course/'gradle/wrapper').mkdir(parents=True)
        (self.course/'gradle/wrapper/gradle-wrapper.properties').write_text('distributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\ndistributionSha256Sum='+self.spec['sha256']+'\n')

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()): return launcher.prepare(self.spec, str(self.zip))

    def test_fixed_properties_are_only_distribution_source(self):
        self.assertEqual(launcher.distribution(), self.spec)
        p=self.course/'gradle/wrapper/gradle-wrapper.properties'
        p.write_text(p.read_text().replace('gradle-8.10.2-bin.zip','gradle-latest-bin.zip'))
        with self.assertRaises(launcher.LauncherError):launcher.distribution()

    def test_offline_prepare_and_full_integrity_verification(self):
        with patch.object(launcher,'download_archive',side_effect=AssertionError('不应联网')), patch.object(launcher.subprocess,'run',side_effect=AssertionError('不应Java')):
            self.assertEqual(self.prepare(),0)
            binary=launcher.verify_managed(self.cache,self.spec)
        self.assertTrue(binary.is_file());self.assertTrue(os.access(binary,os.X_OK))
        self.assertFalse((self.course/'gradlew').exists())

    def test_normal_run_never_downloads_missing_runtime(self):
        with patch.object(launcher,'download_archive') as download, patch.object(launcher.subprocess,'run') as run:
            with self.assertRaises(launcher.LauncherError):launcher.main(['tasks'])
            download.assert_not_called();run.assert_not_called()

    def test_cached_run_passes_original_args_and_exit_code(self):
        self.prepare()
        with patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],7)) as run:
            self.assertEqual(launcher.main(['--no-daemon',':lesson:test']),7)
        self.assertEqual(run.call_args.args[0][1:],['--no-daemon',':lesson:test'])
        self.assertEqual(run.call_args.kwargs['cwd'],self.course)

    def test_cache_must_be_outside_course(self):
        for value in (str(self.course/'build/gradle'),'relative/cache'):
            with patch.dict(os.environ,{'LAB_GRADLE_CACHE':value}), self.assertRaises(launcher.LauncherError):launcher.cache_root()

    def test_wrong_archive_sha_never_publishes(self):
        spec=dict(self.spec);spec['sha256']='0'*64
        with self.assertRaises(launcher.LauncherError):launcher.prepare(spec,str(self.zip))
        self.assertFalse(launcher.receipt_path(self.cache,spec).exists())
        self.assertFalse(list(self.cache.glob('*payload*')))

    def unsafe(self,name,mode=None):
        path=self.base/'unsafe.zip'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('gradle-8.10.2/bin/gradle','fixture')
            info=zipfile.ZipInfo(name)
            if mode is not None:info.create_system=3;info.external_attr=mode<<16
            archive.writestr(info,'payload')
        spec=dict(self.spec);spec['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(launcher.LauncherError):launcher.prepare(spec,str(path))
        self.assertFalse(launcher.receipt_path(self.cache,spec).exists())

    def test_zip_traversal_absolute_and_backslash_paths_rejected(self):
        for name in ('../escape','/absolute','gradle-8.10.2/../escape','C:/escape','gradle-8.10.2\\escape','gradle-8.10.2//escape'):
            self.unsafe(name)
        self.assertFalse((self.base/'escape').exists())

    def test_zip_symlink_and_special_file_rejected(self):
        self.unsafe('gradle-8.10.2/evil-link',stat.S_IFLNK|0o777)
        self.unsafe('gradle-8.10.2/evil-pipe',stat.S_IFIFO|0o600)

    def test_cache_payload_tamper_is_fatal(self):
        self.prepare();binary=launcher.verify_managed(self.cache,self.spec);binary.write_text('changed')
        with self.assertRaises(launcher.LauncherError):launcher.verify_managed(self.cache,self.spec)

    def test_cache_archive_tamper_is_fatal(self):
        self.prepare();record=json.loads(launcher.receipt_path(self.cache,self.spec).read_text())
        (self.cache/record['directory']/'distribution.zip').write_bytes(b'changed')
        with self.assertRaises(launcher.LauncherError):launcher.verify_managed(self.cache,self.spec)

    def test_cache_unregistered_file_is_fatal(self):
        self.prepare();record=json.loads(launcher.receipt_path(self.cache,self.spec).read_text())
        (self.cache/record['directory']/'gradle-8.10.2/lib/extra.jar').write_bytes(b'extra')
        with self.assertRaises(launcher.LauncherError):launcher.verify_managed(self.cache,self.spec)

    def test_existing_unknown_ready_file_is_never_overwritten(self):
        self.cache.mkdir();ready=launcher.receipt_path(self.cache,self.spec);ready.write_text('{"owner":"someone else"}')
        original=ready.read_bytes()
        with self.assertRaises(launcher.LauncherError):self.prepare()
        self.assertEqual(ready.read_bytes(),original)

    def test_existing_lock_and_unknown_directory_preserved(self):
        self.cache.mkdir();lock=self.cache/(launcher.key_for(self.spec)+'.prepare-lock');lock.mkdir();(lock/'owner').write_text('other')
        unrelated=self.cache/'existing-user-files';unrelated.mkdir();(unrelated/'keep').write_text('keep')
        with self.assertRaises(launcher.LauncherError):self.prepare()
        self.assertEqual((lock/'owner').read_text(),'other');self.assertEqual((unrelated/'keep').read_text(),'keep')

    def test_repeated_prepare_is_readonly_for_valid_cache(self):
        self.prepare();before={str(p):p.stat().st_mtime_ns for p in self.cache.rglob('*')}
        self.prepare();after={str(p):p.stat().st_mtime_ns for p in self.cache.rglob('*')}
        self.assertEqual(before,after)

    def test_atomic_publication_never_replaces_racing_destination(self):
        original_link=os.link
        def raced(source,destination):
            Path(destination).write_text('non-managed-race')
            return original_link(source,destination)
        with patch.object(launcher.os,'link',side_effect=raced),self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual(launcher.receipt_path(self.cache,self.spec).read_text(),'non-managed-race')
        self.assertFalse(list(self.cache.glob('*payload*')))

    def test_prepare_download_is_only_explicit_path(self):
        with patch.object(launcher,'download_archive',side_effect=lambda spec,path:path.write_bytes(self.zip.read_bytes())) as download:
            with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(launcher.main(['prepare','--download']),0)
        download.assert_called_once()

    def test_explicit_bin_requires_absolute_path_and_exact_version(self):
        binary=self.base/'chosen-gradle';binary.write_text('fixture');binary.chmod(0o755)
        with patch.dict(os.environ,{'LAB_GRADLE_BIN':str(binary)}),patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'Gradle 8.11\n','')):
            with self.assertRaises(launcher.LauncherError):launcher.explicit_binary()
        with patch.dict(os.environ,{'LAB_GRADLE_BIN':'gradle'}),self.assertRaises(launcher.LauncherError):launcher.explicit_binary()

    def test_explicit_bin_warns_version_is_not_origin_authentication(self):
        binary=self.base/'chosen-gradle';binary.write_text('fixture');binary.chmod(0o755)
        output=io.StringIO()
        with patch.dict(os.environ,{'LAB_GRADLE_BIN':str(binary)}),patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'Gradle 8.10.2\n','')) as run,contextlib.redirect_stderr(output):
            self.assertEqual(launcher.explicit_binary(),binary)
        self.assertIn('版本检查≠来源认证',output.getvalue());self.assertEqual(run.call_args.args[0],[str(binary),'--version'])

    def test_verify_does_not_run_java_or_network(self):
        self.prepare()
        with patch.object(launcher.subprocess,'run',side_effect=AssertionError('不能Java')),patch.object(launcher,'download_archive',side_effect=AssertionError('不能下载')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(['verify']),0)


if __name__=='__main__':unittest.main(verbosity=2)
