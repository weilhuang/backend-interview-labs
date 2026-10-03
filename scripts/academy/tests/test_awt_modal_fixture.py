"""Mocked complete Swing-proof composition; genuine Java/Xvfb cases are NOT_RUN."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import awt_title_fixture as fixture
import modal_window
from display_diagnostic import encode
from test_modal_window import FakeX, _record, _node, proof_fixture, add_child
import test_awt_title_fixture as title_tests


def modal_proof(action=fixture.MODAL_ACTIONS[0], pid=102, count=1):
    """Synthetic data only, validated through the unchanged complete-proof API."""
    identity = {'window_id': 56, 'pid': pid, 'title_sha256': fixture.MODAL_TITLE_HASH,
                **dict(zip(('x', 'y', 'width', 'height', 'border'), fixture.MODAL_GEOMETRY))}
    proof = proof_fixture(action, identity)
    proof['root_children'].extend(_record(1000 + index, -100, -100, 10, 10,
        window_class=2, map_state=0) for index in range(count))
    return modal_window.validate(proof, action)


def modal_cases(count=1):
    return [fixture._modal_case(modal_proof(action, count=count), 102, action)
            for action in fixture.MODAL_ACTIONS]


def modal_response(action, pid=102, count=1):
    return {'schema': 1, 'status': 'PASS', 'action': action,
            'proof': modal_proof(action, pid, count), 'error': None, 'diagnosis': None}


def response(value, code=0):
    return subprocess.CompletedProcess([], code, encode(value))


def title_response():
    return response({'schema': 1, 'status': 'PASS', 'cases': title_tests.cases(), 'diagnosis': None})


class FullModalProbe(unittest.TestCase):
    def probe(self, action=fixture.MODAL_ACTIONS[0], proof=None, error=None):
        proof = modal_proof(action) if proof is None else proof
        with patch.dict(os.environ, {'DISPLAY': fixture.DISPLAY}), patch.object(
                modal_window, 'observe', return_value=proof, side_effect=error) as observed:
            result = fixture._modal_probe(102, action)
        observed.assert_called_once_with(102, action)
        return result

    def test_each_action_calls_exact_production_observe_without_retry(self):
        for action in fixture.MODAL_ACTIONS:
            with self.subTest(action=action):
                proof = modal_proof(action)
                result = self.probe(action, proof)
                self.assertEqual(result['proof'], proof)
                self.assertEqual(result['status'], 'PASS')
                projected = fixture._modal_case(result['proof'], 102, action)
                self.assertEqual(projected['proof_sha256'], hashlib.sha256(encode(proof)).hexdigest())
                self.assertEqual(projected['decision_title_sha256'], fixture.MODAL_TITLE_HASH)
                self.assertEqual(projected['decision_geometry'], list(fixture.MODAL_GEOMETRY))

    def test_production_two_complete_samples_are_used_with_simulated_x_replies(self):
        for action in fixture.MODAL_ACTIONS:
            proof = modal_proof(action)
            child = _record(80, 0, 0, 520, 235, pid=102)
            add_child(proof, child)
            proof['focus_path'].append(80)
            proof['target_route'].append(80)
            x = FakeX(proof)
            with patch.dict(os.environ, {'DISPLAY': fixture.DISPLAY}), patch.object(modal_window, '_X11', return_value=x):
                result = fixture._modal_probe(102, action)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(x.root_calls, 2)
            self.assertEqual(x.tree_calls, [10, 56, 80, 10, 56, 80])
            self.assertTrue(x.closed)
            projected = fixture._modal_case(result['proof'], 102, action)
            self.assertEqual([projected[k] for k in ('root_count', 'node_count', 'focus_count', 'route_count')], [2, 2, 2, 2])

    def test_first_typed_production_failure_is_preserved_exactly(self):
        error = modal_window.ProofError('INPUT_ROUTE_CHANGED', 'SHAPE_INPUT',
                                       {'node_index': 1, 'shape_kind': 2})
        result = self.probe(error=error)
        self.assertEqual(result['error'], 'PROBE_FAILED')
        self.assertEqual(result['diagnosis'], modal_window.failure_from_exception(error))
        self.assertIsNone(result['proof'])

    def test_zero_incidental_roots_pass_both_proofs_without_synthetic_repair(self):
        for action in fixture.MODAL_ACTIONS:
            proof = modal_proof(action, count=0)
            result = self.probe(action, proof=proof)
            self.assertEqual(result['status'], 'PASS')
            self.assertIsNone(result['error'])
            self.assertIsNone(result['diagnosis'])
            self.assertEqual(result['proof'], proof)
            projected = fixture._modal_case(result['proof'], 102, action)
            self.assertEqual(projected['root_count'], 1)
            self.assertEqual(projected['unmapped_inputonly_total'], 0)
            self.assertEqual(projected['unmapped_inputonly'], [])
            self.assertEqual(projected['unmapped_inputonly_omitted'], 0)
            self.assertEqual(len(proof['root_children']), 1)

    def test_zero_incidental_roots_still_use_two_complete_production_samples(self):
        for action in fixture.MODAL_ACTIONS:
            proof = modal_proof(action, count=0)
            x = FakeX(proof)
            with patch.dict(os.environ, {'DISPLAY': fixture.DISPLAY}), patch.object(modal_window, '_X11', return_value=x):
                result = fixture._modal_probe(102, action)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['proof'], proof)
            self.assertEqual(x.root_calls, 2)
            self.assertEqual(x.tree_calls, [10, 56, 10, 56])
            self.assertTrue(x.closed)

    def test_valid_but_foreign_pid_title_or_geometry_has_fixed_failure(self):
        for field, value in (('pid', 103), ('title_sha256', 'f' * 64), ('x', 381),
                             ('y', 336), ('width', 521), ('height', 236)):
            with self.subTest(field=field):
                proof = modal_proof()
                for record in (proof['window_identity'], proof['root_children'][0], proof['dialog_tree'][0]):
                    record[field] = value
                if field in ('width', 'height'):
                    proof['dialog_tree'][0] = _node(proof['root_children'][0], proof['root_id'])
                modal_window.validate(proof, fixture.MODAL_ACTIONS[0])
                result = self.probe(proof=proof)
                self.assertEqual(result['error'], 'MODAL_IDENTITY_MISMATCH')
                self.assertIsNone(result['proof'])
                self.assertIsNone(result['diagnosis'])

    def test_bad_full_proof_cannot_be_projected_or_relabelled(self):
        action = fixture.MODAL_ACTIONS[0]
        for mutation in ({'action': fixture.MODAL_ACTIONS[1]}, {'proof_sha256': 'f' * 64},
                         {'target_route': [999]}, {'focus_path': [999]}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                fixture._modal_case({**modal_proof(), **mutation}, 102, action)
        with self.assertRaises(ValueError):
            fixture._modal_probe_document(modal_response(action, 103), 102, action)
        with self.assertRaises(ValueError):
            fixture._modal_probe_document(modal_response(action), 102, fixture.MODAL_ACTIONS[1])


class ModalProjection(unittest.TestCase):
    def reject_case(self, value):
        with self.assertRaises(ValueError):
            fixture._modal_case_document(value, fixture.MODAL_ACTIONS[0])

    def test_zero_projection_requires_empty_facts_and_exact_zero_omission(self):
        zero = modal_cases(0)[0]
        self.assertEqual(fixture._modal_case_document(zero, fixture.MODAL_ACTIONS[0]), zero)
        for mutation in ({'unmapped_inputonly_total': False}, {'unmapped_inputonly_total': -1},
                         {'unmapped_inputonly_omitted': False}, {'unmapped_inputonly_omitted': 1},
                         {'unmapped_inputonly': modal_cases()[0]['unmapped_inputonly']},
                         {'root_count': 0}, {'unmapped_inputonly_total': 1}):
            with self.subTest(mutation=mutation):
                self.reject_case({**zero, **mutation})

    def test_zero_and_positive_observations_are_distinct_and_both_bounded(self):
        for count in (0, 1, 8, 9, 31):
            value = title_tests.report()
            value['modal_cases'] = modal_cases(count)
            actual = fixture.report_document(value)
            self.assertEqual([c['unmapped_inputonly_total'] for c in actual['modal_cases']], [count, count])
            self.assertLessEqual(len(encode(actual)), 8192)
        self.assertNotEqual(modal_cases(0)[0]['proof_sha256'], modal_cases(1)[0]['proof_sha256'])

    def test_first_eight_matching_original_indexes_and_omitted_count(self):
        proof = modal_proof(count=12)
        # Interleave nonmatching roots. Original root indexes must survive.
        proof['root_children'].insert(1, _record(400, 0, 0, 1, 1, window_class=2, map_state=0))
        proof['root_children'].insert(5, _record(401, -100, -100, 1, 1, window_class=1, map_state=0))
        value = fixture._modal_case(proof, 102, fixture.MODAL_ACTIONS[0])
        self.assertEqual([item['root_index'] for item in value['unmapped_inputonly']], [2, 3, 4, 6, 7, 8, 9, 10])
        self.assertEqual(value['unmapped_inputonly_total'], 12)
        self.assertEqual(value['unmapped_inputonly_omitted'], 4)
        public = encode(value)
        for forbidden in (b'window_id', b'"pid"', b'focus_path', b'target_route', fixture.MODAL_TITLE, b'owner', b'proxy'):
            self.assertNotIn(forbidden, public)

    def test_maximum_projection_whole_report_remains_bounded_and_detached(self):
        value = title_tests.report()
        value['modal_cases'] = modal_cases(modal_window.MAX_ROOT_CHILDREN - 1)
        for item in value['modal_cases']:
            item.update(node_count=modal_window.MAX_NODES, focus_count=modal_window.MAX_DEPTH + 1,
                        route_count=modal_window.MAX_DEPTH + 1)
            for record in item['unmapped_inputonly']:
                record.update(x=-32768, y=-32768, width=1280, height=900)
        value.update(run_id='9' * 20, run_attempt='9' * 20, elapsed_milliseconds=60000)
        projected = fixture.report_document(value)
        self.assertLessEqual(len(encode(projected)), 8192)
        value['modal_cases'][0]['unmapped_inputonly'][0]['x'] = -1
        value['modal_cases'][0]['decision_geometry'][0] = 1
        self.assertNotEqual(value, projected)

    def test_closed_schema_and_counts_reject_unknown_nested_or_inconsistent_data(self):
        base = modal_cases()[0]
        mutations = ({'action': fixture.MODAL_ACTIONS[1]}, {'status': 'NOT_RUN'},
                     {'proof_sha256': 'PRIVATE'}, {'decision_title_sha256': 'f' * 64},
                     {'decision_geometry': [380, 335, 520, 235, False]},
                     {'decision_geometry': [380, 335, 521, 235, 0]},
                     {'root_count': True}, {'root_count': 33}, {'root_count': 1},
                     {'node_count': 65}, {'node_count': 0}, {'focus_count': 10},
                     {'focus_count': 2}, {'route_count': 0}, {'route_count': True},
                     {'unmapped_inputonly_total': 0}, {'unmapped_inputonly_total': 2},
                     {'unmapped_inputonly_total': True}, {'unmapped_inputonly_omitted': 1},
                     {'unmapped_inputonly_omitted': False}, {'unmapped_inputonly': []},
                     {'unmapped_inputonly': [{'private': {'payload': 'PRIVATE'}}]},
                     {'environment': {'payload': 'PRIVATE'}})
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.reject_case({**base, **mutation})

    def test_record_bounds_exact_integer_class_state_border_and_order(self):
        base = modal_cases(9)[0]
        for field, values in (('root_index', (True, -1, 10)), ('x', (True, -32769, 32768)),
                              ('y', (None, -32769, 32768)), ('width', (False, 0, 1281)),
                              ('height', (True, 0, 901)), ('border', (False, 1)),
                              ('window_class', (True, 1)), ('map_state', (False, 1, 2))):
            for invalid in values:
                with self.subTest(field=field, value=invalid):
                    value = copy.deepcopy(base)
                    value['unmapped_inputonly'][0][field] = invalid
                    self.reject_case(value)
        for stored in (list(reversed(base['unmapped_inputonly'])),
                       [base['unmapped_inputonly'][0]] * 8,
                       base['unmapped_inputonly'][:-1],
                       base['unmapped_inputonly'] + [base['unmapped_inputonly'][-1]]):
            self.reject_case({**base, 'unmapped_inputonly': stored})
        value = copy.deepcopy(base)
        value['unmapped_inputonly'][-1]['root_index'] = 9
        self.reject_case(value)  # No index left for the claimed omitted match.
        value = modal_cases()[0]
        value['unmapped_inputonly'][0].update(x=0, y=0)
        self.reject_case(value)

    def test_legacy_pass_missing_cases_or_unreaped_children_never_pass(self):
        base = title_tests.report()
        legacy = {key: value for key, value in base.items() if key != 'modal_cases'}
        legacy.update(schema=1, kind='PRIVATE_BUNDLED_JBR_AWT_TITLE_COMPATIBILITY_NOT_IDE_OR_ACCEPTANCE')
        changes = (legacy, {**base, 'schema': 1}, {**base, 'modal_cases': []},
                   {**base, 'modal_cases': base['modal_cases'][:1]},
                   {**base, 'modal_cases': list(reversed(base['modal_cases']))},
                   {**base, 'cleanup': {'jvm': 'UNVERIFIED', 'xvfb': 'REAPED'}},
                   {**base, 'runtime': None})
        for value in changes:
            with self.subTest(value=value), self.assertRaises(ValueError):
                fixture.report_document(value)


class ModalCoordinator(unittest.TestCase):
    def execute(self, **kwargs):
        return title_tests.CoordinatorLifecycle().execute(**kwargs)

    def test_both_genuine_zero_count_proofs_are_mandatory_before_pass(self):
        replies = [title_response(), *(response(modal_response(action, count=0))
                                      for action in fixture.MODAL_ACTIONS)]
        value, failed, _, _, _, run, _ = self.execute(probe_results=replies)
        self.assertFalse(failed)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(value['modal_cases'], modal_cases(0))
        self.assertEqual(value['status'], 'PASS')

    def test_second_failure_retains_first_safe_zero_projection(self):
        error = modal_window.ProofError('INPUT_ROUTE_CHANGED', 'SHAPE_INPUT', {'node_index': 1})
        failure = {'schema': 1, 'status': 'FAIL', 'action': fixture.MODAL_ACTIONS[1],
                   'proof': None, 'error': 'PROBE_FAILED', 'diagnosis': modal_window.failure_from_exception(error)}
        for last in (response(failure, 1), subprocess.TimeoutExpired('private', 2), InterruptedError('private')):
            value, failed, _, _, _, run, _ = self.execute(probe_results=[title_response(),
                response(modal_response(fixture.MODAL_ACTIONS[0], count=0)), last])
            self.assertTrue(failed)
            self.assertEqual(run.call_count, 3)
            self.assertEqual(value['modal_cases'], modal_cases(0)[:1])
            self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})
            self.assertNotIn(b'private', encode(value))

    def test_cleanup_failure_retains_both_zero_count_projections_without_pass(self):
        replies = [title_response(), *(response(modal_response(action, count=0))
                                      for action in fixture.MODAL_ACTIONS)]
        value, failed, server, _, _, _, _ = self.execute(probe_results=replies, cleanup_failure=True)
        self.assertTrue(failed)
        self.assertEqual(value['error'], 'CLEANUP_UNVERIFIED')
        self.assertEqual(value['modal_cases'], modal_cases(0))
        self.assertEqual(server.wait_calls, [2])

    def test_three_ordered_hard_two_second_children_share_original_deadline(self):
        with patch.object(fixture.time, 'monotonic', return_value=100.0), patch.object(
                fixture, '_remaining', wraps=fixture._remaining) as remaining:
            value, failed, server, jvm, popen, run, _ = self.execute()
        self.assertFalse(failed)
        self.assertEqual(value['modal_cases'], modal_cases())
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].args[0][-2:], ['--probe', '102'])
        for action, call in zip(fixture.MODAL_ACTIONS, run.call_args_list[1:]):
            self.assertEqual(call.args[0][-4:], ['--modal-probe', '102', '--action', action])
        for call in run.call_args_list:
            self.assertEqual(call.kwargs['timeout'], 2)
            self.assertEqual(call.kwargs['stdin'], subprocess.DEVNULL)
            self.assertEqual(call.kwargs['stderr'], subprocess.DEVNULL)
            self.assertEqual(call.kwargs['env']['DISPLAY'], fixture.DISPLAY)
        self.assertEqual([call.args for call in remaining.call_args_list], [(140.0, 2)] * 3 + [(140.0, 1)])
        self.assertEqual(server.wait_calls, [2])
        self.assertEqual(jvm.wait_calls, [2])

    def test_first_modal_failure_preserves_title_cases_and_typed_diagnosis(self):
        error = modal_window.ProofError('INPUT_ROUTE_CHANGED', 'SHAPE_CLIP', {'node_index': 1})
        failure = {'schema': 1, 'status': 'FAIL', 'action': fixture.MODAL_ACTIONS[0],
                   'proof': None, 'error': 'PROBE_FAILED', 'diagnosis': modal_window.failure_from_exception(error)}
        value, failed, _, _, _, run, _ = self.execute(probe_results=[title_response(), response(failure, 1)])
        self.assertTrue(failed)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(value['cases'], title_tests.cases())
        self.assertEqual(value['modal_cases'], [])
        self.assertEqual(value['diagnosis'], failure['diagnosis'])
        self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})

    def test_second_modal_timeout_and_cancellation_preserve_first_case_and_cleanup(self):
        for error, code in ((subprocess.TimeoutExpired('private', 2), 'PROBE_TIMEOUT'),
                            (InterruptedError('private'), 'CANCELLED')):
            with self.subTest(code=code):
                value, failed, _, _, _, run, _ = self.execute(probe_results=[title_response(),
                    response(modal_response(fixture.MODAL_ACTIONS[0])), error])
                self.assertTrue(failed)
                self.assertEqual(run.call_count, 3)
                self.assertEqual(value['error'], code)
                self.assertEqual(value['modal_cases'], modal_cases()[:1])
                self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})
                self.assertNotIn(b'private', encode(value))

    def test_identity_failure_reaches_public_report_without_raw_proof(self):
        for code in ('MODAL_IDENTITY_MISMATCH',):
            failure = {'schema': 1, 'status': 'FAIL', 'action': fixture.MODAL_ACTIONS[0],
                       'proof': None, 'error': code, 'diagnosis': None}
            value, failed, _, _, _, run, _ = self.execute(probe_results=[title_response(), response(failure, 1)])
            self.assertTrue(failed)
            self.assertEqual(value['error'], code)
            self.assertEqual(run.call_count, 2)
            self.assertIsNone(value['diagnosis'])
            self.assertNotIn(b'"pid"', encode(value))

    def test_short_remaining_budget_is_not_reset_and_stops_next_probe(self):
        with patch.object(fixture.time, 'monotonic', side_effect=[0, 10, 39, 40.01, 40.02, 40.03]):
            value, failed, _, _, _, run, _ = self.execute()
        self.assertTrue(failed)
        self.assertEqual(run.call_count, 2)
        self.assertEqual([call.kwargs['timeout'] for call in run.call_args_list], [2, 1])
        self.assertEqual(value['error'], 'BUDGET_EXHAUSTED')
        self.assertEqual(value['modal_cases'], modal_cases()[:1])
        self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})

    def test_malformed_full_response_or_oversize_cannot_produce_pass(self):
        for invalid in (response({**modal_response(fixture.MODAL_ACTIONS[0]), 'proof': {'private': 'PRIVATE'}}),
                        subprocess.CompletedProcess([], 0, b'x' * (fixture.MAX_MODAL_PROBE_BYTES + 1)),
                        response(modal_response(fixture.MODAL_ACTIONS[1])),
                        response(modal_response(fixture.MODAL_ACTIONS[0], 103))):
            with self.subTest(invalid=invalid):
                value, failed, _, _, _, run, _ = self.execute(probe_results=[title_response(), invalid])
                self.assertTrue(failed)
                self.assertEqual(run.call_count, 2)
                self.assertEqual(value['modal_cases'], [])
                self.assertEqual(value['cleanup'], {'jvm': 'REAPED', 'xvfb': 'REAPED'})
                self.assertNotIn(b'PRIVATE', encode(value).replace(fixture.KIND.encode(), b''))

    def test_parent_revalidates_full_proof_identity_and_retains_fixed_failure(self):
        invalid = modal_response(fixture.MODAL_ACTIONS[0], 103)
        value, failed, _, _, _, run, _ = self.execute(probe_results=[title_response(), response(invalid)])
        self.assertTrue(failed)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(value['error'], 'MODAL_IDENTITY_MISMATCH')
        self.assertIsNone(value['diagnosis'])
        invalid = modal_response(fixture.MODAL_ACTIONS[0])
        invalid['proof']['dialog_tree'][0]['shape']['input'][0] = 1
        value, failed, *_ = self.execute(probe_results=[title_response(), response(invalid)])
        self.assertTrue(failed)
        self.assertEqual(value['diagnosis']['call_site'], 'SHAPE_INPUT')

    def test_failed_jvm_reap_after_both_modal_proofs_still_reaps_xvfb(self):
        value, failed, server, _, _, run, _ = self.execute(cleanup_failure=True)
        self.assertTrue(failed)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(value['modal_cases'], modal_cases())
        self.assertEqual(value['error'], 'CLEANUP_UNVERIFIED')
        self.assertEqual(server.wait_calls, [2])


if __name__ == '__main__':
    unittest.main()
