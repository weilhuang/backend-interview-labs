#!/usr/bin/env python3
"""Copy an explicit bounded environment evidence allowlist, never raw files or import ZIP."""
import argparse,json,re
from pathlib import Path
from gates import dump,sha
from safe_io import absolute,read_regular,write_new,new_directory,validate_directory
from collect_evidence import sanitize_value,sanitize_text

def collect(run,output):
    run=absolute(run);output=absolute(output)
    if run.is_relative_to(output) or output.is_relative_to(run):raise ValueError('evidence overlaps run root')
    new_directory(output);source=run/'evidence';copied=[];omitted=[]
    try:validate_directory(source)
    except FileNotFoundError:
        dump(output/'summary.json',{'status':'NOT_RUN','reason':'environment stage not initialized'});return
    names={'summary.json','release-gate.json','browser-layout.json','browser-smoke.png'}|{f'browser-layout-{w}.png' for w in (320,390,800,801,1440)}
    # Only generated exact command filenames, no container/IDE/user log discovery.
    names|={f'command-{i}-{stream}.log' for i in range(1,501) for stream in ('stdout','stderr')}
    total=0
    for name in sorted(names):
        try:data=read_regular(source/name,limit=4*1024*1024)
        except FileNotFoundError:continue
        except Exception as exc:omitted.append({'name':name,'error':type(exc).__name__});continue
        original=sha(data)
        try:
            if name.endswith('.json'):data=(json.dumps(sanitize_value(json.loads(data)),ensure_ascii=False,indent=2)+'\n').encode()
            elif name.endswith('.log'):data=sanitize_text(data.decode('utf8',errors='replace')).encode()
            else:
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('not PNG')
            total+=len(data)
            if total>32*1024*1024:raise ValueError('total evidence cap exceeded')
            write_new(output/name,data);copied.append({'name':name,'original_sha256':original,'uploaded_sha256':sha(data)})
        except Exception as exc:omitted.append({'name':name,'error':type(exc).__name__,'original_sha256':original})
    dump(output/'collection.json',{'status':'PARTIAL' if omitted else 'PASS','copied':copied,'omitted':omitted,'includes_import_archive':False})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();collect(a.run,a.output)
