#!/usr/bin/env python3
"""Copy only bounded no-follow evidence into a new, disjoint artifact directory."""
import argparse
import json
from pathlib import Path
import re
from safe_io import absolute, new_directory, read_regular, validate_directory, write_new
NAMES={'summary.json','toolchain.json','source-ci.json','generation.json','source-contract.json',
       'archive.json','author-changes.json','student-import.json','educator-import.json',
       'student-wrapper-diagnostic.json','educator-wrapper-diagnostic.json',
       'official-validation.json','validation-gate.json','SHA256SUMS','generation.log','failure.log',
       'export.stdout.log','export.stderr.log','validate.stdout.log','validate.stderr.log',
       'export-idea.log','validate-idea.log','export-idea-pretermination.log','validate-idea-pretermination.log','gradle-jvm.jsonl','gradle-jvm-gate.json','unified-source-validation.json','release-gate.json'}
BOOTSTRAP_NAMES={'source-ci.json','bootstrap.json','install.log','go-bootstrap.json'}
MAX_FILE=4*1024*1024

SENSITIVE_KEY = re.compile(r'(?i)(?:[a-z0-9]+[_-])*(?:authorization|password|passwd|secret|token|api[_-]?key|cookie|credentials?|private[_-]?key)(?:[_-][a-z0-9]+)*')


def sanitize_text(text):
    text=re.sub(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)', '[private key redacted]', text, flags=re.S)
    text=re.sub(r'(https?://)[^/\s@]+@',r'\1[redacted]@',text)
    text=re.sub(r'(https?://[^\s?]+)\?[^\s]+',r'\1?[query redacted]',text)
    text=re.sub(r'(?im)((?:set-)?cookie\s*:\s*)[^\r\n]+',r'\1[redacted]',text)
    # Quoted JSON diagnostics and shell/environment assignments may contain spaces.
    text=re.sub(r'(?i)(["\'](?:[a-z0-9]+[_-])*(?:password|passwd|secret|token|api[_-]?key|cookie|authorization|credentials?)(?:[_-][a-z0-9]+)*["\']\s*:\s*)["\'][^"\']*["\']',r'\1"[redacted]"',text)
    text=re.sub(r'(?i)((?:proxy-)?authorization\s*[:=]\s*)(?:(?:Bearer|Basic)\s+)?[^\r\n,;]+',r'\1[redacted]',text)
    text=re.sub(r'(?i)((?:[a-z0-9]+[_-])*(?:password|passwd|secret|token|api[_-]?key|cookie|credentials?)(?:[_-][a-z0-9]+)*\s*[:=]\s*)(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s,;]+)',r'\1[redacted]',text)
    text=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|AKIA[A-Z0-9]{16})\b','[redacted]',text)
    text=re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b','[redacted JWT]',text)
    text=re.sub(r'(?<![\w:/])/(?:Users|home|root|workspace|tmp|opt/hostedtoolcache)(?:/[^\s\'"<>;,\])}]+)+', '[absolute-path]', text)
    text=re.sub(r'\b[A-Za-z]:[\\/](?:[^\s\'"<>;,\])}]+)', '[absolute-path]', text)
    return text


def sanitize_value(value):
    if isinstance(value,str):return sanitize_text(value)
    if isinstance(value,list):return [sanitize_value(v) for v in value]
    if isinstance(value,dict):
        return {sanitize_text(k):('[redacted]' if SENSITIVE_KEY.fullmatch(k) else sanitize_value(v)) for k,v in value.items()}
    return value

def sanitize_log(data):
    return ('[bounded, best-effort redacted diagnostic; never a full profile/environment dump]\n'+sanitize_text(data.decode('utf-8',errors='replace'))).encode()

def collect(run,evidence,bootstrap=None):
    run=absolute(run);evidence=absolute(evidence)
    if run.is_relative_to(evidence) or evidence.is_relative_to(run):raise ValueError('run and artifact output must be disjoint')
    sources=[run/'evidence']
    if bootstrap is not None:sources.append(absolute(bootstrap))
    for src in sources:
        if src.is_relative_to(evidence) or evidence.is_relative_to(src) or run==evidence:
            raise ValueError('evidence source and destination overlap')
        # Parent links are rejected even when a leaf name itself is not a link.
        try:validate_directory(src)
        except FileNotFoundError:pass
    new_directory(evidence)  # No existing output, symlink or previous run may be reused.
    copied=[];omitted=[];output={};hashes={}
    for index,src in enumerate(sources):
        for name in sorted(NAMES if index==0 else BOOTSTRAP_NAMES):
            try:data=read_regular(src/name,limit=MAX_FILE)
            except FileNotFoundError:continue
            except Exception as exc:
                omitted.append({'name':name,'reason':type(exc).__name__});continue
            from hashlib import sha256
            original_sha=sha256(data).hexdigest()
            try:
                if name.endswith('.log'):
                    log_limit=256*1024
                    if name in {'export-idea-pretermination.log','validate-idea-pretermination.log'}:
                        log_limit=128*1024
                    elif name in {'export-idea.log','validate-idea.log'}:
                        before=name.replace('-idea.log','-idea-pretermination.log')
                        if before in output:log_limit=128*1024
                    data=sanitize_log(data[-log_limit:])
                    if name in {'export-idea.log','validate-idea.log','export-idea-pretermination.log','validate-idea-pretermination.log'}:
                        data=data[:log_limit].decode('utf-8',errors='ignore').encode()
                elif name.endswith('.json'):data=(json.dumps(sanitize_value(json.loads(data)),ensure_ascii=False,indent=2)+'\n').encode()
                elif name.endswith('.jsonl'):data=('\n'.join(json.dumps(sanitize_value(json.loads(line)),ensure_ascii=False) for line in data.splitlines())+'\n').encode()
            except (ValueError,UnicodeError) as exc:
                omitted.append({'name':name,'reason':'malformed diagnostic '+type(exc).__name__,'original_sha256':original_sha})
                continue
            hashes[name]={'original_sha256':original_sha,'uploaded_sha256':sha256(data).hexdigest()}
            if name in output:
                if output[name]!=data:raise ValueError('conflicting evidence sources: '+name)
                continue
            output[name]=data
    if 'summary.json' not in output:
        output['summary.json']=(json.dumps({'status':'NOT_RUN','reason':'official command not reached'})+'\n').encode()
    for name,data in output.items():write_new(evidence/name,data);copied.append(name)
    write_new(evidence/'collection.json',(json.dumps({'copied':copied,'omitted':omitted,'zip_uploaded':False,'hashes':hashes,'status':'PARTIAL' if omitted else 'PASS'},indent=2)+'\n').encode())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--bootstrap',type=Path)
    a=p.parse_args();collect(a.run,a.evidence,a.bootstrap)
