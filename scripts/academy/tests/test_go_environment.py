"""Synthetic path/proof propagation checks only; never execute a Go compiler."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from go_environment import validated_go_environment, MODULE_PATHS
import run_official
import ui_session


class GoEnvironmentTests(unittest.TestCase):
    def prepare(self,root):
        repo=root/'repo';repo.mkdir();cache=root/'academy-go-123-1/module-cache';cache.mkdir(parents=True)
        executable=root/'academy-go-123-1/go/bin/go';executable.parent.mkdir(parents=True)
        executable.write_bytes(b'SYNTHETIC_NOT_AN_EXECUTABLE');executable.chmod(0o700)
        module_inputs={}
        for name in MODULE_PATHS:
            path=repo/'authoring/unified-course/overlay'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('synthetic metadata only\n');module_inputs[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        (repo/'authoring/unified-course/manifest.json').write_text(json.dumps({'schema_version':1,'expected_manifest':module_inputs,'overlay_manifest':module_inputs}))
        pins=json.loads((Path(__file__).resolve().parents[1]/'go-toolchain.json').read_text())
        proof={'schema_version':1,'status':'prepared','version':pins['version'],
               'version_output':'go version go'+pins['version']+' '+pins['platform'],
               'run_id':'123','run_attempt':'1','executable':str(executable),'module_cache':str(cache),
               'archive':{k:pins[k] for k in ('url','sha256','size_bytes')},
               'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'module_inputs':module_inputs}
        proof_path=root/'academy-go-123-1/bootstrap.json';proof_path.write_text(json.dumps(proof))
        env={'RUNNER_TEMP':str(root),'GITHUB_WORKSPACE':str(repo),'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1',
             'GO_EXECUTABLE':str(executable),'GO_MODULE_CACHE':str(cache)}
        return env,proof,proof_path

    def test_absent_optional_vars_are_not_invented_but_required_fails(self):
        self.assertEqual(validated_go_environment({}),{})
        with self.assertRaises(ValueError):validated_go_environment({},required=True)

    def test_verified_paths_survive_both_env_filters_without_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            env,proof,path=self.prepare(Path(d))
            env.update(GH_TOKEN='secret',GITHUB_TOKEN='secret',AWS_ACCESS_KEY_ID='secret',HTTP_PROXY='private',HTTPS_PROXY='private',
                       GOPRIVATE='private',GONOPROXY='private',GONOSUMDB='off',GOFLAGS='-toolexec=evil',GOROOT='/private',GOENV='/private')
            with patch.dict(os.environ,env,clear=True):
                for result in (run_official.sanitized_environment(),ui_session.clean_env()):
                    self.assertEqual(result['GO_EXECUTABLE'],env['GO_EXECUTABLE']);self.assertEqual(result['GO_MODULE_CACHE'],env['GO_MODULE_CACHE'])
                    for key in ('GH_TOKEN','GITHUB_TOKEN','AWS_ACCESS_KEY_ID','HTTP_PROXY','HTTPS_PROXY','GOPRIVATE','GONOPROXY','GONOSUMDB','GOFLAGS','GOROOT','GOENV'):
                        self.assertNotIn(key,result)
                    self.assertEqual(validated_go_environment(result),{k:env[k] for k in ('GO_EXECUTABLE','GO_MODULE_CACHE')})

    def test_blank_relative_missing_escaping_or_newline_paths_rejected(self):
        for key in ('GO_EXECUTABLE','GO_MODULE_CACHE'):
            for value in ('','relative','/tmp/foreign','/tmp/../foreign','/tmp/bad\npath',None):
                with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as d:
                    env,proof,path=self.prepare(Path(d))
                    if value is None:env.pop(key)
                    else:env[key]=value
                    with self.assertRaises((ValueError,OSError)):validated_go_environment(env)

    def test_foreign_run_attempt_or_wrong_compiler_cache_version_rejected(self):
        changes=({'version':'1.26.1'},{'version_output':'go version go1.27.1 linux/arm64'},
                 {'run_attempt':'2'},{'run_id':'124'},{'status':'running'},{'executable_sha256':'0'*64},
                 {'module_cache':'/tmp/other-cache'},{'module_inputs':{}},{'archive':{}})
        for change in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                env,proof,path=self.prepare(Path(d));proof.update(change);path.write_text(json.dumps(proof))
                with self.assertRaises(ValueError):validated_go_environment(env)

    def test_nonnumeric_or_pathlike_run_identity_rejected(self):
        for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):
            for value in ('','0','../1','a','1\n2'):
                with tempfile.TemporaryDirectory() as d:
                    env,proof,path=self.prepare(Path(d));env[key]=value
                    with self.assertRaises(ValueError):validated_go_environment(env)

    def test_missing_proof_cache_or_compiler_rejected(self):
        for which in ('proof','cache','compiler'):
            with tempfile.TemporaryDirectory() as d:
                env,proof,path=self.prepare(Path(d))
                target=path if which=='proof' else Path(env['GO_MODULE_CACHE' if which=='cache' else 'GO_EXECUTABLE'])
                target.rmdir() if target.is_dir() else target.unlink()
                with self.assertRaises((ValueError,OSError)):validated_go_environment(env)

    def test_no_symlink_leaf_or_parent_is_accepted(self):
        for which in ('compiler','cache','proof','root'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);env,proof,path=self.prepare(root)
                target={'compiler':Path(env['GO_EXECUTABLE']),'cache':Path(env['GO_MODULE_CACHE']),
                        'proof':path,'root':root/'academy-go-123-1'}[which]
                moved=root/'moved';target.rename(moved);target.symlink_to(moved,target_is_directory=moved.is_dir())
                with self.assertRaises((ValueError,OSError)):validated_go_environment(env)

    def test_modified_compiler_or_module_input_rejected(self):
        for which in ('compiler','module','manifest'):
            with tempfile.TemporaryDirectory() as d:
                env,proof,path=self.prepare(Path(d))
                if which=='compiler':Path(env['GO_EXECUTABLE']).write_bytes(b'changed')
                elif which=='module':(Path(env['GITHUB_WORKSPACE'])/'authoring/unified-course/overlay'/MODULE_PATHS[0]).write_text('changed')
                else:
                    p=Path(env['GITHUB_WORKSPACE'])/'authoring/unified-course/manifest.json';p.write_text('{}')
                with self.assertRaises(ValueError):validated_go_environment(env)

    def test_nonexecutable_or_writable_compiler_rejected(self):
        for mode in (0o600,0o722):
            with tempfile.TemporaryDirectory() as d:
                env,proof,path=self.prepare(Path(d));Path(env['GO_EXECUTABLE']).chmod(mode)
                with self.assertRaises(ValueError):validated_go_environment(env)

class GoWorkflowTests(unittest.TestCase):
    def test_bounded_bootstrap_and_exact_receipt_uploads(self):
        import yaml
        repo=Path(__file__).resolve().parents[3]
        w=yaml.load((repo/'.github/workflows/academy-official.yml').read_text(),Loader=yaml.BaseLoader)
        steps=w['jobs']['package']['steps']
        setup=[s for s in steps if 'prepare_go.py' in s.get('run','')]
        self.assertEqual(len(setup),1);self.assertEqual(setup[0]['timeout-minutes'],'5')
        self.assertIn('academy-go-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT',setup[0]['run'])
        receipts=next(s for s in steps if 'academy-ui-receipts-' in s.get('with',{}).get('name',''))
        self.assertNotIn('*',receipts['with']['path'])
        expected={'${{ env.UI_RUN }}/stage-'+str(stage)+'/'+name for stage in (1,2,3)
                  for name in ('before.png','after.png','request.json','review-target.json','display-identity.json','receipt.json')}
        self.assertEqual(set(receipts['with']['path'].splitlines()),expected)
        self.assertIn('validated_go_environment(required=True)',(repo/'scripts/academy/run_official.py').read_text())

if __name__=='__main__':unittest.main()
