#!/usr/bin/env python3
"""只读控制 ref；记录仅能授权本次画面中的三个限定语义动作。"""
from __future__ import annotations
import argparse, base64, hashlib, json, os, re, time, urllib.error, urllib.request, tempfile
from pathlib import Path

EUA_SHA256 = '96530426ef62cd0eca629350c3ab5afb552c518868a0edbbce85ea5e0f713516'
CONTROL_REF = 'academy-control/eua-ui'
ACTIONS = {1: 'CHECK_EUA', 2: 'CONTINUE_EUA', 3: 'DECLINE_USAGE'}
FIELDS = {'schema', 'run_id', 'run_attempt', 'stage', 'screenshot_sha256', 'eua_sha256', 'action'}


def atomic_json(path,value):
    # 同目录临时文件完整落盘后，以不覆盖目标的硬链接原子发布。
    fd,name=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,ensure_ascii=False,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        os.link(name,path)
    finally:os.unlink(name)


def strict_json(data):
    if len(data) > 4096:
        raise ValueError('控制记录过大')
    def unique(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('重复字段')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def validate_control(value, expected):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('控制字段不符')
    if type(value['schema']) is not int or value['schema'] != 1:
        raise ValueError('控制版本不符')
    if type(value['stage']) is not int or value['stage'] not in ACTIONS:
        raise ValueError('阶段不符')
    for key in ('run_id', 'run_attempt'):
        if not isinstance(value[key], str) or not re.fullmatch(r'[1-9][0-9]{0,19}', value[key]):
            raise ValueError('运行标识不符')
    if value['eua_sha256'] != EUA_SHA256 or value['action'] != ACTIONS[value['stage']]:
        raise ValueError('协议或动作不符')
    if not isinstance(value['screenshot_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', value['screenshot_sha256']):
        raise ValueError('截图摘要不符')
    if value != {key: expected[key] for key in FIELDS}:
        raise ValueError('拒绝过期、异次运行或不同画面的控制记录')
    return value


def checked_budget(record,seconds,observed):
    if seconds not in (300,3600) or set(record)!={'monotonic_deadline','budget_seconds','owner'}:
        raise ValueError('预算记录结构不符')
    if type(record['budget_seconds']) is not int or record['budget_seconds']!=seconds:
        raise ValueError('子阶段预算不得延长')
    owner=record['owner']
    if not isinstance(owner,dict) or set(owner) not in ({'pid','start_time','uid','pgrp','session'}, {'pid','start_time','uid','pgrp','session','ppid'}):
        raise ValueError('预算拥有者身份不符')
    if any(type(owner[key]) is not int or owner[key]<0 for key in owner if key!='start_time'):
        raise ValueError('预算拥有者字段不符')
    if not isinstance(owner['start_time'],str) or not re.fullmatch(r'[0-9]{1,20}',owner['start_time']):
        raise ValueError('启动时间格式不符')
    if any(observed.get(key)!=value for key,value in owner.items()):raise ValueError('预算拥有者已被替换')
    deadline=int(owner['start_time'])/os.sysconf('SC_CLK_TCK')+seconds
    if record['monotonic_deadline']!=deadline:raise ValueError('绝对截止已被重置或延长')
    return deadline


def read_ui_deadline(root):
    from ui_session import process_info
    value=strict_json((root/'ui-deadline.json').read_bytes())
    return checked_budget(value,300,process_info(value['owner']['pid']))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('控制读取不允许重定向')


def fetch_control(repository, run_id, attempt, stage, token, timeout):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('仓库标识不符')
    # 路径含本次身份与阶段：旧运行及旧阶段不会进入候选，404 仅表示尚未批准。
    name = f'{run_id}-{attempt}-{stage}.json'
    url = f'https://api.github.com/repos/{repository}/contents/{name}?ref={CONTROL_REF}'
    request = urllib.request.Request(url, headers={'Accept':'application/vnd.github+json',
        'Authorization':f'Bearer {token}', 'X-GitHub-Api-Version':'2022-11-28'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            body = response.read(16385)
    except urllib.error.HTTPError as exc:
        if exc.code == 404: return None
        raise ValueError(f'控制读取 HTTP {exc.code}') from None
    if len(body) > 16384: raise ValueError('控制 API 响应过大')
    item = json.loads(body)
    if item.get('type') != 'file' or item.get('encoding') != 'base64' or item.get('size', 4097) > 4096:
        raise ValueError('控制对象格式不符')
    payload = base64.b64decode(item['content'].replace('\n',''), validate=True)
    if len(payload) != item['size']: raise ValueError('控制对象长度不符')
    return strict_json(payload)


def receive(root, stage):
    stage_dir = root / f'stage-{stage}'
    expected = json.loads((stage_dir / 'request.json').read_bytes())
    deadline = read_ui_deadline(root)
    output = stage_dir/'control.json'
    if output.exists(): raise ValueError('动作已经提交，不重复执行')
    while time.monotonic() < deadline:
        remaining = deadline-time.monotonic()
        value = fetch_control(os.environ['GITHUB_REPOSITORY'], expected['run_id'], expected['run_attempt'],
                              stage, os.environ['GH_TOKEN'], min(5, remaining))
        if value is not None:
            validate_control(value, expected)
            if time.monotonic() >= deadline: raise TimeoutError('UI 总预算耗尽')
            atomic_json(output,value)
            return
        time.sleep(min(2, max(0,deadline-time.monotonic())))
    raise TimeoutError('UI 总预算耗尽；未写动作记录')


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--stage',type=int,choices=tuple(ACTIONS),required=True)
    args=parser.parse_args()
    receive(args.root,args.stage)
