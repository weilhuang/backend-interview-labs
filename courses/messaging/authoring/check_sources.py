#!/usr/bin/env python3
"""检查固定官方源码路径与目标符号；只写构建报告，不伪造断点证据。"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json, urllib.request
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'build/source-check'; DEST.mkdir(parents=True, exist_ok=True)
def check(item):
    link = item['source_url']
    url = link.replace('https://github.com/', 'https://raw.githubusercontent.com/').replace('/blob/', '/')
    with urllib.request.urlopen(url, timeout=90) as response: content = response.read().decode()
    symbol = item['source_symbol']
    lines = [i for i, line in enumerate(content.splitlines(), 1) if symbol in line]
    if not lines: raise AssertionError('源码不含目标符号：' + item['module'] + ' ' + symbol)
    return {'课程':item['module'],'固定源码':link,'符号':symbol,'匹配行':lines,'状态':'HTTP读取与符号检查通过，未运行断点'}
with ThreadPoolExecutor(max_workers=6) as pool:
    result = list(pool.map(check, json.loads((ROOT/'authoring/manifest.json').read_text())))
(DEST/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
for item in result: print(item['课程'], item['匹配行'], flush=True)
