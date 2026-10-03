#!/usr/bin/env python3
"""在全新目录编译并记录输入/产物哈希；不删除、复用或覆盖旧class。"""
import argparse,datetime,json,pathlib,subprocess,sys,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from verification_guard import VerificationSetupError,java_source_manifest,class_manifest

def compile_project(output,runner=subprocess.run):
    output=pathlib.Path(output)
    if output.exists():raise VerificationSetupError('Output already exists; choose a fresh CLOUDNATIVE_CLASSES directory')
    sources=java_source_manifest(ROOT)
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=output.parent/(output.name+'.compile-'+uuid.uuid4().hex)
    staging.mkdir()
    receipt={'status':'FAILED','release':21,'sources':sources,'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        result=runner(['javac','--release','21','-encoding','UTF-8','-d',str(staging)]+[str(ROOT/p) for p in sources],capture_output=True,text=True,timeout=60)
        if result.returncode:raise VerificationSetupError('javac failed; failed staging output was retained for inspection')
        if java_source_manifest(ROOT)!=sources:raise VerificationSetupError('Source changed while compiling')
        receipt.update(status='COMPILED',classes=class_manifest(staging),completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        (staging/'compile-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if output.exists():raise VerificationSetupError('Output appeared concurrently; refusing replacement')
        staging.rename(output)
        return output
    except BaseException:
        if staging.exists():
            receipt['status']='FAILED'
            (staging/'compile-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=pathlib.Path);args=parser.parse_args()
    try:print('Compiled with input/output receipt:',compile_project(args.out))
    except (VerificationSetupError,OSError,subprocess.SubprocessError) as error:parser.exit(2,str(error)+'\n')
