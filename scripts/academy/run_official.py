#!/usr/bin/env python3
"""Version-pinned adapter around the real Academy CLI, never an archive creator."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import time
import traceback
import re
from safe_io import absolute, read_regular, write_new, replace_regular, validate_directory, exclusive_writer, directory_fd
from gates import (GateError, require, read_json, dump, sha, build_contract, redact_contract,
                   inspect_archive, inspect_import, inspect_author_changes, validate_report)

MIN_FREE_BYTES = 2 * 1024**3
IDE_LOG_BYTES = 256 * 1024
IDE_SPLIT_BYTES = 128 * 1024

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def intermediate_archives(root, phase):
    """Metadata only for the fixed export temp directory, never ZIP contents."""
    require(phase in (None,"export","validate"),"unknown diagnostic phase")
    if phase!='export':return {'status':'NOT_APPLICABLE'}
    result={'status':'UNVERIFIED_INTERMEDIATE','count':0,'entries':[],
            'scan_limit':1000,'entry_limit':10,'truncated':False,'content_read':False}
    try:
        with directory_fd(root/'export-profile/tmp') as directory:
            with os.scandir(directory) as listing:
                for scanned,entry in enumerate(listing):
                    if scanned>=1000:
                        result['truncated']=True;result['count_is_lower_bound']=True;break
                    if not (entry.name.startswith('course_archive_') and entry.name.endswith('.zip')):continue
                    info=os.stat(entry.name,dir_fd=directory,follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):raise ValueError('intermediate is not a regular file')
                    result['count']+=1
                    if len(result['entries'])<10:
                        result['entries'].append({'basename':entry.name,'size_bytes':info.st_size})
                    else:result['truncated']=True
        return result
    except Exception as exc:
        return {'status':'UNAVAILABLE','error':type(exc).__name__,'content_read':False}

def snapshot_before_stop(root, phase):
    """Read only the fixed phase log before termination noise can replace it."""
    require(phase in (None,"export","validate"),"unknown diagnostic phase")
    result={"status":"NOT_RUN","at_utc":utc_now()}
    if phase is None:return result
    result["intermediate_archives"]=intermediate_archives(root,phase)
    try:
        data=read_regular(root/(phase+"-profile")/"log/idea.log",limit=IDE_SPLIT_BYTES,tail=True)
        write_new(root/"evidence"/(phase+"-idea-pretermination.log"),data)
        result.update(status="PASS",bytes=len(data))
    except Exception as exc:
        result.update(status="UNAVAILABLE",error=type(exc).__name__)
    return result

def fresh_target(target, root, forbidden):
    target=absolute(target); root=absolute(root)
    validate_directory(root)
    require(not target.is_symlink(),'CLI target is a symlink')
    existing=target.parent
    while not existing.exists():
        require(not existing.is_symlink(),'CLI target has a dangling symlink ancestor');existing=existing.parent
    validate_directory(existing)
    target=target.resolve(); root=root.resolve()
    require(target.is_relative_to(root) and target!=root,'CLI target must be a disposable child of run root')
    require(not target.exists(),'CLI target already exists; official command would clean it')
    for item in forbidden:
        item=item.resolve()
        require(not item.is_relative_to(target) and not target.is_relative_to(item),'CLI target overlaps source/toolchain/profile')
    return target

def capture(command, env, cwd, stdout, stderr, timeout_seconds, disk_root, phase=None):
    """Own process group only. Timeout/disk exhaustion is failure, never a pass."""
    require(phase in (None,"export","validate"),"unknown diagnostic phase")
    started=time.monotonic(); started_at=utc_now(); timed_out=False; disk_low=False; termination=None
    with exclusive_writer(stdout) as out, exclusive_writer(stderr) as err:
        proc=subprocess.Popen(command,env=env,cwd=cwd,stdout=out,stderr=err,start_new_session=True)
        while proc.poll() is None:
            time.sleep(2)
            timed_out=time.monotonic()-started>timeout_seconds
            disk_low=shutil.disk_usage(disk_root).free<MIN_FREE_BYTES
            if timed_out or disk_low:
                termination=snapshot_before_stop(disk_root,phase)
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                break
    return {'exit_code':proc.returncode,'seconds':round(time.monotonic()-started,2),
            'timed_out':timed_out,'disk_low':disk_low,'timeout_seconds':timeout_seconds,
            'free_bytes_after':shutil.disk_usage(disk_root).free,
            'started_at_utc':started_at,'finished_at_utc':utc_now(),
            'pretermination_snapshot':termination}


def sanitized_environment():
    # Hosted runner process environment is an explicit minimal allowlist. No
    # GitHub/runtime/OIDC credential or language-injection variable is inherited.
    names={'PATH','HOME','USER','LOGNAME','LANG','LC_ALL','LC_CTYPE','LANGUAGE','TZ','TERM',
           'TMPDIR','JAVA_HOME','CI','GITHUB_ACTIONS','GITHUB_WORKSPACE','DISPLAY','XAUTHORITY'}
    return {k:v for k,v in os.environ.items() if k in names}

def cli_environment(idea,plugins,root,phase):
    profile=root/(phase+'-profile');profile.mkdir()
    for name in ('config','system','log','tmp'): (profile/name).mkdir()
    # Core Java remains free in the unified IDEA distribution. No account,
    # license key, agreement acceptance, trust override or telemetry flag copied.
    write_new(profile/'config/disabled_plugins.txt',b'com.intellij.modules.ultimate\n')
    properties=profile/'idea.properties'
    write_new(properties,('\n'.join(f'idea.{key}.path={value}' for key,value in {
        'config':profile/'config','system':profile/'system','log':profile/'log','plugins':plugins}.items())+'\n').encode())
    original=(idea/'bin/idea64.vmoptions').read_text()
    lines=[line for line in original.splitlines() if not line.startswith(('-Xmx','-Djava.io.tmpdir='))]
    options=profile/'idea.vmoptions'
    java_home=Path(os.environ['JAVA_HOME']).resolve()
    require((java_home/'bin/java').is_file(), 'JAVA_HOME has no Java executable')
    release=(java_home/'release').read_text()
    require(re.search(r'^JAVA_VERSION="21(?:[."+])',release,re.M), 'project JDK must be Java 21')
    write_new(options,('\n'.join([*lines,'-Xmx1536m','-XX:ActiveProcessorCount=2',f'-Djava.io.tmpdir={profile/"tmp"}',
        f'-Dproject.jdk={java_home}','-Dproject.jdk.name=academy-ci-jdk21'])+'\n').encode())
    env=sanitized_environment()
    # Token is only used by the preceding read-only GitHub gate; never pass it
    # to the IDE or processes belonging to a course.
    env.update({'IDEA_PROPERTIES':str(properties),'IDEA_VM_OPTIONS':str(options),'IDEA_JDK':str(idea/'jbr'),
                'GRADLE_USER_HOME':str(root/'gradle-home'),'ORG_GRADLE_PROJECT_withDocker':'true',
                'ORG_GRADLE_PROJECT_dockerApiVersion':'1.44'})
    return env,profile


def prepare_gradle_evidence(root):
    home=root/'gradle-home';home.mkdir();(home/'init.d').mkdir()
    destination=root/'evidence/gradle-jvm.jsonl'
    # This observes and enforces the actual Gradle process, not IDEA's JBR.
    # The file lives in a disposable GRADLE_USER_HOME, never in course content.
    script = """import groovy.json.JsonOutput
import org.gradle.util.GradleVersion
gradle.beforeSettings { settings ->
    def observation = [java_version: System.getProperty('java.version'),
        java_home: System.getProperty('java.home'),
        gradle_version: GradleVersion.current().version,
        root: settings.settingsDir.canonicalPath]
    new File(DESTINATION).append(JsonOutput.toJson(observation) + '\\n', 'UTF-8')
    if (JavaVersion.current() != JavaVersion.VERSION_21) {
        throw new GradleException('Official Academy CI requires actual Gradle JVM 21')
    }
    if (GradleVersion.current().version != '8.10.2') {
        throw new GradleException('Official Academy CI requires Gradle 8.10.2')
    }
}
"""
    script=script.replace('DESTINATION',"'"+str(destination).replace("'","\\'")+"'")
    write_new(home/'init.d/academy-ci-jvm-evidence.gradle',script.encode())

def inspect_gradle_evidence(root, expected_roots):
    path=root/'evidence/gradle-jvm.jsonl'
    require(path.is_file() and path.stat().st_size>0,'actual Gradle JVM evidence is missing')
    observations=[json.loads(line) for line in path.read_text().splitlines()]
    require(all(re.match(r'^21(?:[.+]|$)',x['java_version']) and x['gradle_version']=='8.10.2' for x in observations),
            'actual Gradle Java/Gradle version is incorrect')
    require({str(p.resolve()) for p in expected_roots}<={x['root'] for x in observations},'missing actual Gradle JVM evidence for official import')
    return {'status':'PASS','observations':observations}

def small_logs(root,evidence):
    validate_directory(root);validate_directory(evidence)
    for phase in ('export','validate'):
        path=root/(phase+'-profile')/'log/idea.log'
        try:
            read_regular(evidence/(phase+'-idea-pretermination.log'),limit=IDE_SPLIT_BYTES)
            limit=IDE_LOG_BYTES-IDE_SPLIT_BYTES
        except FileNotFoundError:limit=IDE_LOG_BYTES
        try:data=read_regular(path,limit=limit,tail=True)
        except FileNotFoundError:continue
        write_new(evidence/(phase+'-idea.log'),data)
    for name in ('generation.log','failure.log','export.stdout.log','export.stderr.log','validate.stdout.log','validate.stderr.log'):
        try:data=read_regular(evidence/name,limit=1024*1024,tail=True)
        except FileNotFoundError:continue
        replace_regular(evidence/name,data)

def execute(a):
    for candidate in (a.repo,a.run_root.parent,a.idea_home,a.plugins_home):validate_directory(candidate)
    require(not a.run_root.is_symlink(),'run root is a symlink')
    repo=a.repo.resolve(); root=a.run_root.resolve(); idea=a.idea_home.resolve(); plugins=a.plugins_home.resolve()
    require(root.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()),'run root must be in RUNNER_TEMP')
    require(root!=Path(os.environ['RUNNER_TEMP']).resolve() and not root.exists(),'run root must be new, never reused')
    require(not repo.is_relative_to(root) and not root.is_relative_to(repo),'run root must not overlap checkout')
    root.mkdir();evidence=root/'evidence';evidence.mkdir()
    result={'status':'RUNNING','phase':a.phase,'native_tests':'NOT_RUN','native_ui_check_reset':'NOT_RUN',
            'repository':os.environ.get('GITHUB_REPOSITORY'),'commit':os.environ.get('GITHUB_SHA'),
            'run_id':os.environ.get('GITHUB_RUN_ID'),'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
            'stages':{},'final_archive_published':False}
    dump(evidence/'summary.json',result)
    archive=None
    try:
        pins=read_json(Path(__file__).with_name('toolchain.json')); dump(evidence/'toolchain.json',pins)
        ci=read_json(a.source_ci_report);require(ci.get('status')=='PASS' and ci.get('sha')==os.environ.get('GITHUB_SHA'),'source CI is not green for this exact SHA')
        dump(evidence/'source-ci.json',ci)
        prepare_gradle_evidence(root)
        author=root/'author'
        command=[os.sys.executable,str(repo/'scripts/unify_course.py'),'--repo',str(repo),'--output',str(author),'--report',str(evidence/'generation.json')]
        with exclusive_writer(evidence/'generation.log') as generation_log:
            subprocess.run(command,cwd=repo,env=sanitized_environment(),check=True,stdout=generation_log,stderr=subprocess.STDOUT,timeout=60)
        validation_command=[os.sys.executable,str(repo/'scripts/validate_unified_course.py'),'--course',str(author),'--repo',str(repo),'--report',str(evidence/'unified-source-validation.json')]
        subprocess.run(validation_command,cwd=repo,env=sanitized_environment(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,timeout=60)
        result['stages']['unified_source']=read_json(evidence/'unified-source-validation.json')
        contract=build_contract(author);dump(root/'contract-private.json',contract)
        # Store hashes and expected names, never a generated stand-in archive.
        dump(evidence/'source-contract.json',redact_contract(contract))
        result['stages']['source_contract']={'status':'PASS','counts':contract['counts'],'files':len(contract['files'])}
        student=fresh_target(root/'student',root,[repo,author,idea,plugins])
        env,profile=cli_environment(idea,plugins,root,'export')
        command=[str(idea/'bin/idea'),'createCourse',str(student),'--local',str(author)]
        if a.display=='xvfb':command=['xvfb-run','-a','--server-args=-screen 0 1280x900x24',*command]
        else:env.pop('DISPLAY',None)
        require(not list((profile/'tmp').iterdir()),'export temp directory was not empty')
        run=capture(command,env,repo,evidence/'export.stdout.log',evidence/'export.stderr.log',300 if a.phase=='export-import-smoke' else 600,root,phase='export')
        result['stages']['official_export_process']=run;dump(evidence/'summary.json',result)
        require(run['exit_code']==0 and not run['timed_out'] and not run['disk_low'],'official createCourse failed or resource budget exceeded')
        found=list((profile/'tmp').rglob('course_archive_*.zip'))
        require(len(found)==1 and found[0].is_file() and not found[0].is_symlink() and found[0].stat().st_size>0,'expected exactly one fresh nonempty official archive')
        archive=root/'backend-interview-academy.zip'
        captured=read_regular(found[0],limit=128*1024*1024);write_new(archive,captured)
        require(sha(captured)==sha(read_regular(archive,limit=128*1024*1024)),'captured archive bytes changed')
        result['stages']['archive']=inspect_archive(archive,contract,pins);dump(evidence/'archive.json',result['stages']['archive'])
        result['stages']['author_changes']=inspect_author_changes(author,contract);dump(evidence/'author-changes.json',result['stages']['author_changes'])
        result['stages']['student_import']=inspect_import(student,contract,'student');dump(evidence/'student-import.json',result['stages']['student_import'])
        archive_hash=sha(read_regular(archive,limit=128*1024*1024));write_new(evidence/'SHA256SUMS',f'{archive_hash}  backend-interview-academy.zip\n'.encode())
        result['stages']['gradle_jvm']=inspect_gradle_evidence(root,[student]);dump(evidence/'gradle-jvm-gate.json',result['stages']['gradle_jvm'])
        if a.phase=='export-import-smoke':
            result['status']='SMOKE_PASS_NOT_RELEASE';return result
        require(shutil.disk_usage(root).free>=4*1024**3,'less than 4 GiB free before native Docker checks')
        validation=fresh_target(root/'validation',root,[repo,author,student,idea,plugins])
        env,profile=cli_environment(idea,plugins,root,'validate')
        report=evidence/'official-validation.json'
        require(not report.exists() and not report.is_symlink(),'validation output already exists or is linked')
        command=[str(idea/'bin/idea'),'validateCourse',str(validation),'--archive',str(archive),
                 '--tests','true','--links','true','--output-format','json','--output',str(report)]
        if a.display=='xvfb':command=['xvfb-run','-a','--server-args=-screen 0 1280x900x24',*command]
        else:env.pop('DISPLAY',None)
        run=capture(command,env,repo,evidence/'validate.stdout.log',evidence/'validate.stderr.log',2700,root,phase='validate')
        result['stages']['official_validate_process']=run;dump(evidence/'summary.json',result)
        # Parse available failure reports even when process failed/timed out.
        if report.is_file():
            native=validate_report(read_json(report),contract);dump(evidence/'validation-gate.json',native)
            result['stages']['native_validation']=native;result['native_tests']=native['native_tests']['status']
        require(run['exit_code']==0 and not run['timed_out'] and not run['disk_low'],'official validateCourse process failed')
        require(report.is_file(),'missing official validation JSON')
        require(result['stages']['native_validation']['status']=='PASS','native Tests or description links failed; exit 0 is insufficient')
        result['stages']['educator_import']=inspect_import(validation,contract,'educator');dump(evidence/'educator-import.json',result['stages']['educator_import'])
        result['stages']['gradle_jvm']=inspect_gradle_evidence(root,[student,validation]);dump(evidence/'gradle-jvm-gate.json',result['stages']['gradle_jvm'])
        require(sha(read_regular(archive,limit=128*1024*1024))==archive_hash,'archive changed during validation')
        subprocess.run(['git','--no-pager','diff','--no-ext-diff','--no-textconv','--exit-code'],cwd=repo,env=sanitized_environment(),check=True,stdout=subprocess.DEVNULL)
        dist=root/'dist';dist.mkdir();write_new(dist/archive.name,read_regular(archive,limit=128*1024*1024))
        write_new(dist/'SHA256SUMS',read_regular(evidence/'SHA256SUMS',limit=4096))
        require(sha(read_regular(dist/archive.name,limit=128*1024*1024))==archive_hash,'final copy changed archive')
        result['status']='PASS';result['final_archive_ready']=True
        return result
    except Exception as exc:
        result['status']='FAIL';result['error']=f'{type(exc).__name__}: {exc}'
        write_new(evidence/'failure.log',traceback.format_exc().encode())
        return result
    finally:
        try:small_logs(root,evidence)
        except Exception as exc:
            result['status']='FAIL';result['log_collection_error']=type(exc).__name__
        dump(evidence/'summary.json',result)
        # All paths are disposable. Do not remove targets, checkout, Docker state
        # or caches; the hosted VM owns teardown. No ZIP enters failure evidence.

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--idea-home',type=Path,required=True);p.add_argument('--plugins-home',type=Path,required=True)
    p.add_argument('--source-ci-report',type=Path,required=True)
    p.add_argument('--phase',choices=['export-import-smoke','full-validation'],default='export-import-smoke')
    p.add_argument('--display',choices=['headless','xvfb'],default='headless');a=p.parse_args()
    result=execute(a);print(json.dumps({'status':result['status'],'native_tests':result['native_tests']},ensure_ascii=False))
    raise SystemExit(0 if result['status'] in ('PASS','SMOKE_PASS_NOT_RELEASE') else 1)
