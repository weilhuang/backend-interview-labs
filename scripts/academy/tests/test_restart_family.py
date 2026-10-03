import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ACADEMY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ACADEMY))
import restart_family as family_module
from restart_family import Cancellation, Child, Family, FamilyError


class RestartFamilyProcessTests(unittest.TestCase):
    def isolated(self, body):
        # Some test sandboxes omit every /proc task/children hint. New live
        # descendant fixtures supply only PIDs reported by their own fork,
        # while the production registrar still checks real PPID/birth/pidfds.
        hints = '''
def scoped_hints(pids):
    import restart_family as module
    def discover(meta, deadline):
        values=set()
        for pid in pids:
            try:
                if info(pid)['ppid']==meta['pid']:values.add(pid)
            except (FileNotFoundError,ProcessLookupError):pass
        return values
    module.children=discover
'''
        script = "import sys,os,time,json,signal,tempfile\nsys.path.insert(0," + repr(str(ACADEMY)) + ")\nfrom restart_family import *\n" + hints + "\nf=None\ntry:\n" + textwrap.indent(textwrap.dedent(body),'    ') + "\nfinally:\n    if f is not None and not f.closed:\n        f.close()\n"
        result = subprocess.run([sys.executable, '-B', '-c', script], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=12, env={'PATH':os.defpath,'LANG':'C.UTF-8'})
        self.assertEqual(result.returncode, 0, result.stderr.decode()[-3000:])
        return json.loads(result.stdout)

    def test_direct_exit_and_complete_closure(self):
        value = self.isolated('''
            f=Family(time.monotonic()+8)
            p=f.spawn([sys.executable,'-c','raise SystemExit(7)'],{'PATH':os.defpath},role='HELPER')
            while p.poll() is None:time.sleep(.005)
            assert p.returncode==7
            print(json.dumps(f.close()))
        ''')
        self.assertEqual(value['status'],'FAMILY_CLEANUP_VERIFIED')

    def test_terminal_only_adoption_has_no_signal_authority(self):
        value = self.isolated('''
            f=Family(time.monotonic()+8)
            pid=os.fork()
            if pid==0:os._exit(3)
            time.sleep(.03)
            f.tick()
            entry=f.members[f.pid_keys[pid]]
            assert entry['role']=='TERMINAL_ONLY' and entry['fd'] is None and entry['exit_code']==3
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])

    def test_orphan_survives_root_exit_then_is_owned_and_cleaned(self):
        value = self.isolated('''
            f=Family(time.monotonic()+8)
            code='import os,time; p=os.fork(); time.sleep(2) if p==0 else None'
            p=f.spawn([sys.executable,'-c',code],{'PATH':os.defpath},role='HELPER')
            while p.poll() is None:time.sleep(.005)
            # children is only a hint. A missed live orphan must prevent
            # ECHILD, and its actual terminal status must still be reaped.
            assert not f.last_echild
            result=f.close()
            assert len(f.members)>=2
            print(json.dumps(result))
        ''')
        self.assertTrue(value['echild'])

    def test_discovery_omission_cannot_produce_echild(self):
        value = self.isolated('''
            import restart_family as m
            f=Family(time.monotonic()+8)
            p=f.spawn([sys.executable,'-c','import time;time.sleep(.2)'],{'PATH':os.defpath},role='HELPER')
            m.children=lambda *_:set()
            f.tick()
            assert not f.last_echild
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])

    def test_competing_waiter_is_rejected(self):
        value = self.isolated('''
            f=Family(time.monotonic()+8)
            p=f.spawn([sys.executable,'-c','import time;time.sleep(.03)'],{'PATH':os.defpath},role='HELPER')
            os.waitpid(p.pid,0)
            try:f.tick();raise AssertionError('accepted competing waiter')
            except FamilyError as e:assert str(e)=='COMPETING_REAPER'
            assert f.cancel.cancelled
            try:f.close()
            except FamilyError:pass
            print(json.dumps({'rejected':True}))
        ''')
        self.assertTrue(value['rejected'])

    def test_cancel_latch_forbids_spawn_arm_and_validation(self):
        value = self.isolated('''
            f=Family(time.monotonic()+8)
            f.cancel.set('CANCELLED')
            for op in [lambda:f.spawn([sys.executable,'-c','pass'],{},role='HELPER'),f.begin_validation]:
                try:op();raise AssertionError('cancelled launch')
                except InterruptedError:pass
            print(json.dumps(f.close()))
        ''')
        self.assertEqual(value['registered'],0)

    def test_restart_arm_is_one_use_and_cannot_clear_cancel(self):
        value = self.isolated('''
            f=Family(time.monotonic()+8)
            p=f.spawn([sys.executable,'-c','import time;time.sleep(3)'],{'PATH':os.defpath},role='PREPARATION_IDE')
            f.arm_restart(p,'a'*64)
            f.clicked('a'*64)
            try:f.arm_restart(p,'b'*64);raise AssertionError('second arm')
            except FamilyError:pass
            f.cancel.set('CANCEL_AT_CLICK')
            try:f.clicked('a'*64);raise AssertionError('cancel cleared')
            except InterruptedError:pass
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])

    def test_deadline_expiry_still_cleans_without_new_launch(self):
        value = self.isolated('''
            f=Family(time.monotonic()+.05)
            p=f.spawn([sys.executable,'-c','import time;time.sleep(3)'],{'PATH':os.defpath},role='HELPER')
            time.sleep(.07)
            try:f.tick();raise AssertionError('deadline ignored')
            except InterruptedError:pass
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])

    def test_unregistered_live_child_omitted_by_discovery_is_not_closure(self):
        value=self.isolated('''
            import restart_family as m
            f=Family(time.monotonic()+8)
            pid=os.fork()
            if pid==0:time.sleep(.15);os._exit(0)
            m.children=lambda *_:set()
            f.tick();assert not f.last_echild and not f.members
            result=f.close()
            assert len(f.members)==1 and next(iter(f.members.values()))['role']=='TERMINAL_ONLY'
            print(json.dumps(result))
        ''')
        self.assertTrue(value['echild'])

    def test_double_fork_setsid_and_terminal_only_grandchild(self):
        value=self.isolated('''
            f=Family(time.monotonic()+8)
            code='import os,time\\np=os.fork()\\nif p:os._exit(0)\\nos.setsid()\\np=os.fork()\\nif p:os._exit(0)\\ntime.sleep(.1)\\nos._exit(4)'
            p=f.spawn([sys.executable,'-S','-c',code],{'PATH':os.defpath},role='HELPER')
            time.sleep(.2)
            f.tick();result=f.close()
            assert len(f.members)>=3
            assert any(e['role']=='TERMINAL_ONLY' and e['exit_code']==4 for e in f.members.values())
            print(json.dumps(result))
        ''')
        self.assertTrue(value['echild'])

    def test_same_pid_exec_preserves_birth_without_granting_gui_role(self):
        value=self.isolated('''
            f=Family(time.monotonic()+8)
            code='import os,time;time.sleep(.08);os.execve("/bin/sh",["/bin/sh","-c","sleep .2"],{"PATH":"/usr/bin:/bin"})'
            p=f.spawn([sys.executable,'-S','-c',code],{'PATH':os.defpath},role='HELPER')
            before=f.members[p.key]['meta'];observed=False
            while p.poll() is None:
                try:
                    if os.readlink('/proc/'+str(p.pid)+'/exe').endswith('/dash'):
                        assert stable(info(p.pid))==stable(before)
                        assert f.members[p.key]['role']=='HELPER';observed=True;break
                except FileNotFoundError:pass
                time.sleep(.005)
            assert observed
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])

    def test_signal_permission_failure_never_certifies_cleanup(self):
        value=self.isolated('''
            from unittest.mock import patch
            f=Family(time.monotonic()+8)
            p=f.spawn([sys.executable,'-S','-c','import time;time.sleep(.1)'],{'PATH':os.defpath},role='HELPER')
            with patch('restart_family.signal.pidfd_send_signal',side_effect=PermissionError('synthetic')):
                try:f.close();raise AssertionError('false cleanup certificate')
                except FamilyError as error:assert error.code=='FAMILY_CLEANUP_INCOMPLETE'
            assert f.cancel.cancelled
            print(json.dumps({'rejected':True}))
        ''')
        self.assertTrue(value['rejected'])

    def test_expected_probe_harmless_executable_is_one_shot(self):
        value=self.isolated('''
            import hashlib
            from pathlib import Path
            from unittest.mock import patch
            f=Family(time.monotonic()+8)
            path=Path('/usr/bin/true').resolve()
            expected={'path':str(path),'identity':file_identity(path.stat()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            f.expect_sudo_probe(expected)
            with patch.object(f,'_matches_binary',side_effect=PermissionError('setuid exe visibility')) as observed_image:
                result=f.run([str(path),'-n','-l'],env={'PATH':os.defpath},check=True)
                observed_image.assert_not_called()
            assert result.returncode==0 and f.sudo_probe is None
            item=next(iter(f.members.values()))
            assert item['helper_kind']=='SUDO_PROBE' and item['never_signal']
            assert item['reaped'] and item['exit_code']==0 and item['terminal_evidence']=='WAITID_EXIT'
            with patch('restart_family.signal.pidfd_send_signal') as send:
                result=f.close();send.assert_not_called()
            print(json.dumps(result))
        ''')
        self.assertTrue(value['echild'])

    def test_expected_probe_rejects_wrong_arguments_before_spawn(self):
        value=self.isolated('''
            import hashlib
            from pathlib import Path
            f=Family(time.monotonic()+8)
            path=Path('/usr/bin/true').resolve()
            f.expect_sudo_probe({'path':str(path),'identity':file_identity(path.stat()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            try:f.run([str(path),'-n']);raise AssertionError('accepted wrong command')
            except FamilyError as error:assert error.code=='SUDO_PROBE_INVALID'
            assert f.sudo_probe is None and not f.members and f.cancel.cancelled
            print(json.dumps(f.close()))
        ''')
        self.assertEqual(value['registered'],0)

    def test_parent_reaped_helper_preserves_unknown_exit_status(self):
        value=self.isolated('''
            f=Family(time.monotonic()+8)
            output=tempfile.TemporaryFile()
            code='import os,time\\np=os.fork()\\nif p==0:time.sleep(.3);os._exit(9)\\nos.write(1,str(p).encode())\\nos.waitpid(p,0)\\ntime.sleep(1)'
            parent=f.spawn([sys.executable,'-S','-c',code],{'PATH':os.defpath},role='HELPER',stdout_fd=output.fileno())
            while os.fstat(output.fileno()).st_size==0:f.check();time.sleep(.005)
            output.seek(0);leaf_pid=int(output.read());scoped_hints([parent.pid,leaf_pid])
            while len(f.members)<2:f.tick();time.sleep(.005)
            leaf=next(item for item in f.members.values() if item['key']!=parent.key)
            f._set_helper(leaf,'ELEVATED_DESCENDANT',f.members[parent.key])
            while not leaf['terminal']:f.tick();time.sleep(.005)
            assert not leaf['reaped'] and leaf['exit_code'] is None
            assert leaf['terminal_evidence']=='PIDFD_TERMINAL_STATUS_UNKNOWN' and leaf['never_signal']
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])

    def test_first_observed_execed_adopted_replacement(self):
        value=self.isolated('''
            from pathlib import Path
            f=Family(time.monotonic()+8)
            output=tempfile.TemporaryFile()
            executable=str(Path('/usr/bin/sleep').resolve())
            code='import os,time\\ntime.sleep(.08)\\np=os.fork()\\nif p:os.write(1,str(p).encode());os._exit(0)\\nwhile os.getppid()!='+str(os.getpid())+':time.sleep(.001)\\nos.execve('+repr(executable)+',['+repr(executable)+',"1"],{"PATH":"/usr/bin:/bin"})'
            old=f.spawn([sys.executable,'-S','-c',code],{'PATH':os.defpath},role='PREPARATION_IDE',stdout_fd=output.fileno())
            f.arm_restart(old,'a'*64);f.clicked('a'*64)
            images={}
            for name,path in [('restarter',str(Path('/usr/bin/false').resolve())),('executable',executable),('launcher',executable)]:
                st=Path(path).stat();images[name]={'path':path,'dev':st.st_dev,'ino':st.st_ino,'size':st.st_size,'mtime_ns':st.st_mtime_ns}
            f.restart_images=images
            # Model the independently bound terminal acknowledgement. No IDE,
            # terminal, sudo, policy or privileged process is used in this fixture.
            f.restart['acknowledged_at']=time.monotonic()
            time.sleep(.2)
            output.seek(0);new_pid=int(output.read());scoped_hints([old.pid,new_pid])
            replacement=f.replacement()
            assert replacement is not None and f.restart['restarter_key'] is None
            assert f.members[old.key]['reaped'] and f.members[replacement.key]['adopted']
            assert f.restart_provenance()=='NONE'
            f.verify_replacement(replacement)
            assert f.restart_provenance()=='CLOSED_FAMILY_ADOPTED_EXEC'
            f.permit_normal_close(replacement)
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])

    def test_harmless_terminal_identity_and_acknowledgement(self):
        value=self.isolated('''
            import hashlib
            from pathlib import Path
            f=Family(time.monotonic()+8)
            output=tempfile.TemporaryFile()
            terminal=str(Path('/usr/bin/sleep').resolve())
            code='import os,time\\ntime.sleep(.08)\\np=os.fork()\\nif p==0:os.execve('+repr(terminal)+',['+repr(terminal)+',"1"],{"PATH":"/usr/bin:/bin"})\\nos.write(1,str(p).encode())\\ntime.sleep(2)'
            old=f.spawn([sys.executable,'-S','-c',code],{'PATH':os.defpath},role='PREPARATION_IDE',stdout_fd=output.fileno())
            helpers={}
            for kind,name in [('TERMINAL',terminal),('SUDO','/usr/bin/true')]:
                path=Path(name).resolve();helpers[kind]={'path':str(path),'identity':file_identity(path.stat()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            f.configure_install_helpers(helpers,old)
            f.arm_restart(old,'a'*64);f.clicked('a'*64)
            while os.fstat(output.fileno()).st_size==0:f.check();time.sleep(.005)
            output.seek(0);terminal_pid=int(output.read());scoped_hints([old.pid,terminal_pid])
            target=None
            while target is None:target=f.terminal_child();time.sleep(.005)
            assert f.members[target.key]['helper_lineage'] and not f.members[target.key]['lifecycle_only']
            assert f.verify_terminal_helpers(target)
            assert f.restart['acknowledged_at'] is None
            f.terminal_acknowledged('a'*64)
            assert f.restart['acknowledged_at'] is not None
            try:f.terminal_acknowledged('a'*64);raise AssertionError('accepted second Enter')
            except FamilyError as error:assert error.code=='TERMINAL_ACK_INVALID'
            print(json.dumps(f.close()))
        ''')
        self.assertTrue(value['echild'])


class RestartFamilyLifecycleTests(unittest.TestCase):
    """Pure-state elevated/exec races; these never elevate or run vendor code."""
    def meta(self, pid, ppid=10, uid=1000, start='10001', group=20):
        return {'pid':pid,'ppid':ppid,'uid':uid,'start_time':start,'pgrp':group,'session':group,'state':'S'}

    def member(self, pid, **changes):
        meta=self.meta(pid)
        item={'key':(pid,meta['start_time']),'meta':meta,'birth_meta':dict(meta),'fd':pid+100,
              'role':'DESCENDANT','provenance':'KERNEL_SUBREAPER_CHILD','terminal':False,
              'reaped':False,'exit_code':None,'lineage':None,'terminal_evidence':None,
              'observed_uids':[1000],'helper_kind':None,'helper_lineage':False,
              'helper_image_observed':False,'lifecycle_only':False,'never_signal':False,'terminal_root':None,'adopted':True}
        item.update(changes)
        return item

    def family(self, *members):
        f=Family.__new__(Family)
        f.__dict__.update(deadline=1000,cancel=Cancellation(),owner=self.meta(10,start='1',group=10),
            members={item['key']:item for item in members},pid_keys={item['meta']['pid']:item['key'] for item in members},
            pending_pid=None,pending_helper=None,pending_role=None,pending_launch=False,install_helpers=None,install_old_key=None,
            terminal_key=None,terminal_verified_key=None,sudo_probe=None,restart=None,restart_images=None,
            normal_close_key=None,closed=False,launches_closed=False,phase_closed=False,last_echild=False,
            cleanup_active=False,cleanup_deadline=None,tick_active=False,observation_failed=False)
        f.check=f.cancel.check
        return f

    def restart_family(self, *others):
        old=self.member(20,role='PREPARATION_IDE',terminal=True,reaped=True,exit_code=0)
        old['meta']=self.meta(20,start='5000');old['birth_meta']=dict(old['meta'])
        f=self.family(old,*others)
        f.restart={'old_key':old['key'],'binding':'a'*64,'state':'CLICK_DISPATCHED','clicked':True,
                   'armed_at':100.0,'acknowledged_at':101.0,'restarter_key':None,'replacement_key':None,'provenance':'NONE'}
        f.restart_images={'restarter':{'path':'/official/restarter'},'launcher':{'path':'/official/idea'}}
        f._image=lambda item,name:item.get('image')==name
        return f

    def terminal_family(self, *others):
        old=self.member(15,role='PREPARATION_IDE')
        terminal=self.member(20,role='INSTALL_TERMINAL',helper_kind='TERMINAL',
                             terminal_root=(20,'10001'),helper_lineage=True,helper_image_observed=True,
                             lineage=old['key'])
        terminal['meta']=self.meta(20,ppid=15)
        f=self.family(old,terminal,*others)
        f.install_old_key=old['key'];f.install_helpers={'TERMINAL':{},'SUDO':{}}
        f.restart={'armed_at':100.0}
        return f,terminal

    def test_expected_probe_observed_elevated_then_dropped_uid(self):
        f=self.family();f.pending_pid=11;f.pending_role='HELPER';f.pending_helper={'path':'/verified/sudo'}
        elevated=self.meta(11,uid=0,group=11)
        with patch.object(family_module,'info',return_value=elevated),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=101):
            key=f._record_live(11,'DIRECT_SPAWN')
        item=f.members[key]
        self.assertTrue(item['never_signal']);self.assertTrue(item['lifecycle_only'])
        dropped=dict(elevated,uid=1000)
        f._refresh(item,dropped)
        self.assertEqual(item['observed_uids'],[0,1000])
        self.assertEqual(item['birth_meta']['uid'],0)
        self.assertTrue(item['never_signal']);self.assertNotEqual(item['role'],'RESTARTED_IDE')

    def test_unknown_elevated_child_is_rejected(self):
        f=self.family()
        with patch.object(family_module,'info',return_value=self.meta(11,uid=0,group=11)),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=101),patch.object(family_module.os,'close'):
            with self.assertRaisesRegex(FamilyError,'CHILD_IDENTITY_UNVERIFIED'):
                f._record_live(11,'KERNEL_SUBREAPER_CHILD')
        self.assertFalse(f.members)

    def test_pre_exec_launch_already_anchors_helper_lineage(self):
        f=self.family();f.pending_pid=11;f.pending_role='HELPER'
        meta=self.meta(11,group=11)
        with patch.object(family_module,'info',return_value=meta),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=101):
            key=f._record_live(11,'KERNEL_SUBREAPER_CHILD')
        item=f.members[key]
        self.assertEqual(item['provenance'],'DIRECT_SPAWN')
        self.assertEqual(item['lineage'],key);self.assertTrue(item['helper_lineage'])
        self.assertEqual(item['role'],'HELPER');self.assertFalse(item['adopted'])

    def test_expected_helper_unknown_birth_is_rejected(self):
        f=self.family();item=self.member(11,lifecycle_only=True,never_signal=True)
        with self.assertRaisesRegex(FamilyError,'REGISTERED_IDENTITY_CHANGED'):
            f._refresh(item,self.meta(11,uid=0,start='10002'))

    def test_inaccessible_expected_executable_is_not_admitted(self):
        parent=self.member(20,role='PREPARATION_IDE');f=self.family(parent)
        f.install_old_key=parent['key'];f.install_helpers={'TERMINAL':{},'SUDO':{}};f.restart={}
        meta=self.meta(21,ppid=20)
        with patch.object(family_module,'info',return_value=meta),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=121),patch.object(family_module.os,'close'),patch.object(f,'_matches_binary',side_effect=PermissionError('synthetic')):
            with self.assertRaises(PermissionError):f._record_live(21,'VERIFIED_PARENT_CHILD',parent)
        self.assertEqual(len(f.members),1)

    def test_expected_helper_uid_transition_reaped_with_real_status(self):
        item=self.member(11,lifecycle_only=True,never_signal=True,helper_kind='SUDO_PROBE',provenance='DIRECT_SPAWN')
        f=self.family(item)
        terminal=dict(item['meta'],uid=0,state='Z')
        status=SimpleNamespace(si_pid=11,si_uid=0,si_code=os.CLD_EXITED,si_status=7)
        with patch.object(family_module,'info',return_value=terminal),patch.object(family_module.os,'waitid',side_effect=[status,status,ChildProcessError()]):
            f._reap()
        self.assertTrue(item['reaped']);self.assertEqual(item['exit_code'],7)
        self.assertEqual(item['observed_uids'],[1000,0]);self.assertEqual(item['wait_uid'],0)
        self.assertEqual(item['terminal_evidence'],'WAITID_EXIT')

    def test_surviving_dropped_uid_helper_is_never_signalled_or_cleanup_verified(self):
        item=self.member(11,lifecycle_only=True,never_signal=True,helper_kind='TERMINAL_ELEVATED_DESCENDANT',observed_uids=[0,1000])
        f=self.family(item);f.tick=Mock();f._reap=Mock()
        now=[100.0]
        def advance():now[0]+=.25;return now[0]
        with patch.object(family_module.time,'monotonic',side_effect=advance),patch.object(family_module.time,'sleep'),patch.object(family_module,'alive',return_value=True),patch.object(family_module,'children',return_value={11}),patch.object(family_module.signal,'pidfd_send_signal') as send:
            with self.assertRaisesRegex(FamilyError,'FAMILY_CLEANUP_INCOMPLETE'):f.close_phase()
            send.assert_not_called()
        self.assertTrue(f.cancel.cancelled);self.assertFalse(f.phase_closed)
        with self.assertRaises(InterruptedError):f.begin_validation()

    def test_helper_descendants_inherit_lifecycle_only_authority(self):
        parent=self.member(20,lifecycle_only=True,never_signal=True,helper_kind='SUDO',terminal_root=(19,'10001'))
        f=self.family(parent);child=self.meta(21,ppid=20,uid=0)
        def proc(pid):return parent['meta'] if pid==20 else child
        with patch.object(family_module,'info',side_effect=proc),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=121):
            key=f._record_live(21,'VERIFIED_PARENT_CHILD',parent)
        item=f.members[key]
        self.assertEqual(item['helper_kind'],'ELEVATED_DESCENDANT')
        self.assertEqual(item['terminal_root'],parent['terminal_root'])
        self.assertTrue(item['never_signal']);self.assertTrue(item['helper_lineage'])

    def test_known_terminal_child_can_become_elevated_with_hidden_executable(self):
        child=self.member(21,helper_kind='TERMINAL_DESCENDANT',terminal_root=(20,'10001'),helper_lineage=True)
        child['meta']=self.meta(21,ppid=20)
        f,terminal=self.terminal_family(child)
        current=dict(child['meta'],uid=0)
        def proc(pid):return current if pid==21 else f.members[f.pid_keys[pid]]['meta']
        def kids(meta,deadline):return {15} if meta['pid']==10 else {20} if meta['pid']==15 else {21} if meta['pid']==20 else set()
        def image(meta,expected):
            if meta['pid']==21:raise PermissionError('setuid executable hidden')
            return meta['pid']==20
        with patch.object(family_module,'info',side_effect=proc),patch.object(family_module,'children',side_effect=kids),patch.object(family_module,'alive',return_value=True),patch.object(f,'_matches_binary',side_effect=image) as observed,patch.object(family_module.os,'sysconf',return_value=100):
            f._discover()
        self.assertEqual([call.args[0]['pid'] for call in observed.call_args_list],[20])
        self.assertEqual(child['helper_kind'],'TERMINAL_ELEVATED_DESCENDANT')
        self.assertFalse(child['helper_image_observed']);self.assertTrue(child['never_signal'])
        self.assertEqual(child['observed_uids'],[1000,0])
        f._refresh(child,dict(current,uid=1000))
        self.assertTrue(child['lifecycle_only']);self.assertTrue(child['never_signal'])
        self.assertTrue(child['helper_lineage']);self.assertFalse(child['helper_image_observed'])

    def test_first_observed_elevated_terminal_child_needs_no_child_exe_read(self):
        f,terminal=self.terminal_family();elevated=self.meta(21,ppid=20,uid=0)
        def proc(pid):return elevated if pid==21 else terminal['meta']
        def image(meta,expected):
            if meta['pid']==21:raise PermissionError('setuid executable hidden')
            return meta['pid']==20
        with patch.object(family_module,'info',side_effect=proc),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=121),patch.object(family_module.os,'sysconf',return_value=100),patch.object(f,'_matches_binary',side_effect=image) as observed:
            key=f._record_live(21,'VERIFIED_PARENT_CHILD',terminal)
        item=f.members[key]
        self.assertEqual([call.args[0]['pid'] for call in observed.call_args_list],[20])
        self.assertEqual(item['helper_kind'],'TERMINAL_ELEVATED_DESCENDANT')
        self.assertFalse(item['helper_image_observed']);self.assertTrue(item['lifecycle_only'])
        self.assertTrue(item['never_signal']);self.assertEqual(item['terminal_root'],terminal['key'])

    def test_elevated_terminal_child_requires_exact_current_terminal_root(self):
        for variant in ('wrong_image','inaccessible_root_image','old_birth','wrong_lineage','root_elevated','duplicate_terminal'):
            with self.subTest(variant=variant):
                f,terminal=self.terminal_family();elevated=self.meta(21,ppid=20,uid=0)
                if variant=='old_birth':terminal['meta']['start_time']='9999'
                if variant=='wrong_lineage':terminal['lineage']=(99,'10001')
                if variant=='root_elevated':terminal['meta']['uid']=0
                if variant=='duplicate_terminal':
                    other=self.member(22,helper_kind='TERMINAL');f.members[other['key']]=other
                def image(meta,expected):
                    self.assertEqual(meta['pid'],20)
                    if variant=='inaccessible_root_image':raise PermissionError('terminal root image hidden')
                    return variant!='wrong_image'
                with patch.object(family_module,'info',side_effect=lambda pid:elevated if pid==21 else terminal['meta']),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=121),patch.object(family_module.os,'close'),patch.object(family_module.os,'sysconf',return_value=100),patch.object(f,'_matches_binary',side_effect=image):
                    with self.assertRaises((FamilyError,PermissionError)):f._record_live(21,'VERIFIED_PARENT_CHILD',terminal)
                self.assertNotIn(21,f.pid_keys)

    def test_elevated_unrelated_or_adopted_child_is_not_terminal_descendant(self):
        for adopted in (False,True):
            with self.subTest(adopted=adopted):
                f,terminal=self.terminal_family()
                unrelated=self.member(22,role='HELPER',lineage=(22,'10001'),helper_lineage=True)
                f.members[unrelated['key']]=unrelated;f.pid_keys[22]=unrelated['key']
                parent=None if adopted else unrelated
                elevated=self.meta(21,ppid=10 if adopted else 22,uid=0)
                with patch.object(family_module,'info',return_value=elevated),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=121),patch.object(family_module.os,'close'),patch.object(f,'_matches_binary') as observed:
                    with self.assertRaisesRegex(FamilyError,'CHILD_IDENTITY_UNVERIFIED'):
                        f._record_live(21,'KERNEL_SUBREAPER_CHILD' if adopted else 'VERIFIED_PARENT_CHILD',parent)
                    observed.assert_not_called()

    def test_ordinary_waiting_shell_is_not_required_to_exit_before_enter(self):
        f,terminal=self.terminal_family();shell=self.meta(21,ppid=20)
        with patch.object(family_module,'info',side_effect=lambda pid:shell if pid==21 else terminal['meta']),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=121),patch.object(f,'_matches_binary',return_value=False):
            key=f._record_live(21,'VERIFIED_PARENT_CHILD',terminal)
            self.assertTrue(f._install_helpers_complete(terminal['key']))
        item=f.members[key]
        self.assertEqual(item['helper_kind'],'TERMINAL_DESCENDANT')
        self.assertFalse(item['lifecycle_only']);self.assertFalse(item['terminal'])
        self.assertTrue(item['helper_lineage'])

    def test_same_uid_hidden_image_does_not_acquire_elevated_status(self):
        f,terminal=self.terminal_family();shell=self.meta(21,ppid=20)
        with patch.object(family_module,'info',side_effect=lambda pid:shell if pid==21 else terminal['meta']),patch.object(family_module,'alive',return_value=True),patch.object(family_module.os,'pidfd_open',return_value=121),patch.object(family_module.os,'close'),patch.object(f,'_matches_binary',side_effect=PermissionError('unknown same-uid image')):
            with self.assertRaises(PermissionError):f._record_live(21,'VERIFIED_PARENT_CHILD',terminal)
        self.assertNotIn(21,f.pid_keys)

    def test_adopted_official_exec_has_truthful_provenance(self):
        candidate=self.member(30,image='executable');f=self.restart_family(candidate)
        with patch.object(family_module.time,'monotonic',return_value=102),patch.object(family_module.os,'sysconf',return_value=100),patch.object(family_module,'info',return_value=candidate['meta']),patch.object(family_module,'alive',return_value=True):
            f._observe_restart()
        self.assertEqual(f.restart['replacement_key'],candidate['key'])
        self.assertIsNone(f.restart['restarter_key'])
        self.assertEqual(f.restart['provenance'],'CLOSED_FAMILY_ADOPTED_EXEC')
        self.assertEqual(f.restart_provenance(),'NONE')
        f.tick=Mock();f.verify_replacement(Child(f,candidate['key']))
        self.assertEqual(f.restart_provenance(),'CLOSED_FAMILY_ADOPTED_EXEC')

    def test_observed_restarter_same_pid_exec_preserves_distinct_provenance(self):
        candidate=self.member(30,image='restarter');f=self.restart_family(candidate)
        args=b'/official/restarter\0' + b'20\0' + b'1\0/official/idea\0'
        stream=Mock();stream.__enter__=Mock(return_value=stream);stream.__exit__=Mock(return_value=False);stream.read=Mock(return_value=args)
        with patch.object(family_module.time,'monotonic',return_value=102),patch.object(family_module.os,'sysconf',return_value=100),patch.object(family_module,'info',return_value=candidate['meta']),patch.object(family_module,'alive',return_value=True),patch('builtins.open',return_value=stream):
            f._observe_restart()
            self.assertEqual(f.restart['restarter_key'],candidate['key'])
            self.assertIsNone(f.restart['replacement_key'])
            candidate['image']='executable';f._observe_restart()
        self.assertEqual(f.restart['replacement_key'],candidate['key'])
        self.assertEqual(f.restart['provenance'],'OBSERVED_RESTARTER_EXEC')

    def test_adopted_exec_rejects_wrong_phase_birth_origin_or_helper_lineage(self):
        for variant in ('old_live','born_before_arm','helper','unadopted','direct_spawn','wrong_group'):
            with self.subTest(variant=variant):
                candidate=self.member(30,image='executable');f=self.restart_family(candidate)
                if variant=='old_live':f.members[f.restart['old_key']]['terminal']=False
                if variant=='born_before_arm':candidate['meta']['start_time']='9999'
                if variant=='helper':candidate['helper_lineage']=True
                if variant=='unadopted':candidate['adopted']=False
                if variant=='direct_spawn':candidate['provenance']='DIRECT_SPAWN'
                if variant=='wrong_group':candidate['meta']['pgrp']=candidate['meta']['session']=30
                def proc(pid):return candidate['meta'] if pid==30 else f.members[f.restart['old_key']]['meta']
                with patch.object(family_module.time,'monotonic',return_value=102),patch.object(family_module.os,'sysconf',return_value=100),patch.object(family_module,'info',side_effect=proc),patch.object(family_module,'alive',return_value=True):
                    f._observe_restart()
                self.assertIsNone(f.restart['replacement_key'])

    def test_multiple_official_adopted_candidates_are_rejected(self):
        one=self.member(30,image='executable');two=self.member(31,image='executable');f=self.restart_family(one,two)
        with patch.object(family_module.time,'monotonic',return_value=102),patch.object(family_module.os,'sysconf',return_value=100),patch.object(family_module,'info',side_effect=lambda pid:one['meta'] if pid==30 else two['meta']),patch.object(family_module,'alive',return_value=True):
            with self.assertRaisesRegex(FamilyError,'MULTIPLE_REPLACEMENT_IDES'):f._observe_restart()

    def test_restart_countdown_starts_only_after_ack(self):
        f=self.restart_family();f.restart['acknowledged_at']=None
        with patch.object(family_module.time,'monotonic',return_value=200):f._observe_restart()
        f.restart['acknowledged_at']=190
        with patch.object(family_module.time,'monotonic',return_value=249):f._observe_restart()
        with patch.object(family_module.time,'monotonic',return_value=251):
            with self.assertRaisesRegex(FamilyError,'RESTART_DEADLINE'):f._observe_restart()
        self.assertEqual(f.deadline,1000)

    def test_ack_requires_verified_binding_and_complete_helpers(self):
        helper=self.member(31,lifecycle_only=True,never_signal=True,terminal_root=(30,'10001'))
        f=self.restart_family(helper);f.tick=Mock();f.restart['acknowledged_at']=None
        f.terminal_key=f.terminal_verified_key=(30,'10001')
        with patch.object(family_module,'alive',return_value=True):
            with self.assertRaisesRegex(FamilyError,'INSTALL_HELPERS_INCOMPLETE'):f.terminal_acknowledged('a'*64)
        helper['terminal']=True;helper['fd']=None;helper['exit_code']=1
        with self.assertRaisesRegex(FamilyError,'INSTALL_HELPER_FAILED'):f.terminal_acknowledged('a'*64)
        helper['exit_code']=None
        with self.assertRaisesRegex(FamilyError,'TERMINAL_ACK_INVALID'):f.terminal_acknowledged('b'*64)
        f.cancel.set('AT_ACK')
        with self.assertRaises(InterruptedError):f.terminal_acknowledged('a'*64)

    def test_observation_failure_stays_uncertified_after_child_exits(self):
        f=self.family();f.observation_failed=True;f.tick=Mock()
        def reaped():f.last_echild=True
        f._reap=reaped
        with patch.object(family_module,'children',return_value=set()),patch.object(family_module.time,'sleep'):
            with self.assertRaisesRegex(FamilyError,'FAMILY_CLEANUP_INCOMPLETE'):f.close_phase()
        self.assertFalse(f.phase_closed)


if __name__ == '__main__':
    unittest.main()
