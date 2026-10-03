"""Passive, bounded post-Trust dump metadata and safe stack projections.

The caller owns the immutable Trust anchor, polling cadence and total deadline.
This module never creates dumps, discovers processes or writes source files.
Internal Scan/Candidate objects contain filesystem identity; public JSON does not.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from safe_io import absolute, directory_fd
from thread_diagnostics import FILE, MAX_THREADS, MAX_FRAMES, ROLES, STATES, normalized_frame

MAX_ENTRIES = 256
MAX_SOURCE = 1024 * 1024
MAX_TOTAL_READ = 2 * MAX_SOURCE
MAX_METADATA = 64 * 1024
MAX_SAMPLE = 88 * 1024
MAX_OUTPUT = 248 * 1024  # Reserve 8 KiB for the enclosing receipt/display context.
MAX_NS = 2**63 - 1
STATUSES = {'COLLECTED_NOT_ACCEPTANCE', 'PARTIAL_NOT_ACCEPTANCE', 'UNAVAILABLE_NOT_ACCEPTANCE'}
RELATIONS = {'PRE_TRUST', 'AT_ANCHOR', 'POST_TRUST', 'CLOCK_INCONSISTENT', 'UNKNOWN'}
SELECTIONS = {'NONE', 'FIRST_OBSERVED', 'FIRST_MTIME', 'LATEST',
              'FIRST_OBSERVED_AND_LATEST', 'FIRST_MTIME_AND_LATEST'}
CODES = {'NONE', 'PRE_TRUST', 'AT_ANCHOR', 'NOT_SELECTED', 'DIRECTORY_UNAVAILABLE',
         'SCAN_LIMIT', 'SCAN_DEADLINE', 'SCAN_INCOMPLETE', 'SCAN_CHANGED',
         'DUPLICATE_SOURCE_ID', 'UNSAFE_FILE', 'SOURCE_METADATA_INVALID',
         'CLOCK_INCONSISTENT', 'SOURCE_EMPTY', 'PREFIX_ONLY', 'SOURCE_CHANGED',
         'READ_UNAVAILABLE', 'MALFORMED_UTF8', 'PREFIX_ENCODING_BOUNDARY', 'NO_COMPLETE_RECORDS', 'NO_STACK_FRAMES',
         'UNSUPPORTED_FRAMES', 'PROJECTION_LIMIT', 'FIRST_OBSERVED_UNAVAILABLE',
         'CAPTURE_DEADLINE'}
PARTS = ('validate-profile', 'log', 'bg-wa')


def require(condition, code='invalid post-Trust stacks'):
    if not condition:
        raise ValueError(code)


def payload(value):
    return (json.dumps(value, ensure_ascii=True, separators=(',', ':')) + '\n').encode()


def strict_json(raw):
    """Bound bytes before parsing; reject duplicate keys, floats and nonfinite values."""
    require(type(raw) in (bytes, str) and len(raw) <= MAX_OUTPUT)
    try:
        text = raw.decode('utf-8') if type(raw) is bytes else raw
        require(len(text.encode('utf-8')) <= MAX_OUTPUT)
    except UnicodeError as exc:
        raise ValueError('invalid post-Trust JSON') from exc
    # Reject excessive nesting before the platform JSON decoder can recurse.
    depth = 0
    quoted = escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in '[{':
            depth += 1
            require(depth <= 12)
        elif character in ']}':
            depth -= 1

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result

    def reject(_):
        raise ValueError('invalid JSON scalar')

    try:
        return json.loads(text, object_pairs_hook=unique, parse_float=reject, parse_constant=reject)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('invalid post-Trust JSON') from exc


def integer(value, low=0, high=MAX_NS):
    require(type(value) is int and low <= value <= high)
    return value


def enum(value, choices):
    require(type(value) is str and value in choices)
    return value


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected))


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_mtime_ns, info.st_ctime_ns)


def _owned_file(info):
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()


@dataclass(frozen=True)
class Candidate:
    source_id: int
    mtime_ns: object
    bytes: object
    relation: str
    identity: object
    omission: str

    @property
    def basename(self):
        return f'thread-dump-{self.source_id}.txt'


@dataclass(frozen=True)
class Scan:
    root: str
    anchor_wall_ns: int
    observed_wall_ns: int
    candidates: tuple
    examined: int
    unknown: int
    complete: bool
    omissions: tuple
    directory_identity: object


def scan(root, anchor_wall_ns, *, observed=None, deadline=None):
    """Metadata only; at most 256 entries and one second, clipped by deadline.

    ``observed`` is the current wall-clock time in nanoseconds. ``deadline`` is
    an absolute time.monotonic() deadline. No arbitrary filename is returned.
    """
    integer(anchor_wall_ns)
    observed = time.time_ns() if observed is None else integer(observed)
    root = absolute(root)
    end = time.monotonic() + 1.0
    if deadline is not None:
        end = min(end, deadline)
    candidates = []
    omissions = []
    seen = set()
    examined = unknown = 0
    complete = True
    directory_identity = None
    if observed < anchor_wall_ns:
        complete = False
        omissions.append('CLOCK_INCONSISTENT')
    try:
        with directory_fd(root.joinpath(*PARTS)) as fd:
            directory_identity = _directory_identity(os.fstat(fd))
            with os.scandir(fd) as entries:
                while True:
                    if time.monotonic() >= end:
                        complete = False
                        omissions.append('SCAN_DEADLINE')
                        break
                    # Conservatively incomplete at the cap: even probing for
                    # exhaustion could retrieve an unauthorized 257th entry.
                    if examined == MAX_ENTRIES:
                        complete = False
                        omissions.append('SCAN_LIMIT')
                        break
                    try:
                        entry = next(entries)
                    except StopIteration:
                        break
                    examined += 1
                    match = FILE.fullmatch(entry.name)
                    if match is None or int(match[1]) > 2147483647:
                        unknown += 1
                        continue
                    ident = int(match[1])
                    if ident in seen:
                        complete = False
                        omissions.append('DUPLICATE_SOURCE_ID')
                        continue
                    seen.add(ident)
                    mtime = size = identity = None
                    relation = 'UNKNOWN'
                    code = 'NONE'
                    try:
                        info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                        identity = _identity(info)
                        mtime = info.st_mtime_ns if -(2**63) <= info.st_mtime_ns <= MAX_NS else None
                        size = info.st_size if 0 <= info.st_size <= MAX_NS else None
                        if not _owned_file(info):
                            code = 'UNSAFE_FILE'
                            # The lstat of a link/non-file is not a dump body's
                            # size or time. Its canonical name still prevents a
                            # complete ordering of every possible dump source.
                            mtime = size = identity = None
                            complete = False
                        elif mtime is None or mtime < 0 or size is None:
                            code = 'SOURCE_METADATA_INVALID'
                            complete = False
                        elif mtime > observed or observed < anchor_wall_ns:
                            relation, code = 'CLOCK_INCONSISTENT', 'CLOCK_INCONSISTENT'
                            complete = False
                        else:
                            relation = ('POST_TRUST' if mtime > anchor_wall_ns else
                                        'AT_ANCHOR' if mtime == anchor_wall_ns else 'PRE_TRUST')
                    except InterruptedError:
                        raise
                    except OSError:
                        code = 'READ_UNAVAILABLE'
                        complete = False
                    candidates.append(Candidate(ident, mtime, size, relation, identity, code))
                    if code != 'NONE':
                        omissions.append(code)
                if _directory_identity(os.fstat(fd)) != directory_identity:
                    complete = False
                    omissions.append('SCAN_CHANGED')
            if time.monotonic() >= end and 'SCAN_DEADLINE' not in omissions:
                complete = False
                omissions.append('SCAN_DEADLINE')
    except InterruptedError:
        raise
    except (OSError, ValueError):
        complete = False
        omissions.append('DIRECTORY_UNAVAILABLE')
    return Scan(str(root), anchor_wall_ns, observed,
                tuple(sorted(candidates, key=lambda c: c.source_id)), examined, unknown,
                complete, tuple(dict.fromkeys(omissions)), directory_identity)


def stable_post_ids(previous, current):
    """Two complete, same-context observations with unchanged full stat identity."""
    if not (isinstance(previous, Scan) and isinstance(current, Scan) and
            previous.complete and current.complete and previous.root == current.root and
            previous.anchor_wall_ns == current.anchor_wall_ns and
            previous.observed_wall_ns <= current.observed_wall_ns):
        return ()
    old = {c.source_id: c for c in previous.candidates}
    stable = [c for c in current.candidates if c.relation == 'POST_TRUST' and
              c.omission == 'NONE' and c.source_id in old and
              old[c.source_id].relation == 'POST_TRUST' and
              old[c.source_id].identity == c.identity]
    return tuple(c.source_id for c in sorted(stable, key=lambda c: (c.mtime_ns, c.source_id)))


def _role(header):
    name = header.split('"', 2)[1] if '"' in header[1:] else ''
    if name == 'main':
        return 'MAIN'
    if re.fullmatch(r'AWT-EventQueue-[0-9]{1,4}', name):
        return 'EDT'
    if re.fullmatch(r'DefaultDispatcher-worker-[0-9]{1,4}', name):
        return 'COROUTINE_WORKER'
    if re.fullmatch(r'ApplicationImpl pooled thread [0-9]{1,4}', name):
        return 'POOLED'
    return 'OTHER'


def project_stacks(raw, *, prefix=False):
    """Keep whole records only; a prefix never makes EOF a record terminator.

    UTF-8 is strict. A valid sequence cut only by the prefix boundary has its
    own unavailable code; it does not imply corruption in the original file.
    A blank line or subsequent thread header terminates a record; only
    whole-file EOF can terminate the last record. Fragments are never joined.
    """
    require(type(raw) is bytes and len(raw) <= MAX_SOURCE)
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        if prefix and exc.reason == 'unexpected end of data' and exc.end == len(raw):
            raise ValueError('PREFIX_ENCODING_BOUNDARY') from None
        raise
    lines = text.split('\n')
    if prefix:
        lines.pop()  # trailing empty sentinel or incomplete final line
    threads = []
    current = None
    complete_records = 0
    unsupported = False
    truncated = False

    def finish():
        nonlocal current, complete_records, truncated
        if current is not None:
            complete_records += 1
            if current['frames']:
                if len(threads) < MAX_THREADS:
                    threads.append(current)
                else:
                    truncated = True
            current = None

    for line in lines:
        line = line.removesuffix('\r')
        if line.startswith('"'):
            finish()
            if len(line) <= 1024 and '"' in line[1:]:
                current = {'role': _role(line), 'state': 'UNKNOWN', 'frames': []}
            continue
        if not line.strip():
            finish()
            continue
        if current is None:
            continue
        state = re.fullmatch(r'\s*java\.lang\.Thread\.State: ([A-Z_]+)(?: \([a-z ]{1,40}\))?', line)
        if state and state[1] in STATES:
            current['state'] = state[1]
        stripped = line.strip()
        if not stripped.startswith('at '):
            continue
        try:
            frame = normalized_frame(stripped[3:])
        except ValueError:
            unsupported = True
            continue
        if len(current['frames']) < MAX_FRAMES:
            current['frames'].append(frame)
        else:
            truncated = True
    if not prefix:
        finish()
    require(complete_records, 'NO_COMPLETE_RECORDS')
    require(threads, 'NO_STACK_FRAMES')
    # Exact serialized accounting, including JSON escaping, instead of assuming
    # every normalized Java symbol consumes one byte in the public JSON.
    used = len(payload(threads))
    while used > MAX_SAMPLE - 2048:
        truncated = True
        thread = threads[-1]
        if len(thread['frames']) == 1:
            used -= len(payload(thread)) - 1 + (1 if len(threads) > 1 else 0)
            threads.pop()
        else:
            # payload adds one newline; the removed list comma replaces it.
            used -= len(payload(thread['frames'].pop()))
    codes = (['UNSUPPORTED_FRAMES'] if unsupported else []) + (['PROJECTION_LIMIT'] if truncated else [])
    return threads, truncated, codes


def _read_source(root, candidate, directory_identity, deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise ValueError('CAPTURE_DEADLINE')
    directory = root.joinpath(*PARTS)
    with directory_fd(directory) as dfd:
        require(_directory_identity(os.fstat(dfd)) == directory_identity, 'SOURCE_CHANGED')
        fd = os.open(candidate.basename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        try:
            before = os.fstat(fd)
            require(_owned_file(before) and _identity(before) == candidate.identity, 'SOURCE_CHANGED')
            require(_identity(os.stat(candidate.basename, dir_fd=dfd, follow_symlinks=False)) == candidate.identity,
                    'SOURCE_CHANGED')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(min(before.st_size, MAX_SOURCE))
            require(len(raw) == min(before.st_size, MAX_SOURCE), 'SOURCE_CHANGED')
            require(_identity(os.fstat(fd)) == candidate.identity and
                    _identity(os.stat(candidate.basename, dir_fd=dfd, follow_symlinks=False)) == candidate.identity,
                    'SOURCE_CHANGED')
            with directory_fd(directory) as fresh:
                require(_directory_identity(os.fstat(fresh)) == directory_identity, 'SOURCE_CHANGED')
        finally:
            os.close(fd)
    if deadline is not None and time.monotonic() >= deadline:
        raise ValueError('CAPTURE_DEADLINE')
    return raw, before.st_size


def capture(root, anchor_wall_ns, *, first_observed_id=None, scan_result=None, deadline=None):
    """Select before reading: never replace an oversized/failed newest candidate.

    Passing first_observed_id preserves the observer's first stable source. If
    omitted, FIRST_MTIME explicitly describes the fallback chronology. This
    function returns JSON data only; atomic staging belongs to the caller.
    """
    integer(anchor_wall_ns)
    if first_observed_id is not None:
        integer(first_observed_id, 0, 2147483647)
    root = absolute(root)
    scan_result = scan(root, anchor_wall_ns, deadline=deadline) if scan_result is None else scan_result
    require(isinstance(scan_result, Scan) and scan_result.root == str(root) and
            scan_result.anchor_wall_ns == anchor_wall_ns)
    result = {'schema_version': 1, 'status': 'UNAVAILABLE_NOT_ACCEPTANCE',
              'anchor_wall_ns': anchor_wall_ns, 'observed_wall_ns': scan_result.observed_wall_ns,
              'scan': {'examined': scan_result.examined, 'unknown': scan_result.unknown,
                       'complete': scan_result.complete},
              'candidates': [], 'samples': [], 'omissions': list(scan_result.omissions)}
    selected = {}
    post = sorted((c for c in scan_result.candidates if c.relation == 'POST_TRUST' and c.omission == 'NONE'),
                  key=lambda c: (c.mtime_ns, c.source_id))
    if scan_result.complete and post:
        label = 'FIRST_OBSERVED' if first_observed_id is not None else 'FIRST_MTIME'
        first = next((c for c in post if c.source_id == first_observed_id), None) if first_observed_id is not None else post[0]
        if first is None:
            result['omissions'].append('FIRST_OBSERVED_UNAVAILABLE')
        else:
            selected[first.source_id] = label
        latest = post[-1]
        selected[latest.source_id] = label + '_AND_LATEST' if first == latest else 'LATEST'
    elif first_observed_id is not None and scan_result.complete:
        result['omissions'].append('FIRST_OBSERVED_UNAVAILABLE')
    read_bytes = 0
    for candidate in scan_result.candidates:
        row = {'source_id': candidate.source_id, 'basename': candidate.basename,
               'mtime_ns': candidate.mtime_ns, 'bytes': candidate.bytes,
               'relation': candidate.relation, 'selection': selected.get(candidate.source_id, 'NONE'),
               'omission': candidate.omission, 'read': None}
        result['candidates'].append(row)
        if row['omission'] != 'NONE':
            continue
        if candidate.relation != 'POST_TRUST':
            row['omission'] = candidate.relation
            continue
        if not scan_result.complete:
            row['omission'] = 'SCAN_INCOMPLETE'
            continue
        if row['selection'] == 'NONE':
            row['omission'] = 'NOT_SELECTED'
            continue
        row['read'] = {'scope': 'UNVERIFIED', 'source_bytes': None, 'bytes_read': None, 'sha256': None}
        try:
            raw, actual_size = _read_source(root, candidate, scan_result.directory_identity, deadline)
            read_bytes += len(raw)
            require(read_bytes <= MAX_TOTAL_READ)
            prefix = actual_size > MAX_SOURCE
            # Preserve verified read facts even when decoding or projecting the
            # bytes fails. This never represents an unstable read as evidence.
            row['read'] = {'scope': 'EMPTY' if actual_size == 0 else 'PREFIX' if prefix else 'WHOLE_FILE',
                           'source_bytes': actual_size, 'bytes_read': len(raw),
                           'sha256': hashlib.sha256(raw).hexdigest()}
            if actual_size == 0:
                row['omission'] = 'SOURCE_EMPTY'
                result['omissions'].append('SOURCE_EMPTY')
                continue
            threads, truncated, codes = project_stacks(raw, prefix=prefix)
            if deadline is not None and time.monotonic() >= deadline:
                raise ValueError('CAPTURE_DEADLINE')
            if prefix:
                codes.insert(0, 'PREFIX_ONLY')
            sample = {'source_id': candidate.source_id, 'selection': row['selection'],
                      'source_mtime_ns': candidate.mtime_ns, 'source_bytes': actual_size,
                      'bytes_read': len(raw), 'hash_scope': 'PREFIX' if prefix else 'WHOLE_FILE',
                      'sha256': row['read']['sha256'], 'projection_truncated': truncated,
                      'omissions': codes, 'threads': threads}
            row['omission'] = codes[0] if codes else 'NONE'
            result['samples'].append(sample)
            result['omissions'].extend(codes)
        except InterruptedError:
            raise
        except UnicodeError:
            row['omission'] = 'MALFORMED_UTF8'
            result['omissions'].append(row['omission'])
        except (OSError, ValueError) as exc:
            row['omission'] = str(exc) if type(exc) is ValueError and str(exc) in CODES else 'READ_UNAVAILABLE'
            result['omissions'].append(row['omission'])
    result['omissions'] = list(dict.fromkeys(result['omissions']))
    if result['samples']:
        result['status'] = 'PARTIAL_NOT_ACCEPTANCE' if result['omissions'] else 'COLLECTED_NOT_ACCEPTANCE'
    return validate_document(result)


def validate_document(value):
    """Strict public replay boundary: exact keys/types, normalized frames, caps."""
    fields(value, {'schema_version', 'status', 'anchor_wall_ns', 'observed_wall_ns',
                   'scan', 'candidates', 'samples', 'omissions'})
    integer(value['schema_version'], 1, 1)
    enum(value['status'], STATUSES)
    integer(value['anchor_wall_ns'])
    integer(value['observed_wall_ns'])
    scan_data = value['scan']
    fields(scan_data, {'examined', 'unknown', 'complete'})
    integer(scan_data['examined'], 0, MAX_ENTRIES)
    integer(scan_data['unknown'], 0, scan_data['examined'])
    require(type(scan_data['complete']) is bool)
    candidates = value['candidates']
    require(type(candidates) is list and len(candidates) <= scan_data['examined'] - scan_data['unknown'])
    by_id = {}
    selected = {}
    for row in candidates:
        fields(row, {'source_id', 'basename', 'mtime_ns', 'bytes', 'relation', 'selection', 'omission', 'read'})
        ident = integer(row['source_id'], 0, 2147483647)
        require(type(row['basename']) is str and row['basename'] == f'thread-dump-{ident}.txt')
        require(ident not in by_id)
        by_id[ident] = row
        if row['mtime_ns'] is not None:
            integer(row['mtime_ns'], -(2**63))
        if row['bytes'] is not None:
            integer(row['bytes'])
        enum(row['relation'], RELATIONS)
        enum(row['selection'], SELECTIONS)
        enum(row['omission'], CODES)
        if row['omission'] in {'UNSAFE_FILE', 'SOURCE_METADATA_INVALID'}:
            require(not scan_data['complete'] and row['selection'] == 'NONE' and row['relation'] == 'UNKNOWN')
        if row['omission'] == 'UNSAFE_FILE':
            require(row['mtime_ns'] is None and row['bytes'] is None)
        if row['relation'] in {'PRE_TRUST', 'AT_ANCHOR', 'POST_TRUST'}:
            require(row['mtime_ns'] is not None and row['bytes'] is not None and row['mtime_ns'] >= 0)
            relation = ('POST_TRUST' if row['mtime_ns'] > value['anchor_wall_ns'] else
                        'AT_ANCHOR' if row['mtime_ns'] == value['anchor_wall_ns'] else 'PRE_TRUST')
            require(row['relation'] == relation and row['mtime_ns'] <= value['observed_wall_ns'])
        if row['selection'] != 'NONE':
            require(scan_data['complete'] and row['relation'] == 'POST_TRUST')
            selected[ident] = row
            reading = row['read']
            fields(reading, {'scope', 'source_bytes', 'bytes_read', 'sha256'})
            enum(reading['scope'], {'EMPTY', 'WHOLE_FILE', 'PREFIX', 'UNVERIFIED'})
            if reading['scope'] == 'UNVERIFIED':
                require(all(reading[key] is None for key in ('source_bytes', 'bytes_read', 'sha256')))
            else:
                size = integer(reading['source_bytes'])
                amount = integer(reading['bytes_read'], 0, MAX_SOURCE)
                require(size == row['bytes'] and amount == min(size, MAX_SOURCE))
                expected = 'EMPTY' if size == 0 else 'PREFIX' if size > MAX_SOURCE else 'WHOLE_FILE'
                require(reading['scope'] == expected)
                require(type(reading['sha256']) is str and re.fullmatch('[0-9a-f]{64}', reading['sha256']) is not None)
                if size == 0:
                    require(reading['sha256'] == hashlib.sha256(b'').hexdigest())
        else:
            require(row['read'] is None)
    require(len(selected) <= 2)
    selections = [r['selection'] for r in selected.values()]
    require(len(selections) == len(set(selections)))
    require(not any('_AND_' in s for s in selections) or len(selected) == 1)
    require(sum(s.startswith('FIRST_') for s in selections) <= 1)
    post = sorted((row for row in candidates if row['relation'] == 'POST_TRUST'),
                  key=lambda row: (row['mtime_ns'], row['source_id']))
    if scan_data['complete'] and post:
        latest = [row for row in selected.values() if row['selection'].endswith('LATEST')]
        require(len(latest) == 1 and latest[0]['source_id'] == post[-1]['source_id'])
        first_mtime = [row for row in selected.values() if row['selection'].startswith('FIRST_MTIME')]
        require(not first_mtime or first_mtime[0]['source_id'] == post[0]['source_id'])
    omissions = value['omissions']
    require(type(omissions) is list and len(omissions) <= len(CODES))
    for code in omissions:
        enum(code, CODES - {'NONE', 'PRE_TRUST', 'AT_ANCHOR', 'NOT_SELECTED'})
    require(len(omissions) == len(set(omissions)))
    samples = value['samples']
    require(type(samples) is list and len(samples) <= 2)
    seen = set()
    total = 0
    for sample in samples:
        fields(sample, {'source_id', 'selection', 'source_mtime_ns', 'source_bytes', 'bytes_read',
                        'hash_scope', 'sha256', 'projection_truncated', 'omissions', 'threads'})
        ident = integer(sample['source_id'], 0, 2147483647)
        require(ident in selected and ident not in seen)
        seen.add(ident)
        candidate = selected[ident]
        reading = candidate['read']
        require(type(sample['selection']) is str and sample['selection'] == candidate['selection'])
        integer(sample['source_mtime_ns'])
        integer(sample['source_bytes'], 1)
        require(sample['source_mtime_ns'] == candidate['mtime_ns'] and sample['source_bytes'] == candidate['bytes'])
        amount = integer(sample['bytes_read'], 1, MAX_SOURCE)
        total += amount
        enum(sample['hash_scope'], {'PREFIX', 'WHOLE_FILE'})
        prefix = sample['source_bytes'] > MAX_SOURCE
        require(sample['hash_scope'] == ('PREFIX' if prefix else 'WHOLE_FILE'))
        require(amount == min(sample['source_bytes'], MAX_SOURCE))
        require(type(sample['sha256']) is str and re.fullmatch('[0-9a-f]{64}', sample['sha256']) is not None)
        require(reading == {'scope': sample['hash_scope'], 'source_bytes': sample['source_bytes'],
                            'bytes_read': sample['bytes_read'], 'sha256': sample['sha256']})
        require(type(sample['projection_truncated']) is bool)
        codes = sample['omissions']
        require(type(codes) is list and len(codes) <= 3)
        for code in codes:
            enum(code, {'PREFIX_ONLY', 'UNSUPPORTED_FRAMES', 'PROJECTION_LIMIT'})
        require(len(codes) == len(set(codes)) and all(c in omissions for c in codes))
        require(('PREFIX_ONLY' in codes) == prefix)
        require(('PROJECTION_LIMIT' in codes) == sample['projection_truncated'])
        require(candidate['omission'] == (codes[0] if codes else 'NONE'))
        threads = sample['threads']
        require(type(threads) is list and 1 <= len(threads) <= MAX_THREADS)
        for thread in threads:
            fields(thread, {'role', 'state', 'frames'})
            enum(thread['role'], ROLES)
            enum(thread['state'], STATES)
            frames = thread['frames']
            require(type(frames) is list and 1 <= len(frames) <= MAX_FRAMES)
            for frame in frames:
                require(normalized_frame(frame) == frame)  # Reject noncanonical module/title payloads.
        require(len(payload(sample)) <= MAX_SAMPLE)
    require(total <= MAX_TOTAL_READ)
    read_failures = {'SOURCE_EMPTY', 'SOURCE_CHANGED', 'READ_UNAVAILABLE', 'MALFORMED_UTF8', 'PREFIX_ENCODING_BOUNDARY',
                     'NO_COMPLETE_RECORDS', 'NO_STACK_FRAMES', 'CAPTURE_DEADLINE'}
    for ident, row in selected.items():
        if ident not in seen:
            require(row['omission'] in read_failures and row['omission'] in omissions)
        require(row['omission'] != 'SOURCE_EMPTY' or row['bytes'] == 0)
        reading = row['read']
        require(reading['scope'] != 'UNVERIFIED' or row['omission'] in
                {'SOURCE_CHANGED', 'READ_UNAVAILABLE', 'CAPTURE_DEADLINE'})
        require(row['omission'] not in {'SOURCE_CHANGED', 'READ_UNAVAILABLE'} or reading['scope'] == 'UNVERIFIED')
        require(row['omission'] not in {'MALFORMED_UTF8', 'NO_COMPLETE_RECORDS', 'NO_STACK_FRAMES'} or
                reading['scope'] in {'WHOLE_FILE', 'PREFIX'})
        require(row['omission'] != 'PREFIX_ENCODING_BOUNDARY' or reading['scope'] == 'PREFIX')
        require(reading['scope'] != 'EMPTY' or row['omission'] == 'SOURCE_EMPTY')
        require(row['omission'] != 'SOURCE_EMPTY' or reading['scope'] == 'EMPTY')
    require(sum(row['read']['bytes_read'] or 0 for row in selected.values()) <= MAX_TOTAL_READ)
    metadata = {key: val for key, val in value.items() if key != 'samples'}
    require(len(payload(metadata)) <= MAX_METADATA and len(payload(value)) <= MAX_OUTPUT)
    expected = ('PARTIAL_NOT_ACCEPTANCE' if omissions else 'COLLECTED_NOT_ACCEPTANCE') if samples else 'UNAVAILABLE_NOT_ACCEPTANCE'
    require(value['status'] == expected)
    require(scan_data['complete'] or (not selected and not samples and bool(omissions)))
    require(value['observed_wall_ns'] >= value['anchor_wall_ns'] or
            (not scan_data['complete'] and 'CLOCK_INCONSISTENT' in omissions))
    return value
