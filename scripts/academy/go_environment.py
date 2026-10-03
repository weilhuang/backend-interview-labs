"""Only propagate verified, current-attempt Go paths; never inherit Go/proxy settings."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from safe_io import absolute, read_regular, validate_directory

MODULE_PATHS = ('go-course/http/gin-pipeline/go/go.mod', 'go-course/http/gin-pipeline/go/go.sum')


def require(ok, message):
    if not ok: raise ValueError(message)


def unique_pairs(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'duplicate Go proof key'); result[key]=value
    return result


def read_json(path):
    return json.loads(read_regular(path,limit=1024*1024),object_pairs_hook=unique_pairs)


def validated_go_environment(env=None, required=False):
    env=os.environ if env is None else env
    supplied={key:env.get(key) for key in ('GO_EXECUTABLE','GO_MODULE_CACHE')}
    if all(value is None for value in supplied.values()) and not required:return {}
    require(all(isinstance(value,str) and value and len(value)<=1024 and not re.search(r'[\x00-\x20\x7f]',value) for value in supplied.values()),'both explicit Go paths are required')
    for value in supplied.values():
        require(Path(value).is_absolute() and '..' not in Path(value).parts,'Go paths must be absolute without traversal')
    for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):
        require(isinstance(env.get(key),str) and re.fullmatch(r'[1-9][0-9]{0,19}',env[key]),'Go proof requires typed current run identity')
    temp=env.get('RUNNER_TEMP');workspace=env.get('GITHUB_WORKSPACE')
    require(isinstance(temp,str) and Path(temp).is_absolute() and isinstance(workspace,str) and Path(workspace).is_absolute(),'Go proof requires absolute runner/workspace roots')
    temp=absolute(temp);repo=absolute(workspace);validate_directory(temp);validate_directory(repo)
    root=temp/('academy-go-'+env['GITHUB_RUN_ID']+'-'+env['GITHUB_RUN_ATTEMPT'])
    executable=root/'go/bin/go';cache=root/'module-cache'
    require(supplied=={'GO_EXECUTABLE':str(executable),'GO_MODULE_CACHE':str(cache)},'Go paths are not owned by current attempt')
    validate_directory(root);validate_directory(cache)
    info=executable.stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and info.st_mode & 0o111 and not info.st_mode & 0o022,'Go executable must be a regular non-writable executable')
    proof=read_json(root/'bootstrap.json');pins=read_json(Path(__file__).with_name('go-toolchain.json'))
    require(proof.get('schema_version')==1 and proof.get('status')=='prepared'
            and proof.get('version')==pins['version']
            and proof.get('version_output')=='go version go'+pins['version']+' '+pins['platform'], 'Go compiler/cache proof version mismatch')
    require(proof.get('run_id')==env['GITHUB_RUN_ID'] and proof.get('run_attempt')==env['GITHUB_RUN_ATTEMPT'],'Go proof belongs to another run/attempt')
    require(proof.get('executable')==str(executable) and proof.get('module_cache')==str(cache),'Go proof path mismatch')
    require(proof.get('archive')=={key:pins[key] for key in ('url','sha256','size_bytes')},'Go official archive proof mismatch')
    digest=hashlib.sha256(read_regular(executable,limit=64*1024*1024)).hexdigest()
    require(proof.get('executable_sha256')==digest,'Go executable changed since verified preparation')
    inputs=read_json(repo/'authoring/unified-course/manifest.json')
    expected=inputs.get('expected_manifest',{});overlay=inputs.get('overlay_manifest',{})
    module_inputs={name:hashlib.sha256(read_regular(repo/'authoring/unified-course/overlay'/name,limit=1024*1024)).hexdigest() for name in MODULE_PATHS}
    require(all(expected.get(name)==digest==overlay.get(name) for name,digest in module_inputs.items()),'Go module inputs differ from sealed source')
    require(proof.get('module_inputs')==module_inputs,'Go prepared cache uses different locked module inputs')
    return supplied
