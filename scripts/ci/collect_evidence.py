#!/usr/bin/env python3
"""Bounded allowlisted public CI evidence; never copy source, profiles or caches.

Collection status is not a test verdict. The original job outcome and sanitized
failure/test results are retained. Unsafe or unavailable evidence is explicit.
"""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'academy'))
from safe_io import absolute, directory_fd, new_directory, read_regular, validate_directory, write_new
from collect_evidence import sanitize_text, sanitize_value

MAX_FILE = 4 * 1024 * 1024
MAX_LOG = 128 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILES = 1200
MAX_SCAN = 30000
MAX_DEPTH = 24
MAX_PATH = 1024
MAX_OMISSIONS = 1200
MAX_MANIFEST = 4 * 1024 * 1024
SKIP_DIRS = {'.git', '.idea', '.gradle', '.aws', '.ssh', '.config', 'node_modules',
             '__pycache__', 'classes', 'libs', 'distributions', 'tmp', 'gradle-home',
             'browser', 'ui-tools', 'html', 'binary', 'profiles', 'profile'}
COURSES = {
    'java-pilot': ('java-recovery-collections', 'java-recovery-collections'),
    'java-foundations': ('java-foundations', 'java-foundations'),
    'java-concurrency': ('java-concurrency', 'java-concurrency'),
    'java-jvm': ('java-jvm', 'java-jvm'),
    'java-frameworks-backend': ('java-frameworks', 'java-frameworks'),
    'java-frameworks-ui': ('java-frameworks', None),
    'mysql': ('data-storage/mysql-engineering', 'mysql'),
    'redis': ('data-storage/redis-engineering', 'redis'),
    'messaging': ('messaging', 'messaging'),
    'distributed': ('distributed-systems', 'distributed-systems'),
    'backend-capstone': ('backend-capstone', 'backend-capstone'),
    'lab-environment': ('java-recovery-collections', None),
}
AUTHOR_REPORTS = {'metadata-report.json', 'negative-report.json', 'callers-report.json',
                  'ui-verification.json', 'verification-report.json', 'variant-report.json',
                  'variants-report.json', 'script-report.json', 'source-verification.json'}
PHASE_LOGS = {'learner-rejected.log', 'reference-accepted.log', 'rebuilt-learner-rejected.log'}
PNG_NAMES = {'browser-smoke.png', 'browser-failure.png'} | {
    f'browser-layout-{width}.png' for width in (320, 390, 800, 801, 1440)}


def allowed(profile, relative):
    """Return format only for reviewed producers and names, not arbitrary suffixes."""
    p = Path(relative); name = p.name; parts = p.parts
    ci = {'ci-plan': {'build/ci/plan.json'},
          'ci-static': {'build/ci/docs.json', 'build/quality/academy-metadata.json',
                        'build/quality/academy-legacy-metadata.json', 'build/ci/public-course.json'},
          'ci-result': {'build/ci/evidence.json'}}
    if profile in ci:
        return 'json' if relative in ci[profile] else None
    course, key = COURSES[profile]
    prefix = 'courses/' + course + '/'
    keys = ([key] if key else []) + (['distributed-region-audit'] if profile == 'distributed' else [])
    for quality in keys:
        base = 'build/quality/' + quality + ('-roundtrip' if quality != 'distributed-region-audit' else '')
        if relative == base + '.json': return 'json'
        if relative.startswith(base + '/'):
            if name == 'source-manifest.json': return 'json'
            if name in PHASE_LOGS: return 'log'
            if '/build/test-results/' in relative and re.fullmatch(r'TEST-[A-Za-z0-9_.$-]+\.xml', name): return 'xml'
    if relative.startswith(prefix):
        rest = relative[len(prefix):]
        if rest.startswith('authoring/') and rest.count('/') == 1 and name in AUTHOR_REPORTS: return 'json'
        if '/build/test-results/' in '/' + rest and re.fullmatch(r'TEST-[A-Za-z0-9_.$-]+\.xml', name): return 'xml'
        if rest in {'build/verification/report.json', 'build/browser-layout.json', 'build/process-recovery.json'}: return 'json'
        if rest.startswith(('build/verification/', 'build/variants/', 'build/negative-verification/', 'build/callers/')):
            if name in {'compile.log', 'junit.log', 'usage.log', 'tests.log'}: return 'log'
            if profile == 'backend-capstone' and re.fullmatch(r'0[1-5]-[a-z]+-(reference|alternate|learner|mutation)(-compile)?\.log', name): return 'log'
            if profile == 'messaging' and re.fullmatch(r'[A-Za-z0-9_-]+\.log', name): return 'log'
        if course == 'java-frameworks':
            if rest in {'build/ui/mobile.png', 'build/ui/desktop.png', 'build/ui/failure.png'}: return 'png'
            if rest == 'build/server/application.log': return 'log'
        if course == 'backend-capstone':
            if rest == 'build/compose.log': return 'log'
            if rest == 'build/' + name and name in PNG_NAMES: return 'png'
    if profile == 'lab-environment' and relative in {
        'infra/artifacts/' + n + '.log' for n in ('mysql', 'redis', 'kafka', 'rocketmq', 'namesrv', 'broker', 'proxy', 'rocketmq-namesrv', 'rocketmq-broker', 'rocketmq-proxy')}: return 'log'
    return None


def roots(profile):
    if profile.startswith('ci-'): return ['build/ci', 'build/quality']
    course, key = COURSES[profile]
    result = ['courses/' + course]
    if key: result.append('build/quality/' + key + '-roundtrip')
    if profile == 'distributed': result.append('build/quality/distributed-region-audit')
    if profile == 'lab-environment': result.append('infra/artifacts')
    # Top-level quality JSON files only; recursion is explicitly pruned below.
    result.append('build/quality')
    return result


def walk_files(root, budget, depth=0):
    """Traverse directory descriptors with O_NOFOLLOW, including every parent."""
    if depth > MAX_DEPTH: raise ValueError('scan_depth_limit')
    with directory_fd(root) as fd:
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                budget[0] += 1
                if budget[0] > MAX_SCAN: raise ValueError('scan_entry_limit')
                names.append(entry.name)
        for name in sorted(names):
            if not re.fullmatch(r'[A-Za-z0-9_.@+-]{1,200}', name): continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            path = root / name
            if stat.S_ISDIR(info.st_mode):
                if name not in SKIP_DIRS and not name.startswith('.'):
                    # build/quality root is scanned for summary files only.
                    if root.parts[-2:] != ('build', 'quality'):
                        yield from walk_files(path, budget, depth + 1)
            else:
                # Return linked/special allowlisted leaves so omissions are visible.
                yield path


def unique_json_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate_json_key')
        result[key]=value
    return result


def clean_xml(data):
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)', data, re.I): raise ValueError('xml_declaration_forbidden')
    root = ET.fromstring(data)
    if root.tag not in {'testsuite', 'testsuites'}: raise ValueError('unknown_junit_schema')
    allowed_tags = {'testsuites', 'testsuite', 'testcase', 'failure', 'error', 'skipped'}
    attributes = {'name', 'classname', 'tests', 'failures', 'errors', 'skipped', 'disabled', 'time', 'type', 'message', 'timestamp'}
    def clean(node, depth=0):
        if depth > 24: raise ValueError('xml_depth_limit')
        result = ET.Element(node.tag, {key: sanitize_text(value)[:4096] for key, value in node.attrib.items() if key in attributes})
        if node.tag in {'failure', 'error', 'skipped'} and node.text:
            result.text = sanitize_text(node.text)[:MAX_LOG]
        for child in node:
            if child.tag in allowed_tags: result.append(clean(child, depth + 1))
        return result
    return ET.tostring(clean(root), encoding='utf-8', xml_declaration=True)


def clean_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('invalid_png')
    out = bytearray(data[:8]); pos = 8; tags = []
    while pos < len(data):
        if pos + 12 > len(data): raise ValueError('truncated_png')
        size = struct.unpack('>I', data[pos:pos+4])[0]; end = pos + 12 + size
        if end > len(data): raise ValueError('truncated_png')
        kind = data[pos+4:pos+8]; payload = data[pos+8:pos+8+size]
        if zlib.crc32(kind+payload) & 0xffffffff != struct.unpack('>I',data[end-4:end])[0]: raise ValueError('png_crc')
        tags.append(kind)
        if len(tags) > 10000: raise ValueError('png_chunk_limit')
        if kind in {b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'}: out.extend(data[pos:end])
        elif kind[:1].isupper(): raise ValueError('unknown_critical_png_chunk')
        pos = end
        if kind == b'IEND': break
    if not tags or tags[0] != b'IHDR' or tags[-1] != b'IEND' or b'IDAT' not in tags or pos != len(data): raise ValueError('invalid_png_structure')
    return bytes(out)


def collect(repo, output, profile, job_status='unknown'):
    if profile not in COURSES and profile not in {'ci-plan', 'ci-static', 'ci-result'}: raise ValueError('unknown_profile')
    if job_status not in {'success', 'failure', 'cancelled', 'unknown'}: raise ValueError('unknown_job_status')
    repo = absolute(repo); output = absolute(output); validate_directory(repo)
    if output.is_relative_to(repo) or repo.is_relative_to(output): raise ValueError('output_must_be_disjoint')
    new_directory(output)
    copied = []; omitted = []; seen = set(); total = 0; budget = [0]; omitted_count = 0
    def omission(path, reason):
        nonlocal omitted_count
        omitted_count += 1
        if len(omitted) < MAX_OMISSIONS:
            safe_path = path if len(path.encode('utf-8')) <= MAX_PATH else '[overlong-path-sha256:' + hashlib.sha256(path.encode()).hexdigest() + ']'
            omitted.append({'path': safe_path, 'reason': reason})
    for name in roots(profile):
        try:
            for path in walk_files(repo / name, budget):
                relative = path.relative_to(repo).as_posix()
                if len(relative.encode('utf-8')) > MAX_PATH:
                    omission(relative, 'PathLimit'); continue
                if relative in seen: continue
                seen.add(relative); fmt = allowed(profile, relative)
                if fmt is None: continue
                try:
                    if len(copied) >= MAX_FILES: raise ValueError('file_count_limit')
                    data = read_regular(path, limit=MAX_FILE)
                    original = hashlib.sha256(data).hexdigest()
                    truncated = False
                    if fmt == 'json':
                        data = (json.dumps(sanitize_value(json.loads(data, object_pairs_hook=unique_json_pairs)), ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
                    elif fmt == 'xml': data = clean_xml(data)
                    elif fmt == 'png': data = clean_png(data)
                    else:
                        truncated = len(data) > MAX_LOG
                        header = b'[sanitized bounded diagnostic; original outcome retained in reports]\n'
                        body = sanitize_text(data[-MAX_LOG:].decode('utf-8', errors='replace')).encode()
                        body_budget = max(0, MAX_LOG-len(header))
                        truncated = truncated or len(body) > body_budget
                        data = header[:MAX_LOG] + (body[-body_budget:].decode('utf-8', errors='ignore').encode() if body_budget else b'')
                    if len(data) > MAX_FILE: raise ValueError('sanitized_file_byte_limit')
                    if total + len(data) > MAX_TOTAL: raise ValueError('total_byte_limit')
                    target = output / relative; target.parent.mkdir(parents=True, exist_ok=True)
                    validate_directory(target.parent); write_new(target, data); total += len(data)
                    copied.append({'path': relative, 'bytes': len(data), 'original_sha256': original,
                                   'uploaded_sha256': hashlib.sha256(data).hexdigest(), 'truncated': truncated})
                except (OSError, ValueError, RecursionError, ET.ParseError) as exc:
                    omission(relative, type(exc).__name__)
        except FileNotFoundError: continue
        except (OSError, ValueError) as exc:
            omission(name, type(exc).__name__)
    summary = {'schema_version': 1, 'profile': profile, 'job_status': job_status,
               'collection_status': 'PARTIAL' if omitted else ('COMPLETE' if copied else 'NO_EVIDENCE'),
               'test_verdict': 'NOT_INFERRED_FROM_COLLECTION', 'copied': copied, 'omitted': omitted,
               'omitted_count': omitted_count, 'omissions_truncated': omitted_count > len(omitted),
               'bytes': total, 'limits': {'file': MAX_FILE, 'total': MAX_TOTAL, 'count': MAX_FILES, 'log': MAX_LOG,
                                         'collection_manifest': MAX_MANIFEST, 'artifact_total': MAX_TOTAL + MAX_MANIFEST,
                                         'artifact_count': MAX_FILES + 1},
               'excluded': ['source', 'credentials', 'IDE/browser profiles', 'caches', 'archives', 'raw JUnit streams/properties']}
    manifest = (json.dumps(summary, ensure_ascii=False, indent=2) + '\n').encode()
    if len(manifest) > MAX_MANIFEST: raise ValueError('collection_manifest_byte_limit')
    write_new(output / 'collection.json', manifest)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--job-status', default='unknown')
    args = parser.parse_args()
    result = collect(args.repo, args.output, args.profile, args.job_status)
    print(json.dumps({key: result[key] for key in ('profile', 'job_status', 'collection_status', 'bytes')}))
