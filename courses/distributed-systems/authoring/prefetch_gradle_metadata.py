#!/usr/bin/env python3
"""补齐已锁定坐标的官方 Gradle 元数据；保存真实原始字节与来源 SHA256。"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'build/maven-cache'
BASE = 'https://repo.maven.apache.org/maven2/'
os.environ['NO_PROXY'] = ''
os.environ['no_proxy'] = ''


def fetch(relative):
    url = BASE + relative
    try:
        data = urllib.request.urlopen(url, timeout=30).read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {'path': relative, 'url': url, 'status': 404}
        raise
    target = CACHE / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {'path': relative, 'url': url, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'status': 200}


def main():
    coordinates = set()
    for lock in [ROOT / 'support/gradle.lockfile', *ROOT.glob('distributed-course/services/*/gradle.lockfile')]:
        for line in lock.read_text().splitlines():
            if line and not line.startswith('#') and not line.startswith('empty='):
                coordinates.add(tuple(line.split('=')[0].split(':')))
    paths = []
    for group, artifact, version in sorted(coordinates):
        base = f'{group.replace(".", "/")}/{artifact}/{version}/{artifact}-{version}'
        pom = CACHE / (base + '.pom')
        if pom.is_file() and b'published-with-gradle-metadata' in pom.read_bytes():
            paths.extend([base + '.pom', base + '.module'])
        elif artifact.endswith('-bom') and pom.is_file():
            paths.append(base + '.pom')
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(fetch, paths))
    report = {'source': BASE, 'notice': '官方 POM 与 .module 原始字节；没有关闭 TLS、改写 POM 或禁用依赖锁。404 表示该固定坐标没有发布相应文件。', 'files': results}
    (ROOT / 'authoring/dependency-metadata-evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('官方元数据文件：', len(results), '，成功：', sum(x['status'] == 200 for x in results))


if __name__ == '__main__':
    main()
