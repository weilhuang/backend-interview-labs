"""Nonprivileged strict-proof fixtures; no X connection, Java, or GUI is started."""
import copy
import ctypes as C
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modal_window as modal


def _shape(width, height, border=0, window_class=1):
    return {"bounding": [-border, -border, width + 2 * border, height + 2 * border],
            "input": [-border, -border, width + 2 * border, height + 2 * border],
            "clip": [0, 0, width, height] if window_class == 1 else None,
            "orders": [3, 3, 3] if window_class == 1 else [3, 3]}


def _record(window_id, x, y, width, height, **changes):
    return {"window_id": window_id, "pid": None, "title_sha256": None,
            "x": x, "y": y, "width": width, "height": height, "border": 0,
            "window_class": 1, "map_state": 2, "override_redirect": False,
            "event_mask": 0, "do_not_propagate_mask": 0, **changes}


def _node(record, parent, children=()):
    return {**record, "parent": parent, "children": list(children),
            "shape": _shape(record["width"], record["height"], record["border"], record["window_class"])}


def proof_fixture(action="CHECK_ACADEMY_PLUGIN_ONLY", window_identity=None):
    """Reusable minimal valid proof matching the existing plugin approval fixture."""
    identity = copy.deepcopy(window_identity) if window_identity is not None else {
        "window_id": 56, "pid": 100, "x": 380, "y": 335, "width": 520,
        "height": 235, "border": 0, "title_sha256": "e" * 64}
    record = _record(**identity)
    return {"schema": 1, "action": action, "root_id": 10, "screen": [1280, 900],
            "shape_version": [1, 1], "root_shape": _shape(1280, 900),
            "window_identity": identity, "root_children": [record],
            "dialog_tree": [_node(record, 10)], "focus_path": [identity["window_id"]],
            "focus_revert": 0, "target_route": [identity["window_id"]]}


def add_child(proof, record, parent=None):
    parent = parent or proof["window_identity"]["window_id"]
    owner = next(node for node in proof["dialog_tree"] if node["window_id"] == parent)
    owner["children"].append(record["window_id"])
    proof["dialog_tree"].append(_node(record, parent))


class FakeX:
    """Deterministic sampled X replies with the same read-only adapter interface."""
    def __init__(self, proof):
        self.proof = copy.deepcopy(proof)
        self.root_calls = 0
        self.tree_calls = []
        self.entered = False
        self.closed = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_):
        self.closed = True

    def root(self):
        self.root_calls += 1
        return self.proof["root_id"]

    def version(self):
        return self.proof["shape_version"]

    def _node(self, window):
        return next(node for node in self.proof["dialog_tree"] if node["window_id"] == window)

    def attributes(self, window, root):
        if window == root:
            return _record(root, 0, 0, 1280, 900)
        for node in self.proof["root_children"] + self.proof["dialog_tree"]:
            if node["window_id"] == window:
                return {key: node[key] for key in modal._ATTRS}
        raise AssertionError("unexpected window read")

    def tree(self, window, cap):
        self.tree_calls.append(window)
        if window == self.proof["root_id"]:
            result = [node["window_id"] for node in self.proof["root_children"]]
            parent = 0
        else:
            node = self._node(window)
            result, parent = node["children"], node["parent"]
        modal._require(len(result) <= cap)
        return self.proof["root_id"], parent, list(result)

    def shape(self, window, window_class):
        if window == self.proof["root_id"]:
            return self.proof["root_shape"]
        return self._node(window)["shape"]

    def focus(self):
        return self.proof["focus_path"][-1], self.proof["focus_revert"]

    def child_at(self, window, point):
        if window == self.proof["root_id"]:
            return self.proof["window_identity"]["window_id"]
        route = self.proof["target_route"]
        index = route.index(window)
        return route[index + 1] if index + 1 < len(route) else 0


class ProofSchemaTests(unittest.TestCase):
    def setUp(self):
        self.proof = proof_fixture()
        self.action = self.proof["action"]

    def valid(self, proof=None):
        return modal.validate(self.proof if proof is None else proof, self.action)

    def reject(self, mutate, reason=None):
        proof = copy.deepcopy(self.proof)
        mutate(proof)
        with self.assertRaises(ValueError) as raised:
            self.valid(proof)
        if reason is not None:
            self.assertEqual(raised.exception.reason, reason)

    def test_both_fixed_actions_have_strict_original_window_identity(self):
        for action in modal.ACTIONS:
            proof = proof_fixture(action)
            self.assertIs(modal.validate(proof, action), proof)
            self.assertEqual(set(proof["window_identity"]), {
                "window_id", "pid", "x", "y", "width", "height", "border", "title_sha256"})
        for action in ("TRUST_VALIDATION_PROJECT", "INSTALL_PROFILE", [448, 403], None):
            with self.assertRaises(ValueError):
                modal.validate(self.proof, action)

    def test_all_records_are_closed(self):
        for path in ((), ("window_identity",), ("root_shape",), ("root_children", 0),
                     ("dialog_tree", 0), ("dialog_tree", 0, "shape")):
            def extra(proof):
                current = proof
                for key in path:
                    current = current[key]
                current["private"] = {"secret": "never accepted"}
            with self.subTest(path=path):
                self.reject(extra)
        for key in self.proof:
            self.reject(lambda p: p.pop(key))

    def test_all_numeric_fields_reject_booleans_strings_floats_and_null(self):
        for key in ("schema", "root_id", "focus_revert"):
            for value in (True, "1", 1.0, None):
                self.reject(lambda p: p.__setitem__(key, value))
        for key in ("window_id", "x", "y", "width", "height", "border", "window_class",
                    "map_state", "event_mask", "do_not_propagate_mask"):
            for value in (True, "1", 1.0, None):
                with self.subTest(key=key, value=value):
                    self.reject(lambda p: p["root_children"][0].__setitem__(key, value))
        for key in ("screen", "shape_version", "target_route", "focus_path"):
            self.reject(lambda p: p[key].__setitem__(0, True))
        self.reject(lambda p: p["root_children"][0].__setitem__("override_redirect", 0))
        self.reject(lambda p: p["dialog_tree"][0]["shape"]["input"].__setitem__(0, False))

    def test_action_and_identity_are_bound_to_root_record(self):
        for key, value in (("window_id", 57), ("pid", 101), ("x", 381), ("y", 336),
                           ("width", 519), ("height", 234), ("title_sha256", "f" * 64), ("border", 1)):
            self.reject(lambda p: p["window_identity"].__setitem__(key, value))
        self.reject(lambda p: p.__setitem__("action", modal.ACTIONS[1]))

    def test_root_count_duplicates_root_as_child_and_window_bounds(self):
        self.reject(lambda p: p.__setitem__("root_children", p["root_children"] * 33))
        self.reject(lambda p: p["root_children"].append(copy.deepcopy(p["root_children"][0])))
        self.reject(lambda p: p["root_children"].append(_record(10, 0, 0, 1, 1)))
        for changes in ({"x": -1}, {"x": 1279, "width": 2}, {"y": 899, "height": 2},
                        {"border": 9}, {"map_state": 1}, {"window_class": 3}):
            self.reject(lambda p: p["root_children"].append({**_record(99, 0, 0, 1, 1), **changes}))

    def test_mapped_higher_overlay_anywhere_on_whole_modal_rejected(self):
        for window_class in (1, 2):
            for pid in (None, 100, 999):
                overlay = _record(80, 850, 500, 2, 2, window_class=window_class, pid=pid)
                self.reject(lambda p: p["root_children"].append(overlay), "WINDOW_OCCLUDED")
        overlay = _record(80, 898, 400, 1, 1, border=1)
        self.reject(lambda p: p["root_children"].append(overlay), "WINDOW_OCCLUDED")

    def test_lower_or_unmapped_or_nonoverlapping_sibling_stays_bound(self):
        for overlay, position in ((_record(80, 400, 400, 20, 20), 0),
                                  (_record(80, 400, 400, 20, 20, map_state=0), 1),
                                  (_record(80, 900, 335, 20, 20), 1)):
            proof = copy.deepcopy(self.proof)
            proof["root_children"].insert(position, overlay)
            self.valid(proof)
            self.assertNotEqual(proof, self.proof)

    def test_inputonly_descendant_interception_away_from_target_rejected(self):
        self.reject(lambda p: add_child(p, _record(57, 500, 200, 1, 1, window_class=2)), "INPUT_ROUTE_CHANGED")

    def test_negative_offcontent_mapped_focus_proxy_is_valid(self):
        add_child(self.proof, _record(57, -1, -1, 1, 1, window_class=2))
        self.proof["focus_path"] = [56, 57]
        self.valid()
        self.assertEqual(self.proof["target_route"], [56])

    def test_clipped_inputonly_proxy_cannot_gain_authority_through_large_negative_rect(self):
        self.reject(lambda p: add_child(p, _record(57, -1, -1, 2, 2, window_class=2)), "INPUT_ROUTE_CHANGED")

    def test_nested_signed_coordinates_and_parent_clip_define_target_route(self):
        add_child(self.proof, _record(57, -20, 20, 200, 150))
        add_child(self.proof, _record(58, 60, 30, 100, 80), 57)
        self.proof["target_route"] = [56, 57, 58]
        self.valid()
        self.reject(lambda p: p.__setitem__("target_route", [56, 58]), "INPUT_ROUTE_CHANGED")

    def test_descendant_order_is_preserved_and_restack_changes_hit_route(self):
        add_child(self.proof, _record(57, 0, 0, 200, 150))
        add_child(self.proof, _record(58, 0, 0, 200, 150))
        self.proof["target_route"] = [56, 58]
        self.valid()
        self.reject(lambda p: p["dialog_tree"][0]["children"].reverse())
        self.reject(lambda p: p.__setitem__("target_route", [56, 57]), "INPUT_ROUTE_CHANGED")

    def test_contradictory_descendant_pid_rejected_but_missing_pid_allowed(self):
        add_child(self.proof, _record(57, -1, -1, 1, 1))
        self.valid()
        self.reject(lambda p: p["dialog_tree"][1].__setitem__("pid", 101), "INPUT_ROUTE_CHANGED")
        self.reject(lambda p: p["dialog_tree"][1].__setitem__("pid", True))

    def test_topology_extra_nodes_missing_nodes_cycles_and_wrong_parents_rejected(self):
        self.reject(lambda p: p["dialog_tree"].append(_node(_record(57, 0, 0, 1, 1), 56)))
        self.reject(lambda p: p["dialog_tree"][0]["children"].append(57))
        self.reject(lambda p: p["dialog_tree"][0]["children"].append(56))
        self.reject(lambda p: p["dialog_tree"][0].__setitem__("parent", 99))
        self.reject(lambda p: p["dialog_tree"].append(copy.deepcopy(p["dialog_tree"][0])))

    def test_map_state_inconsistent_with_ancestry_rejected(self):
        add_child(self.proof, _record(57, -1, -1, 1, 1))
        self.reject(lambda p: p["dialog_tree"][1].__setitem__("map_state", 1))
        self.proof["dialog_tree"][1]["map_state"] = 0
        add_child(self.proof, _record(58, 0, 0, 1, 1), 57)
        with self.assertRaises(ValueError):
            self.valid()

    def test_max_depth_is_eight_and_max_total_nodes_is_sixtyfour(self):
        parent = 56
        for window in range(57, 65):
            add_child(self.proof, _record(window, -1, -1, 1, 1), parent)
            parent = window
        self.valid()
        add_child(self.proof, _record(65, -1, -1, 1, 1), 64)
        with self.assertRaises(ValueError):
            self.valid()
        proof = proof_fixture()
        for window in range(57, 121):
            add_child(proof, _record(window, -1, -1, 1, 1))
        with self.assertRaises(ValueError):
            self.valid(proof)

    def test_focus_outside_tree_wrong_ancestry_or_unmapped_rejected(self):
        for focus in ([], [10], [0], [1], [999], [56, 999], [56, 56]):
            self.reject(lambda p: p.__setitem__("focus_path", focus))
        add_child(self.proof, _record(57, -1, -1, 1, 1, map_state=0))
        self.reject(lambda p: p.__setitem__("focus_path", [56, 57]), "INPUT_ROUTE_CHANGED")

    def test_real_input_bounding_and_clip_coverage_required(self):
        for kind in ("input", "bounding", "clip"):
            self.reject(lambda p: p["dialog_tree"][0]["shape"][kind].__setitem__(2, 519), "INPUT_ROUTE_CHANGED")
            self.reject(lambda p: p["dialog_tree"][0]["shape"].__setitem__(kind, []))
        self.reject(lambda p: p["root_shape"]["input"].__setitem__(2, 1279), "INPUT_ROUTE_CHANGED")
        self.reject(lambda p: p.__setitem__("shape_version", [1, 0]))
        self.reject(lambda p: p["dialog_tree"][0]["shape"]["orders"].__setitem__(0, 4))

    def test_serialized_proof_budget_includes_newline(self):
        size = len(json.dumps(self.proof, sort_keys=True, separators=(",", ":")).encode()) + 1
        with patch.object(modal, "MAX_PROOF_BYTES", size):
            self.valid()
        with patch.object(modal, "MAX_PROOF_BYTES", size - 1), self.assertRaises(ValueError):
            self.valid()


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.proof = proof_fixture()
        self.fake = FakeX(self.proof)

    def observe(self, fake=None):
        with patch.dict(modal.os.environ, {"DISPLAY": ":100"}, clear=True), \
             patch.object(modal, "_X11", return_value=fake or self.fake), \
             patch.object(modal.time, "monotonic", return_value=10):
            return modal.observe(100, self.proof["action"])

    def test_two_complete_observations_query_root_once_each(self):
        self.assertEqual(self.observe(), self.proof)
        self.assertEqual(self.fake.root_calls, 2)
        self.assertEqual(self.fake.tree_calls, [10, 56, 10, 56])
        self.assertTrue(self.fake.closed)

    def test_dialog_geometry_root_stack_focus_and_input_shape_changes_refused(self):
        cases = (
            lambda x: x.proof["root_children"].append(_record(90, 0, 0, 1, 1)),
            lambda x: x.proof["root_children"][0].__setitem__("title_sha256", "f" * 64),
            lambda x: x.proof.__setitem__("focus_path", [999]),
            lambda x: x.proof["dialog_tree"][0]["shape"]["input"].__setitem__(2, 519))
        for change in cases:
            fake = FakeX(self.proof)
            original = fake.root
            def root():
                if fake.root_calls == 1:
                    change(fake)
                return original()
            fake.root = root
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.observe(fake)

    def test_wrong_owned_pid_or_external_focus_never_returns_proof(self):
        self.fake.proof["root_children"][0]["pid"] = 101
        with self.assertRaises(ValueError):
            self.observe()

    def test_server_geometric_child_answer_must_match_derived_fixed_route(self):
        actual = self.fake.child_at
        self.fake.child_at = lambda window, point: 999 if window == 56 else actual(window, point)
        with self.assertRaises(modal.ProofError) as raised:
            self.observe()
        self.assertEqual(raised.exception.reason, "INPUT_ROUTE_CHANGED")

    def test_signed_focus_proxy_observed_with_exact_ancestry(self):
        add_child(self.proof, _record(57, -1, -1, 1, 1, window_class=2))
        self.proof["focus_path"] = [56, 57]
        self.assertEqual(self.observe(FakeX(self.proof)), self.proof)

    def test_two_samples_share_one_total_deadline(self):
        deadlines = []
        def observation(x, pid, action, deadline):
            deadlines.append(deadline)
            return copy.deepcopy(self.proof)
        with patch.dict(modal.os.environ, {"DISPLAY": ":100"}, clear=True), \
             patch.object(modal, "_X11", return_value=self.fake), \
             patch.object(modal, "_observation", side_effect=observation), \
             patch.object(modal.time, "monotonic", side_effect=[10, 12]), self.assertRaises(ValueError):
            modal.observe(100, self.proof["action"])
        self.assertEqual(deadlines, [12, 12])
        self.assertTrue(self.fake.closed)

    def test_invalid_display_pid_and_action_rejected_before_loading_xlib(self):
        for display in ("localhost:100", ":100.0", ":12345", "", ":10;command"):
            with patch.dict(modal.os.environ, {"DISPLAY": display}, clear=True), \
                 patch.object(modal, "_X11") as loader, self.assertRaises(ValueError):
                modal.observe(100, self.proof["action"])
            loader.assert_not_called()
        for pid in (True, 0, -1, 2**31, "100"):
            with patch.object(modal, "_X11") as loader, self.assertRaises(ValueError):
                modal.observe(pid, self.proof["action"])
            loader.assert_not_called()

    def test_x_error_cancellation_and_library_failure_never_yield_proof(self):
        for error in (modal.ProofError(), InterruptedError(), OSError("private failure")):
            with patch.dict(modal.os.environ, {"DISPLAY": ":100"}, clear=True), \
                 patch.object(modal, "_X11", side_effect=error), self.assertRaises((ValueError, InterruptedError)) as raised:
                modal.observe(100, self.proof["action"])
            self.assertNotIn("private", str(raised.exception))

    def test_descendant_traversal_stops_at_total_count_and_depth_caps(self):
        for deep in (False, True):
            proof = copy.deepcopy(self.proof)
            parent = 56
            for window in range(57, 122 if not deep else 66):
                add_child(proof, _record(window, -1, -1, 1, 1), parent)
                if deep:
                    parent = window
            fake = FakeX(proof)
            with self.subTest(deep=deep), self.assertRaises(ValueError):
                self.observe(fake)
            self.assertLessEqual(len(fake.tree_calls), modal.MAX_NODES + 1)

    def test_inconsistent_tree_root_or_parent_fails_closed(self):
        for bad_root, bad_parent in ((11, 10), (10, 99)):
            fake = FakeX(self.proof)
            original = fake.tree
            def tree(window, cap):
                root, parent, children = original(window, cap)
                return (bad_root, bad_parent, children) if window == 56 else (root, parent, children)
            fake.tree = tree
            with self.subTest(root=bad_root, parent=bad_parent), self.assertRaises(ValueError):
                self.observe(fake)


class XlibAdapterTests(unittest.TestCase):
    def adapter(self):
        # Allocate without CDLL: fixtures exercise calls and allocation handling only.
        adapter = modal._X11.__new__(modal._X11)
        adapter.connection, adapter.deadline, adapter.error = 123, 20, False
        adapter.x, adapter.ext = Mock(), Mock()
        adapter.sync = Mock()
        return adapter

    def test_shape_adapter_retrieves_actual_bounding_input_clip_rectangles(self):
        adapter = self.adapter()
        rectangles = (modal._Rectangle * 1)(modal._Rectangle(0, 0, 520, 235))
        seen = []
        def retrieve(connection, window, kind, count, order):
            seen.append(kind)
            count._obj.value = 1
            order._obj.value = 3
            return C.cast(rectangles, C.POINTER(modal._Rectangle))
        adapter.ext.XShapeGetRectangles.side_effect = retrieve
        with patch.object(modal.time, "monotonic", return_value=10):
            self.assertEqual(adapter.shape(56, 1), _shape(520, 235))
        self.assertEqual(seen, [0, 2, 1])
        self.assertEqual(adapter.x.XFree.call_count, 3)

    def test_inputonly_has_real_input_and_bounding_without_invalid_clip_request(self):
        adapter = self.adapter()
        rectangles = (modal._Rectangle * 1)(modal._Rectangle(0, 0, 1, 1))
        seen = []
        def retrieve(connection, window, kind, count, order):
            seen.append(kind)
            count._obj.value = 1
            order._obj.value = 3
            return C.cast(rectangles, C.POINTER(modal._Rectangle))
        adapter.ext.XShapeGetRectangles.side_effect = retrieve
        with patch.object(modal.time, "monotonic", return_value=10):
            self.assertEqual(adapter.shape(57, 2), _shape(1, 1, window_class=2))
        self.assertEqual(seen, [0, 2])

    def test_empty_or_multiple_rectangles_rejected_before_pointer_read_and_freed(self):
        for number in (0, 2, 1000000, -1):
            adapter = self.adapter()
            def retrieve(connection, window, kind, count, order):
                count._obj.value = number
                return C.cast(C.c_void_p(1), C.POINTER(modal._Rectangle))
            adapter.ext.XShapeGetRectangles.side_effect = retrieve
            with patch.object(modal.time, "monotonic", return_value=10), self.assertRaises(ValueError):
                adapter.shape(56, 1)
            adapter.x.XFree.assert_called_once()

    def test_oversized_tree_refused_before_pointer_read_and_freed(self):
        adapter = self.adapter()
        def query(connection, window, root, parent, children, count):
            count._obj.value = 33
            C.cast(children, C.POINTER(C.POINTER(C.c_ulong)))[0] = C.cast(C.c_void_p(1), C.POINTER(C.c_ulong))
            return 1
        adapter.x.XQueryTree.side_effect = query
        with patch.object(modal.time, "monotonic", return_value=10), self.assertRaises(ValueError):
            adapter.tree(10, 32)
        adapter.x.XFree.assert_called_once()

    def test_sync_checks_error_and_same_deadline(self):
        adapter = self.adapter()
        del adapter.sync
        adapter.error = True
        with patch.object(modal.time, "monotonic", return_value=10), self.assertRaises(ValueError):
            adapter.sync()
        adapter.error = False
        with patch.object(modal.time, "monotonic", side_effect=[19.9, 20]), self.assertRaises(ValueError):
            adapter.sync()

    def test_property_absence_is_explicit_and_malformed_or_truncated_metadata_rejected(self):
        for kind in ("absent", "oversized", "wrong_format", "wrong_type", "multiple_pid"):
            adapter = self.adapter()
            adapter.x.XInternAtom.return_value = 7
            storage = (C.c_ulong * 2)(100, 100)
            def property_reply(connection, window, atom, offset, length, delete, requested_type,
                               actual, fmt, count, remaining, data):
                actual._obj.value = 0 if kind == "absent" else 7
                fmt._obj.value = 0 if kind == "absent" else 32
                count._obj.value = 0 if kind == "absent" else 1
                remaining._obj.value = 4 if kind == "oversized" else 0
                data._obj.value = C.cast(storage, C.c_void_p).value
                if kind == "wrong_format":
                    fmt._obj.value = 8
                if kind == "wrong_type":
                    actual._obj.value = 8
                if kind == "multiple_pid":
                    count._obj.value = 2
                self.assertEqual(length, 256)
                self.assertFalse(delete)
                return 0
            adapter.x.XGetWindowProperty.side_effect = property_reply
            with self.subTest(kind=kind), patch.object(modal.time, "monotonic", return_value=10):
                if kind == "absent":
                    self.assertIsNone(adapter.property(56, b"_NET_WM_PID", 32, b"CARDINAL"))
                else:
                    with self.assertRaises(ValueError):
                        adapter.property(56, b"_NET_WM_PID", 32, b"CARDINAL")
            adapter.x.XFree.assert_called_once()


if __name__ == "__main__":
    unittest.main()
