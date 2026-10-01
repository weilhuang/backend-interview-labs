#!/usr/bin/env python3
"""Summarize this workflow only. Required skipped/cancelled jobs never pass the gate."""
from __future__ import annotations
import json
import os
from pathlib import Path
from plan import SUITES


def finish(plan: dict, results: dict, env: dict) -> tuple[dict, list[str]]:
    errors = []
    for job in ('plan', 'static'):
        if results.get(job, {}).get('result') != 'success':
            errors.append(f'{job}: 未通过')
    if set(plan.get('suites', {})) != set(SUITES):
        errors.append('计划必须完整覆盖全部已配置suite，缺项/未知项不能当成未运行')
    evidence = {key: plan.get(key) for key in ['repository', 'tested_sha', 'head_sha', 'full']}
    evidence.update(schema_version=1, run_id=int(env['GITHUB_RUN_ID']),
                    run_attempt=int(env['GITHUB_RUN_ATTEMPT']), suites={})
    for suite in SUITES:
        row = plan.get('suites', {}).get(suite, {})
        result = results.get(suite, {}).get('result', 'missing')
        if row.get('decision') == 'run':
            status = 'passed' if result == 'success' else result
            if result != 'success':
                errors.append(f'{suite}: 要求真实执行，但结果是 {result}')
        elif row.get('decision') == 'not-required' and result == 'skipped':
            status = 'not-run'
        else:
            status = 'invalid'
            errors.append(f"{suite}: 计划/执行不一致 {row.get('decision')}/{result}")
        evidence['suites'][suite] = {'status': status, 'reason': row.get('reason')}
    evidence['errors'] = errors
    return evidence, errors


def main() -> int:
    plan = json.loads(os.environ.get('CI_PLAN') or '{}')
    results = json.loads(os.environ['CI_RESULTS'])
    evidence, errors = finish(plan, results, os.environ)
    output = Path('build/ci/evidence.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    lines = ['## 当前提交的验收结果',
             'passed = 此工作流中的真实任务通过；not-run = 本PR范围外，未运行；没有跨运行结果复用。',
             '局部重试可以沿用同一工作流同一提交已成功的任务；本清单不宣称它们在本次attempt重新执行。']
    lines += [f"- {suite}: **{row['status']}**" for suite, row in evidence['suites'].items()]
    lines += [f'- ERROR: {error}' for error in errors]
    print('\n'.join(lines))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('\n'.join(lines) + '\n')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
