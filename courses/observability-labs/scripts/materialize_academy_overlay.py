if not __debug__: raise SystemExit("拒绝Python优化模式，不能移除静态契约断言")
from pathlib import Path
import shutil,json,yaml
R=Path(__file__).resolve().parents[1];O=R/'academy-overlay'
source=R/'observability-lab/src/main/java/labs/observability'
plan=[('safe-events','C12-01 · 结构化日志与脱敏','SafeEvents.java','public String encode(','01-结构化日志练习与答案.md'),('metrics','C12-03 · 计数器直方图与基数','RequestMetrics.java','public void observe(','02-指标练习与答案.md'),('trace-context','C12-05 · 跨服务上下文传播','TraceBridge.java','public Context extract(','03-链路传播练习与答案.md')]
def put(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
def yamlput(p,d):put(p,yaml.safe_dump(d,allow_unicode=True,sort_keys=False))
def u16(s):return len(s.encode('utf-16-le'))//2
section=O/'observability';lesson=section/'first-slice'
yamlput(section/'section-info.yaml',{'type':'section','custom_name':'C12 · 从一次请求理解可观测性','content':['first-slice']})
yamlput(lesson/'lesson-info.yaml',{'type':'lesson','custom_name':'安全日志、指标与跨服务链路','content':[a[0] for a in plan]})
rows=[]
for slug,title,file,signature,doc in plan:
 t=lesson/slug;files=[]
 for p in source.glob('*.java'):
  dest=t/'src/labs/observability'/p.name;put(dest,p.read_text());entry={'name':str(dest.relative_to(t)),'visible':True}
  if p.name==file:
   text=p.read_text();start=text.index('{',text.index(signature))+1;depth=1;i=start
   while depth:depth+=(text[i]=='{')-(text[i]=='}');i+=1
   entry['placeholders']=[{'offset':u16(text[:start]),'length':u16(text[start:i-1]),'placeholder_text':'\n        throw new UnsupportedOperationException("请按中文步骤完成此方法");\n    '}]
  files.append(entry)
 for p in (R/'observability-lab/src/test/java/labs/observability').glob('*.java'):
  dest=t/'test/labs/observability'/p.name;put(dest,p.read_text());files.append({'name':str(dest.relative_to(t)),'visible':True})
 for variant in ['reference-map','reference-typed']:
  p=R/'variants'/variant/'src/labs/observability'/file;dest=t/'answers'/variant/file;put(dest,p.read_text());files.append({'name':str(dest.relative_to(t)),'visible':True})
 for name,text in [('task.md',(R/'docs'/doc).read_text()),('solution.md','# 参考实现阅读\n\nreference-map对应方法练习；reference-typed是只读完整类对照，含区外变化，不能当单一练习区替换文本。两者当前均未运行。\n\n'+(R/'docs'/doc).read_text()),('source-guide.md',(R/'docs/05-官方版本源码与面试路线.md').read_text())]:
  text=text.replace('bash scripts/verify_java.sh test',f'bash scripts/gradle.sh :observability-first-slice-{slug}:test').replace('bash scripts/verify_java.sh usage',f'bash scripts/gradle.sh :observability-first-slice-{slug}:usage').replace('bash scripts/verify_java.sh run',f'bash scripts/gradle.sh :observability-first-slice-{slug}:run')
  text=text.replace('observability-lab/src/main/java/labs/observability/','src/labs/observability/').replace('variants/reference-map/src/labs/observability/','answers/reference-map/').replace('variants/reference-typed/src/labs/observability/','answers/reference-typed/')
  text=text.replace('(06-参考实现范围与验证器契约.md)','(../../../materials/observability/docs/06-参考实现范围与验证器契约.md)')
  put(t/name,text);files.append({'name':name,'visible':True})
 yamlput(t/'task-info.yaml',{'type':'edu','custom_name':title,'files':files})
 rows.append({'source_course':'observability','source_task':f'first-slice/{slug}','path':f'observability/first-slice/{slug}','gradle_project':f':observability-first-slice-{slug}','original_module':'observability-lab','placeholders':1,'status':'IMPLEMENTED_UNTESTED'})
materials=O/'materials/observability'
for folder in ['docs','infra']:
 shutil.copytree(R/folder,materials/folder,dirs_exist_ok=True)
shutil.copytree(R/'observability-lab/src/main/resources',materials/'resources',dirs_exist_ok=True)
put(materials/'course.gradle.fragment',(R/'observability-lab/build.gradle.fragment').read_text())
manifest={'schema_version':1,'overlay_version':'v2-observability-overlay-1','target_course':'courses/backend-interview','approved_for_merge':False,'replaces_v1_counts':False,'source_courses':['observability'],'sections':[{'source_course':'observability','source_section':'observability','path':'observability'}],'tasks':rows,'additional_files_policy':'owner enumerates materials/**, does not hide learner resources','native_status':'NOT_RUN'}
put(R/'manifest/academy-overlay-proposal.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
# Static UTF16 checks are metadata checks, not native Academy acceptance.
for task in lesson.iterdir():
 if not task.is_dir():continue
 data=yaml.safe_load((task/'task-info.yaml').read_text())
 for f in data['files']:
  assert (task/f['name']).exists() and f['visible']
  for p in f.get('placeholders',[]):
   raw=(task/f['name']).read_text().encode('utf-16-le');region=raw[p['offset']*2:(p['offset']+p['length'])*2].decode('utf-16-le');assert 'return' in region or 'requests.add' in region
print('3 tasks / 3 UTF16 regions; overlay only; native NOT_RUN')
