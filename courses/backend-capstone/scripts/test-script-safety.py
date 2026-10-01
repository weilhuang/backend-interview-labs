#!/usr/bin/env python3
"""不启动Docker的命令边界回归；不能替代Linux/macOS真实Compose验收。"""
from pathlib import Path
import tempfile,subprocess,os,json
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='capstone-script-') as directory:
 base=Path(directory);tool=base/'docker';log=base/'calls.jsonl'
 tool.write_text('#!/usr/bin/env python3\nimport os,sys,json\nwith open(os.environ["FAKE_DOCKER_LOG"],"a") as f:f.write(json.dumps(sys.argv[1:])+"\\n")\n');tool.chmod(0o700)
 env=os.environ|{'PATH':str(base)+os.pathsep+os.environ['PATH'],'FAKE_DOCKER_LOG':str(log),'LAB_SHARED_VERSIONS':str(root/'shared/versions.env')}
 def run(args,good=True,extra=None):
  p=subprocess.run(['bash',str(root/'scripts/course.sh'),*args],env=env|(extra or {}),capture_output=True,text=True,timeout=5)
  assert (p.returncode==0)==good,(args,p.stdout,p.stderr)
 for args in [['stop'],['status'],['pause-service','delivery'],['recover-service','mysql'],['logs'],['crash-service','delivery']]:run(args)
 calls=[json.loads(x) for x in log.read_text().splitlines()]
 assert len(calls)==6
 for call in calls:assert call[0]=='compose' and call[1]=='--project-name' and call[2].startswith('capstone-')
 assert all('--volumes' not in call and '-v' not in call and 'down' not in call for call in calls)
 run(['crash-service','mysql'],False);run(['pause-service','not-this-project'],False);run(['recover-service',';kill -1'],False);run(['stop'],False,{'CAPSTONE_STAGE':'bad'});run(['stop'],False,{'LAB_SHARED_VERSIONS':str(base/'absent')})
 assert len(log.read_text().splitlines())==6
 report={'通过场景':11,'平台':'Linux命令边界','真实Docker':'未由本脚本执行','macOS':'未实测','禁止数据清理':True,'只操作本项目命名服务':True}
 (root/'authoring/script-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False))
