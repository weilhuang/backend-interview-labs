"""Bounded diagnostics only; never replace the import byte-equality gate."""
import hashlib
import re
from urllib.parse import urlsplit
from safe_io import read_regular

RELATIVE = 'gradle/wrapper/gradle-wrapper.properties'
KEYS = ('distributionBase', 'distributionPath', 'distributionUrl', 'distributionSha256Sum',
        'networkTimeout', 'validateDistributionUrl', 'zipStoreBase', 'zipStorePath')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def key_label(key):
    return key if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', key) else 'sha256:' + sha(key.encode())


def parse(data):
    text = data.decode('utf-8')
    lines = text.splitlines()
    if len(lines) > 128 or any(len(line) > 2048 for line in lines):
        raise ValueError('properties line bound exceeded')
    stats = {'bytes': len(data), 'sha256': sha(data), 'lines': len(lines),
             'crlf': text.count('\r\n'), 'lf_only': text.count('\n') - text.count('\r\n'),
             'cr_only': text.count('\r') - text.count('\r\n'),
             'comments': 0, 'blank_lines': 0, 'key_order': []}
    values = {}
    for line in lines:
        item = line.strip()
        if not item:
            stats['blank_lines'] += 1
            continue
        if item.startswith(('#', '!')):
            stats['comments'] += 1
            continue
        if item.endswith('\\') or '=' not in item:
            raise ValueError('unsupported properties syntax')
        key, value = item.split('=', 1)
        key = key.strip()
        if not key or key in values:
            raise ValueError('empty or duplicate properties key')
        value = value.strip().replace(r'\:', ':').replace(r'\=', '=')
        if '\\' in key or '\\' in value:
            raise ValueError('unsupported properties escape')
        values[key] = value
        stats['key_order'].append(key_label(key))
    return values, stats


def disclosed(key, value):
    if value is None:
        return None
    safe = False
    if key == 'distributionUrl':
        try:
            parsed = urlsplit(value)
            safe = (parsed.scheme == 'https' and parsed.netloc == 'services.gradle.org'
                    and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                    and re.fullmatch(r'/distributions/gradle-[0-9.]+-(?:bin|all)\.zip', parsed.path))
        except ValueError:
            pass
    elif key in {'distributionBase', 'zipStoreBase'}:
        safe = value in {'GRADLE_USER_HOME', 'PROJECT'}
    elif key in {'distributionPath', 'zipStorePath'}:
        safe = bool(re.fullmatch(r'[A-Za-z0-9_/-]{1,128}', value))
    elif key == 'distributionSha256Sum':
        safe = bool(re.fullmatch(r'[a-fA-F0-9]{64}', value))
    elif key == 'networkTimeout':
        safe = bool(re.fullmatch(r'[0-9]{1,9}', value))
    elif key == 'validateDistributionUrl':
        safe = value in {'true', 'false'}
    return {'value': value} if safe else {'value': '[redacted unexpected value]', 'sha256': sha(value.encode())}


def compare_wrapper(author, imported):
    result = {'status': 'UNVERIFIED_DIAGNOSTIC', 'path': RELATIVE,
              'byte_gate_unchanged': True, 'acceptance': 'NOT_EVALUATED_BY_DIAGNOSTIC'}
    raw = {}
    parsed = {}
    for label, root in [('expected', author), ('actual', imported)]:
        try:
            data = read_regular(root / RELATIVE, limit=8192)
            raw[label] = data
            result[label] = {'bytes': len(data), 'sha256': sha(data)}
            values, stats = parse(data)
            parsed[label] = values
            result[label].update(stats=stats,
                                 unknown_keys=[key_label(key) for key in values if key not in KEYS])
        except Exception as exc:
            result['status'] = 'UNAVAILABLE_OR_UNPARSEABLE'
            result.setdefault(label, {})['error'] = type(exc).__name__
    if len(raw) == 2:
        result['byte_equal'] = raw['expected'] == raw['actual']
    if len(parsed) == 2:
        result['fields'] = {key: {'expected': disclosed(key, parsed['expected'].get(key)),
                                  'actual': disclosed(key, parsed['actual'].get(key)),
                                  'equal': parsed['expected'].get(key) == parsed['actual'].get(key),
                                  'expected_present': key in parsed['expected'],
                                  'actual_present': key in parsed['actual']}
                            for key in KEYS}
        result['all_eight_fields_present_and_equal'] = all(
            row['equal'] and row['expected_present'] and row['actual_present']
            for row in result['fields'].values())
        a, b = result['expected']['stats'], result['actual']['stats']
        result['format_changes'] = {key: a[key] != b[key]
                                    for key in ('key_order', 'comments', 'blank_lines', 'crlf', 'lf_only', 'cr_only')}
    return result
