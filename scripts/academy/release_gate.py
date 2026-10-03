#!/usr/bin/env python3
"""Release only freshly rehashed official bytes with complete same-run proof."""
import argparse
from pathlib import Path
from gates import dump,read_json,require,sha
from native_handoff import check_native
from environment_contract import validate_environment
from safe_io import read_regular,new_directory,write_new,absolute

MAX_ARCHIVE=128*1024*1024

def evaluate(native, environment=None, identity=None, archive=None):
    require(native.get('status')=='PASS' and native.get('native_archive_verified') is True,'native archive gates are incomplete')
    if environment is None or identity is None:
        return {'status':'BLOCKED','native_archive_gates':'PASS','unified_environment_runtime':'NOT_RUN',
                'reason':'Separate same-archive real unified environment proof is required','archive_upload_allowed':False}
    check_native(native)
    require(native['stages']['source_contract']['sha256']==identity.get('contract_sha256'), 'release source contract identity mismatch')
    proof=validate_environment(environment,native,identity)
    require(archive is not None,'final archive regular-file read is required; JSON alone cannot authorize release')
    content=read_regular(archive,limit=MAX_ARCHIVE)
    size=native['stages']['archive'].get('bytes')
    require(type(size) is int and 0<size<=MAX_ARCHIVE and len(content)==size,'final archive size differs from native archive')
    digest=sha(content)
    require(digest==identity['archive_sha256']==environment['archive_sha256']==native['stages']['archive']['archive_sha256'],'final archive bytes differ from the native/environment tested ZIP')
    # These three full-course verifiers do not exist yet. A caller-supplied PASS
    # string is not evidence and cannot enable publication. Keep diagnostic
    # handoff/import checks available, but fail closed until reviewed verifiers
    # replace this explicit blocker.
    return {'status':'BLOCKED','native_archive_gates':'PASS','unified_environment_runtime':'PASS',
            'archive_upload_allowed':False,
            'native_ui_check_reset':'NOT_VERIFIED','negative_controls':'NOT_VERIFIED',
            'extension_environment_lifecycle':'NOT_VERIFIED',
            'blocked_gates':['native Check/Reset proof verifier not implemented',
                             'native negative-control proof verifier not implemented',
                             'extension environment lifecycle proof verifier not implemented'],**{key:identity[key] for key in ('repository','commit','run_id','run_attempt','archive_sha256','contract_sha256','handoff_sha256')},
            'environment_checks':proof['checks'],'final_archive_bytes':len(content),'final_archive_rehashed':True}

def prepare_release(native,environment,identity,archive,destination):
    """Publish only to a fresh separate directory from a second verified no-follow read."""
    archive=absolute(archive);destination=absolute(destination)
    require(not archive.is_relative_to(destination) and not destination.is_relative_to(archive.parent),'release output overlaps mutable handoff inputs')
    result=evaluate(native,environment,identity,archive)
    require(result.get('status')=='PASS' and result.get('archive_upload_allowed') is True,
            'Final release blocked: '+ '; '.join(result.get('blocked_gates', ['full-course proof incomplete'])))
    # If the input changed between the gate read and copy read, reject it again.
    content=read_regular(archive,limit=MAX_ARCHIVE)
    require(len(content)==result['final_archive_bytes'] and sha(content)==result['archive_sha256'],'archive changed while preparing final release')
    new_directory(destination)
    output=destination/'backend-interview-academy.zip';write_new(output,content)
    write_new(destination/'SHA256SUMS',(result['archive_sha256']+'  '+output.name+'\n').encode())
    require(sha(read_regular(output,limit=MAX_ARCHIVE))==result['archive_sha256'],'verified release copy changed')
    output.chmod(0o400,follow_symlinks=False);(destination/'SHA256SUMS').chmod(0o400,follow_symlinks=False)
    result['release_copy']='backend-interview-academy.zip';return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--native-summary',type=Path,required=True);p.add_argument('--environment-summary',type=Path);p.add_argument('--identity',type=Path);p.add_argument('--archive',type=Path);p.add_argument('--release-dir',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    try:
        native=read_json(a.native_summary);environment=read_json(a.environment_summary) if a.environment_summary else None;identity=read_json(a.identity) if a.identity else None
        if a.release_dir is not None:
            require(a.archive is not None and environment is not None and identity is not None,'release copy requires all proof inputs and archive')
            result=prepare_release(native,environment,identity,a.archive,a.release_dir)
        else:result=evaluate(native,environment,identity,a.archive)
    except Exception as exc:result={'status':'BLOCKED','archive_upload_allowed':False,'error':type(exc).__name__+': '+str(exc)}
    dump(a.report,result);print(result['status']);raise SystemExit(0 if result['status']=='PASS' else 1)
