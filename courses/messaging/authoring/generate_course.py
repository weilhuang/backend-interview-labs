#!/usr/bin/env python3
"""从已完成的代码和中文课稿生成Academy元数据；标准解代码保持单一真源。"""
from pathlib import Path
import json
import yaml
ROOT = Path(__file__).resolve().parents[1]
lessons = json.loads((ROOT / 'authoring/lessons.json').read_text())
def yaml_file(path, obj):
    path.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, width=1000))
revisions = json.loads((ROOT / 'authoring/source-revisions.json').read_text())
manifest = []
for key, lesson in lessons.items():
    section, directory = key.split('/')
    base = ROOT / key
    task = base / 'practice'
    if not task.exists(): continue
    yaml_file(base / 'lesson-info.yaml', {'type': 'lesson', 'custom_name': lesson['title'], 'content': ['practice']})
    files = []
    listed = sorted(task.rglob('*.java'))
    if (task/'gradle.lockfile').is_file(): listed.append(task/'gradle.lockfile')
    for source in listed:
        relative = str(source.relative_to(task))
        entry = {'name': relative, 'visible': True}
        content = source.read_text()
        if source.name == 'Lab.java':
            marker = '        // 学习区开始\n'
            end_marker = '        // 学习区结束'
            start = content.index(marker) + len(marker)
            end = content.index(end_marker)
            entry['placeholders'] = [{
                'offset': len(content[:start].encode('utf-16-le')) // 2,
                'length': len(content[start:end].encode('utf-16-le')) // 2,
                'placeholder_text': '        throw new UnsupportedOperationException("TODO：请按题目实现本方法");\n'}]
        files.append(entry)
    yaml_file(task / 'task-info.yaml', {'type': 'edu', 'custom_name': lesson['title'] + ' · 编码与故障验证', 'files': files})
    source_path, symbol, reading = lesson['source']
    repo = 'kafka' if section == 'kafka' else 'rocketmq'
    tag = '3.9.1' if section == 'kafka' else 'rocketmq-all-5.3.2'
    revision = revisions[repo]['提交']
    source_url = f'https://github.com/apache/{repo}/blob/{revision}/{source_path}'
    module = section + '-' + directory
    source_blocks = '\n\n'.join('### '+p.name+'\n\n```java\n'+p.read_text()+'```' for p in sorted((task / 'src').rglob('*.java')))
    steps = '\n'.join(f'{i}. {step}' for i, step in enumerate(lesson['steps'], 1))
    qa = '\n\n'.join(f'### 问题{i}：{q}\n\n标准回答：{a}\n\n追问练习：用本节一个具体测试、状态或故障窗口支撑回答；如果删除前提，构造反例。' for i,(q,a) in enumerate(lesson['questions'],1))
    text = f'''# {lesson['title']}

## 企业场景与学习目标

{lesson['scene']}

本节范围：先运行完整作者实现，再在 Academy 预览的占位区独立编码，最后对照公开标准解。预计 60–100 分钟；先修不足请回到首页给出的课程。容器测试目前是可执行待云端 Docker 实证，不代表已经运行成功。

## 概念、机制与图解

{lesson['concept']}

```text
{lesson['diagram']}
```

## 一步一步运行、编码与验证

在课程根目录执行，不要在 task 子目录运行。所有数据是随机命名的合成课堂资源。

```bash
./gradlew :{module}:test
./gradlew :{module}:test -PwithDocker
./gradlew :{module}:run
```

{steps}

默认命令只跑无容器用例；带 -PwithDocker 才会启动真实服务。无 Docker 时后者必须失败，不使用 disabledWithoutDocker 自动跳过来制造全绿。第一次依赖下载失败属于环境问题，先检查 Maven Central 与 Wrapper 下载；API 或断言失败再按中文提示检查代码。

## 本节输入与预期结果

{lesson['expected']}

## 完整调用示例

src/labs/messaging/Usage.java 是可见命令行调用端；无参数打印准确参数说明，有参数连接明确指定的课堂端点。BrokerTest.java 是本节专用业务调用链，展示正常和故障路径；所有测试都在 test/ 中公开。公共 Event、Inbox 与容器夹具在课程根 support/src/labs/messaging/，不依赖作者机器的私有文件。

## 真实源码阅读与断点路线

固定源码：[{repo} {tag}：{source_path}]({source_url})

固定提交：{revision}。目标符号：{symbol}。{reading}

按入口→关键状态→条件分支→可观察结果阅读；记录一次正常路径和一次失败路径。断点可对官方 sources JAR 附源码调试；本次没有伪造断点截图。support/ 与 Lab 中的自写模型不是上游源码替身。不要从一个模型断言生产系统所有故障都被覆盖。

## 标准答案与逐步解析

{lesson['answer']}

下方为与工程同源的完整实现及调用方，不隐藏答案。先自己完成再读；已读答案后需换条件盲做才能判断掌握程度。

{source_blocks}

## 成本、复杂度与替代方案

{lesson['cost']}

## 面试问题、标准回答与追问

{qa}

## 边界、测试解释与独立迁移

- 可见 LabTest 是快速边界检查；BrokerTest 验证实际broker消息与状态，不能用前者代替后者
- 时间上界只用于判定失败；故障先等待真实消息/位点/锁存器状态，不能靠一次偶然睡眠声称一致性
- 每次真实测试用 try-with-resources 清理自己创建的容器，不重置用户现有数据；不要把课堂明文无认证端点暴露到公网
- 修改一个原假设：重复、乱序、消费者重启、组扩容或数据库不可用，先写失败测试，再解释修复的作用域
- 完成标准：能运行、独立实现、读源码解释分支，并用新反例指出保证不成立的条件

### 提示1
先列出输入、状态和必须保持的不变量，区分消息交付与业务效果。

### 提示2
用本节已有正常测试找最小调用链，再把故障点前后两步写在时间线上。

### 提示3
检查重试是否保留业务标识、确认是否领先持久业务、恢复是否真的重建客户端；然后对照完整标准解。
'''
    (task / 'task.md').write_text(text)
    manifest.append({'task':key+'/practice','module':module,'title':lesson['title'],'source_url':source_url,'source_symbol':symbol,'docker_tests':[p.name for p in sorted((task/'test').glob('*Test.java')) if '@Tag("docker")' in p.read_text()]})
sections=[]
for section,title in [('kafka','C08 Kafka 消息可靠性'),('rocketmq','C09 RocketMQ 消息与事务消息')]:
    directories=[key.split('/')[1] for key in lessons if key.startswith(section+'/')]
    if directories:
        sections.append(section)
        yaml_file(ROOT/section/'section-info.yaml', {'type':'section','custom_name':title,'content':directories})
additional = ['README.md','验证报告.md','build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','gradle/wrapper/gradle-wrapper.properties','gradle/wrapper/gradle-wrapper.jar','THIRD_PARTY_NOTICES.md','LICENSE-JetBrains-template','authoring/source-revisions.json','authoring/source-evidence.json','.courseignore','support/gradle.lockfile']
if (ROOT/'shared/versions.env').is_file(): additional += ['shared/versions.env','shared/source-manifest.json']
additional += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'support').rglob('*.java'))]
additional += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'authoring').iterdir()) if p.suffix in {'.py','.json','.txt'}]
additional = list(dict.fromkeys(additional))
yaml_file(ROOT/'course-info.yaml',{'type':'marketplace','title':'后端面试实验室：Kafka 与 RocketMQ','language':'Chinese','summary':'两门消息队列课程十二个实验单元，包含完整源码、调用端、全部测试、每节标准答案、真实容器故障验证与面试追问；容器动态和Academy导入尚待实测，不代表完整V1发布。','programming_language':'Java','content':sections,'environment_settings':{'jvm_language_level':'JDK_21'},'additional_files':[{'name':p,**({'is_binary':True} if p.endswith('.jar') else {})} for p in additional],'yaml_version':2})
(ROOT/'authoring/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('已生成中文课稿与UTF-16占位：',len(manifest),'节')
