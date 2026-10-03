#!/usr/bin/env python3
"""显式调用才会运行JDK；当前交付未执行。"""
import argparse,json,pathlib,shutil,subprocess,tempfile,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bin'));from lab import TASKS
p=argparse.ArgumentParser();p.add_argument('--task',choices=TASKS);p.add_argument('--task-dir',type=pathlib.Path);a=p.parse_args()
if not shutil.which('javac') or not shutil.which('java'):print('{"status":"INVALID_ENV","reason":"JDK21_REQUIRED"}');sys.exit(2)
r=subprocess.run(['javac','-version'],capture_output=True,text=True)
if not r.stdout.strip().startswith('javac 21.') and not r.stderr.strip().startswith('javac 21.'):print('{"status":"INVALID_ENV","reason":"JDK21_REQUIRED"}');sys.exit(2)
if bool(a.task)!=bool(a.task_dir):p.error('--task and --task-dir must be supplied together')
with tempfile.TemporaryDirectory(prefix='c11-java-') as t:
    temp=pathlib.Path(t);shutil.copytree(ROOT/'src',temp/'src');shutil.copytree(ROOT/'test-java',temp/'test')
    if a.task:
        for source,target in TASKS[a.task].items():
            if target.endswith('.java'):shutil.copy2(a.task_dir/source,temp/target)
    files=sorted(str(p) for d in ('src','test') for p in (temp/d).rglob('*.java'))
    build=subprocess.run(['javac','--release','21','--add-modules','jdk.httpserver','-d',str(temp/'classes'),*files],capture_output=True,text=True)
    if build.returncode:print(json.dumps({'status':'FAIL','phase':'JAVA_COMPILE','output':build.stderr}));sys.exit(1)
    run=subprocess.run(['java','--add-modules','jdk.httpserver','-cp',str(temp/'classes'),'labs.PolicyContractTest'],capture_output=True,text=True,timeout=30)
    print(json.dumps({'status':'PASS' if run.returncode==0 else 'FAIL','phase':'JAVA_CONTRACT','output':run.stdout+run.stderr,'kind_e2e':'NOT_RUN'}));sys.exit(0 if run.returncode==0 else 1)
