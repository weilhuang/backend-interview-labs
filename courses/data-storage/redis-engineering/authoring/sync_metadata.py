#!/usr/bin/env python3
"""维护真实Academy元数据与公开标准解；不把此脚本输出称为IDE验收。"""
from pathlib import Path
import yaml,json,re
ROOT=Path(__file__).resolve().parents[1]
UNITS=[('01-structures','数据结构与原子命令','Structures'),('02-expiry','过期淘汰与容量','Expiry'),('03-stampede','穿透击穿与雪崩','Stampede'),('04-consistency','数据库与缓存竞态','Consistency'),('05-replication','持久化复制与故障转移','Replication'),('06-leases','分布式租约与fencing','Leases'),('07-resilience','缓存服务故障演练','Resilience')]
for unit,title,name in UNITS:
    root=ROOT/'redis'/unit; source=root/'src/labs'/f'{name}.java'; text=source.read_text()
    marker=re.search(r'(?m)^([ \t]*)// 学员实现开始\n',text); assert marker
    begin=marker.end(); indent=marker.group(1); end=text.index(indent+'// 学员实现结束',begin)
    files=[]
    for path in sorted(root.rglob('*.java')):
        item={'name':str(path.relative_to(root)),'visible':True}
        if path==source:item['placeholders']=[{'offset':begin,'length':end-begin,'placeholder_text':indent+'throw new UnsupportedOperationException("TODO：按中文步骤实现核心方法");\n'}]
        files.append(item)
    files.append({'name':'solution.md','visible':True})
    (root/'task-info.yaml').write_text(yaml.safe_dump({'type':'edu','custom_name':f'C07-{unit[:2]} · {title}','files':files},allow_unicode=True,sort_keys=False))
    (root/'solution.md').write_text(f'# C07-{unit[:2]} 公开标准解\n\n完整参考实现如下，与src/labs/{name}.java自动同步。逐步讲解、复杂度、边界和替代方案在题面。学习者可随时查看；独立回测建议换数据/故障点后重写。\n\n```java\n'+text+'```\n')
(ROOT/'redis/lesson-info.yaml').write_text(yaml.safe_dump({'custom_name':'Redis工程：从命令契约到缓存故障闭环','content':[x[0] for x in UNITS]},allow_unicode=True,sort_keys=False))
files=[]
for name in ['README.md','中文阶段报告.md','SOURCES.md','THIRD_PARTY_NOTICES.md','LICENSE-JetBrains-template','build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat']:
    files.append({'name':name})
for folder in ['gradle','support','authoring']:
    for path in sorted((ROOT/folder).rglob('*')):
        if path.is_file() and 'build' not in path.parts and '__pycache__' not in path.parts:
            item={'name':str(path.relative_to(ROOT))}
            if path.suffix=='.jar':item['is_binary']=True
            files.append(item)
(ROOT/'course-info.yaml').write_text(yaml.safe_dump({'type':'marketplace','title':'Java后端实验室 · C07 Redis与缓存一致性','language':'Chinese','summary':'完整七单元：真实Redis与MySQL、可控竞态、版本失效恢复、双节点复制和租约fencing。全部测试、调用端及标准解公开。无Docker时仅可做纯Java验证。','programming_language':'Java','content':['redis'],'environment_settings':{'jvm_language_level':'JDK_21'},'additional_files':files,'yaml_version':2},allow_unicode=True,sort_keys=False))
print('已同步七题、公开解答与课程元数据')
