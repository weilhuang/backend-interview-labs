"""来源限定的教学命令/路径迁移；Java 示例和答案代码逐字保留。"""
import re

def sections(text):
    """Yield (protected Java fence, text); do not parse Java as shell/prose."""
    current=[];java=False;fence=None
    for line in text.splitlines(keepends=True):
        match=re.match(r'^\s*(`{3,}|~{3,})(\w*)',line)
        if match:
            if fence is None:
                if current:yield False,''.join(current);current=[]
                fence=match[1][0];java=match[2].lower() in ('java','kotlin','groovy')
                current.append(line)
            elif match[1][0]==fence:
                current.append(line);yield java,''.join(current);current=[];java=False;fence=None
            else:current.append(line)
        else:current.append(line)
    if current:yield java,''.join(current)

def launcher_text(text):
    """Only instructional prose/shell; callers invoke this outside protected code fences."""
    unified='统一启动方式：源码目录与官方Academy导入都使用随包的 `bash scripts/gradle.sh <Gradle参数>`，不依赖被官方剔除的Wrapper程序。首次先按根README显式准备固定Gradle8.10.2；缺运行时不会自动下载。项目SDK、Gradle与测试均用完整JDK21，IDE Check/Run仍是独立原生验收。\n'
    rows=[]
    for line in text.splitlines(keepends=True):
        if any(marker in line for marker in ('运行路线先区分：','**Academy官方归档导入模式**','Academy官方归档路线：','Academy官方ZIP导入后使用题目Check','以下命令用于源码仓库/公开源码包；','**Academy导入模式**')):
            line=unified
        elif line.startswith('源码仓库路线：只打开本目录'):
            line='只打开生成的统一课程根，不再逐个打开材料目录。所有终端命令使用随包启动器；Project SDK、Gradle JVM和测试JVM均设JDK21。首次依赖解析失败属于环境问题，不是答案错误。\n'
        elif line.startswith('**源码仓库或普通Gradle学员副本模式**'):
            line='**统一命令行模式**：以下CLI在统一课程根使用 `bash scripts/gradle.sh`，源码与官方导入形式相同。完整诊断教程保留；首次依赖解析失败应与作答失败区分。\n'
        line=line.replace('**源码仓库/普通Gradle副本CLI模式**','**统一课程命令行模式**')
        line=line.replace('Windows改用gradlew.bat','Windows的官方导入CLI尚未独立验证；保留Wrapper的源码目录可用gradlew.bat')
        line=line.replace('Windows使用gradlew.bat','Windows的官方导入CLI尚未独立验证；保留Wrapper的源码目录可用gradlew.bat')
        line=line.replace('Windows用gradlew.bat','Windows的官方导入CLI尚未独立验证；保留Wrapper的源码目录可用gradlew.bat')
        line=line.replace('Windows的Gradle命令换gradlew.bat。','Windows官方导入CLI尚未独立验证；源码目录保留的gradlew.bat不是发行包入口。')
        line=line.replace('源码仓库在Windows把./gradlew换gradlew.bat。','Windows官方导入CLI尚未独立验证；源码目录保留的gradlew.bat不是发行包入口。')
        line=re.sub(r'(?:bash[ \t]+)?(?:\./)?gradlew(?:\.bat)?(?=[ \t]+(?:[:A-Za-z-]))','bash scripts/gradle.sh',line)
        rows.append(line)
    return ''.join(rows)

def migrate(text, cid, source_root, mapping, relative):
    entries=[x for x in mapping['tasks']+mapping['support_projects'] if x['source_course']==cid]
    modules={x['original_module']:x['gradle_project'] for x in entries}
    prefixes=[p.name for p in source_root.iterdir() if p.is_dir() and p.name in
              ('scripts','docs','support','app','reference','fixtures','sql','benchmark','diagnostics','experiments','common')]
    current=next((x for x in mapping['tasks'] if relative.startswith(x['source_task']+'/')),None)
    if relative=='README.md' and cid in ('mysql-engineering','redis-engineering'):
        text=text.replace('](shared/README.md)','](../../shared/README.md)')
        text=text.replace('完整仓库直接使用根镜像台账；独立导入时使用课程内自动生成、带SHA256的shared快照，不需要父仓库。也可用LAB_SHARED_VERSIONS或LAB_REPO_ROOT显式覆盖。','统一课程只读取根 shared/versions.env 及 SHA256，不需要父仓库，不向上查找，也不支持原分课环境变量覆盖。')
        text=text.replace('独立导出保留自动生成的shared镜像快照与SHA256，无需父仓库；LAB_SHARED_VERSIONS或LAB_REPO_ROOT可显式覆盖，旧LAB_VERSIONS仍兼容。','统一课程保留唯一 shared/versions.env 与 SHA256，无需父仓库；原分课的 LAB_SHARED_VERSIONS、LAB_REPO_ROOT、LAB_VERSIONS 覆盖只属于历史读取器兼容说明，统一 Gradle 入口不使用它们。')
        text=text.replace('support的Images向上查台账；独立导出用LAB_VERSIONS指定同一原始文件','统一 Gradle 显式传入根 shared/versions.env；不使用父目录或环境覆盖')
        text=text.replace('从仓库infra/versions.env或其自动生成的shared快照读取MYSQL_IMAGE','从统一根 shared/versions.env 读取 MYSQL_IMAGE')
    result=[]
    for protected, part in sections(text):
        if protected:result.append(part);continue
        # Protect real URLs, Markdown destinations, already-mapped paths, and root environment scripts.
        masks={}
        def mask(match):
            key=f'UNIFIEDMASK{len(masks)}TOKEN';masks[key]=match[0];return key
        part=re.sub(r'https?://[^\s<>）)`，。；、！？]*|(?<=\]\()[^)]*',mask,part)
        for old,new in sorted(modules.items(),key=lambda x:-len(x[0])):
            part=re.sub(r'(?<![\w:-]):'+re.escape(old)+r':(?=[A-Za-z])',new+':',part)
        # Expand root goals to explicit source-course modules, including multi-goal commands.
        # This avoids both accidental whole-course execution and new aggregate build behavior.
        def aggregate_goal(match):
            goal=match[0];actual='test' if goal=='check' else goal
            if actual=='unitTest' and cid not in ('mysql-engineering','redis-engineering','distributed-systems'):actual='test'
            selected=[x for x in entries if 'source_task' in x]
            if actual in ('integrationTest','compileIntegrationTestJava'):
                selected=[x for x in selected if (source_root/x['source_task']/'integration-test').is_dir() or cid=='redis-engineering']
            if not selected:return goal
            return ' '.join(x['gradle_project']+':'+actual for x in selected)
        def command(match):
            args=re.sub(r'(?<![\w:-])(clean|test|unitTest|integrationTest|check|classes|testClasses|verificationClasspath|compileIntegrationTestJava)(?![\w:-])',aggregate_goal,match.group(2))
            return match.group(1)+args
        part=re.sub(r'(gradlew(?:\.bat)?\s+)([^`\n]*)',command,part)
        part=re.sub(r'(?:\.\./)*infra/versions\.env','shared/versions.env',part)
        part=re.sub(r'(?m)^cd courses/[^\s]+\s*$', '# 以下命令均在统一课程根执行，不再切入原作者目录', part)
        part=part.replace('仓库 docs/curriculum/08-release-plan.md','统一课程根 docs/合并设计与验收.md')
        if cid=='messaging':part=part.replace('./scripts/lab.sh doctor','bash scripts/lab.sh doctor kafka && bash scripts/lab.sh doctor rocketmq')
        if cid=='backend-capstone':
            part=re.sub(r'python3?\s+(?:\./)?scripts/check\.py', 'bash scripts/lab.sh workbench-check capstone', part)
            part=part.replace('设置 `CAPSTONE_STAGE=02-reliability` 再start', '运行 `bash scripts/lab.sh start capstone --stage 02-reliability`')
            stage=current['original_module'] if current else '05-defense'
            part=re.sub(r'CAPSTONE_STAGE=([\w-]+)\s+(?:bash\s+)?(?:\./)?scripts/course\.sh\s+start',r'bash scripts/lab.sh start capstone --stage \1',part)
            part=re.sub(r'(?:bash\s+)?(?:\./)?scripts/course\.sh\s+(pause-service|recover-service|crash-service)\s+(mysql|redis|kafka|orders|delivery)',r'bash scripts/lab.sh \1 capstone --service \2',part)
            part=re.sub(r'(?:bash\s+)?(?:\./)?scripts/course\.sh\s+start',f'bash scripts/lab.sh start capstone --stage {stage}',part)
            part=re.sub(r'(?:bash\s+)?(?:\./)?scripts/course\.sh\s+(doctor|stop|status|logs|health)',r'bash scripts/lab.sh \1 capstone',part)
            part=re.sub(r'(?<!lab.sh )pause-service mysql',r'bash scripts/lab.sh pause-service capstone --service mysql',part)
            part=re.sub(r'(?<!lab.sh )recover-service mysql',r'bash scripts/lab.sh recover-service capstone --service mysql',part)
            part=part.replace('再暂停delivery','再运行 `bash scripts/lab.sh pause-service capstone --service delivery` 暂停配送服务')
            part=part.replace('恢复delivery再重放','运行 `bash scripts/lab.sh recover-service capstone --service delivery` 恢复配送服务后再重放，投影追平')
            part=part.replace('scripts/course.sh只按当前课程路径生成Compose项目名，stop不删卷，没有reset或down -v。','统一 scripts/lab.sh 只操作本课程 Compose 项目，stop 保留卷；不执行全局清理。')
        if cid=='distributed-systems':part=re.sub(r'(?:bash\s+)?(?:\./)?scripts/course\.sh\s+doctor','bash scripts/lab.sh doctor distributed-outbox',part)
        if cid=='java-frameworks' and 'scripts/course.sh doctor' in part:
            old='`scripts/course.sh doctor`检查JDK；`start 02-http-contract`或`start 07-integrated-service`启动；`check`等待真实HTTP就绪；`stop`只停止本课程登记且归属匹配的进程。脚本当前按Linux云端编写；其他学习环境可直接运行Gradle的run任务并用Ctrl+C停止。开发验证可显式用LAB_GRADLE_BIN选择已安装的同版本Gradle，LAB_OFFLINE=1使用已验证依赖缓存，不更换版本。'
            new='在统一课程根运行 `bash scripts/lab.sh doctor java` 检查 JDK。网页示例用 `./gradlew :framework-course-01-boot-02-http-contract:run` 或 `./gradlew :framework-course-01-boot-07-integrated-service:run` 启动，按 Ctrl+C 停止当前进程。再打开文中 URL 操作并使用该题公开测试验证；不要运行原分课的进程脚本。'
            part=part.replace(old,new)
        if cid in ('mysql-engineering','redis-engineering'):
            profile='mysql' if cid=='mysql-engineering' else 'redis'
            part=re.sub(r'(?:\./)?scripts/lab\.sh\s+doctor(?![ \t]+[a-z-])',f'bash scripts/lab.sh doctor {profile}',part)
            part=re.sub(r'(?:\./)?scripts/lab\.sh\s+up\s+(mysql|redis|core)',lambda m:'bash scripts/lab.sh start '+('redis-mysql' if m[1]=='core' else m[1]),part)
            part=re.sub(r'(?:\./)?scripts/lab\.sh\s+check\s+(mysql|redis|core)(?![/\w-])',lambda m:'bash scripts/lab.sh health '+('redis-mysql' if m[1]=='core' else m[1]),part)
            part=re.sub(r'(?:\./)?scripts/lab\.sh\s+down','bash scripts/lab.sh stop '+('redis-mysql' if cid=='redis-engineering' else profile),part)
            part=part.replace('不接受组件参数；停止本项目而保留数据','只停止所选本课程服务；保留容器与数据卷')
            part=part.replace('仓库docs/environment/README.md','统一根 docs/统一环境.md')
            part=part.replace('`lab.sh build`不挂Docker socket，不能默认用它承载嵌套Testcontainers。','统一入口不提供旧 build 子命令；请用根 Gradle 构建，不把 Docker socket 挂入构建容器。')
        part=re.sub(r'(python3?\s+authoring/materialize_learner\.py)\s+(?:build/[^\s`；，。]+|新目录)',r'\1 ../backend-interview-learner',part)
        # Separate original author tooling from current learner commands at the exact occurrence.
        maintained=[]
        for line in part.splitlines(keepends=True):
            if re.search(r'python3?\s+authoring/(?!materialize_learner\.py)[\w.-]+\.py',line):
                if re.match(r'^\s*python3?\s',line):
                    line='# 原作者项目维护专用（仓库 '+next(x['source'] for x in mapping['source_courses'] if x['id']==cid)+'，不可在统一课程执行）：'+line
                else:
                    line='作者维护记录（仅在仓库 '+next(x['source'] for x in mapping['source_courses'] if x['id']==cid)+' 使用；统一课程学习者不执行这些脚本）：'+line
            maintained.append(line)
        part=''.join(maintained)
        part=re.sub(r'scripts/lab\.sh',mask,part)
        for prefix in prefixes:
            part=re.sub(r'(?<![A-Za-z0-9_./:-])'+re.escape(prefix)+r'/',f'materials/{cid}/{prefix}/',part)
        if (source_root/'SOURCES.md').is_file():part=re.sub(r'(?<![A-Za-z0-9_./-])SOURCES\.md',f'materials/{cid}/SOURCES.md',part)
        if current:part=part.replace('根README',f'材料 materials/{cid}/README.md')
        if cid=='messaging':part=part.replace('materials/messaging/support/Inbox.java','materials/messaging/support/src/labs/messaging/Inbox.java')
        if cid=='backend-capstone':part=re.sub(r'(?<![A-Za-z0-9_./:-])shared/(?!versions\.env)',f'materials/{cid}/shared/',part)
        if cid=='java-jvm':
            for path in ('build/evidence','build/labs','build/modules','build/migration','build/java25'):
                part=re.sub(r'(?<![A-Za-z0-9_./:-])'+re.escape(path),f'materials/{cid}/'+path,part)
        if cid=='java-foundations':part=re.sub(r'(?<![A-Za-z0-9_./:-])build/hashmap-trace',f'materials/{cid}/build/hashmap-trace',part)
        for key,value in masks.items():part=part.replace(key,value)
        result.append(launcher_text(part))
    migrated=''.join(result).replace('投影追平，投影追平','投影追平')
    migrated=migrated.replace('两门课程可分别生成独立项目目录，只保留对应六节。','以上分包命令仅保留为作者历史维护记录。当前不拆成两个课程；普通练习副本统一运行 `python authoring/materialize_learner.py ../backend-interview-learner`，保留全部章节。')
    if not current and not relative.startswith('authoring/'):
        migrated='来源与验收范围：本页保留原分课资料及历史证据，命令已迁移到统一根；旧通过记录不能替代统一课程的原生导入、判题或真实容器验收。当前统一课程边界见根 docs/合并设计与验收.md。\n\n'+migrated
    if relative.startswith('authoring/'):
        migrated='原作者维护资料：本文件记录源课程维护流程；这里的作者生成/变异脚本须在仓库的原作者项目中运行。统一课程学习入口见根 README 与统一环境说明。\n\n'+migrated
    if current and relative.endswith('/task.md') and cid in ('messaging','java-jvm'):
        note='\n\n统一课程运行提示：以下教学步骤已经使用本课实际路径。Java 源码及其原样展示中的历史打印文案保留用于溯源；若 Usage 输出旧分课模块名或脚本路径，请执行本页给出的统一命令。此显示文案尚待作者真源专项修补，不影响本题代码与判题。\n'
        command=f"\n本题当前调用入口：`bash scripts/gradle.sh {current['gradle_project']}:run`。\n"
        at=migrated.find('\n');migrated=migrated[:at]+note+command+migrated[at:]
    return migrated

def command_inventory(text):
    result=[]
    for protected,part in sections(text):
        if protected:continue
        part=re.sub(r'https?://[^\s<>）)`，。；、！？]*','',part)
        result.extend(re.findall(r'(?<![\w:-]):([a-z0-9][a-z0-9:-]*):([A-Za-z][A-Za-z0-9]*)',part))
    return sorted(set(':'+project+':'+task for project,task in result))
