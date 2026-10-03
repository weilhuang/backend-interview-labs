#!/usr/bin/env python3
"""Real Docker acceptance of hash-bound official educator/student imports on a fresh CI VM.

No source-course fallback, global prune, credential inheritance, or learner business-pass claim.
All operations are bounded and only the two initially-empty run-owned Compose projects are mutated.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from gates import require, read_json, dump, sha, inspect_import
from safe_io import read_regular, write_new, new_directory, validate_directory
from native_handoff import unpack, MAX_CONTAINER
from environment_contract import validate_environment
from collect_evidence import sanitize_text
from run_official import sanitized_environment

SERVICES = ('mysql','redis','kafka','rocketmq')
PORTS = {'mysql':('MYSQL_PORT','3306/tcp'),'redis':('REDIS_PORT','6379/tcp'),'kafka':('KAFKA_PORT','19092/tcp'),'rocketmq':('ROCKETMQ_PORT','8081/tcp'),'orders':('CAPSTONE_HTTP_PORT','8080/tcp')}
IMAGE_KEYS = {'mysql':'MYSQL_IMAGE','redis':'REDIS_IMAGE','kafka':'KAFKA_IMAGE','rocketmq':'ROCKETMQ_IMAGE','orders':'JAVA_BUILD_IMAGE','delivery':'JAVA_BUILD_IMAGE'}
MAX_OUTPUT = 4*1024*1024

class Execution:
    def __init__(self, root, report, env):
        self.root=root;self.report=report;self.env=env
        self.raw=root/'raw';new_directory(self.raw)
        self.evidence=root/'evidence';new_directory(self.evidence)
    def run(self, argv, cwd, timeout=90, env=None):
        require(0 < timeout <= 1200, 'invalid subprocess timeout')
        identifier=len(self.report['commands'])+1;start=time.monotonic()
        out=self.raw/f'{identifier}.out';err=self.raw/f'{identifier}.err'
        record={'id':identifier,'argv':[str(x) for x in argv],'cwd':str(cwd),'timeout_seconds':timeout,'timed_out':False,'output_limit':False,'disk_low':False}
        self.report['commands'].append(record)
        with out.open('xb') as stdout, err.open('xb') as stderr:
            process=subprocess.Popen(record['argv'],cwd=cwd,env=env or self.env,stdout=stdout,stderr=stderr,start_new_session=True)
            while process.poll() is None:
                record['timed_out']=time.monotonic()-start>timeout
                record['output_limit']=out.stat().st_size>MAX_OUTPUT or err.stat().st_size>MAX_OUTPUT
                record['disk_low']=shutil.disk_usage(self.root).free<2*1024**3
                if any(record[k] for k in ('timed_out','output_limit','disk_low')):
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    break
                time.sleep(.2)
        record.update(exit_code=process.returncode,seconds=round(time.monotonic()-start,3))
        for path,key in ((out,'stdout'),(err,'stderr')):
            content=read_regular(path,limit=MAX_OUTPUT,tail=True)
            record[key+'_sha256']=sha(content)
            # Only bounded output of our exact commands. No broad log/profile scan.
            text=content.decode('utf8',errors='replace')
            for name,value in (env or self.env).items():
                if 'PASSWORD' in name and value:text=text.replace(value,'[redacted]')
            write_new(self.evidence/f'command-{identifier}-{key}.log',sanitize_text(text[-32768:]).encode())
        dump(self.evidence/'summary.json',self.report)
        require(process.returncode==0 and not any(record[k] for k in ('timed_out','output_limit','disk_low')), 'command '+str(identifier)+' failed or exceeded resource budget')
        return read_regular(out,limit=MAX_OUTPUT).decode('utf8')
    def check(self,name,action):
        before=len(self.report['commands'])
        observations=action()
        require(len(self.report['commands'])>before, 'check has no actual command: '+name)
        self.report['checks'][name]={'status':'PASS','command_ids':list(range(before+1,len(self.report['commands'])+1)),'observations':observations or {'completed':True}}
        dump(self.evidence/'summary.json',self.report)

class Acceptance:
    def __init__(self, a, root, identity, native, contract, imports):
        self.a=a;self.root=root;self.course=root/'handoff/educator';self.student=root/'handoff/student'
        self.identity=identity;self.native=native;self.contract=contract
        self.project='totalacademy-ci-'+identity['run_id']+'-'+identity['run_attempt'];self.projects=[self.project,self.project+'-capstone']
        self.report={'schema_version':1,**identity,'status':'RUNNING','runtime':'real-docker','course_origin':'official-import-snapshot','docker_api_version':'1.44',
            'learner_business_checks':'NOT_RUN_EXPECTED_STARTER','python_executable':sys.executable,'repo_root':str(a.repo.resolve()),'run_root':str(root),'imports':imports,'checks':{},'commands':[],
            'ownership':{'projects':self.projects,'empty_before':False,'empty_after':False,'containers':{},'volumes':{}},
            'platform_scope':'ubuntu-24.04 amd64 only; macOS/Apple Silicon and native GUI Check/Reset not covered'}
        self.env=sanitized_environment();self.env.pop('DISPLAY',None)
        self.env.update({key:os.environ[key] for key in ('DOCKER_HOST','DOCKER_CONTEXT') if key in os.environ})
        self.env.update(CI='true',DOCKER_API_VERSION='1.44',ORG_GRADLE_PROJECT_dockerApiVersion='1.44',GRADLE_USER_HOME=str(root/'gradle-home'),
                        LAB_GRADLE_CACHE=str(root/'gradle-launcher'),PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1')
        self.ex=Execution(root,self.report,self.env)
        spec=importlib.util.spec_from_file_location('imported_lab',self.course/'scripts/lab.py')
        sys.path.insert(0,str(self.course/'scripts'));self.lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.lab)
        require(self.lab.ROOT==self.course.resolve(),'imported environment entry escaped snapshot')
        self.cfg=None;self.envpath=None;self.containers={};self.volumes={};self.networks={};self.preflight_complete=False
    def run(self,command,timeout=90,env=None,cwd=None):return self.ex.run(command,cwd or self.course,timeout,env)
    def labcmd(self,*args,timeout=300):return self.run(['bash',str(self.course/'scripts/lab.sh'),*args],timeout)
    def compose(self,cap=False):return self.lab.compose(self.cfg,self.envpath,cap)
    def docker(self,*args):return self.run(['docker',*args],60)
    def jsoninspect(self,kind,name,template):
        return json.loads(self.docker(kind,'inspect','--format',template,name))
    def listed(self,kind,project):
        command=['docker',kind,'ls','--quiet','--filter','label=com.docker.compose.project='+project]
        if kind=='container':command.insert(3,'--all')
        return self.run(command,60).split()
    def preflight(self):
        require(self.run(['git','rev-parse','HEAD'],30,cwd=self.a.repo).strip()==self.identity['commit'],'checkout differs from tested SHA')
        self.run(['git','--no-pager','diff','--no-ext-diff','--no-textconv','--exit-code'],30,cwd=self.a.repo)
        require(not self.run(['git','ls-files','--others','--exclude-standard'],30,cwd=self.a.repo).strip(),'unexpected untracked checkout input')
        # Reject remote endpoint/context before even read-only daemon queries.
        if self.env.get('DOCKER_HOST'):self.lab.require_local_endpoint(self.env['DOCKER_HOST'],'DOCKER_HOST')
        context=self.env.get('DOCKER_CONTEXT') or self.run(['docker','context','show'],30).strip()
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',context),'invalid Docker context')
        endpoint=json.loads(self.run(['docker','context','inspect','--format','{{json .Endpoints.docker.Host}}',context],30))
        self.lab.require_local_endpoint(endpoint,'Docker context '+context)
        self.run(['docker','version','--format','{{json .}}'],30)
        self.run(['docker','compose','version','--short'],30)
        for project in self.projects:
            for kind in ('container','volume','network'):require(not self.listed(kind,project),'project existed before CI: '+project)
        self.preflight_complete=True;self.report['ownership']['empty_before']=True
        example=read_regular(self.course/'infra/.env.example',limit=16384).decode()
        require('LAB_PROJECT_NAME=auto' in example,'unexpected project template')
        # Allocate currently free loopback ports; lab.py rechecks before startup.
        ports=[]
        for _ in range(5):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            require(port not in ports,'duplicate free port allocation');ports.append(port)
        text=example.replace('LAB_PROJECT_NAME=auto','LAB_PROJECT_NAME='+self.project)
        for (key,_),port in zip(PORTS.values(),ports):text=re.sub(r'^'+key+r'=.*$',key+'='+str(port),text,flags=re.M)
        write_new(self.course/'infra/.env',text.encode());self.cfg,self.envpath=self.lab.config()
        require(self.cfg['LAB_PROJECT_NAME']==self.project,'CI configuration project mismatch')
        self.report['ports']={key:self.cfg[key] for key,_ in PORTS.values()};self.report['mysql_database']=self.cfg['MYSQL_DATABASE']
        own=self.lab.versions();self.report['image_ledger']=own
        self.report['image_ledger_sha256']=sha(read_regular(self.course/'shared/versions.env',limit=16384))
        # The lab environment helper normally preserves a learner's environment.
        # CI admits only its ledger/config-derived values; it cannot replace our
        # private Gradle homes, toolchain variables or minimal credential-free env.
        derived=self.lab.environment(self.cfg,'05-defense')
        allowed=set(self.cfg)|set(own)|{'CAPSTONE_DIST_PATH','LAB_SHARED_VERSIONS','CAPSTONE_STAGE'}
        self.env.update({key:derived[key] for key in allowed})
        self.ex.env=self.env
        return {'docker_api_version':'1.44','unique_empty_projects':self.projects,'available_ports':ports}
    def entry(self,root):
        require(not any((root/name).exists() for name in ('gradlew','gradlew.bat','gradle/wrapper/gradle-wrapper.jar')),'acceptance must exercise official import without excluded Wrapper')
        for action in ('verify','profiles'):self.run(['bash',str(root/'scripts/lab.sh'),action],60,cwd=root)
        return {'wrapper_absent':True,'launcher_shell':'bash','launcher_mode':oct((root/'scripts/gradle.sh').stat().st_mode&0o777),'business_tests':'NOT_RUN_EXPECTED_STARTER' if root==self.student else 'separate real environment probes'}
    def launcher_prepare(self):
        self.run(['bash',str(self.course/'scripts/gradle.sh'),'prepare','--download'],600)
        return {'fixed_distribution':'Gradle8.10.2','explicit_download':True,'source':'imported gradle-wrapper.properties'}
    def launcher_verify(self):
        for root in (self.course,self.student):self.run(['bash',str(root/'scripts/gradle.sh'),'verify'],60,cwd=root)
        output=self.run(['bash',str(self.course/'scripts/gradle.sh'),'--version'],60)
        require('Gradle 8.10.2' in output,'actual launcher Gradle version mismatch')
        return {'actual_version':'8.10.2','both_imports':True}
    def compile_probes(self):
        script=self.a.repo/'scripts/academy/probes/classpath.gradle'
        output=self.run(['bash',str(self.course/'scripts/gradle.sh'),'--no-daemon','--max-workers=1','--console=plain','-PdockerApiVersion=1.44','-I',str(script),':messaging-support:academyEnvironmentClasspath'],600)
        matches=[line.removeprefix('ACADEMY_CLASSPATH=') for line in output.splitlines() if line.startswith('ACADEMY_CLASSPATH=')]
        require(len(matches)==1,'missing unique imported locked classpath')
        jars=matches[0].split(os.pathsep)
        require(jars and all(Path(j).is_absolute() and Path(j).is_relative_to(self.root/'gradle-home') and Path(j).suffix=='.jar' for j in jars),'unexpected dependency classpath')
        for jar in jars:read_regular(jar,limit=64*1024*1024)
        self.classes=self.root/'probe-classes';new_directory(self.classes)
        sources=[self.a.repo/'scripts/academy/probes'/name for name in ('RocketSmoke.java','ServiceSmoke.java')]
        self.run(['javac','--release','21','-cp',matches[0],'-d',str(self.classes),*[str(p) for p in sources]],120)
        self.classpath=str(self.classes)+os.pathsep+matches[0]
        return {'actual_gradle_jvm':'21','dependency_source':'official educator messaging-support runtimeClasspath strict locks','source_sha256':{p.name:sha(read_regular(p,limit=65536)) for p in [script,*sources]},'jar_count':len(jars)}
    def inspect(self,cap=False,require_healthy=True):
        project=self.projects[int(cap)];expected=set(('mysql','redis','kafka','delivery','orders') if cap else self.current_services)
        ids=self.listed('container',project);result={}
        template='{"id":{{json .Id}},"labels":{{json .Config.Labels}},"state":{"running":{{json .State.Running}},"health":{{json .State.Health.Status}},"oom":{{json .State.OOMKilled}}},"ports":{{json .NetworkSettings.Ports}},"image":{{json .Config.Image}},"image_id":{{json .Image}},"mounts":{{json .Mounts}}}'
        records=[json.loads(line) for line in self.docker('inspect','--format',template,*ids).splitlines()] if ids else []
        for raw in records:
            cid=raw['id'];labels=raw['labels']
            service=labels.get('com.docker.compose.service')
            require(labels.get('com.docker.compose.project')==project and service in (('mysql','redis','kafka','delivery','orders') if cap else SERVICES),'foreign service in CI project')
            require(labels.get('com.docker.compose.project.working_dir')==str(self.course/'infra'),'container source directory mismatch')
            expected_config=str(self.course/('infra/capstone.compose.yaml' if cap else 'infra/compose.yaml'))
            require(labels.get('com.docker.compose.project.config_files')==expected_config,'container Compose source mismatch')
            state=raw['state'];ports=raw['ports'] or {};image=raw['image']
            require(image==self.report['image_ledger'][IMAGE_KEYS[service]],'container image drift')
            mounts=raw['mounts']
            safe_mounts=[]
            for mount in mounts:
                if mount['Type']=='volume':
                    name=mount['Name']
                    if name not in self.volumes:
                        vlabels=self.jsoninspect('volume',name,'{{json .Labels}}')
                        require(vlabels.get('com.docker.compose.project')==project,'foreign volume mounted')
                    volume={'project':project,'name':name,'destination':mount['Destination']};self.volumes[name]=volume;safe_mounts.append(volume)
                elif mount['Type']=='bind':
                    src=Path(mount['Source']);require(src.is_relative_to(self.course) and not mount['RW'],'foreign/writable bind mount')
                    safe_mounts.append({'source':str(src),'destination':mount['Destination'],'rw':False})
                else:raise ValueError('unapproved mount type')
            record={'id':cid,'service':service,'project':project,'state':state,'ports':ports,'image':image,'image_id':raw['image_id'],'mounts':safe_mounts}
            self.containers[cid]=record
            if service not in expected:
                require(not state['running'],'unselected profile is running');continue
            require(service not in result,'duplicate service')
            if require_healthy:require(state=={'running':True,'health':'healthy','oom':False},'unhealthy actual container')
            published={key:value for key,value in ports.items() if value}
            if not state['running']:
                result[service]=record;continue
            if service in PORTS and (not cap or service=='orders'):
                key,container_port=PORTS[service]
                require(published=={container_port:[{'HostIp':'127.0.0.1','HostPort':self.cfg[key]}]},'unexpected actual published ports')
            else:require(not published,'private capstone dependency exposed')
            result[service]=record
        require(set(result)==expected,'missing service containers')
        self.report['ownership']['containers']=self.containers;self.report['ownership']['volumes']=self.volumes
        return result
    def bindings(self,cap=False):
        snapshot=self.inspect(cap);return {'actual_loopback_only':True,'container_ids':[x['id'] for x in snapshot.values()],'services':snapshot}
    def stop(self,profile):
        self.labcmd('stop',profile,timeout=180)
        states=self.inspect(profile=='capstone',False)
        require(all(not state['state']['running'] for state in states.values()),'stop left a service running')
        return {'stopped_container_ids':[x['id'] for x in states.values()]}
    def preserved(self,profile,before):
        after=self.inspect(profile=='capstone',False)
        require({s:(r['id'],r['mounts']) for s,r in before.items()}=={s:(r['id'],r['mounts']) for s,r in after.items()},'stop replaced containers/mounts')
        for name in self.volumes:self.docker('volume','inspect','--format','{{.Name}}',name)
        return {'same_volume_ids':True,'same_container_ids':True,'volumes':[m for r in after.values() for m in r['mounts'] if 'name' in m]}
    def probe(self,service,read=False):
        self.inspect(False)
        action=service+('-read' if read else '-write')
        if service=='redis':
            # Python host probe uses the actual published socket, auth and RESP.
            output=self.run([sys.executable,str(self.a.repo/'scripts/academy/redis_probe.py'),'--port',self.cfg['REDIS_PORT'],'--marker',self.project]+(['--read-only'] if read else []),30)
            require('REDIS_SMOKE_OK' in output,'Redis probe missing success')
        elif service=='rocketmq':
            if not read:
                for topic,group in (('lab_ci_roundtrip','lab_ci_roundtrip_group'),('lab_ci_durable','lab_ci_durable_group')):
                    admin=self.compose()+['exec','-T','rocketmq','bash','/opt/lab-rocketmq/admin.sh']
                    self.run(admin+['updateTopic','-n','127.0.0.1:9876','-b','127.0.0.1:10911','-t',topic,'-r','1','-w','1','-a','+message.type=NORMAL'],60)
                    self.run(admin+['updateSubGroup','-n','127.0.0.1:9876','-b','127.0.0.1:10911','-g',group],60)
            output=self.run(['java','-Xmx256m','-XX:MaxDirectMemorySize=64m','-cp',self.classpath,'lab.environment.RocketSmoke','read' if read else 'write','127.0.0.1:'+self.cfg['ROCKETMQ_PORT'],'lab_ci_roundtrip','lab_ci_roundtrip_group','lab_ci_durable','lab_ci_durable_group',self.project],180)
            require('ROCKETMQ_SMOKE_OK='+('read' if read else 'write') in output,'RocketMQ probe missing success')
        else:
            output=self.run(['java','-Xmx256m','-cp',self.classpath,'lab.environment.ServiceSmoke',action,'127.0.0.1:'+self.cfg[PORTS[service][0]],self.cfg['MYSQL_DATABASE'],self.project],150)
            require('SERVICE_SMOKE_OK='+action in output,'service probe missing success')
        return {'protocol':'host-loopback','operation':'read_existing_marker_without_write' if read else 'write_then_read_exact_marker','marker':self.project}
    def profile(self,profile):
        self.current_services=(profile,)
        self.ex.check(profile+'.start',lambda:self.labstep('start',profile,timeout=720))
        self.ex.check(profile+'.doctor',lambda:self.labstep('doctor',profile,timeout=120))
        self.ex.check(profile+'.health',lambda:self.labstep('health',profile,timeout=120))
        self.ex.check(profile+'.bindings',lambda:self.bindings())
        self.ex.check(profile+'.write_read',lambda:self.probe(profile))
        before=self.inspect()
        self.ex.check(profile+'.stop',lambda:self.stop(profile))
        self.ex.check(profile+'.preserved',lambda:self.preserved(profile,before))
        self.ex.check(profile+'.restart',lambda:self.labstep('start',profile,timeout=720))
        self.ex.check(profile+'.read_after_restart',lambda:self.probe(profile,True))
        self.ex.check(profile+'.stop_final',lambda:self.stop(profile))
    def labstep(self,*args,timeout=300):
        self.labcmd(*args,timeout=timeout);return {'entrypoint':'bash scripts/lab.sh','arguments':list(args)}
    def browser(self):
        self.inspect(True)
        base=self.course/'materials/backend-capstone';build=base/'build';build.mkdir(exist_ok=True)
        self.run(['google-chrome','--version'],30)
        self.run(['node','--version'],30)
        self.run(['npm','install','--prefix',str(build/'browser'),'--no-save','--package-lock=false','--ignore-scripts','playwright@1.62.1'],120)
        self.run(['node',str(base/'scripts/browser-smoke.mjs')],200,cwd=base)
        layouts=read_json(build/'browser-layout.json')
        require([row['viewport'] for row in layouts]==[320,390,800,801,1440],'browser output viewports missing')
        for name in ['browser-layout.json','browser-smoke.png']+[f'browser-layout-{width}.png' for width in (320,390,800,801,1440)]:
            content=read_regular(build/name,limit=4*1024*1024);write_new(self.ex.evidence/name,content)
        return {'viewports':[320,390,800,801,1440],'provided_script_sha256':sha(read_regular(base/'scripts/browser-smoke.mjs',limit=65536)),'real_api_actions':['submit','same-ID-retry','conflict409','cancel','replay','projection']}
    def request(self,path,value=None,expected=200):
        # A separate bounded process records each HTTP request and response hash;
        # arguments contain only synthetic CI request IDs and fixture quantities.
        snapshot=self.inspect(True,False)
        require(snapshot['orders']['state']=={'running':True,'health':'healthy','oom':False},'HTTP target orders is not healthy')
        command=[sys.executable,str(self.a.repo/'scripts/academy/http_probe.py'),'--port',self.cfg['CAPSTONE_HTTP_PORT'],'--path',path,'--status',','.join(map(str,expected)) if isinstance(expected,tuple) else str(expected)]
        if isinstance(expected,tuple):command+=['--envelope']
        if value is not None:command+=['--json',json.dumps(value,separators=(',',':'))]
        output=self.run(command,60);return json.loads(output)
    def capstone(self):
        profile='capstone';self.current_services=()
        self.ex.check(profile+'.start',lambda:self.labstep('start','capstone','--stage','05-defense',timeout=1200))
        self.ex.check(profile+'.doctor',lambda:self.labstep('doctor','capstone',timeout=120))
        self.ex.check(profile+'.health',lambda:self.labstep('health','capstone',timeout=120))
        self.ex.check(profile+'.bindings',lambda:self.bindings(True))
        self.ex.check(profile+'.http',lambda:self.labstep('workbench-check','capstone',timeout=300))
        self.ex.check(profile+'.browser',self.browser)
        before=self.inspect(True)
        stage=self.lab.capstone_task('05-defense')
        expected_dist=self.course/stage['path']/'build/install'/stage['gradle_project'][1:]
        for service in ('orders','delivery'):
            require(any(m.get('source')==str(expected_dist) and m['destination']=='/opt/app' for m in before[service]['mounts']),'original checkpoint mount mismatch')
        request_id='recover-'+self.identity['run_id']+'-'+self.identity['run_attempt']
        def pause():
            self.request('/api/orders',{'requestId':request_id,'sku':'book','quantity':1})
            self.labcmd('pause-service','capstone','--service','orders',timeout=180)
            require(not self.inspect(True,False)['orders']['state']['running'],'orders did not pause')
            self.labcmd('recover-service','capstone','--service','orders',timeout=240)
            require(self.request('/api/orders/'+request_id+'?fresh=true')['status']=='RESERVED','order fact lost across process pause')
            self.labcmd('pause-service','capstone','--service','delivery',timeout=180)
            require(not self.inspect(True,False)['delivery']['state']['running'],'delivery did not pause')
            return {'orders_restart_preserved_fact':True,'delivery_paused':True,'request_id':request_id}
        self.ex.check(profile+'.pause',pause)
        def unavailable():
            self.request('/api/replay',{},503)
            require(self.request('/api/dashboard')['projectionLag']>=1,'unavailable delivery fabricated current projection')
            return {'replay_status':503,'projection_lag_observed':True}
        self.ex.check(profile+'.unavailable',unavailable)
        self.ex.check(profile+'.recover',lambda:self.labstep('recover-service','capstone','--service','delivery',timeout=240))
        def replay():
            self.replay_until(request_id,'RESERVED')
            self.request('/api/orders/'+request_id+'/cancel',{})
            dashboard=self.replay_until(request_id,'CANCELLED')
            require(not [r for r in dashboard['audit'] if r['severity']=='ERROR'],'recovery audit failed')
            return {'same_request_id':request_id,'projection':'CANCELLED','audit_errors':0}
        self.ex.check(profile+'.replay',replay)
        def same_stage():
            after=self.inspect(True)
            require({s:(r['id'],r['mounts']) for s,r in before.items()}=={s:(r['id'],r['mounts']) for s,r in after.items()},'recovery replaced a container or mount')
            return {'stage':'05-defense','same_container_ids':True,'same_mounts':True}
        self.ex.check(profile+'.same_stage',same_stage)
        self.ex.check(profile+'.stop',lambda:self.stop(profile))
        self.ex.check(profile+'.preserved',lambda:self.preserved(profile,before))
    def replay_until(self,request_id,status):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            response=self.request('/api/replay',{},(200,503))
            if response['status_code']==503:
                time.sleep(.5);continue
            view=self.request('/api/dashboard')
            if any(r['requestId']==request_id and r['status']==status for r in view['deliveries']):return view
            time.sleep(.5)
        raise ValueError('recovery projection did not converge')
    def cleanup(self):
        require(self.preflight_complete,'never cleanup a project that was not initially empty')
        # Collect all created resources, including a partial failed startup. Only
        # exact run-owned labels AND expected working_dir/config qualify.
        for cap,project in enumerate(self.projects):
            for cid in self.listed('container',project):
                labels=self.jsoninspect('container',cid,'{{json .Config.Labels}}')
                expected=str(self.course/('infra/capstone.compose.yaml' if cap else 'infra/compose.yaml'))
                require(labels.get('com.docker.compose.project')==project and labels.get('com.docker.compose.project.working_dir')==str(self.course/'infra') and labels.get('com.docker.compose.project.config_files')==expected,'cleanup refused foreign container')
                self.docker('container','stop','--time','20',cid)
                self.docker('container','rm',cid)
            for kind in ('volume','network'):
                for name in self.listed(kind,project):
                    labels=self.jsoninspect(kind,name,'{{json .Labels}}')
                    require(labels.get('com.docker.compose.project')==project,'cleanup refused foreign resource')
                    self.docker(kind,'rm',name)
            for kind in ('container','volume','network'):require(not self.listed(kind,project),'CI-owned resource remained after cleanup')
        self.report['ownership']['empty_after']=True
        return {'only_exact_initially_empty_projects':self.projects,'removed_ci_test_volumes':True,'default_user_volumes_untouched':True}
    def import_integrity(self):
        self.run(['git','--no-pager','diff','--no-ext-diff','--no-textconv','--exit-code'],30,cwd=self.a.repo)
        results={}
        for mode,root in (('student',self.student),('educator',self.course)):
            self.run(['bash',str(root/'scripts/lab.sh'),'verify'],60,cwd=root)
            result=inspect_import(root,self.contract,mode);results[mode]={'status':result['status'],'files':len(result['files']),'post_runtime_revalidated':True}
        self.report['imports']=results
        return {'all_official_import_source_bytes_unchanged':True}
    def execute(self):
        try:
            self.ex.check('preflight',self.preflight)
            self.ex.check('learner_entry',lambda:self.entry(self.student))
            self.ex.check('educator_entry',lambda:self.entry(self.course))
            self.ex.check('launcher_prepare',self.launcher_prepare)
            self.ex.check('launcher_verify',self.launcher_verify)
            self.ex.check('probe_compile',self.compile_probes)
            for profile in SERVICES:self.profile(profile)
            self.capstone()
            self.ex.check('import_integrity',self.import_integrity)
        except Exception as error:
            self.report['status']='FAIL';self.report['error']=sanitize_text(type(error).__name__+': '+str(error))
        finally:
            if self.preflight_complete:
                try:self.ex.check('cleanup',self.cleanup)
                except Exception as error:self.report['status']='FAIL';self.report['cleanup_error']=sanitize_text(type(error).__name__+': '+str(error))
            if self.report['status']!='FAIL':
                self.report['status']='PASS'
                try:validate_environment(self.report,self.native,self.identity)
                except Exception as error:self.report['status']='FAIL';self.report['error']=str(error)
            dump(self.ex.evidence/'summary.json',self.report)
        return self.report

def main(a):
    for path in (a.repo,a.run_root.parent,a.handoff.parent):validate_directory(path)
    root=a.run_root.absolute();temp=Path(os.environ['RUNNER_TEMP']).resolve()
    require(root!=temp and root.is_relative_to(temp) and not root.is_relative_to(a.repo.absolute()),'run root must be fresh child of RUNNER_TEMP outside repo')
    require(os.environ.get('CI')=='true' and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_OS')=='Linux' and os.environ.get('RUNNER_ARCH')=='X64' and re.fullmatch(r'\d+',os.environ.get('GITHUB_RUN_ID','')) and re.fullmatch(r'\d+',os.environ.get('GITHUB_RUN_ATTEMPT','')),'hosted CI identity required')
    new_directory(root)
    expected={key:os.environ[name] for key,name in [('repository','GITHUB_REPOSITORY'),('commit','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('run_attempt','GITHUB_RUN_ATTEMPT')]}
    require(re.fullmatch(r'[0-9a-f]{64}',a.handoff_sha256) and sha(read_regular(a.handoff,limit=MAX_CONTAINER))==a.handoff_sha256,'same-run handoff digest mismatch')
    identity,native,contract,imports=unpack(a.handoff,root/'handoff',expected)
    return Acceptance(a,root,identity,native,contract,imports).execute()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--run-root',type=Path,required=True);p.add_argument('--handoff',type=Path,required=True);p.add_argument('--handoff-sha256',required=True);a=p.parse_args()
    try:report=main(a)
    except Exception as error:
        report={'status':'FAIL','runtime':'NOT_RUN','error':type(error).__name__+': '+str(error)}
        if a.run_root.is_dir() and not a.run_root.is_symlink():
            evidence=a.run_root/'evidence';evidence.mkdir(exist_ok=True);dump(evidence/'summary.json',report)
    print(json.dumps({'status':report['status']}));sys.exit(0 if report['status']=='PASS' else 1)
