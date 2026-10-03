"""Synthetic passive dump/privacy regressions; no JVM/IDE or process attachment."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import post_trust_stacks as stacks


FRAME = b'\tat java.base@21/java.lang.Thread.sleep(Native Method)\n'
STACK = b'"AWT-EventQueue-0" priority=6\n java.lang.Thread.State: WAITING (parking)\n' + FRAME
RECORD = STACK + b'\n'


class PassiveStacksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'run'
        self.directory = self.root / 'validate-profile/log/bg-wa'
        self.directory.mkdir(parents=True)
        self.anchor = 100
        self.observed = 1000

    def add(self, ident, mtime=200, raw=STACK):
        path = self.directory / f'thread-dump-{ident}.txt'
        path.write_bytes(raw)
        os.utime(path, ns=(mtime, mtime))
        return path

    def scan(self, **kwargs):
        return stacks.scan(self.root, self.anchor, observed=self.observed, **kwargs)

    def capture(self, **kwargs):
        kwargs.setdefault('scan_result', self.scan())
        return stacks.capture(self.root, self.anchor, **kwargs)

    def test_boundary_and_numeric_ties_are_deterministic(self):
        for ident, mtime in [(1, 99), (2, 100), (9, 101), (4, 200), (5, 200)]:
            self.add(ident, mtime)
        result = self.capture()
        rows = {r['source_id']: r for r in result['candidates']}
        self.assertEqual([s['source_id'] for s in result['samples']], [5, 9])
        self.assertEqual(rows[1]['relation'], 'PRE_TRUST')
        self.assertEqual(rows[2]['relation'], 'AT_ANCHOR')
        self.assertEqual(rows[9]['selection'], 'FIRST_MTIME')
        self.assertEqual(rows[5]['selection'], 'LATEST')
        self.assertEqual(rows[4]['omission'], 'NOT_SELECTED')

    def test_first_observed_and_latest_are_selected_independently(self):
        self.add(1, 101)
        self.add(2, 200)
        self.add(3, 300)
        result = self.capture(first_observed_id=2)
        self.assertEqual([(s['source_id'], s['selection']) for s in result['samples']],
                         [(2, 'FIRST_OBSERVED'), (3, 'LATEST')])
        missing = self.capture(first_observed_id=8)
        self.assertEqual([s['source_id'] for s in missing['samples']], [3])
        self.assertIn('FIRST_OBSERVED_UNAVAILABLE', missing['omissions'])

    def test_single_source_has_one_body_read_and_both_selection_roles(self):
        self.add(7)
        with patch.object(stacks, '_read_source', wraps=stacks._read_source) as read:
            result = self.capture(first_observed_id=7)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(result['samples'][0]['selection'], 'FIRST_OBSERVED_AND_LATEST')
        self.assertEqual(result['samples'][0]['hash_scope'], 'WHOLE_FILE')
        self.assertEqual(result['samples'][0]['sha256'], hashlib.sha256(STACK).hexdigest())
        self.assertEqual(result['candidates'][0]['read'],
                         {'scope': 'WHOLE_FILE', 'source_bytes': len(STACK), 'bytes_read': len(STACK),
                          'sha256': hashlib.sha256(STACK).hexdigest()})

    def test_scan_reads_no_bodies_and_stability_uses_full_stat_identity(self):
        path = self.add(2)
        with patch.object(stacks, '_read_source', side_effect=AssertionError('body read')):
            first = self.scan()
            second = self.scan()
        self.assertEqual(stacks.stable_post_ids(first, second), (2,))
        path.write_bytes(STACK + b'\n')
        os.utime(path, ns=(200, 200))
        changed = self.scan()
        self.assertEqual(stacks.stable_post_ids(second, changed), ())
        self.assertEqual(stacks.stable_post_ids(None, second), ())

    def test_zero_exact_cap_and_oversized_latest_keep_distinct_outcomes(self):
        self.add(1, 101, b'')
        self.add(2, 200, RECORD + b'x' * (stacks.MAX_SOURCE - len(RECORD)))
        self.add(3, 300, RECORD + b'x' * stacks.MAX_SOURCE)
        with patch.object(stacks, '_read_source', wraps=stacks._read_source) as read:
            result = self.capture()
        self.assertLessEqual(read.call_count, 2)
        self.assertEqual([s['source_id'] for s in result['samples']], [3])
        candidate = {r['source_id']: r for r in result['candidates']}
        self.assertEqual(candidate[1]['omission'], 'SOURCE_EMPTY')
        self.assertEqual(candidate[1]['read'],
                         {'scope': 'EMPTY', 'source_bytes': 0, 'bytes_read': 0,
                          'sha256': hashlib.sha256(b'').hexdigest()})
        self.assertEqual(candidate[2]['selection'], 'NONE')
        self.assertIsNone(candidate[2]['read'])
        latest = result['samples'][0]
        self.assertEqual(latest['source_bytes'], stacks.MAX_SOURCE + len(RECORD))
        self.assertEqual(latest['bytes_read'], stacks.MAX_SOURCE)
        self.assertEqual(latest['hash_scope'], 'PREFIX')
        raw = (self.directory / 'thread-dump-3.txt').read_bytes()[:stacks.MAX_SOURCE]
        self.assertEqual(latest['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(candidate[3]['omission'], 'PREFIX_ONLY')
        result = self.capture(first_observed_id=2)
        exact = next(s for s in result['samples'] if s['source_id'] == 2)
        self.assertEqual(exact['hash_scope'], 'WHOLE_FILE')
        self.assertEqual(exact['bytes_read'], stacks.MAX_SOURCE)
        self.assertEqual(sum(s['bytes_read'] for s in result['samples']), stacks.MAX_TOTAL_READ)

    def test_oversized_latest_without_complete_record_is_not_replaced(self):
        self.add(1, 200)
        self.add(2, 300, b'"main"\n' + FRAME + b'x' * stacks.MAX_SOURCE)
        result = self.capture()
        self.assertEqual([s['source_id'] for s in result['samples']], [1])
        latest = next(r for r in result['candidates'] if r['source_id'] == 2)
        self.assertEqual(latest['selection'], 'LATEST')
        self.assertEqual(latest['omission'], 'NO_COMPLETE_RECORDS')
        self.assertEqual(latest['bytes'], 7 + len(FRAME) + stacks.MAX_SOURCE)
        raw = (self.directory / 'thread-dump-2.txt').read_bytes()
        self.assertEqual(latest['read'],
                         {'scope': 'PREFIX', 'source_bytes': len(raw), 'bytes_read': stacks.MAX_SOURCE,
                          'sha256': hashlib.sha256(raw[:stacks.MAX_SOURCE]).hexdigest()})

    def test_prefix_read_observation_survives_utf8_and_terminal_frame_failures(self):
        boundary = RECORD + b'x' * (stacks.MAX_SOURCE - len(RECORD) - 1) + b'\xe2\x82\xac'
        malformed = RECORD + b'x' * (stacks.MAX_SOURCE - len(RECORD) - 2) + b'\xffxx'
        unfinished_frame = b'"main"\n' + b' ' * (stacks.MAX_SOURCE - 20) + b'\tat java.lang.Thread.run(Thread.java:1)\n'
        for raw, code in ((boundary, 'PREFIX_ENCODING_BOUNDARY'), (malformed, 'MALFORMED_UTF8'),
                          (unfinished_frame, 'NO_COMPLETE_RECORDS')):
            with self.subTest(code=code):
                self.add(1, raw=raw)
                result = self.capture()
                self.assertFalse(result['samples'])
                self.assertEqual(result['status'], 'UNAVAILABLE_NOT_ACCEPTANCE')
                candidate = result['candidates'][0]
                self.assertEqual(candidate['omission'], code)
                self.assertEqual(candidate['read'],
                                 {'scope': 'PREFIX', 'source_bytes': len(raw), 'bytes_read': stacks.MAX_SOURCE,
                                  'sha256': hashlib.sha256(raw[:stacks.MAX_SOURCE]).hexdigest()})
                self.assertEqual(stacks.validate_document(stacks.strict_json(stacks.payload(result))), result)

    def test_prefix_drops_terminal_record_and_never_joins_frame_fragments(self):
        raw = RECORD + b'"main"\n\tat java.lang.Thread.run(Thread.java:1)\n'
        threads, truncated, codes = stacks.project_stacks(raw, prefix=True)
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]['role'], 'EDT')
        self.assertFalse(truncated)
        self.assertEqual(codes, [])
        for suffix in (b'\tat java.lang.Th', b'\tat java.lang.Thread.\nrun(Thread.java:1)\n', b'"cut'):
            threads, _, _ = stacks.project_stacks(RECORD + b'"main"\n' + suffix, prefix=True)
            self.assertEqual(len(threads), 1)
            self.assertEqual(threads[0]['frames'], ['java.lang.Thread.sleep(Native Method)'])

    def test_prefix_utf8_cut_is_unavailable_and_whole_eof_can_finish_record(self):
        with self.assertRaisesRegex(ValueError, 'PREFIX_ENCODING_BOUNDARY'):
            stacks.project_stacks(RECORD + b'\xe2\x82', prefix=True)
        with self.assertRaises(UnicodeError):
            stacks.project_stacks(RECORD + b'\xffx', prefix=True)
        with self.assertRaises(UnicodeError):
            stacks.project_stacks(RECORD + b'\xe2\x82', prefix=False)
        with self.assertRaisesRegex(ValueError, 'NO_COMPLETE_RECORDS'):
            stacks.project_stacks(STACK, prefix=True)
        threads, _, _ = stacks.project_stacks(STACK.rstrip(b'\n'))
        self.assertEqual(threads[0]['role'], 'EDT')

    def test_unknown_names_are_counts_and_only_canonical_basename_is_public(self):
        names = ['thread-dump-00.txt', 'thread-dump-2147483648.txt', 'thread-dump--1.txt',
                 'PRIVATE_PASSWORD.txt', 'thread-dump-' + '9' * 100 + '.txt']
        for name in names:
            (self.directory / name).write_bytes(STACK)
        self.add(2147483647)
        self.add(0, 201)
        result = self.capture()
        self.assertEqual(result['scan']['unknown'], len(names))
        self.assertTrue(result['scan']['complete'])
        self.assertEqual(len(result['samples']), 2)
        self.assertEqual([r['source_id'] for r in result['candidates']], [0, 2147483647])
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_missing_directory_and_nonrecursive_scan_have_typed_results(self):
        nested = self.directory / 'nested'
        nested.mkdir()
        (nested / 'thread-dump-1.txt').write_bytes(STACK)
        result = self.capture()
        self.assertEqual(result['scan']['unknown'], 1)
        self.assertEqual(result['status'], 'UNAVAILABLE_NOT_ACCEPTANCE')
        other = self.root / 'missing'
        result = stacks.capture(other, self.anchor)
        self.assertIn('DIRECTORY_UNAVAILABLE', result['omissions'])
        self.assertFalse(result['samples'])

    def test_leaf_symlink_hardlink_fifo_and_directory_are_unsafe(self):
        outside = self.root / 'private'
        outside.write_bytes(STACK)
        (self.directory / 'thread-dump-1.txt').symlink_to(outside)
        os.link(outside, self.directory / 'thread-dump-2.txt')
        os.mkfifo(self.directory / 'thread-dump-3.txt')
        (self.directory / 'thread-dump-4.txt').mkdir()
        result = self.capture()
        self.assertEqual(len(result['candidates']), 4)
        self.assertTrue(all(r['omission'] == 'UNSAFE_FILE' for r in result['candidates']))
        self.assertTrue(all(r['bytes'] is None and r['mtime_ns'] is None for r in result['candidates']))
        self.assertFalse(result['samples'])

    def test_unsafe_or_invalid_canonical_source_prevents_older_latest_claim(self):
        self.add(1, 101)
        for mode in ('symlink', 'hardlink', 'invalid_time'):
            with self.subTest(mode=mode):
                path = self.directory / 'thread-dump-2.txt'
                if path.exists() or path.is_symlink():
                    path.unlink()
                outside = self.root / 'outside'
                if outside.exists():
                    outside.unlink()
                if mode == 'symlink':
                    outside.write_bytes(STACK)
                    path.symlink_to(outside)
                    os.utime(path, ns=(300, 300), follow_symlinks=False)
                elif mode == 'hardlink':
                    outside.write_bytes(STACK)
                    os.utime(outside, ns=(300, 300))
                    os.link(outside, path)
                else:
                    self.add(2, -1)
                result = self.capture()
                self.assertFalse(result['scan']['complete'])
                self.assertFalse(result['samples'])
                self.assertTrue(all(r['selection'] == 'NONE' for r in result['candidates']))
                self.assertEqual(result['candidates'][0]['omission'], 'SCAN_INCOMPLETE')
                code = 'SOURCE_METADATA_INVALID' if mode == 'invalid_time' else 'UNSAFE_FILE'
                self.assertIn(code, result['omissions'])
                unsafe = result['candidates'][1]
                if mode != 'invalid_time':
                    self.assertIsNone(unsafe['mtime_ns'])
                    self.assertIsNone(unsafe['bytes'])
                replay = copy.deepcopy(result)
                replay['scan']['complete'] = True
                with self.assertRaises(ValueError):
                    stacks.validate_document(replay)

    def test_every_ancestor_and_root_symlink_is_rejected(self):
        self.add(1)
        for folder in (self.root, self.root / 'validate-profile', self.root / 'validate-profile/log', self.directory):
            with self.subTest(folder=folder):
                displaced = folder.with_name(folder.name + '-real')
                folder.rename(displaced)
                folder.symlink_to(displaced, target_is_directory=True)
                try:
                    result = self.capture()
                    self.assertFalse(result['samples'])
                    self.assertIn('DIRECTORY_UNAVAILABLE', result['omissions'])
                finally:
                    folder.unlink()
                    displaced.rename(folder)

    def test_wrong_uid_is_rejected(self):
        self.add(1)
        with patch.object(stacks.os, 'getuid', return_value=os.getuid() + 1):
            result = self.capture()
        self.assertIn('UNSAFE_FILE', result['omissions'])

    def test_clock_inconsistency_and_negative_metadata_fail_closed(self):
        self.add(1, 1001)
        self.add(2, -1)
        result = self.capture()
        self.assertIn('CLOCK_INCONSISTENT', result['omissions'])
        self.assertIn('SOURCE_METADATA_INVALID', result['omissions'])
        self.assertFalse(result['samples'])
        before_anchor = stacks.scan(self.root, self.anchor, observed=99)
        self.assertFalse(before_anchor.complete)
        result = self.capture(scan_result=before_anchor)
        self.assertEqual(result['status'], 'UNAVAILABLE_NOT_ACCEPTANCE')

    def test_scan_count_time_and_duplicate_bounds_prevent_extrema_claims(self):
        for ident in range(stacks.MAX_ENTRIES + 1):
            self.add(ident)
        result = self.capture()
        self.assertEqual(result['scan']['examined'], stacks.MAX_ENTRIES)
        self.assertIn('SCAN_LIMIT', result['omissions'])
        self.assertFalse(result['samples'])
        with patch.object(stacks.time, 'monotonic', side_effect=[0, 2, 2]):
            limited = self.scan()
        self.assertIn('SCAN_DEADLINE', limited.omissions)
        self.assertFalse(limited.candidates)
        original = stacks.os.scandir

        class Repeated:
            def __enter__(inner):
                with original(self.directory) as entries:
                    entry = next(entries)
                return iter([entry, entry])

            def __exit__(inner, *args):
                return False

        with patch.object(stacks.os, 'scandir', return_value=Repeated()):
            duplicate = self.scan()
        self.assertIn('DUPLICATE_SOURCE_ID', duplicate.omissions)
        self.assertFalse(self.capture(scan_result=duplicate)['samples'])

    def test_scan_never_advances_past_the_entry_cap(self):
        path = self.add(1)
        original = stacks.os.scandir
        with original(self.directory) as entries:
            entry = next(entries)

        class EntryLimit:
            def __enter__(inner):
                def entries():
                    for _ in range(stacks.MAX_ENTRIES):
                        yield entry
                    raise AssertionError('257th entry retrieved')
                return entries()

            def __exit__(inner, *args):
                return False

        with patch.object(stacks.os, 'scandir', return_value=EntryLimit()):
            result = self.scan()
        self.assertEqual(result.examined, stacks.MAX_ENTRIES)
        self.assertIn('SCAN_LIMIT', result.omissions)

    def test_growth_truncation_and_replacement_after_scan_are_not_retried(self):
        path = self.add(1)
        for mutation in ('grow', 'truncate', 'replace', 'link'):
            with self.subTest(mutation=mutation):
                if path.exists() or path.is_symlink():
                    path.unlink()
                path = self.add(1)
                before = self.scan()
                if mutation == 'grow':
                    path.write_bytes(STACK + b'additional')
                elif mutation == 'truncate':
                    path.write_bytes(b'')
                elif mutation == 'replace':
                    path.unlink()
                    self.add(1)
                else:
                    os.link(path, self.root / 'second-link')
                result = self.capture(scan_result=before)
                self.assertFalse(result['samples'])
                self.assertIn('SOURCE_CHANGED', result['omissions'])
                self.assertEqual(result['candidates'][0]['read'],
                                 {'scope': 'UNVERIFIED', 'source_bytes': None, 'bytes_read': None, 'sha256': None})

    def test_growth_during_read_and_replacement_at_name_are_detected(self):
        path = self.add(1)
        before = self.scan()
        real_fdopen = stacks.os.fdopen

        class MutatingRead:
            def __init__(inner, fd, *args, **kwargs):
                inner.stream = real_fdopen(fd, *args, **kwargs)

            def __enter__(inner):
                inner.stream.__enter__()
                return inner

            def read(inner, size):
                data = inner.stream.read(size)
                path.write_bytes(STACK + b'growth')
                return data

            def __exit__(inner, *args):
                return inner.stream.__exit__(*args)

        with patch.object(stacks.os, 'fdopen', MutatingRead):
            result = self.capture(scan_result=before)
        self.assertIn('SOURCE_CHANGED', result['omissions'])
        self.assertFalse(result['samples'])
        self.assertEqual(result['candidates'][0]['read']['scope'], 'UNVERIFIED')
        self.assertIsNone(result['candidates'][0]['read']['sha256'])

    def test_empty_source_that_changes_or_expires_stays_typed(self):
        path = self.add(1, raw=b'')
        before = self.scan()
        expired = self.capture(scan_result=before, deadline=0)
        self.assertIn('CAPTURE_DEADLINE', expired['omissions'])
        path.write_bytes(STACK)
        changed = self.capture(scan_result=before)
        self.assertIn('SOURCE_CHANGED', changed['omissions'])
        self.assertEqual(changed['candidates'][0]['bytes'], 0)
        self.assertFalse(changed['samples'])
        self.assertEqual(changed['candidates'][0]['read']['scope'], 'UNVERIFIED')

    def test_inode_and_ancestor_replacement_during_read_are_detected(self):
        for mode in ('inode', 'ancestor'):
            with self.subTest(mode=mode):
                path = self.add(1)
                before = self.scan()
                real_fdopen = stacks.os.fdopen

                class ReplacingRead:
                    def __init__(inner, fd, *args, **kwargs):
                        inner.stream = real_fdopen(fd, *args, **kwargs)

                    def __enter__(inner):
                        inner.stream.__enter__()
                        return inner

                    def read(inner, size):
                        data = inner.stream.read(size)
                        if mode == 'inode':
                            path.unlink()
                            self.add(1)
                        else:
                            old = self.directory.with_name('old-bg-wa')
                            self.directory.rename(old)
                            self.directory.mkdir()
                            self.add(1)
                        return data

                    def __exit__(inner, *args):
                        return inner.stream.__exit__(*args)

                with patch.object(stacks.os, 'fdopen', ReplacingRead):
                    result = self.capture(scan_result=before)
                self.assertFalse(result['samples'])
                self.assertIn('SOURCE_CHANGED', result['omissions'])

    def test_invalid_utf8_and_unsupported_whole_dump_are_typed(self):
        for raw, code in ((b'\xff', 'MALFORMED_UTF8'), (b'no dump', 'NO_COMPLETE_RECORDS'),
                          (b'"main"\n\tat untrusted.package.Class.run(Class.java:1)\n', 'NO_STACK_FRAMES')):
            with self.subTest(code=code):
                self.add(1, raw=raw)
                result = self.capture()
                self.assertFalse(result['samples'])
                self.assertIn(code, result['omissions'])

    def test_cancellation_propagates_scan_and_capture(self):
        self.add(1)
        with patch.object(stacks.os, 'stat', side_effect=InterruptedError('cancel')):
            with self.assertRaises(InterruptedError):
                self.scan()
        before = self.scan()
        with patch.object(stacks, '_read_source', side_effect=InterruptedError('cancel')):
            with self.assertRaises(InterruptedError):
                self.capture(scan_result=before)

    def test_absolute_deadline_and_scan_context_are_enforced(self):
        self.add(1)
        before = self.scan()
        result = self.capture(scan_result=before, deadline=0)
        self.assertIn('CAPTURE_DEADLINE', result['omissions'])
        self.assertFalse(result['samples'])
        with self.assertRaises(ValueError):
            stacks.capture(self.root, self.anchor + 1, scan_result=before)
        with self.assertRaises(ValueError):
            stacks.capture(self.root / '..', self.anchor, scan_result=before)

    def test_arbitrary_headers_commands_and_environment_never_escape(self):
        self.add(1, raw=b'"PRIVATE_PASSWORD=/bin/secret"\ncommand=PRIVATE\nenv={PRIVATE}\n' + FRAME)
        result = self.capture()
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(result['samples'][0]['threads'][0]['role'], 'OTHER')

    def test_credentials_in_retained_frames_are_rejected_and_modules_removed(self):
        secrets = ['ghp_SYNTHETICFIXTURE000000000000', 'github_pat_SYNTHETICFIXTURE0000',
                   'AKIAABCDEFGHIJKLMNOP', 'AIzaSYNTHETICFIXTURE000000000000',
                   'eyJfixture.payload.signature']
        for secret in secrets:
            for frame in ['java.lang.' + secret + '.run(Thread.java:1)',
                          'java.lang.Thread.' + secret + '(Thread.java:1)',
                          'java.lang.Thread.run(' + secret + '.java:1)']:
                with self.subTest(frame=frame):
                    self.add(1, raw=('"main"\n\tat ' + frame + '\n').encode())
                    result = self.capture()
                    self.assertFalse(result['samples'])
                    self.assertNotIn(secret, json.dumps(result))
        self.add(1, raw=('"main"\n\tat ' + secrets[0] + '/java.lang.Thread.run(Thread.java:1)\n').encode())
        result = self.capture()
        self.assertEqual(result['samples'][0]['threads'][0]['frames'], ['java.lang.Thread.run(Thread.java:1)'])

    def test_public_validator_rejects_unknown_nested_keys_types_and_secrets(self):
        self.add(1)
        original = self.capture()
        mutations = [(['schema_version'], True), (['status'], {'command': 'PRIVATE'}),
                     (['scan', 'complete'], 1), (['scan', 'unknown'], False),
                     (['candidates', 0, 'bytes'], '10'), (['candidates', 0, 'basename'], '/tmp/PRIVATE'),
                     (['candidates', 0, 'read'], True), (['candidates', 0, 'read', 'scope'], 'PREFIX'),
                     (['candidates', 0, 'read', 'bytes_read'], stacks.MAX_SOURCE),
                     (['candidates', 0, 'read', 'sha256'], 'b' * 64),
                     (['samples', 0, 'source_bytes'], True), (['samples', 0, 'sha256'], ['PRIVATE']),
                     (['samples', 0, 'threads', 0, 'frames'], [{'command': 'PRIVATE'}]),
                     (['samples', 0, 'threads', 0, 'frames'], ['java.lang.ghp_SYNTHETICFIXTURE.run(Thread.java:1)'])]
        for path, bad in mutations:
            value = copy.deepcopy(original)
            target = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = bad
            with self.subTest(path=path), self.assertRaises(ValueError):
                stacks.validate_document(value)
        for path in ([], ['scan'], ['candidates', 0], ['candidates', 0, 'read'], ['samples', 0], ['samples', 0, 'threads', 0]):
            value = copy.deepcopy(original)
            target = value
            for key in path:
                target = target[key]
            target['extra'] = {'environment': ['PRIVATE' * 100000]}
            with self.subTest(path=path), self.assertRaises(ValueError):
                stacks.validate_document(value)

    def test_strict_json_rejects_duplicates_floats_nonfinite_huge_and_recursive(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.0}',
                    b' ' * (stacks.MAX_OUTPUT + 1), b'[' * 5000 + b']' * 5000):
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                stacks.strict_json(raw)

    def test_projection_and_output_caps_include_metadata(self):
        long_frame = b'\tat com.intellij.' + b'Package' * 22 + b'.run(' + b'Long' * 24 + b'.java:1234567)\n'
        raw = (b'"main"\n' + long_frame * 48 + b'\n') * 65
        self.assertLessEqual(len(raw), stacks.MAX_SOURCE)
        self.add(0, 200, raw)
        self.add(254, 300, raw)
        for ident in range(1, 254):
            self.add(ident, 250)
        result = self.capture()
        self.assertEqual(len(result['samples']), 2)
        self.assertTrue(all(s['projection_truncated'] for s in result['samples']))
        self.assertTrue(all(len(stacks.payload(s)) <= stacks.MAX_SAMPLE for s in result['samples']))
        metadata = {k: v for k, v in result.items() if k != 'samples'}
        self.assertLessEqual(len(stacks.payload(metadata)), stacks.MAX_METADATA)
        self.assertLessEqual(len(stacks.payload(result)), stacks.MAX_OUTPUT)
        self.assertEqual(stacks.validate_document(stacks.strict_json(stacks.payload(result))), result)

    def test_public_validator_rejects_false_full_hash_scope_and_acceptance(self):
        self.add(1, raw=RECORD + b'x' * stacks.MAX_SOURCE)
        result = self.capture()
        for path, bad in [(['status'], 'PASS'), (['samples', 0, 'hash_scope'], 'WHOLE_FILE'),
                          (['samples', 0, 'bytes_read'], stacks.MAX_SOURCE + 1),
                          (['samples', 0, 'source_bytes'], stacks.MAX_SOURCE),
                          (['samples', 0, 'omissions'], [])]:
            value = copy.deepcopy(result)
            target = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = bad
            with self.subTest(path=path), self.assertRaises(ValueError):
                stacks.validate_document(value)


if __name__ == '__main__':
    unittest.main()
