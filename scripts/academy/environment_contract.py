"""Strict evidence schema for actual imported-course environment acceptance."""
import re
import json
from pathlib import PurePosixPath
from gates import require

PROFILES = ('mysql', 'redis', 'kafka', 'rocketmq', 'capstone')
COMMON = ('start', 'doctor', 'health', 'bindings', 'write_read', 'stop', 'preserved', 'restart', 'read_after_restart', 'stop_final')
CAPSTONE = ('start', 'doctor', 'health', 'bindings', 'http', 'browser', 'pause', 'unavailable', 'recover', 'replay', 'same_stage', 'stop', 'preserved')
IDENTITY = ('repository', 'commit', 'run_id', 'run_attempt', 'archive_sha256', 'contract_sha256', 'handoff_sha256')

def expected_checks():
    return {'preflight', 'learner_entry', 'educator_entry', 'launcher_prepare', 'launcher_verify', 'probe_compile', 'import_integrity', 'cleanup'} | {
        f'{profile}.{step}' for profile in PROFILES for step in (CAPSTONE if profile == 'capstone' else COMMON)}

def validate_environment(report, native, identity):
    require(report.get('schema_version') == 1, 'unknown environment report schema')
    require(report.get('status') == 'PASS' and report.get('runtime') == 'real-docker', 'real environment acceptance did not pass')
    for key in IDENTITY:
        require(report.get(key) == identity.get(key) and identity.get(key), 'environment identity mismatch: '+key)
    for key in ('repository', 'commit', 'run_id', 'run_attempt'):
        require(native.get(key) == identity[key], 'native identity mismatch: '+key)
    require(re.fullmatch(r'[0-9a-f]{40}', report['commit']) is not None, 'invalid tested commit')
    for key in ('archive_sha256', 'contract_sha256', 'handoff_sha256'):
        require(re.fullmatch(r'[0-9a-f]{64}', report[key]) is not None, 'invalid evidence hash')
    require(native.get('stages', {}).get('archive', {}).get('archive_sha256') == report['archive_sha256'], 'environment tested another archive')
    require(report.get('docker_api_version') == '1.44', 'Docker SDK API pin missing')
    require(report.get('learner_business_checks') == 'NOT_RUN_EXPECTED_STARTER', 'learner starter must not be reported as passing reference business checks')
    require(report.get('course_origin') == 'official-import-snapshot', 'source-only assets are not environment proof')
    checks = report.get('checks', {})
    require(set(checks) == expected_checks(), 'missing or unexpected environment checks')
    commands = report.get('commands', [])
    require(commands and len(commands) <= 500, 'actual command evidence missing/oversize')
    ids = {command.get('id') for command in commands}
    require(len(ids) == len(commands) and ids == set(range(1, len(commands)+1)), 'ambiguous command IDs')
    for command in commands:
        require(isinstance(command.get('argv'), list) and command['argv'] and all(isinstance(v, str) for v in command['argv']), 'actual argv missing')
        require(command.get('exit_code') == 0 and command.get('timed_out') is False, 'failed or timed-out command')
        require(type(command.get('timeout_seconds')) is int and 0 < command['timeout_seconds'] <= 1200, 'unbounded command')
        require(isinstance(command.get('seconds'), (float, int)) and 0 <= command['seconds'] <= command['timeout_seconds']+20, 'invalid command duration')
        require(re.fullmatch(r'[0-9a-f]{64}', command.get('stdout_sha256', '')) is not None and re.fullmatch(r'[0-9a-f]{64}', command.get('stderr_sha256', '')) is not None, 'command output hashes missing')
    for name, check in checks.items():
        require(check.get('status') == 'PASS' and check.get('command_ids') and set(check['command_ids']) <= ids, 'missing execution for '+name)
        require(check.get('observations'), 'empty observation for '+name)
    imports = report.get('imports', {})
    require(set(imports) == {'educator', 'student'} and all(x.get('status') == 'PASS' and x.get('files', 0) >= 900 and x.get('post_runtime_revalidated') is True for x in imports.values()), 'official imports were not revalidated')
    image_refs = report.get('image_ledger', {})
    require(set(image_refs) == {'MYSQL_IMAGE', 'REDIS_IMAGE', 'KAFKA_IMAGE', 'ROCKETMQ_IMAGE', 'JAVA_BUILD_IMAGE', 'TESTCONTAINERS_RYUK_IMAGE', 'TESTCONTAINERS_TINY_IMAGE'}, 'fixed image ledger incomplete')
    require(re.fullmatch(r'[0-9a-f]{64}', report.get('image_ledger_sha256', '')) is not None, 'image ledger provenance missing')
    require(report['image_ledger_sha256']==identity.get('image_ledger_sha256'),'image ledger differs from native source contract')
    validate_commands(checks,commands,report)
    ownership = report.get('ownership', {})
    prefix = 'totalacademy-ci-'+report['run_id']+'-'+report['run_attempt']
    require(ownership.get('projects') == [prefix, prefix+'-capstone'], 'project isolation mismatch')
    require(ownership.get('empty_before') is True and ownership.get('empty_after') is True, 'CI-owned resource cleanup incomplete')
    require(ownership.get('containers') and ownership.get('volumes'), 'resource evidence missing')
    for profile in PROFILES:
        observed = checks[profile+'.bindings']['observations']
        require(observed.get('actual_loopback_only') is True and observed.get('container_ids'), 'actual Docker bindings missing: '+profile)
        require(checks[profile+'.preserved']['observations'].get('same_volume_ids') is True, 'stop lost volumes: '+profile)
    require(checks['capstone.same_stage']['observations'].get('stage') == '05-defense' and checks['capstone.same_stage']['observations'].get('same_container_ids') is True and checks['capstone.same_stage']['observations'].get('same_mounts') is True, 'recovery replaced original stage/container/mounts')
    require(checks['capstone.browser']['observations'].get('viewports') == [320,390,800,801,1440], 'provided frontend browser coverage incomplete')
    return {'status':'PASS', 'unified_environment_runtime':'PASS', 'checks':len(checks), 'archive_sha256':report['archive_sha256']}



def validate_commands(checks,commands,report):
    """Match the implemented command grammar, never mere argument presence."""
    python=report.get('python_executable','');repo=report.get('repo_root','');run=report.get('run_root','')
    def absolute(value):return isinstance(value,str) and value.startswith('/') and value!='/' and not value.endswith('/') and '..' not in PurePosixPath(value).parts
    require(absolute(python) and re.fullmatch(r'python(?:3(?:\.[0-9]+)?)?',PurePosixPath(python).name),'actual Python executable missing')
    require(absolute(repo) and absolute(run) and repo!=run,'actual repository/run root missing')
    course=run+'/handoff/educator';student=run+'/handoff/student';probes=repo+'/scripts/academy/probes'
    ports=report.get('ports',{});database=report.get('mysql_database','')
    require(set(ports)=={'MYSQL_PORT','REDIS_PORT','KAFKA_PORT','ROCKETMQ_PORT','CAPSTONE_HTTP_PORT'},'actual configured ports missing')
    require(all(isinstance(value,str) and re.fullmatch(r'[1-9][0-9]{3,4}',value) and 1024<=int(value)<=65535 for value in ports.values()) and len(set(ports.values()))==5,'invalid configured ports')
    require(isinstance(database,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}',database),'actual fixture database missing')
    project='totalacademy-ci-'+report['run_id']+'-'+report['run_attempt']
    by_id={row['id']:row['argv'] for row in commands}
    def selected(name):return [by_id[key] for key in checks[name]['command_ids']]
    def has(name, predicate):require(any(predicate(argv) for argv in selected(name)), 'required actual command absent: '+name)
    def lab(argv,action,profile,*extra):return argv==['bash',course+'/scripts/lab.sh',action,profile,*extra]
    def gradle(*args):return ['bash',course+'/scripts/gradle.sh',*args]
    def external_classpath(value):
        if not isinstance(value,str):return False
        entries=value.split(':')
        return bool(entries) and len(entries)==len(set(entries)) and all(absolute(path) and PurePosixPath(path).is_relative_to(run+'/gradle-home') and path.endswith('.jar') for path in entries)
    def javac(argv):return len(argv)==9 and argv[:4]==['javac','--release','21','-cp'] and external_classpath(argv[4]) and argv[5:]==['-d',run+'/probe-classes',probes+'/RocketSmoke.java',probes+'/ServiceSmoke.java']
    has('probe_compile',javac)
    compiled=[argv[4] for argv in selected('probe_compile') if javac(argv)]
    require(len(compiled)==1,'ambiguous compiled probe classpath')
    classpath=run+'/probe-classes:'+compiled[0]
    has('probe_compile',lambda argv:argv==gradle('--no-daemon','--max-workers=1','--console=plain','-PdockerApiVersion=1.44','-I',probes+'/classpath.gradle',':messaging-support:academyEnvironmentClasspath'))
    def inspect(argv):return len(argv)>=5 and argv[:3]==['docker','inspect','--format'] and argv[3].startswith('{"id":{{json .Id}},') and all(re.fullmatch(r'[0-9a-f]{12,64}',value) for value in argv[4:])
    for profile in PROFILES:
        for step,action in [('start','start'),('doctor','doctor'),('health','health'),('stop','stop')]+([] if profile=='capstone' else [('restart','start'),('stop_final','stop')]):
            extra=['--stage','05-defense'] if profile=='capstone' and action=='start' else []
            has(profile+'.'+step,lambda argv,a=action,p=profile,e=extra:lab(argv,a,p,*e))
        for step in ('bindings','preserved'):has(profile+'.'+step,inspect)
        if profile=='capstone':continue
        for step,read in [('write_read',False),('read_after_restart',True)]:
            name=profile+'.'+step
            if profile=='redis':
                expected=[python,repo+'/scripts/academy/redis_probe.py','--port',ports['REDIS_PORT'],'--marker',project]+(['--read-only'] if read else [])
            elif profile=='rocketmq':
                expected=['java','-Xmx256m','-XX:MaxDirectMemorySize=64m','-cp',classpath,'lab.environment.RocketSmoke','read' if read else 'write','127.0.0.1:'+ports['ROCKETMQ_PORT'],'lab_ci_roundtrip','lab_ci_roundtrip_group','lab_ci_durable','lab_ci_durable_group',project]
            else:
                key='MYSQL_PORT' if profile=='mysql' else 'KAFKA_PORT'
                expected=['java','-Xmx256m','-cp',classpath,'lab.environment.ServiceSmoke',profile+('-read' if read else '-write'),'127.0.0.1:'+ports[key],database,project]
            has(name,lambda argv,wanted=expected:argv==wanted)
    has('launcher_prepare',lambda argv:argv==gradle('prepare','--download'))
    has('launcher_verify',lambda argv:argv==gradle('--version'))
    for mode,root in (('student',student),('educator',course)):
        has('learner_entry' if mode=='student' else 'educator_entry',lambda argv,r=root:argv==['bash',r+'/scripts/lab.sh','verify'])
        has('import_integrity',lambda argv,r=root:argv==['bash',r+'/scripts/lab.sh','verify'])
    has('capstone.http',lambda argv:lab(argv,'workbench-check','capstone'))
    has('capstone.browser',lambda argv:argv==['node',course+'/materials/backend-capstone/scripts/browser-smoke.mjs'])
    for service in ('orders','delivery'):has('capstone.pause',lambda argv,s=service:lab(argv,'pause-service','capstone','--service',s))
    has('capstone.recover',lambda argv:lab(argv,'recover-service','capstone','--service','delivery'))
    def http(argv,path,status):return argv==[python,repo+'/scripts/academy/http_probe.py','--port',ports['CAPSTONE_HTTP_PORT'],'--path',path,'--status',status,'--json','{}']
    has('capstone.unavailable',lambda argv:http(argv,'/api/replay','503'))
    has('capstone.replay',lambda argv:http(argv,'/api/orders/recover-'+report['run_id']+'-'+report['run_attempt']+'/cancel','200'))
    has('capstone.same_stage',inspect)
    has('preflight',lambda argv:argv==['docker','version','--format','{{json .}}'])
    for kind in ('container','volume','network'):
        has('cleanup',lambda argv,k=kind:len(argv)==4 and argv[:3]==['docker',k,'rm'] and bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*',argv[3])))
