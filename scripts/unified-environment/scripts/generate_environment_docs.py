#!/usr/bin/env python3
"""只从真实课程映射和环境配置生成说明；不创建另一份可执行版本台账。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import lab


def documents():
    tasks = lab.courses()
    lines = ['# 逐题环境与完整检查映射', '',
             '本页由 `scripts/generate_environment_docs.py` 从 `authoring/course-map.json` 与环境规则生成，不手工维护题目计数、路径或 Gradle 项目名。', '',
             'profile 是可选的手动演示环境。完整 `check` 不使用这些常驻容器，而由课程 Testcontainers 按题目创建隔离实例；基础题不启动容器。', '',
             '| 题目路径（传给 check） | 手动 profile | 实际完整判题任务 | 特殊拓扑 |',
             '| --- | --- | --- | --- |']
    for task in tasks:
        command = lab.check_plan(task)[4:]
        lines.append(f'| `{task["path"]}` | `{lab.profile_for(task)}` | ' + ' '.join('`'+value+'`' for value in command) + ' | ' + lab.topology_note(task) + ' |')
    versions = lab.versions()
    image_lines = ['# 环境配置清单（生成快照）', '',
                   '本页是说明，不参与执行。镜像唯一配置在 `shared/versions.env`；JDK 唯一配置在根 `gradle.properties` 的 `javaVersion`。发布时重新生成并核对。', '',
                   '- JDK：`' + lab.java_version() + '`',
                   '- 镜像台账 SHA256：`' + hashlib.sha256((lab.ROOT/'shared/versions.env').read_bytes()).hexdigest() + '`', '',
                   '| 台账键 | 固定镜像引用 |', '| --- | --- |']
    for key, value in sorted(versions.items()): image_lines.append(f'| `{key}` | `{value}` |')
    image_lines += ['', '标签已固定到完整版本，只有 JAVA_BUILD_IMAGE 额外绑定多架构摘要；完整标签仍可被上游重建。此基线不代表最新版本或无已知漏洞。', '',
                    '## 手动 profile 的容器上限', '',
                    '以下由 Compose 内存上限相加，既非实测常驻占用，也不是 Docker/IDEA/JDK/临时测试容器总峰值。', '',
                    '| profile | 常驻服务 | 内存上限合计 MiB |', '| --- | --- | --- |']
    shared = json.loads((lab.ROOT/'infra/compose.yaml').read_text())['services']
    capstone = json.loads((lab.ROOT/'infra/capstone.compose.yaml').read_text())['services']
    for name, services in lab.PROFILES.items():
        spec = capstone if name == 'capstone' else shared
        total = sum(int(spec[service]['mem_limit'].removesuffix('m')) for service in services)
        image_lines.append(f'| `{name}` | '+('、'.join(services) or '无')+f' | {total} |')
    return {'docs/题目环境映射.md': '\n'.join(lines)+'\n', 'docs/环境配置清单.md': '\n'.join(image_lines)+'\n'}


def main():
    p=argparse.ArgumentParser(description='生成或只读校验环境说明');p.add_argument('--check', action='store_true');args=p.parse_args()
    failed=[]
    for relative, text in documents().items():
        path=lab.ROOT/relative
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != text: failed.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True);path.write_text(text, encoding='utf-8')
    if failed: print('需要重新生成：'+', '.join(failed), file=sys.stderr);return 2
    print('环境说明与实际映射一致' if args.check else '已生成环境说明（未运行 Docker/Java）');return 0


if __name__=='__main__': sys.exit(main())
