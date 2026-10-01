#!/usr/bin/env python3
"""Release boundary: native positive cases do not prove unified service entrypoints."""
import argparse
from pathlib import Path
from gates import dump,read_json,require

# This may be replaced only with the reviewed separate real-environment job.
# It cannot be enabled by dispatch inputs, shell environment or a source CI flag.

def evaluate(native):
    require(native.get('status')=='PASS' and native.get('final_archive_ready') is True,'native archive gates are incomplete')
    return {'status':'BLOCKED','native_archive_gates':'PASS','unified_environment_runtime':'NOT_RUN',
            'reason':'Separate real unified start/doctor/read-write/frontend/stop and C14 recovery/browser acceptance is not yet wired; old source CI and 84 native reference checks do not substitute',
            'archive_upload_allowed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--native-summary',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    try:result=evaluate(read_json(a.native_summary))
    except Exception as exc:result={'status':'BLOCKED','archive_upload_allowed':False,'error':type(exc).__name__+': '+str(exc)}
    dump(a.report,result);print(result['status']);raise SystemExit(1)
