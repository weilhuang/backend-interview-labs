"""Synthetic bootstrap regressions: no Go, Java, network, or downloaded code runs."""
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_go as go

REPO = Path(__file__).resolve().parents[3]


def tar_fixture(path, rows=None):
    rows = rows or [('go/bin/go', b'INERT MOCK BINARY', 0o755),
                    ('go/VERSION', b'go1.27.1', 0o644)]
    with tarfile.open(path, 'w:gz') as archive:
        for name, content, mode in rows:
            member = tarfile.TarInfo(name)
            member.mode = mode
            if isinstance(content, bytes):
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            else:
                member.type, member.linkname = content
                archive.addfile(member)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.runner = self.base / 'runner'
        self.runner.mkdir()
        self.root = self.runner / 'academy-go-123-2'
        self.env_file = self.runner / 'github-env'
        self.env_file.write_bytes(b'EXISTING=preserved\n')
        self.report = self.runner / 'go-report.json'
        self.environment = {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '2',
                            'RUNNER_TEMP': str(self.runner), 'GITHUB_ENV': str(self.env_file),
                            'GITHUB_WORKSPACE': str(self.repo), 'GH_TOKEN': 'SECRET',
                            'GOPROXY': 'https://untrusted.invalid',
                            'LD_PRELOAD': '/untrusted.so', 'GOFLAGS': '-toolexec=bad'}
        self.inputs = {go.MODULE_PATHS[0]: b'module course.local/gin-pipeline\n\ngo 1.27.1\n',
                       go.MODULE_PATHS[1]: b'example.org/fixture v1.0.0 h1:fixture\n'}
        self.manifest = self.repo / 'authoring/unified-course/manifest.json'
        expected = {}
        for relative, content in self.inputs.items():
            path = self.repo / 'authoring/unified-course/overlay' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            expected[relative] = hashlib.sha256(content).hexdigest()
        self.manifest.write_text(json.dumps({'schema_version': 1, 'expected_manifest': expected, 'overlay_manifest': expected}))
        self.source_root = self.repo / 'authoring/unified-course/overlay/go-course/http/gin-pipeline/go'
        (self.source_root / 'evil.go').write_text('MUST NOT COPY OR EXECUTE')
        (self.source_root / 'go.work').write_text('MUST NOT COPY')

    def execute_mock(self, argv, cwd, environment, timeout):
        self.assertEqual(argv[0], str(self.root / 'go/bin/go'))
        self.assertEqual(cwd, self.root / 'module-inputs')
        self.assertEqual(set(p.name for p in cwd.iterdir()), {'go.mod', 'go.sum'})
        self.assertNotIn('SECRET', str(environment))
        if argv[1:] == ['version']:
            return {'stdout': (go.GO_VERSION_OUTPUT + '\n').encode(), 'stderr': b''}
        if argv[1:] == ['mod', 'download']:
            (self.root / 'module-cache' / 'synthetic-cache').write_bytes(b'mocked cache')
            return {'stdout': b'', 'stderr': b''}
        self.assertEqual(argv[1:], ['mod', 'verify'])
        return {'stdout': b'all modules verified\n', 'stderr': b''}

    def run_prepare(self, execute=None, **kwargs):
        with patch.object(go, 'download_archive', side_effect=lambda p, d: tar_fixture(p)) as download, \
                patch.object(go, 'run_checked', side_effect=execute or self.execute_mock) as run, \
                patch.object(go.platform, 'system', return_value='Linux'), \
                patch.object(go.platform, 'machine', return_value='x86_64'):
            proof = go.prepare(kwargs.get('repo', self.repo), kwargs.get('output', self.root),
                               kwargs.get('github_env', self.env_file), kwargs.get('report', self.report),
                               kwargs.get('environment', self.environment))
            return proof, download, run


class PrepareTests(Fixture):
    def test_pinned_metadata_exact(self):
        self.assertEqual(go.PINS, {'version': '1.27.1',
                                  'url': 'https://go.dev/dl/go1.27.1.linux-amd64.tar.gz',
                                  'sha256': '63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445',
                                  'size_bytes': 70553950, 'platform': 'linux/amd64'})

    def test_checked_in_module_inputs_match_sealed_manifest(self):
        data, hashes, manifest_hash = go.read_module_inputs(REPO)
        self.assertEqual(set(data), set(go.MODULE_PATHS))
        self.assertEqual(set(hashes), set(go.MODULE_PATHS))
        self.assertRegex(manifest_hash, '^[0-9a-f]{64}$')

    def test_success_only_copies_pins_and_exports_verified_runtime(self):
        original = {p: p.read_bytes() for p in self.source_root.iterdir()}
        proof, download, run = self.run_prepare()
        download.assert_called_once()
        self.assertEqual([call.args[0][1:] for call in run.call_args_list],
                         [['version'], ['mod', 'download'], ['mod', 'verify']])
        self.assertEqual([call.args[3] for call in run.call_args_list], [10, 110, 25])
        self.assertEqual(proof['status'], 'prepared')
        self.assertEqual(proof['compiler_identity'], go.GO_VERSION_OUTPUT)
        self.assertEqual(proof['version_output'], go.GO_VERSION_OUTPUT)
        self.assertEqual(proof['run_id'], '123')
        self.assertEqual(proof['run_attempt'], '2')
        self.assertEqual(proof['module_inputs'], {k: hashlib.sha256(v).hexdigest() for k, v in self.inputs.items()})
        self.assertEqual(proof['executable_sha256'], hashlib.sha256(b'INERT MOCK BINARY').hexdigest())
        self.assertEqual(json.loads(self.report.read_bytes()), proof)
        self.assertEqual((self.root / 'bootstrap.json').read_bytes(), self.report.read_bytes())
        self.assertEqual(self.env_file.read_text(), 'EXISTING=preserved\nGO_EXECUTABLE=' +
                         str(self.root / 'go/bin/go') + '\nGO_MODULE_CACHE=' + str(self.root / 'module-cache') + '\n')
        self.assertEqual({p: p.read_bytes() for p in self.source_root.iterdir()}, original)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)

    def test_prepared_outputs_pass_child_environment_boundary(self):
        from go_environment import validated_go_environment
        proof, _, _ = self.run_prepare()
        env = {**self.environment, 'GO_EXECUTABLE': proof['executable'],
               'GO_MODULE_CACHE': proof['module_cache']}
        self.assertEqual(validated_go_environment(env, required=True),
                         {'GO_EXECUTABLE': proof['executable'], 'GO_MODULE_CACHE': proof['module_cache']})

    def test_environment_allowlist_drops_secrets_and_injection(self):
        env = go.isolated_environment(self.root)
        for name in ('GH_TOKEN', 'GITHUB_TOKEN', 'LD_PRELOAD', 'PYTHONPATH', 'JAVA_TOOL_OPTIONS',
                     'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'SSH_AUTH_SOCK', 'GIT_CONFIG_COUNT'):
            self.assertNotIn(name, env)
        for name in ('GOPRIVATE', 'GONOPROXY', 'GONOSUMDB'):
            self.assertEqual(env[name], '')
        for name, value in {'GOENV': 'off', 'GOWORK': 'off', 'GOTOOLCHAIN': 'local',
                            'GOSUMDB': 'sum.golang.org', 'GOPROXY': 'https://proxy.golang.org',
                            'GOFLAGS': '-mod=readonly', 'GOVCS': '*:off', 'GOAUTH': 'off',
                            'GOTELEMETRY': 'off'}.items():
            self.assertEqual(env[name], value)
        for name in ('HOME', 'TMPDIR', 'GOPATH', 'GOCACHE', 'GOMODCACHE', 'GOROOT'):
            self.assertTrue(Path(env[name]).is_relative_to(self.root))

    def test_wrong_root_and_preexisting_root_rejected_before_network(self):
        for output in (self.runner / 'academy-go-123-1', self.runner / 'academy-go-123-2/suffix', self.repo / 'runtime'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.run_prepare(output=output)
        self.root.mkdir()
        with self.assertRaises(FileExistsError):
            self.run_prepare()

    def test_unsafe_run_identifier_or_runner_path_rejected(self):
        for name, value in [('GITHUB_RUN_ID', ''), ('GITHUB_RUN_ID', '1\nGOFLAGS=bad'),
                            ('GITHUB_RUN_ATTEMPT', '0'), ('RUNNER_TEMP', 'relative')]:
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                self.run_prepare(environment={**self.environment, name: value})
        linked = self.base / 'runner-link'
        linked.symlink_to(self.runner, target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_prepare(output=linked / self.root.name,
                             environment={**self.environment, 'RUNNER_TEMP': str(linked)})

    def test_report_outside_runner_temp_rejected(self):
        with self.assertRaisesRegex(ValueError, 'under RUNNER_TEMP'):
            self.run_prepare(report=self.base / 'report.json')

    def test_workspace_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'GITHUB_WORKSPACE'):
            self.run_prepare(environment={**self.environment, 'GITHUB_WORKSPACE': str(self.base)})

    def test_report_collision_or_repository_report_rejected(self):
        self.report.write_text('original')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_prepare()
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            self.run_prepare(report=self.repo / 'report.json')
        self.assertEqual(self.report.read_text(), 'original')

    def test_symlink_report_rejected(self):
        self.report.symlink_to(self.base / 'not-created')
        with self.assertRaises(ValueError):
            self.run_prepare()
        self.assertFalse((self.base / 'not-created').exists())

    def test_github_env_symlink_and_hardlink_rejected(self):
        other = self.runner / 'other'
        other.write_text('original')
        self.env_file.unlink()
        self.env_file.symlink_to(other)
        with self.assertRaises(OSError):
            self.run_prepare()
        self.env_file.unlink()
        os.link(other, self.env_file)
        with self.assertRaisesRegex(ValueError, 'hardlink'):
            self.run_prepare()
        self.assertEqual(other.read_text(), 'original')

    def test_manifest_missing_mismatch_and_source_symlink_rejected(self):
        path = self.source_root / 'go.mod'
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            self.run_prepare()
        path.unlink()
        path.symlink_to(self.source_root / 'go.sum')
        with self.assertRaises(OSError):
            self.run_prepare()
        self.manifest.write_text('{"schema_version":1,"expected_manifest":{}}')
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.run_prepare()

    def test_command_failure_does_not_export_or_write_success(self):
        with self.assertRaisesRegex(ValueError, 'mock failure'):
            self.run_prepare(execute=lambda *args: (_ for _ in ()).throw(ValueError('mock failure')))
        self.assertEqual(self.env_file.read_bytes(), b'EXISTING=preserved\n')
        self.assertFalse(self.report.exists())
        self.assertFalse((self.root / 'bootstrap.json').exists())

    def test_wrong_version_rejected_without_export(self):
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.run_prepare(execute=lambda *args: {'stdout': b'go version go1.99.0 linux/amd64\n', 'stderr': b''})
        self.assertEqual(self.env_file.read_bytes(), b'EXISTING=preserved\n')

    def test_changed_module_metadata_rejected(self):
        def execute(argv, cwd, env, timeout):
            output = self.execute_mock(argv, cwd, env, timeout)
            if argv[1:] == ['mod', 'download']:
                (cwd / 'go.sum').write_bytes(b'mutated')
            return output
        with self.assertRaisesRegex(ValueError, 'changed sealed module input'):
            self.run_prepare(execute=execute)
        self.assertEqual(self.env_file.read_bytes(), b'EXISTING=preserved\n')

    def test_changed_source_manifest_rejected(self):
        def execute(argv, cwd, env, timeout):
            output = self.execute_mock(argv, cwd, env, timeout)
            if argv[1:] == ['mod', 'verify']:
                self.manifest.write_bytes(self.manifest.read_bytes() + b'\n')
            return output
        with self.assertRaisesRegex(ValueError, 'changed during preparation'):
            self.run_prepare(execute=execute)
        self.assertEqual(self.env_file.read_bytes(), b'EXISTING=preserved\n')

    def test_unverified_or_empty_module_cache_rejected(self):
        for wrong in ('verify', 'empty'):
            with self.subTest(wrong=wrong):
                root = self.root
                def execute(argv, cwd, env, timeout):
                    output = self.execute_mock(argv, cwd, env, timeout)
                    if argv[1:] == ['mod', 'verify']:
                        if wrong == 'verify': output['stdout'] = b'not verified\n'
                        else: (root / 'module-cache' / 'synthetic-cache').unlink()
                    return output
                with self.assertRaises(ValueError):
                    self.run_prepare(execute=execute)
                self.assertEqual(self.env_file.read_bytes(), b'EXISTING=preserved\n')
                # Fresh run identity avoids reusing any failed preparation root.
                self.environment['GITHUB_RUN_ATTEMPT'] = '3'
                self.root = self.runner / 'academy-go-123-3'


class DownloadTests(unittest.TestCase):
    def response(self, data, length=None):
        response = io.BytesIO(data)
        response.status = 200
        response.headers = {} if length is None else {'Content-Length': length}
        return response

    def test_download_uses_only_official_pin_no_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            data = b'mocked official archive'
            opener = MagicMock()
            opener.open.return_value = self.response(data, str(len(data)))
            with patch.object(go.urllib.request, 'build_opener', return_value=opener) as build, \
                    patch.object(go, 'GO_ARCHIVE_SIZE', len(data)), \
                    patch.object(go, 'GO_ARCHIVE_SHA256', hashlib.sha256(data).hexdigest()):
                target = Path(folder) / 'archive'
                go.download_archive(target, time.monotonic() + 30)
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(build.call_args.args[0].proxies, {})
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, go.GO_ARCHIVE_URL)
            self.assertIsNone(request.get_header('Authorization'))
            self.assertLessEqual(opener.open.call_args.kwargs['timeout'], 15)

    def test_wrong_hash_short_oversize_and_content_length_rejected(self):
        for body, length, digest in ((b'bad', '3', '0' * 64),
                                     (b'aa', None, hashlib.sha256(b'aa').hexdigest()),
                                     (b'aaaa', None, hashlib.sha256(b'aaaa').hexdigest()),
                                     (b'aaa', '100', hashlib.sha256(b'aaa').hexdigest())):
            with self.subTest(body=body, length=length), tempfile.TemporaryDirectory() as folder:
                opener = MagicMock()
                opener.open.return_value = self.response(body, length)
                with patch.object(go.urllib.request, 'build_opener', return_value=opener), \
                        patch.object(go, 'GO_ARCHIVE_SIZE', 3), patch.object(go, 'GO_ARCHIVE_SHA256', digest), \
                        self.assertRaises(ValueError):
                    go.download_archive(Path(folder) / 'archive', time.monotonic() + 30)

    def test_only_exact_official_redirect_allowed(self):
        handler = go.OfficialRedirect()
        request = urllib.request.Request(go.GO_ARCHIVE_URL)
        target = 'https://dl.google.com/go/' + go.GO_ARCHIVE_NAME
        redirected = handler.redirect_request(request, None, 302, 'Found', {}, target)
        self.assertEqual(redirected.full_url, target)
        for bad in ('http://dl.google.com/go/' + go.GO_ARCHIVE_NAME,
                    target + '?token=secret', 'https://evil.invalid/go.tar.gz',
                    'https://go.dev@evil.invalid/a', 'file:///tmp/go'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, 'Found', {}, bad)
        with self.assertRaises(ValueError):
            handler.redirect_request(redirected, None, 302, 'Found', {}, target)

    def test_expired_budget_fails_without_opening_network(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(go.urllib.request, 'build_opener') as build:
            with self.assertRaises(TimeoutError):
                go.download_archive(Path(folder) / 'archive', time.monotonic() - 1)
            build.return_value.open.assert_not_called()


class ArchiveTests(unittest.TestCase):
    def extract(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'archive.tar.gz'
            destination = base / 'go'
            destination.mkdir()
            tar_fixture(source, rows)
            go.extract_go_archive(source, destination, time.monotonic() + 30)
            return {str(p.relative_to(destination)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                    for p in destination.rglob('*') if p.is_file()}

    def test_regular_archive_extracts_without_post_install_and_strips_setuid(self):
        result = self.extract([('go/bin/go', b'inert', 0o4777), ('go/post-install.sh', b'NEVER EXECUTE', 0o755)])
        self.assertEqual(result['bin/go'], (b'inert', 0o700))
        self.assertEqual(result['post-install.sh'], (b'NEVER EXECUTE', 0o700))

    def test_traversal_wrong_root_duplicate_links_specials_rejected(self):
        invalid = [
            [('go/../outside', b'x', 0o600)], [('other/bin/go', b'x', 0o700)],
            [('go/bin/go', b'x', 0o700), ('go/bin/go', b'y', 0o700)],
            [('go/bin/go', (tarfile.SYMTYPE, '/bin/true'), 0o700)],
            [('go/bin/go', (tarfile.LNKTYPE, 'go/other'), 0o700)],
            [('go/bin/go', (tarfile.FIFOTYPE, ''), 0o700)],
            [('go', b'not a directory', 0o700)],
        ]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.extract(rows)

    def test_archive_without_executable_or_executable_bit_rejected(self):
        with self.assertRaises(FileNotFoundError):
            self.extract([('go/VERSION', b'version', 0o600)])
        with self.assertRaisesRegex(ValueError, 'not executable'):
            self.extract([('go/bin/go', b'inert', 0o600)])

    def test_unpacked_bytes_bounded(self):
        with patch.object(go, 'MAX_UNPACKED_BYTES', 2), self.assertRaises(ValueError):
            self.extract([('go/bin/go', b'oversize', 0o700)])

    def test_cache_symlink_hardlink_empty_and_size_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / 'cache'
            cache.mkdir()
            deadline = time.monotonic() + 30
            with self.assertRaisesRegex(ValueError, 'empty'):
                go.cache_inventory(cache, deadline)
            (cache / 'link').symlink_to('/tmp')
            with self.assertRaises(ValueError):
                go.cache_inventory(cache, deadline)
            (cache / 'link').unlink()
            (cache / 'file').write_bytes(b'data')
            os.link(cache / 'file', cache / 'hardlink')
            with self.assertRaises(ValueError):
                go.cache_inventory(cache, deadline)
            (cache / 'hardlink').unlink()
            with patch.object(go, 'MAX_CACHE_BYTES', 1), self.assertRaises(ValueError):
                go.cache_inventory(cache, deadline)
            with patch.object(go, 'MAX_CACHE_ENTRIES', 0), self.assertRaises(ValueError):
                go.cache_inventory(cache, deadline)


class SubprocessTests(unittest.TestCase):
    def test_run_checked_uses_exact_environment_no_shell_and_bounded_pipes(self):
        process = MagicMock()
        process.wait.return_value = 0
        selector = MagicMock()
        selector.get_map.side_effect = [True, False]
        key = MagicMock()
        key.fileobj = process.stdout
        key.data = 'stdout'
        selector.select.return_value = [(key, 1)]
        with patch.object(go.subprocess, 'Popen', return_value=process) as spawn, \
                patch.object(go.selectors, 'DefaultSelector') as factory, \
                patch.object(go.os, 'read', return_value=b'go version mock\n'):
            factory.return_value.__enter__.return_value = selector
            result = go.run_checked(['/private/go', 'version'], Path('/private/module'), {'GOENV': 'off'}, 10)
        self.assertEqual(result['stdout'], b'go version mock\n')
        self.assertEqual(spawn.call_args.args, (['/private/go', 'version'],))
        self.assertEqual(spawn.call_args.kwargs['env'], {'GOENV': 'off'})
        self.assertNotIn('shell', spawn.call_args.kwargs)
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertEqual(spawn.call_args.kwargs['stdin'], go.subprocess.DEVNULL)
        self.assertLessEqual(process.wait.call_args.kwargs['timeout'], 10)

    def test_failure_kills_process_group(self):
        process = MagicMock(pid=12345)
        process.wait.return_value = 1
        selector = MagicMock()
        selector.get_map.return_value = False
        with patch.object(go.subprocess, 'Popen', return_value=process), \
                patch.object(go.selectors, 'DefaultSelector') as factory, \
                patch.object(go.os, 'killpg') as kill:
            factory.return_value.__enter__.return_value = selector
            with self.assertRaisesRegex(ValueError, 'exit 1'):
                go.run_checked(['/private/go', 'mod', 'download'], Path('/private/module'), {}, 10)
        kill.assert_called_once_with(12345, signal.SIGKILL)

    def test_output_bound_kills_process_group(self):
        process = MagicMock(pid=12345)
        selector = MagicMock()
        selector.get_map.return_value = True
        key = MagicMock()
        key.fileobj = process.stdout
        key.data = 'stderr'
        selector.select.return_value = [(key, 1)]
        with patch.object(go.subprocess, 'Popen', return_value=process), \
                patch.object(go.selectors, 'DefaultSelector') as factory, \
                patch.object(go.os, 'read', return_value=b'long'), \
                patch.object(go, 'MAX_OUTPUT_BYTES', 1), patch.object(go.os, 'killpg') as kill:
            factory.return_value.__enter__.return_value = selector
            with self.assertRaisesRegex(ValueError, 'output exceeds bound'):
                go.run_checked(['/private/go', 'mod', 'download'], Path('/private/module'), {}, 10)
        kill.assert_called_once_with(12345, signal.SIGKILL)


if __name__ == '__main__':
    unittest.main()
