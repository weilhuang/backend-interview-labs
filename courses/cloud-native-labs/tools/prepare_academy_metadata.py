#!/usr/bin/env python3
"""为三课生成独立作者overlay；不生成第二课程根或假造Gradle/JUnit接线。"""
import argparse,hashlib,json,pathlib,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
COURSE=ROOT/'course';SHARED=COURSE/'materials/cloud-native';OVERLAY=ROOT/'academy-overlay'
LESSONS=[('C11-01','01-images','01-build-and-stop','Docker镜像与优雅停止','Dockerfile'),('C11-02','02-compose','01-ready-and-seed','Compose就绪与幂等初始化','CloudPolicy.java'),('C11-03','03-network','01-service-discovery','容器网络与服务发现','AddressPolicy.java')]

def utf16_len(text):return len(text.encode('utf-16-le'))//2

def slot(source,selection,starter):
    if source.count(selection)!=1:raise ValueError('Placeholder anchor must be unique')
    start=source.index(selection)
    return {'offset':utf16_len(source[:start]),'length':utf16_len(selection),'placeholder_text':starter}

def apply_placeholders(source,placeholders):
    raw=source.encode('utf-16-le')
    end=len(raw)//2
    for item in sorted(placeholders,key=lambda x:x['offset'],reverse=True):
        start=item['offset'];stop=start+item['length']
        if not 0<=start<=stop<=end:raise ValueError('Overlapping or out-of-range UTF-16 placeholder')
        raw=raw[:start*2]+item['placeholder_text'].encode('utf-16-le')+raw[stop*2:];end=start
    return raw.decode('utf-16-le')

def write_yaml(path,data):
    # JSON is a YAML-compatible representation; no extra package is needed to regenerate metadata.
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build():
    results=[]
    # 预览资产从唯一课程素材生成；集成时只取下面的c11子树，不导入这份预览副本。
    previews=OVERLAY/'materials/cloud-native/diagrams';previews.mkdir(parents=True,exist_ok=True)
    for source in sorted((SHARED/'diagrams').glob('*.svg')):shutil.copy2(source,previews/source.name)
    section=OVERLAY/'c11-cloud-native';section.mkdir(parents=True,exist_ok=True)
    write_yaml(section/'section-info.yaml',{'custom_name':'C11 · Docker、Compose与容器网络','content':[row[1] for row in LESSONS]})
    for code,lesson,task,title,editable in LESSONS:
        dest=section/lesson/task;dest.mkdir(parents=True,exist_ok=True)
        source_task=COURSE/'c11-cloud-native'/lesson/task
        write_yaml(dest.parent/'lesson-info.yaml',{'custom_name':title,'content':[task]})
        for name in ['task.md','solution.md','observations.md']:shutil.copy2(source_task/name,dest/name)
        answers=dest/'answers';answers.mkdir(exist_ok=True)
        if code=='C11-01':
            text=(SHARED/'container/Dockerfile').read_text();placeholders=[slot(text,text,(source_task/editable).read_text())]
            for name in ['Dockerfile.exec','Dockerfile.exec-script']:shutil.copy2(SHARED/'answers'/name,answers/name)
            shutil.copy2(SHARED/'container/entrypoint.sh',answers/'entrypoint.sh')
            checks='真实镜像非root、无构建器和合成秘密；在预算内停止并完成进行中HTTP请求。离线shell检查不能替代Docker PID1验证。'
        elif code=='C11-02':
            text=(SHARED/'src/labs/CloudPolicy.java').read_text();placeholders=[slot(text,'return dependencyHealthy && seeded && !draining;','return true;')]
            (answers/'CloudPolicy.expression.java.txt').write_text(text)
            shutil.copy2(SHARED/'answers/CloudPolicy-explicit.java.txt',answers/'CloudPolicy.explicit.java.txt')
            checks='ready真值表、未seed不能接单、seed后发生交易再seed不回填、请求重放不重复扣减。Redis Lua仍需真实容器执行。'
        else:
            text=(SHARED/'src/labs/AddressPolicy.java').read_text()
            host=text.split('    public static String host(Map<String, String> env) {\n',1)[1].split('    }\n',1)[0]
            # The host body has an inner if; anchor through the return, not the first closing brace.
            host=text[text.index('        String host ='):text.index('        return host;')+len('        return host;\n')]
            port=text[text.index('        int port ='):text.index('        return port;')+len('        return port;\n')]
            placeholders=[slot(text,host,'        return "localhost";\n'),slot(text,port,'        return 6379;\n')]
            (answers/'AddressPolicy.defaults.java.txt').write_text(text)
            shutil.copy2(SHARED/'answers/AddressPolicy-explicit.java.txt',answers/'AddressPolicy.explicit.java.txt')
            checks='使用注入的服务名和容器端口；DNS、CONNECT、AUTH、TIMEOUT、PROTOCOL分别定位；真实容器localhost反例尚待运行。'
        (dest/editable).write_text(text,encoding='utf-8')
        (dest/'visible-test-contract.md').write_text('# 可见测试与当前边界\n\n'+checks+'\n\n完整可见测试位于总课程共享项目materials/cloud-native/tests；Java策略断言位于test-java/labs/PolicyContractTest.java。\n\n本overlay只提供作者元数据和答案，不含JUnit桥、总课Gradle适配或strict locks，Academy原生Check为NOT_RUN。\n',encoding='utf-8')
        names=[editable,'solution.md','observations.md','visible-test-contract.md']+[p.relative_to(dest).as_posix() for p in sorted(answers.iterdir())]
        entries=[dict(name=name,visible=True,**({'placeholders':placeholders} if name==editable else {})) for name in names]
        write_yaml(dest/'task-info.yaml',{'type':'edu','custom_name':code+' · '+title,'files':entries})
        projected=apply_placeholders(text,placeholders)
        results.append({'id':code,'task_path':dest.relative_to(OVERLAY).as_posix(),'editable':editable,'placeholder_count':len(placeholders),'author_sha256':hashlib.sha256(text.encode()).hexdigest(),'learner_projection_sha256':hashlib.sha256(projected.encode()).hexdigest(),'utf16':'CHECKED','learner_compilation':'NOT_RUN','academy_native_check':'NOT_RUN'})
    return results

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=pathlib.Path,default=ROOT/'qa/academy-metadata.json',help='静态检查报告路径；父目录自动创建')
    args=parser.parse_args()
    results=build();args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps({'schema_validation':'STATIC_ONLY','tasks':results,'missing':['JUnit bridge','total-course Gradle integration','strict dependency locks'],'native_check':'NOT_RUN'},ensure_ascii=False,indent=2)+'\n')
    print('Prepared',len(results),'tasks; runtime NOT_RUN')
