#!/usr/bin/env python3
"""统一lab入口调用的真实Docker验证器。没有daemon时返回NOT_RUN；统一调用方应映射为退出77，绝不降级成mock PASS。

run_verification只接受统一driver构造的、专用verify项目与新namespace。保留卷和日志；
收尾只stop本项目，不down -v、不prune、不改Docker socket/权限。
"""
import concurrent.futures,hashlib,json,os,pathlib,re,subprocess,time,urllib.error
from contract import request,wait_status,fresh_inventory_contract
from verification_guard import (claim_evidence,VerificationSetupError,VerificationInfrastructureError,
                                ContractViolation,require_contract)
from compose_policy import validate_compose

class InvalidEnvironment(RuntimeError):pass

def validate_context(compose_argv,env,base_url):
    if compose_argv[:2]!=['docker','compose']:raise InvalidEnvironment('Expected official Docker Compose argv')
    if compose_argv.count('--project-name')!=1:raise InvalidEnvironment('Exactly one explicit project required')
    project=compose_argv[compose_argv.index('--project-name')+1]
    if not re.fullmatch(r'totalacademy-[a-z0-9-]{1,48}-verify-[a-f0-9]{8}',project):
        raise InvalidEnvironment('Refuse fault injection outside dedicated verify project')
    if not re.fullmatch(r'c11-verify-[a-f0-9]{16}',env.get('CLOUDNATIVE_NAMESPACE','')):
        raise InvalidEnvironment('Fresh verification namespace required; never clear learner data')
    if env.get('LAB_PROJECT_NAME')!=project:raise InvalidEnvironment('Image namespace must match the isolated Compose project')
    files=[];index=2
    while index<len(compose_argv):
        flag=compose_argv[index]
        if flag not in ('--project-name','--project-directory','--env-file','-f','--file','--profile') or index+1>=len(compose_argv):
            raise InvalidEnvironment('Only bounded Compose global options are allowed')
        if flag in ('-f','--file'):files.append(pathlib.Path(compose_argv[index+1]).resolve())
        index+=2
    expected=pathlib.Path(__file__).resolve().parents[3]/'infra/cloudnative.compose.yaml'
    if not files or files[0]!=expected.resolve():raise InvalidEnvironment('Use the explicit course Compose file; never infer one from current directory')
    try:
        config=json.loads(files[0].read_text())
        errors=validate_compose(config)
        if errors:raise InvalidEnvironment('Unsafe base Compose configuration: '+','.join(errors))
        for path in files[1:]:
            override=json.loads(path.read_text())
            if set(override)!={'services'} or set(override['services'])!={'cloudnative-api'}:
                raise InvalidEnvironment('Verification overrides may change only the API build context')
            service=override['services']['cloudnative-api']
            if set(service)!={'build'} or set(service['build'])!={'context','dockerfile'} or service['build']['dockerfile']!='container/Dockerfile':
                raise InvalidEnvironment('Verification override cannot change ports, volumes or runtime privileges')
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise InvalidEnvironment('Compose configuration unavailable or malformed') from error
    port=env.get('CLOUDNATIVE_HTTP_PORT','')
    if not port.isdigit() or base_url!=f'http://127.0.0.1:{port}':raise InvalidEnvironment('Loopback URL must match checked configured port')
    return project

def run_verification(compose_argv,env,base_url,evidence_dir):
    project=validate_context(compose_argv,env,base_url)
    evidence_dir=pathlib.Path(evidence_dir);context=claim_evidence(evidence_dir)
    report={'run_id':context['run_id'],'status':'NOT_RUN','mode':'REAL_DOCKER','project':project,'namespace':env['CLOUDNATIVE_NAMESPACE'],'cases':[],
            'http_observations':[],'cleanup':'stop only; volumes preserved','limits':['No Kubernetes/Istio verification in this slice']}
    command_log=[];started=False
    def execute(argv,timeout=90,required=True):
        result=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=timeout)
        # 不记录env/compose config/password，仅记去秘密argv与服务输出；API无秘密日志。
        safe_argv=['<redacted>' if env.get('REDIS_PASSWORD') and env['REDIS_PASSWORD'] in a else a for a in argv]
        secret=env.get('REDIS_PASSWORD')
        redact=lambda text:text.replace(secret,'<redacted>') if secret else text
        command_log.append({'argv':safe_argv,'returncode':result.returncode,'stdout':redact(result.stdout),'stderr':redact(result.stderr)})
        if required and result.returncode:raise VerificationSetupError('Docker command failed: '+' '.join(safe_argv))
        return result
    def compose(*args,**kwargs):return execute(compose_argv+list(args),**kwargs)
    try:
        # probe daemon不触碰权限；缺失与拒绝均保持NOT_RUN/异常，调用方不得把它计作PASS。
        try:
            result=execute(['docker','info','--format','{{.ServerVersion}}'],required=False,timeout=15)
        except FileNotFoundError:
            report['reason']='Docker CLI not available';return report
        if result.returncode:
            report['reason']='Docker daemon unavailable; do not install or change permissions';return report
        report['docker_server']=result.stdout.strip();report['status']='FAIL'
        started=True # failed up may already have created some of this dedicated project's containers
        compose('up','-d','--build',timeout=600)
        wait_status(base_url,'/downstream-check',seconds=45)
        fresh_inventory_contract(base_url,'real',report['http_observations'],report['cases'])
        if not report['cases']:raise VerificationSetupError('No HTTP business cases executed')
        cid=compose('ps','-q','cloudnative-api').stdout.strip();assert cid
        actual_user=execute(['docker','inspect','--format','{{.Config.User}}',cid]).stdout.strip()
        assert actual_user=='10001:10001',actual_user;report['cases'].append('runtime_nonroot')
        content_check=compose('exec','-T','cloudnative-api','sh','-c',
            'command -v find >/dev/null || exit 2; if test ! -e /build && test -z "$(find /opt/app -name .env -o -name synthetic-course-secret.txt)" && test ! -d /usr/share/maven && ! command -v javac >/dev/null 2>&1; then echo C11_IMAGE_CONTENT_CHECK=0; else echo C11_IMAGE_CONTENT_CHECK=1; fi')
        marker=content_check.stdout.strip()
        if marker not in ('C11_IMAGE_CONTENT_CHECK=0','C11_IMAGE_CONTENT_CHECK=1'):
            raise VerificationSetupError('Missing runtime-image inspection result')
        require_contract(marker=='C11_IMAGE_CONTENT_CHECK=0','runtime_image_contents',{'marker':marker})
        report['cases'].append('runtime_has_no_build_tree_compiler_or_env')
        bindings=execute(['docker','inspect','--format','{{json .HostConfig.PortBindings}}',cid]).stdout
        for values in json.loads(bindings).values():
            for binding in values:assert binding['HostIp']=='127.0.0.1',binding
        redis_id=compose('ps','-q','redis').stdout.strip()
        redis_ports=execute(['docker','inspect','--format','{{json .HostConfig.PortBindings}}',redis_id]).stdout.strip()
        assert json.loads(redis_ports) in ({},None),redis_ports
        report['cases'].append('only_loopback_api_no_redis_host_port')
        # 保留同一个Redis卷；暂停依赖而不是删除/重置数据。
        compose('stop','redis')
        assert request(base_url,'/ready')[0]==503
        assert request(base_url,'/live')[0]==200
        assert request(base_url,'/orders?request_id=outage&quantity=1','POST')[0]==503
        report['cases'].append('dependency_outage_rejects_business_keeps_live')
        compose('up','-d','redis');wait_status(base_url,'/ready',seconds=45)
        assert request(base_url,'/stock')==(200,{'stock':0})
        assert request(base_url,'/seed','POST')==(200,{'created':False,'stock':0})
        report['cases'].append('redis_restart_preserves_inventory_and_seed')
        # 复用应用的DNS/TCP/RESP客户端，在一次性容器内做真实网络错误对照。
        for host,port,layer in [('academy-c11-missing.invalid','6379','DNS'),('localhost','6379','CONNECT'),('redis','1','CONNECT')]:
            result=compose('run','--rm','--no-deps','-e','REDIS_HOST='+host,'-e','REDIS_PORT='+port,'--entrypoint','java','cloudnative-api','-cp','/opt/app/classes','labs.RedisDiagnostic',required=False)
            assert result.returncode!=0,(host,result.stdout)
            lines=[line for line in result.stdout.splitlines() if line.startswith('{')]
            assert lines and json.loads(lines[-1])['layer']==layer,(host,result.stdout)
            report['cases'].append('network_'+host+'_'+port+'_'+layer)
        # 防止仅用退出码掩盖SIGKILL：必须收到进行中请求完整200和完成日志。
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            response=pool.submit(request,base_url,'/slow?millis=1500')
            deadline=time.monotonic()+3
            while 'slow_started' not in compose('logs','--no-color','cloudnative-api').stdout:
                assert time.monotonic()<deadline;time.sleep(.05)
            begin=time.monotonic();compose('stop','-t','6','cloudnative-api');elapsed=time.monotonic()-begin
            assert response.result()==(200,{'status':'COMPLETED'})
            assert elapsed<7,elapsed
        logs=compose('logs','--no-color','cloudnative-api').stdout
        state=json.loads(execute(['docker','inspect','--format','{{json .State}}',cid]).stdout)
        if state.get('OOMKilled'):raise VerificationSetupError('OOM is a resource failure, not proof of swallowed SIGTERM')
        if 'started' not in logs:raise VerificationSetupError('Lifecycle logs unavailable')
        require_contract(state['ExitCode']!=137,'sigterm_forced_kill',{'exit_code':state['ExitCode'],'hook_completed':'shutdown_completed' in logs})
        require_contract('shutdown_completed' in logs,'shutdown_hook_missing',{'exit_code':state['ExitCode']})
        report['cases'].append('sigterm_drains_inflight_no_forced_kill')
        compose('up','-d','cloudnative-api');wait_status(base_url,'/ready',seconds=45)
        assert request(base_url,'/stock')==(200,{'stock':0});report['cases'].append('app_restart_preserves_inventory')
        if not report['cases']:raise VerificationSetupError('No Docker behavior cases executed')
        report['status']='PASS'
        return report
    except (ContractViolation,VerificationInfrastructureError) as error:
        report['failure']={'classification':'INFRASTRUCTURE' if isinstance(error,VerificationInfrastructureError) else 'CONTRACT_VIOLATION',
                           'case_id':error.case_id,'detail':error.detail}
        raise
    except (VerificationSetupError,OSError,subprocess.SubprocessError) as error:
        report['failure']={'classification':'INFRASTRUCTURE','error_type':type(error).__name__}
        raise
    finally:
        if started:
            try:
                stopped=compose('stop',required=False)
                if stopped.returncode:report['cleanup_status']='STOP_FAILED';report['status']='FAIL'
                compose('ps','--all',required=False);compose('logs','--no-color','--tail','200',required=False)
            except (OSError,subprocess.SubprocessError):report['cleanup_status']='COLLECT_FAILED';report['status']='FAIL'
        (evidence_dir/'docker-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        (evidence_dir/'docker-commands.json').write_text(json.dumps(command_log,ensure_ascii=False,indent=2)+'\n')
