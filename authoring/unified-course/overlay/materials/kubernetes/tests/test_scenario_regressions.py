"""Python-only verifier regressions. Fake observations are never cluster evidence."""
import sys,pathlib,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'bin'))
import lab,scenarios

class BaselineFake:
    state={'run':'123456abcdef'}
    def __init__(self,stocks=(6,6),seed=6):self.stocks=iter(stocks);self.seed=seed
    def call(self,path,method='GET'):
        if path.startswith('/orders'):return {'status':200,'body':{'status':'REPLAY','remaining':8}}
        if path=='/stock':return {'status':200,'body':{'stock':next(self.stocks)}}
        if path=='/seed':return {'status':200,'body':{'created':False,'stock':self.seed}}
class RolloutFake:
    state={'images':{'v1':'image:v1','v2':'image:v2','broken':'image:broken'}}
    def __init__(self,image='image:v2'):self.image=image;self.mutations=[]
    def own(self,*a):return {'metadata':{'annotations':{'deployment.kubernetes.io/revision':'2'}},'spec':{'template':{'spec':{'containers':[{'image':self.image}]}}},'status':{'replicas':2,'updatedReplicas':2,'availableReplicas':2,'conditions':[{'type':'Progressing','status':'False','reason':'ProgressDeadlineExceeded'}]}}
    def kubectl(self,*a):
        if a[:2]==('set','image'):
            new=a[-1].split('=',1)[1];self.mutations.append((self.image,new));self.image=new
        if a[:2]==('rollout','undo'):self.image='image:v2'
    def call(self,path,**kw):return {'status':503 if path=='/ready' else 200,'body':{'release':'v1' if self.image=='image:v1' else 'v2'}}
    def rollout(self):pass
    def eventually(self,fn,**kw):assert fn()
    def api_pods(self):return [{'metadata':{'name':'pod-'+str(i)},'spec':{'containers':[{'image':self.image}]}} for i in range(2)]
class ConfigFake:
    state={'namespace':'c11-kind-123456abcdef'}
    def __init__(self,stale_before=False,stale_after=False,replace_early=False):self.restarted=False;self.stale_before=stale_before;self.stale_after=stale_after;self.replace_early=replace_early;self.list_calls=0
    def own(self,kind,name):return {'spec':{'selector':{'app':'orders'}},'data':{'greeting':'hello-v1','banner':'banner-v1'}}
    def call(self,path,**kw):
        stale=kw.get('pod')=='pod-1' and (self.stale_after if self.restarted else self.stale_before)
        return {'status':200,'body':{'greetingEnv':'hello-v2' if self.restarted and not stale else 'hello-v1','bannerFile':'banner-v1' if stale else 'banner-v2'}}
    def api_pods(self):
        self.list_calls+=1
        prefix='new' if self.restarted or (self.replace_early and self.list_calls>2) else 'old'
        return [{'metadata':{'name':'pod-'+str(i),'uid':prefix+str(i)},'status':{'containerStatuses':[{'ready':True}]}} for i in range(2)]
    def eventually(self,fn,**kw):
        for _ in range(3):
            if fn():return
        raise lab.LabError('FAIL',kw.get('reason','TIMEOUT'))
    def kubectl(self,*a,**kw):
        if a[:2]==('rollout','restart'):self.restarted=True
        if a[:2]==('auth','can-i'):return SimpleNamespace(stdout='yes' if a[2:4]==('get','pods') and a[-1]!='--namespace=default' else 'no')
        return SimpleNamespace(stdout='clean log')
    def rollout(self):pass
    def get(self,*a):return {'data':{'password':'c3ludGhldGlj'}}
class ScenarioRegressions(unittest.TestCase):
    def baseline(self,f):
        with patch.object(scenarios,'healthy'):return scenarios.baseline(f)
    def config(self,f):
        with patch.object(scenarios,'healthy',return_value={'greetingEnv':'hello-v1'}),patch.object(scenarios,'patch'),patch.object(scenarios,'ready_endpoint_uids',side_effect=[set(),{'a','b'}]):return scenarios.config(f)
    def assert_reason(self,reason,fn):
        with self.assertRaises(lab.LabError) as c:fn()
        self.assertEqual(reason,c.exception.reason)
    def test_old_replay_after_other_order_is_valid(self):self.assertEqual('PASS',self.baseline(BaselineFake())['status'])
    def test_replay_must_not_change_live_stock(self):self.assert_reason('REPLAY_CHANGED_LIVE_STOCK',lambda:self.baseline(BaselineFake((6,4),4)))
    def test_seed_must_not_refill_stock(self):self.assert_reason('SEED_REFILLED_STOCK',lambda:self.baseline(BaselineFake(seed=10)))
    def test_rerun_forces_real_v1_to_v2_transition(self):
        f=RolloutFake()
        with patch.object(scenarios,'healthy'),patch.object(scenarios.time,'sleep'):r=scenarios.rollout(f)
        self.assertEqual([('image:v2','image:v1'),('image:v1','image:v2')],f.mutations[:2]);self.assertTrue(r['reset_to_v1']);self.assertEqual('PASS',r['status'])
    def test_first_run_does_not_need_baseline_reset(self):
        f=RolloutFake('image:v1')
        with patch.object(scenarios,'healthy'),patch.object(scenarios.time,'sleep'):r=scenarios.rollout(f)
        self.assertEqual(('image:v1','image:v2'),f.mutations[0]);self.assertFalse(r['reset_to_v1'])
    def test_all_config_replicas_converge(self):self.assertEqual('PASS',self.config(ConfigFake())['status'])
    def test_one_stale_banner_cannot_pass(self):self.assert_reason('PROJECTED_CONFIG_NOT_RELOADED_ON_ALL_REPLICAS',lambda:self.config(ConfigFake(stale_before=True)))
    def test_one_stale_replacement_cannot_pass(self):self.assert_reason('CONFIG_NOT_UPDATED_ON_ALL_REPLACEMENTS',lambda:self.config(ConfigFake(stale_after=True)))
    def test_unrequested_pod_replacement_cannot_prove_file_reload(self):self.assert_reason('CONFIG_REPLICAS_CHANGED_WITHOUT_REQUESTED_RESTART',lambda:self.config(ConfigFake(replace_early=True)))
if __name__=='__main__':unittest.main()
