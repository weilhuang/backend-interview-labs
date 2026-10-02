#!/usr/bin/env python3
"""核对单课结构、真源保真与实际 Gradle 模型；静态检查不替代原生验收。"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, sys
from pathlib import Path
import yaml

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok, message):
    if not ok: raise ValueError(message)

def validate(root, repo=None, gradle_model=None):
    sys.path.insert(0,str(root/'authoring/quality'))
    from academy_gate import inspect_course
    model=inspect_course(root)
    mapping=json.loads((root/'authoring/course-map.json').read_text())
    require(len(mapping['source_courses'])==9,'来源必须为9个完整V1作者项目')
    require(len(mapping['sections'])==11,'章节计数变化')
    require(len(mapping['tasks'])==84 and len(model['tasks'])==84,'任务计数变化')
    require(sum(len(p) for p in model['placeholders'].values())==136,'练习区计数变化')
    require({t['path'] for t in mapping['tasks']}=={t['path'] for t in model['tasks']},'映射与原生元数据不一致')
    for task in mapping['tasks']:
        require(task['gradle_project']==':'+task['path'].replace('/','-'),'原生Gradle项目命名不符：'+task['path'])
        require(task['placeholders']==next(t['placeholders'] for t in model['tasks'] if t['path']==task['path']),'题目练习区映射不符')
    require(len({t['gradle_project'] for t in mapping['tasks']})==84,'Gradle路径冲突')
    for section in mapping['sections']:
        require((root/section['path']/'section-info.yaml').is_file(),'必须全部使用顶层section')
    require(not any(p.name=='section-info.yaml' and len(p.relative_to(root).parts)>2 for p in root.rglob('section-info.yaml') if 'build' not in p.relative_to(root).parts),'不支持嵌套section')
    require([p.relative_to(root).as_posix() for p in root.rglob('versions.env') if 'build' not in p.relative_to(root).parts]==['shared/versions.env'],'发行镜像台账必须唯一')
    require('javaVersion=21' in (root/'gradle.properties').read_text(),'JDK21入口缺失')
    ledger=json.loads((root/'authoring/dependency-ledger.json').read_text())
    expected_locks={x['gradle_project'][1:]+'.lockfile' for x in mapping['tasks']+mapping['support_projects']}|{'environment-ledger.lockfile'}
    locks=ledger.get('active_lockfiles',[])
    require(len(locks)==90 and {Path(x['path']).name for x in locks}==expected_locks,'统一依赖锁覆盖不完整')
    for entry in locks:
        require(entry['path']=='dependency-locks/'+Path(entry['path']).name,'统一锁路径非法')
        require(digest(root/entry['path'])==entry['sha256'],'统一依赖锁已漂移：'+entry['path'])
    require('lockMode = LockMode.STRICT' in (root/'build.gradle').read_text(),'依赖锁必须使用严格模式')
    provenance=json.loads((root/'authoring/source-provenance.json').read_text())
    checked=0
    for entry in provenance['files']:
        path=root/entry['path']
        if path.suffix=='.java' or path.name in ('task-info.yaml','gradle.lockfile'):
            require(digest(path)==entry['source_sha256'],'保护文件被改变：'+entry['path'])
            if repo: require(digest(repo/entry['source'])==entry['source_sha256'],'作者真源已改变，须重生成：'+entry['source'])
            checked+=1
    gradle='NOT_RUN'
    if gradle_model:
        rows=json.loads(gradle_model.read_text())
        require({r['path'] for r in rows}=={t['path'] for t in mapping['tasks']},'实际Gradle模型未覆盖84题')
        for row in rows:
            expected=next(t for t in mapping['tasks'] if t['path']==row['path'])
            require(row['gradle_project']==expected['gradle_project'],'实际Gradle名不符')
            seen={}
            for source in row['main_sources']:
                path=root/source;text=path.read_text();package=re.search(r'^package\s+([\w.]+)',text,re.M)
                fqn=(package[1]+'.' if package else '')+path.stem
                require(fqn not in seen,f'同模块出现重复类：{row["path"]}: {fqn}')
                seen[fqn]=source
            if row['path'] in ('distributed-course/services/06-transactions','distributed-course/services/07-outbox-cache'):
                require(any('/integrationTest' in p for p in row['grading_classes']),'C10真实判题被降级')
            if row['path'].startswith('capstone/'):
                references={p.split('/')[3] for p in row['main_sources'] if p.startswith('materials/backend-capstone/reference/')}
                require(len(references)==4 and Path(row['path']).name not in references,'C14参考源隔离被破坏')
        gradle='MODEL_PASS'
    return {'status':'PASS','kind':'static-and-model' if gradle_model else 'static-only','courses':1,'sections':11,'tasks':84,'placeholders':136,'protected_files':checked,'assets':len(model['assets']),'gradle':gradle,'native_idea':'NOT_RUN','docker':'NOT_RUN'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--course',type=Path,required=True);p.add_argument('--repo',type=Path);p.add_argument('--gradle-model',type=Path);p.add_argument('--report',type=Path)
    a=p.parse_args()
    if a.report:
        report=a.report.resolve();root=a.course.resolve()
        require(not report.exists(), '报告必须使用独立新文件，拒绝覆盖')
        require(not report.is_relative_to(root), '报告不能写入课程资产目录')
        if a.repo:
            repo=a.repo.resolve()
            require(not report.is_relative_to(repo) or report.is_relative_to(repo/'build'), '仓库内报告只能写入build')
    try:r=validate(a.course.resolve(),a.repo.resolve() if a.repo else None,a.gradle_model)
    except Exception as e:r={'status':'FAIL','error':str(e)}
    text=json.dumps(r,ensure_ascii=False,indent=2)+'\n';print(text)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        with a.report.open('x',encoding='utf-8') as stream:stream.write(text)
    return 0 if r['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
