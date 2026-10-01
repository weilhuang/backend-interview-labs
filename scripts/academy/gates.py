#!/usr/bin/env python3
"""Read-only, fail-closed gates for an unchanged official Academy archive.

Never serializes an Academy archive and never decrypts official content. Actual
plaintext is inspected only after the official plugin imports it. JSON fixtures
exercise the parser, not the IDE.
"""
from __future__ import annotations
import base64
import hashlib
import json
import re
import html
import io
from pathlib import Path
import stat
import zipfile
import yaml
from safe_io import read_regular, replace_regular, validate_directory

COUNTS = {'courses': 1, 'sections': 11, 'tasks': 84, 'placeholders': 136}
WRAPPER_EXCLUSIONS = {'gradlew', 'gradlew.bat', 'gradle/wrapper/gradle-wrapper.jar'}

def official_exclusion_reason(name):
    parts=Path(name).parts; base=parts[-1]
    if base in {'.courseignore','gradlew','gradlew.bat','gradle-wrapper.jar','local.properties','EduTestRunner.java'}:
        return 'Pinned official MUST_EXCLUDE file rule'
    if set(parts[:-1]) & {'build','out','gradle'} and base != 'gradle-wrapper.properties':
        return 'Pinned official MUST_EXCLUDE generated-directory rule'
    return None

class GateError(ValueError): pass

def require(ok, message):
    if not ok: raise GateError(message)

def sha(data): return hashlib.sha256(data).hexdigest()
def dump(path, data):
    path = Path(path); validate_directory(path.parent)
    replace_regular(path,(json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode())

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate JSON key: {key}')
        result[key] = value
    return result

def read_json(path):
    return json.loads(read_regular(path,limit=8*1024*1024).decode('utf-8'), object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(GateError(f'invalid JSON constant: {value}')))

class UniqueLoader(yaml.SafeLoader): pass

def yaml_mapping(loader, node, deep=False):
    pairs = [(loader.construct_object(k, deep=deep), loader.construct_object(v, deep=deep)) for k, v in node.value]
    return unique_pairs(pairs)
UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, yaml_mapping)

def read_yaml(path):
    value = yaml.load(read_regular(path,limit=8*1024*1024).decode('utf-8'), Loader=UniqueLoader)
    require(isinstance(value, dict), f'not a YAML mapping: {path}')
    return value

def safe_name(name):
    require(isinstance(name, str) and name and not name.startswith('/') and '\\' not in name
            and ':' not in name and all(p not in ('', '.', '..') for p in name.split('/')), f'unsafe path: {name!r}')
    return name

def local_file(root, name):
    path = root / safe_name(name)
    require(path.resolve().is_relative_to(root.resolve()), f'path escaped root: {name}')
    require(path.is_file() and not path.is_symlink(), f'not a regular file: {name}')
    require(not any(p.is_symlink() for p in path.parents if p != root.parent), f'symlink parent: {name}')
    return path

def learner_content(raw, placeholders):
    text = raw.decode('utf-8').replace('\r\n', '\n')
    source = text.encode('utf-16-le'); end_before = 0; spans = []
    delta = 0; expected = []
    for p in placeholders:
        start, length, hint = p['offset'], p['length'], p['placeholder_text']
        require(type(start) is int and type(length) is int and start >= end_before and length > 0,
                'invalid or overlapping source placeholder')
        end = start + length; require(end * 2 <= len(source), 'placeholder exceeds file')
        answer = source[start*2:end*2].decode('utf-16-le')
        require(isinstance(hint, str) and hint and answer != hint, 'placeholder is empty or reference solution')
        length_hint = len(hint.encode('utf-16-le')) // 2
        expected.append({'offset': start + delta, 'length': length_hint, 'placeholder_text': hint,
                         'author_offset':start,'author_length':length,'answer_sha256': sha(answer.encode()), 'answer': answer})
        spans.append((start, end, hint)); delta += length_hint - length; end_before = end
    for start, end, hint in reversed(spans):
        source = source[:start*2] + hint.encode('utf-16-le') + source[end*2:]
    return source.decode('utf-16-le').encode('utf-8'), expected

def build_contract(author):
    """Expected task suites use presentableName; containers use their path names."""
    validate_directory(author)
    author = Path(author).resolve(); meta = read_yaml(author/'course-info.yaml')
    course_map = read_json(author/'authoring/course-map.json')
    require(course_map.get('schema_version') == 1 and course_map.get('course_id') == 'backend-interview', 'unknown course-map schema')
    require(meta.get('type')=='marketplace' and meta.get('programming_language') == 'Java' and meta.get('language') == 'Chinese', 'wrong course type/language')
    require(meta.get('environment_settings', {}).get('jvm_language_level') == 'JDK_21', 'JDK21 metadata missing')
    require(meta.get('yaml_version') == 2, 'explicit additional_files requires yaml_version 2')
    sections = meta['content']; require(len(sections) == len(set(sections)) == 11, 'expected 11 unique sections')
    tasks=[]; files={}; containers={}; container_contents={}; source_snap={}
    for path in author.rglob('*'):
        if path.is_file() and not {'.idea','.gradle','build','__pycache__'}.intersection(path.relative_to(author).parts):
            require(not path.is_symlink(), f'symlink source: {path}')
            source_snap[path.relative_to(author).as_posix()] = sha(path.read_bytes())
    for sec in sections:
        safe_name(sec); require('/' not in sec, 'section is not a direct child')
        sm = read_yaml(author/sec/'section-info.yaml'); containers[sec] = sm.get('custom_name'); container_contents[sec]=sm['content']
        require(len(sm['content']) == len(set(sm['content'])), 'duplicate lessons')
        for les in sm['content']:
            safe_name(les); require('/' not in les, 'lesson is not a direct child')
            lp=f'{sec}/{les}'; lm=read_yaml(author/lp/'lesson-info.yaml'); containers[lp]=lm.get('custom_name'); container_contents[lp]=lm['content']
            require(lm.get('type') != 'framework', 'framework lessons need a separate native checker')
            require(len(lm['content']) == len(set(lm['content'])), 'duplicate task names')
            for task in lm['content']:
                safe_name(task); require('/' not in task, 'task is not a direct child')
                tp=f'{lp}/{task}'; tm=read_yaml(author/tp/'task-info.yaml'); require(tm['type']=='edu', 'non-edu task')
                label=tm.get('custom_name') or task; suite=['root_node',meta['title'],sec,les,label]
                description=local_file(author,tp+'/task.md').read_text()
                outside_code=re.sub(r'```.*?```','',description,flags=re.S)
                expected_links=sorted(set(html.unescape(u) for u in re.findall(r'!?\[[^\]\n]*\]\((https?://[^\s)]+)\)',outside_code)))
                require(expected_links, 'every V1 task must have an explicit HTTP source link for coverage: '+tp)
                task_entry={'expected_link_urls':expected_links,'path':tp, 'suite':suite, 'custom_name':tm.get('custom_name'), 'files':{},
                            'description_sha256':sha(local_file(author,tp+'/task.md').read_bytes())}
                for f in tm['files']:
                    rel=f['name']; path=f'{tp}/{safe_name(rel)}'; require(path not in files,'duplicate task file')
                    raw=local_file(author,path).read_bytes(); ps=f.get('placeholders',[])
                    learner, expected = learner_content(raw,ps) if ps else (raw,[])
                    record={'author_sha256':sha(raw),'learner_sha256':sha(learner),'placeholders':expected,
                            'visible':f.get('visible',False),'binary':f.get('is_binary',False)}
                    require(record['visible'] is True,'task asset not visible')
                    files[path]=record; task_entry['files'][rel]=record
                task_entry['placeholder_count']=sum(len(f['placeholders']) for f in task_entry['files'].values())
                tasks.append(task_entry)
    require(len(tasks)==84 and len({tuple(t['suite']) for t in tasks})==84, 'missing/ambiguous task report paths')
    require(sum(t['placeholder_count'] for t in tasks)==136, 'expected 136 placeholders')
    mapped={t['path']:t['placeholders'] for t in course_map['tasks']}
    require(len(mapped)==len(course_map['tasks'])==84 and mapped=={t['path']:t['placeholder_count'] for t in tasks},'course-map coverage drift')
    require({s['path'] for s in course_map['sections']}==set(sections), 'course-map section drift')
    additional=[]; exclusions=[]
    for f in meta['additional_files']:
        name=safe_name(f['name']); require(name not in additional and name not in files,'duplicate additional file')
        additional.append(name); raw=local_file(author,name).read_bytes()
        reason=official_exclusion_reason(name)
        if reason: exclusions.append({'path':name,'reason':reason})
        else:
            files[name]={'author_sha256':sha(raw),'learner_sha256':sha(raw),'placeholders':[], 'binary':f.get('is_binary',False)}
    require({'settings.gradle','build.gradle','gradle.properties','gradle/wrapper/gradle-wrapper.properties'}<=set(files), 'missing build files')
    return {'schema_version':1,'counts':COUNTS,'course_metadata':{k:meta[k] for k in ('type','language','programming_language')},'title':meta['title'],'sections':sections,'containers':containers,'container_contents':container_contents,
            'tasks':tasks,'files':files,'additional_files':[n for n in additional if not official_exclusion_reason(n)],'official_exclusions':exclusions,
            'source_snapshot':source_snap,'course_map_sha256':sha((author/'authoring/course-map.json').read_bytes()),
            'source_manifest_sha256':sha((author/'authoring/source-provenance.json').read_bytes())}

def redact_contract(contract):
    value=json.loads(json.dumps(contract))
    for f in value['files'].values():
        for p in f['placeholders']: p.pop('answer',None)
    for t in value['tasks']:
        for f in t['files'].values():
            for p in f['placeholders']: p.pop('answer',None)
    return value

def validate_report(report, contract):
    """Root is concrete ValidationSuite (no discriminator); child nodes have type."""
    expected={tuple(t['suite']):t['path'] for t in contract['tasks']}
    require(len(expected)==84,'expected exactly 84 unique tasks')
    require(isinstance(report,dict) and set(report)=={'name','children'} and report['name']=='root_node','unknown root report schema')
    seen={}; links=[]; suites=set()
    allowed_suites={tuple(t['suite'][:n]) for t in contract['tasks'] for n in range(1,6)}
    def walk(node,parent=(),root=False):
        require(isinstance(node,dict),'node is not an object'); name=node.get('name')
        require(isinstance(name,str) and name,'empty node name'); here=(*parent,name)
        kind='suite' if root else node.get('type')
        if kind=='suite':
            require(set(node)==({'name','children'} if root else {'type','name','children'}),'unknown suite fields')
            require(here not in suites,'duplicate suite: '+repr(here)); suites.add(here)
            require(here in allowed_suites or (name=='Task description links' and parent in expected),'unexpected suite: '+repr(here))
            children=node['children']; require(isinstance(children,list) and children,'empty suite: '+repr(here))
            for child in children: walk(child,here)
        elif kind=='case':
            require(set(node)=={'type','name','result'},'unknown case fields')
            result=node['result']; require(isinstance(result,dict),'invalid case result'); state=result.get('type')
            require(state in {'success','failed','ignored'},'unknown result type')
            allowed={'success':{'type'},'ignored':{'type','message'},'failed':{'type','message','details','diff'}}[state]
            require(set(result)<=allowed and (state=='success' or isinstance(result.get('message'),str)),'unknown result fields')
            if name=='Tests' and parent in expected:
                require(parent not in seen,'duplicate Tests case');seen[parent]={'task':expected[parent],'result':state}
            elif parent and parent[-1]=='Task description links' and parent[:-1] in expected:
                links.append({'task':expected[parent[:-1]],'link':name,'result':state})
            else: raise GateError('unexpected case: '+repr(here))
        else: raise GateError('unknown validation node type')
    walk(report,root=True)
    missing=sorted('/'.join(p) for p in set(expected)-set(seen))
    tests_pass=not missing and len(seen)==84 and all(v['result']=='success' for v in seen.values())
    expected_links={t['path']:set(t.get('expected_link_urls',[])) for t in contract['tasks']}
    require(all(expected_links.values()), 'expected per-task link coverage is missing')
    observed_links={t['path']:{x['link'] for x in links if x['task']==t['path']} for t in contract['tasks']}
    missing_links={p:sorted(urls-observed_links[p]) for p,urls in expected_links.items() if urls-observed_links[p]}
    link_pass=not missing_links and all(v['result']=='success' for v in links)
    return {'status':'PASS' if tests_pass and link_pass else 'FAIL',
            'native_tests':{'status':'PASS' if tests_pass else 'FAIL','expected':84,'observed':len(seen),
                            'missing':missing,'cases':list(seen.values())},
            'description_links':{'status':'PASS' if link_pass else 'FAIL','expected_tasks':len(expected_links),'observed_tasks':sum(bool(x) for x in observed_links.values()),'missing':missing_links,'observed':len(links),'cases':links},
            'native_ui_check_reset':'NOT_RUN','negative_controls':'NOT_RUN_BY_THIS_COMMAND'}

def inspect_archive(archive,contract,pins):
    archive_bytes=read_regular(archive,limit=128*1024*1024)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        infos=z.infolist(); names=[i.filename for i in infos]
        require(len(names)==len(set(names)),'duplicate archive member')
        require(sum(i.file_size for i in infos)<256*1024*1024,'archive expands beyond 256MiB')
        for i in infos:
            safe_name(i.filename); require(not stat.S_ISLNK(i.external_attr>>16),'archive symlink')
        require(z.testzip() is None,'ZIP CRC failure')
        meta=json.loads(z.read('course.json'),object_pairs_hook=unique_pairs)
        require(meta.get('version')==pins['academy']['archive_schema_version'],'archive schema version drift')
        require(meta.get('edu_plugin_version')==pins['academy']['version'],'wrong exporter version')
        require(meta.get('title')==contract['title'] and meta.get('programming_language_id')=='JAVA' and meta.get('language')=='zh','course identity mismatch')
        require(meta.get('environment_settings',{}).get('jvm_language_level')=='JDK_21','archive JDK mismatch')
        sections=meta['items'];require([s['title'] for s in sections]==contract['sections'],'archive section order/coverage')
        actual={}; ids=[]
        for s in sections:
            ids.append(s.get('id')); require('task_list' not in s,'top-level lesson is unsupported')
            require(s.get('custom_name')==contract['containers'][s['title']], 'section custom name changed')
            for l in s['items']:
                ids.append(l.get('id'));lp=s['title']+'/'+l['title']
                require(l.get('custom_name')==contract['containers'].get(lp),'lesson custom name changed')
                for t in l['task_list']:
                    ids.append(t.get('id'));tp=lp+'/'+t['name'];require(tp not in actual,'duplicate archive task');actual[tp]=t
        require(all(type(i) is int and i>0 for i in ids) and len(ids)==len(set(ids)),'invalid/duplicate generated study ids')
        require(set(actual)=={t['path'] for t in contract['tasks']},'archive task coverage mismatch')
        for t in contract['tasks']:
            item=actual[t['path']];require(item.get('custom_name')==t['custom_name'] and item.get('task_type')=='edu' and item.get('description_format')=='MD','task identity/description format changed')
            require(sha(item['description_text'].encode())==t['description_sha256'],'task description changed')
            require(set(item['files'])==set(t['files']),'archive task files mismatch')
            for rel,expected in t['files'].items():
                f=item['files'][rel]; require(f.get('name')==rel and f.get('is_visible') is True and f.get('is_binary',False)==expected['binary'],'archive task file metadata mismatch')
                ph=f.get('placeholders',[]);require(len(ph)==len(expected['placeholders']),'archive placeholder count changed')
                for got,want in zip(ph,expected['placeholders']):
                    require(all(type(got.get(k)) is type(want[k]) and got.get(k)==want[k] for k in ('offset','length','placeholder_text')),'archive learner placeholder span changed')
                    encrypted=got.get('possible_answer');require(isinstance(encrypted,str) and encrypted!=want.get('answer'),'plaintext/missing possible_answer')
                    try: decoded=base64.b64decode(encrypted,validate=True)
                    except ValueError as exc: raise GateError('possible_answer is not base64 ciphertext') from exc
                    require(len(decoded)>0 and len(decoded)%16==0,'invalid encrypted answer block size')
        additional=[f['name'] for f in meta['additional_files']]
        require(len(additional)==len(set(additional)) and set(additional)==set(contract['additional_files']),'additional file loss/unexpected additions')
        expected_names={'course.json'}|{'contents/'+name for name in contract['files']}
        require(set(names)==expected_names,'unexpected or missing archive member (including stale source/release artifacts)')
        for path,expected in contract['files'].items():
            data=z.read('contents/'+path); require(data and len(data)%16==0,'content is not encrypted blocks: '+path)
            require(sha(data) not in {expected['author_sha256'],expected['learner_sha256']},'content unexpectedly plaintext: '+path)
    return {'status':'PASS','archive_sha256':sha(archive_bytes),'counts':COUNTS,'files':len(contract['files']),
            'plugin':pins['academy']['version'],'bytes':len(archive_bytes)}

def inspect_import(root,contract,mode):
    root=Path(root);validate_directory(root);mismatches=[];observed=[]
    for name,expected in contract['files'].items():
        path=local_file(root,name);actual=sha(read_regular(path,limit=32*1024*1024));wanted=expected['learner_sha256' if mode=='student' else 'author_sha256']
        if actual!=wanted:mismatches.append(name)
        observed.append({'path':name,'sha256':actual})
    require(not mismatches,mode+' import plaintext mismatch: '+repr(mismatches))
    cm=read_yaml(root/'course-info.yaml');require(cm['title']==contract['title'] and cm['content']==contract['sections'],'import course metadata mismatch')
    require(all(cm.get(k)==v for k,v in contract['course_metadata'].items()),'import course type/language changed')
    require(cm.get('environment_settings',{}).get('jvm_language_level')=='JDK_21','import course JDK changed')
    actual_tasks={p.parent.relative_to(root).as_posix() for p in root.rglob('task-info.yaml')
                  if not {'.idea','.gradle','build'}.intersection(p.relative_to(root).parts)}
    require(actual_tasks=={t['path'] for t in contract['tasks']}, 'import orphan/missing task metadata')
    for rel,names in contract['container_contents'].items():
        kind='section' if '/' not in rel else 'lesson'
        meta=read_yaml(root/rel/(kind+'-info.yaml'))
        require(meta['content']==names and meta.get('custom_name')==contract['containers'][rel], 'import container metadata mismatch')
    for t in contract['tasks']:
        require(sha(read_regular(local_file(root,t['path']+'/task.md'),limit=8*1024*1024))==t['description_sha256'],'import task instructions missing/changed')
        tm=read_yaml(root/t['path']/'task-info.yaml');require(tm.get('type')=='edu' and tm.get('custom_name')==t['custom_name'],'import task type/name mismatch')
        require(isinstance(tm.get('files'),list), 'import files must be a list')
        declared={f['name']:f for f in tm['files']};require(len(declared)==len(tm['files']) and set(declared)==set(t['files']),'duplicate/missing import declared task files')
        for rel,expected in t['files'].items():
            require(declared[rel].get('visible') is expected['visible'] and declared[rel].get('is_binary',False) is expected['binary'], 'import file visibility/binary metadata changed')
            require(declared[rel].get('learner_created',False) is False,'import file unexpectedly learner-created')
            got=declared[rel].get('placeholders',[]); require(len(got)==len(expected['placeholders']),'import placeholder count mismatch')
            if mode=='student':
                for p,want in zip(got,expected['placeholders']):
                    require(all(type(p.get(k)) is type(want[k]) and p.get(k)==want[k] for k in ('offset','length','placeholder_text')),'import learner span mismatch')
                    require(p.get('status')=='Unchecked' and p.get('initial_state')=={'offset':want['offset'],'length':want['length']},'student state is not fresh')
                if got: require(tm.get('status')=='Unchecked','task is not fresh')
            else:
                for p,want in zip(got,expected['placeholders']):
                    require(type(p.get('offset')) is int and type(p.get('length')) is int and p.get('offset')==want['author_offset'] and p.get('length')==want['author_length'] and p.get('placeholder_text')==want['placeholder_text'], 'educator placeholder span mismatch')
    return {'status':'PASS','mode':mode,'files':observed,'counts':COUNTS}

def inspect_author_changes(root,contract):
    after={p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()
           and not {'.idea','.gradle','build','__pycache__'}.intersection(p.relative_to(root).parts)}
    before=contract['source_snapshot']; changed=[n for n in before if before[n]!=after.get(n)]
    # Generated IDs/remote metadata are allowed only in the disposable author staging.
    allowed={'course-info.yaml','section-info.yaml','lesson-info.yaml','task-info.yaml',
             'course-remote-info.yaml','section-remote-info.yaml','lesson-remote-info.yaml','task-remote-info.yaml'}
    require(all(Path(n).name in allowed for n in changed),'official export changed source assets: '+repr(changed))
    added=sorted(set(after)-set(before));require(all(Path(n).name in allowed for n in added),'unexpected staged author files: '+repr(added))
    return {'status':'PASS','changed_metadata':changed,'added_metadata':added,'source_checkout':'NOT_USED_AS_CLI_TARGET'}
