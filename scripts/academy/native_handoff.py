#!/usr/bin/env python3
"""Same-run regular-file handoff of official import bytes; never recreates Academy ZIP."""
import argparse
import io
import json
import os
from pathlib import Path
import stat
import zipfile
from gates import require, read_json, sha, dump, inspect_import, safe_name, unique_pairs
from safe_io import read_regular, write_new, new_directory, validate_directory
MAX_FILE = 128*1024*1024
MAX_TOTAL = 256*1024*1024
MAX_CONTAINER = MAX_TOTAL+8*1024*1024
MAX_FILES = 4000
MAX_PATH_BYTES = 1024

def load_json(data):
    return json.loads(data,object_pairs_hook=unique_pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('invalid JSON constant')))

def permitted(name):
    safe_name(name)
    require(len(name.encode("utf-8")) <= MAX_PATH_BYTES and len(Path(name).parts) <= 32 and all(len(part.encode("utf-8")) <= 255 for part in Path(name).parts), "handoff path limit exceeded")
    require(not set(Path(name).parts)&{'.git','.idea','.gradle','__pycache__','build','node_modules','.env'} and '\x00' not in name,'private/cache/config handoff path forbidden')
    return name

def json_bytes(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()

def import_names(contract):
    names = set(contract['files']) | {'course-info.yaml'}
    names |= {rel+('/section-info.yaml' if '/' not in rel else '/lesson-info.yaml') for rel in contract['container_contents']}
    names |= {task['path']+'/'+name for task in contract['tasks'] for name in ('task-info.yaml','task.md')}
    return sorted(permitted(name) for name in names)

def check_native(native):
    require(native.get('status') == 'PASS' and native.get('final_archive_ready') is True and native.get('phase') == 'full-validation', 'native gates incomplete')
    stages = native.get('stages', {})
    for name in ('archive','student_import','educator_import','gradle_jvm','native_validation'):
        require(stages.get(name, {}).get('status') == 'PASS', 'native stage missing: '+name)
    require(native.get('native_tests') == 'PASS', 'native 84 tests incomplete')
    tests=stages['native_validation'].get('native_tests',{})
    links=stages['native_validation'].get('description_links',{})
    require(tests.get('status')=='PASS' and tests.get('expected')==84 and tests.get('observed')==84 and tests.get('missing')==[] and len(tests.get('cases',[]))==84 and all(row.get('result')=='success' for row in tests['cases']), 'native 84-case execution incomplete')
    require(links.get('status')=='PASS' and links.get('expected_tasks')==84 and links.get('observed_tasks')==84 and links.get('missing')=={} and links.get('cases') and all(row.get('result')=='success' for row in links['cases']), 'native description-link execution incomplete')
    for name in ('official_export_process', 'official_validate_process'):
        require(stages.get(name, {}).get('exit_code') == 0 and stages[name].get('timed_out') is False and stages[name].get('disk_low') is False, 'official process did not complete')

def pack(run, destination):
    validate_directory(run);validate_directory(destination.parent)
    native = read_json(run/'evidence/summary.json');check_native(native)
    contract_bytes = read_regular(run/'evidence/source-contract.json', limit=8*1024*1024)
    contract = load_json(contract_bytes)
    archive = read_regular(run/'dist/backend-interview-academy.zip', limit=MAX_FILE)
    require(sha(archive) == native['stages']['archive']['archive_sha256'], 'official archive changed before handoff')
    files = {'native-summary.json': json_bytes(native), 'source-contract.json':contract_bytes, 'backend-interview-academy.zip':archive}
    modes = {name:0o600 for name in files}
    for mode, folder in (('student','student'), ('educator','validation')):
        root = run/folder;inspect_import(root,contract,mode)
        for name in import_names(contract):
            source = root/name
            data = read_regular(source, limit=32*1024*1024)
            permission = stat.S_IMODE(source.stat(follow_symlinks=False).st_mode)
            require(not permission & 0o7022, 'unsafe imported permission: '+name)
            key = permitted(mode+'/'+name)
            require(len(files)+2 <= MAX_FILES and sum(map(len,files.values()))+len(data) <= MAX_TOTAL, 'handoff size/count bound exceeded')
            files[key]=data; modes[key]=permission
    identity = {key:native[key] for key in ('repository','commit','run_id','run_attempt')}
    identity.update(archive_sha256=sha(archive), contract_sha256=sha(contract_bytes))
    manifest = {'schema_version':2, 'container':'zip-stored', **identity, 'origin':'official-import-snapshot',
        'imports':{'student':'createCourse --local captured archive','educator':'validateCourse --archive same archive'},
        'files':{name:{'sha256':sha(data), 'bytes':len(data), 'mode':modes[name]} for name,data in sorted(files.items())}}
    files['handoff-manifest.json']=json_bytes(manifest);modes['handoff-manifest.json']=0o600
    require(len(files) <= MAX_FILES and sum(map(len,files.values())) <= MAX_TOTAL, 'handoff too large')
    # No directory recursion, IDE profiles, dependency caches, .env or log collection.
    with io.BytesIO() as buffer:
        with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive_file:
            for name,data in sorted(files.items()):
                permitted(name)
                info=zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
                info.create_system=3;info.compress_type=zipfile.ZIP_STORED
                info.external_attr=(stat.S_IFREG|modes[name]) << 16
                archive_file.writestr(info,data)
        payload=buffer.getvalue()
    require(len(payload) <= MAX_CONTAINER, 'handoff container too large')
    write_new(destination,payload)
    return {**identity,'handoff_sha256':sha(payload),'files':len(files),'bytes':len(payload)}

def unpack(archive, output, expected):
    # Ordinary trusted producer -> consumer handoff. No compression or custom parser.
    # The container bound also bounds bytes presented to Python's ZIP parser;
    # entry count and payload bounds are checked before member reads.
    payload=read_regular(archive, limit=MAX_CONTAINER)
    files={};modes={};total=0
    with zipfile.ZipFile(io.BytesIO(payload), mode='r', allowZip64=False) as source:
        entries=source.infolist()
        require(not source.comment and len(entries) <= MAX_FILES, 'handoff entry count/comment invalid')
        names=set()
        for info in entries:
            name=permitted(info.filename)
            mode=info.external_attr >> 16
            require(name not in names and info.create_system == 3 and stat.S_ISREG(mode), 'nonregular/duplicate handoff entry')
            require(info.compress_type == zipfile.ZIP_STORED and info.compress_size == info.file_size, 'only stored handoff entries permitted')
            require(not info.extra and not info.comment and not info.flag_bits & ~0x800 and info.extract_version <= 20, 'unsupported handoff metadata')
            require(0 <= info.file_size <= MAX_FILE and not stat.S_IMODE(mode) & 0o7022, 'unsafe handoff entry')
            total+=info.file_size;require(total <= MAX_TOTAL, 'handoff size bound exceeded')
            names.add(name);modes[name]=stat.S_IMODE(mode)
        for info in entries:
            data=source.read(info)
            require(len(data)==info.file_size, 'handoff entry size changed')
            files[info.filename]=data
    require('handoff-manifest.json' in files,'handoff manifest missing')
    manifest=load_json(files.pop('handoff-manifest.json'))
    require(manifest.get('schema_version')==2 and manifest.get('container')=='zip-stored' and manifest.get('origin')=='official-import-snapshot','wrong handoff schema')
    require(set(files)==set(manifest['files']), 'handoff inventory mismatch')
    for key in ('repository','commit','run_id','run_attempt'):
        require(manifest.get(key)==expected.get(key) and expected.get(key),'foreign run/commit handoff: '+key)
    for name,data in files.items():
        require(manifest['files'][name] == {'sha256':sha(data),'bytes':len(data),'mode':modes[name]},'handoff bytes/mode changed: '+name)
    require(sha(files['backend-interview-academy.zip'])==manifest['archive_sha256'] and sha(files['source-contract.json'])==manifest['contract_sha256'],'handoff provenance mismatch')
    native=load_json(files['native-summary.json']);check_native(native)
    for key in ('repository','commit','run_id','run_attempt'):require(native[key]==manifest[key],'native handoff identity drift')
    contract=load_json(files['source-contract.json'])
    allowed={'backend-interview-academy.zip','source-contract.json','native-summary.json'} | {mode+'/'+name for mode in ('student','educator') for name in import_names(contract)}
    require(set(files)==allowed,'unexpected handoff files')
    require(native['stages']['archive']['archive_sha256']==manifest['archive_sha256'],'native/archive identity mismatch')
    require(all('/'.join(Path(name).parts[:index]) not in files for name in files for index in range(1,len(Path(name).parts))),'file parent collides with directory')
    new_directory(output)
    for name,data in files.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);validate_directory(path.parent);write_new(path,data);os.chmod(path,modes[name],follow_symlinks=False)
    imports={}
    for mode in ('student','educator'):
        result=inspect_import(output/mode,contract,mode)
        imports[mode]={'status':result['status'],'files':len(result['files'])}
    identity={key:manifest[key] for key in ('repository','commit','run_id','run_attempt','archive_sha256','contract_sha256')}
    identity.update(handoff_sha256=sha(payload),image_ledger_sha256=contract['files']['shared/versions.env']['author_sha256'])
    dump(output/'identity.json',identity)
    return identity, native, contract, imports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(pack(a.run,a.output)))
