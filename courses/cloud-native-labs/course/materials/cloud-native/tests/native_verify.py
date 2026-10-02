#!/usr/bin/env python3
"""真实JVM+HTTP+TCP+SIGTERM；Redis为明确标注的协议假服务。编译由外部JDK21窗口负责。"""
import argparse,concurrent.futures,json,os,pathlib,signal,socket,subprocess,tempfile,threading,time,uuid
from contract import request,wait_status,fresh_inventory_contract
from fake_redis import FakeRedis
from verification_guard import verify_compilation,claim_report,VerificationSetupError
ROOT=pathlib.Path(__file__).resolve().parents[1]

class App:
    def __init__(self,classes,redis,overrides=None):
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env=dict(os.environ,BIND_HOST='127.0.0.1',HTTP_PORT=str(port),REDIS_HOST='127.0.0.1',REDIS_PORT=str(redis.port),REDIS_PASSWORD=redis.state.password,LAB_NAMESPACE='c11-'+uuid.uuid4().hex,WEB_ROOT=str(ROOT/'web'))
        env.update(overrides or {})
        self.lines=[];self.base=f'http://127.0.0.1:{port}'
        self.process=subprocess.Popen(['java','-cp',str(classes),'labs.CloudNativeApp'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        self.reader=threading.Thread(target=lambda:self.lines.extend(iter(self.process.stdout.readline,'')),daemon=True);self.reader.start()
        try:wait_status(self.base,'/live')
        except Exception:self.stop();raise
    def stop(self):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:self.process.wait(timeout=6)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait();raise AssertionError('JVM failed six-second stop budget')
        self.reader.join(timeout=2)
        self.process.stdout.close()

def verify(classes):
    results=[];redis=FakeRedis().start()
    try:
        app=App(classes,redis)
        try:
            results.extend(fresh_inventory_contract(app.base))
            assert request(app.base,'/downstream-check')==(200,{'status':'PONG','layer':'APPLICATION'})
            results.append('downstream_success_layer')
            redis.state.mode='timeout'
            assert request(app.base,'/ready')[1]['layer']=='TIMEOUT'
            assert request(app.base,'/live')[0]==200
            redis.state.mode='ok'
            assert request(app.base,'/ready')[0]==200
            results.extend(['dependency_timeout_bounded','liveness_independent_of_dependency','readiness_recovers'])
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                response=pool.submit(request,app.base,'/slow?millis=1500')
                deadline=time.monotonic()+2
                while not any('slow_started' in line for line in app.lines):
                    assert time.monotonic()<deadline,'slow request did not start';time.sleep(.02)
                start=time.monotonic();app.stop();elapsed=time.monotonic()-start
                assert response.result()==(200,{'status':'COMPLETED'})
                assert elapsed<6,(elapsed,app.lines)
                assert any('drain_started' in line for line in app.lines)
                assert any('shutdown_completed' in line for line in app.lines)
                assert app.process.returncode in (0,143,-signal.SIGTERM),app.process.returncode
                results.extend(['sigterm_drains_inflight_request','sigterm_exits_within_budget','sigterm_emits_completion'])
        finally:app.stop()
        for overrides,layer in [({'REDIS_HOST':'academy-c11-missing.invalid'},'DNS'),({'REDIS_PORT':'1'},'CONNECT'),({'REDIS_PASSWORD':'wrong-password'},'AUTH')]:
            app=App(classes,redis,overrides)
            try:
                code,body=request(app.base,'/downstream-check');assert code==503 and body['layer']==layer,(code,body)
                assert request(app.base,'/live')[0]==200
                results.append('network_failure_'+layer)
            finally:app.stop()
        redis.state.mode='malformed';app=App(classes,redis)
        try:
            assert request(app.base,'/downstream-check')[1]['layer']=='PROTOCOL';results.append('protocol_failure_classified')
        finally:app.stop()
    finally:redis.close()
    return results

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--classes',required=True,type=pathlib.Path);parser.add_argument('--evidence',required=True,type=pathlib.Path);args=parser.parse_args()
    try:
        compilation=verify_compilation(args.classes,ROOT)
        context=claim_report(args.evidence)
    except VerificationSetupError as error:parser.error(str(error))
    evidence={'run_id':context['run_id'],'compilation_sources':compilation['sources'],'mode':'actual JVM+HTTP+TCP+signals; fake Redis does NOT execute Lua','docker':'NOT_RUN','redis_integration':'NOT_RUN','cases':[],'status':'FAIL'}
    try:
        evidence['cases']=verify(args.classes)
        if not evidence['cases']:raise VerificationSetupError('No JVM/HTTP cases executed')
        evidence['status']='PASS'
    finally:args.evidence.parent.mkdir(parents=True,exist_ok=True);args.evidence.write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
