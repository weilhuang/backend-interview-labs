#!/usr/bin/env python3
"""Check repository Markdown file/anchor links without flaky third-party requests."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit


def prose(text: str) -> str:
    lines, fence = [], None
    for line in text.splitlines():
        match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if match:
            char = match.group()[len(match.group()) - 1]
            fence = None if fence == char else (char if fence is None else fence)
            continue
        if fence is None:
            lines.append(line)
    return '\n'.join(lines)


def anchors(text: str) -> set[str]:
    result, seen = set(), {}
    text = prose(text)
    for title in re.findall(r'^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$', text, re.M):
        title = re.sub(r'<[^>]*>', '', html.unescape(title)).strip().lower()
        slug = ''.join(c for c in title if c in {'-', '_', ' '} or unicodedata.category(c)[0] in {'L', 'N', 'M'})
        slug = slug.replace(' ', '-')
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug if count == 0 else f'{slug}-{count}')
    result.update(re.findall(r'<a\s+(?:[^>]*?\s)?(?:id|name)=["\']([^"\']+)["\']', text, re.I))
    return result


def links(text: str) -> list[str]:
    text = re.sub(r'`+[^`\n]*`+', '', prose(text))
    # Inline and reference-style links; examples inside fenced/inline code are excluded.
    result = re.findall(r'!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?\s*\)', text)
    result.extend(re.findall(r'^\s{0,3}\[[^\]]+\]:\s*(<[^>\n]+>|\S+)', text, re.M))
    return [value[1:-1] if value.startswith('<') else value for value in result]


def validate(root: Path, files: list[str]) -> dict:
    errors, checked = [], 0
    root = root.resolve()
    known = set(files)
    for name in files:
        if not name.endswith('.md'):
            continue
        path = root / name
        if not path.is_file():
            errors.append(f'{name}: tracked document is missing')
            continue
        for href in links(path.read_text(encoding='utf-8')):
            checked += 1
            parsed = urlsplit(href)
            if parsed.scheme:
                if parsed.scheme in {'http', 'https'} and not parsed.netloc:
                    errors.append(f'{name}: malformed external link {href}')
                continue
            if parsed.netloc:  # Protocol-relative URL.
                continue
            target = (root / unquote(parsed.path.lstrip('/')) if parsed.path.startswith('/') else path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not target.is_relative_to(root):
                errors.append(f'{name}: link escapes repository {href}')
                continue
            rel = target.relative_to(root).as_posix()
            if rel not in known and not any(value.startswith(rel.rstrip('/') + '/') for value in known):
                errors.append(f'{name}: missing tracked link target {href}')
            elif parsed.fragment and target.suffix == '.md' and target.is_file():
                if unquote(parsed.fragment) not in anchors(target.read_text(encoding='utf-8')):
                    errors.append(f'{name}: missing heading anchor {href}')
    return {'schema_version': 1, 'status': 'passed' if not errors else 'failed',
            'checked_links': checked, 'external_http_reachability': 'NOT_RUN', 'errors': errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--report', type=Path, default=Path('build/ci/docs.json'))
    parser.add_argument('--files-json', type=Path, help='Optional tracked path inventory for source snapshots without .git')
    args = parser.parse_args()
    files = json.loads(args.files_json.read_text()) if args.files_json else [x.decode() for x in subprocess.check_output(['git', 'ls-files', '-z'], cwd=args.root).split(b'\0') if x]
    report = validate(args.root, files)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
