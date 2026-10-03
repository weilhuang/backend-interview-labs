"""Closed sampled-X fixtures; no display, JVM or input is used by these tests."""
import copy
import unittest
from unittest.mock import patch

from test_modal_window import FakeX, _record, add_child, modal, proof_fixture


class UnmappedRootGeometryTests(unittest.TestCase):
    def proof(self, **changes):
        proof = proof_fixture()
        proof["root_children"].append(_record(90, -100, -100, 10, 10,
                                               window_class=2, map_state=0, **changes))
        return proof

    def observe(self, proof, change=None):
        fake = FakeX(proof)
        original = fake.root
        def root():
            if fake.root_calls == 1 and change is not None:
                change(fake.proof)
            return original()
        fake.root = root
        with patch.dict(modal.os.environ, {"DISPLAY": ":100"}, clear=True), \
             patch.object(modal, "_X11", return_value=fake), \
             patch.object(modal.time, "monotonic", return_value=10):
            result = modal.observe(100, proof["action"])
        self.assertEqual(fake.root_calls, 2)
        self.assertTrue(fake.closed)
        return result

    def test_actual_r26_geometry_is_preserved_in_both_complete_samples(self):
        proof = self.proof()
        for action in modal.ACTIONS:
            with self.subTest(action=action):
                proof["action"] = action
                self.assertEqual(modal.validate(proof, action), proof)
                self.assertEqual(self.observe(proof), proof)
                self.assertEqual(proof["root_children"][-1]["x"], -100)
                self.assertEqual(proof["root_children"][-1]["map_state"], 0)

    def test_unmapped_root_signed_domain_and_extent_are_bounded(self):
        for klass in (1, 2):
            for x, y in ((-32768, -32768), (32767, 32767), (-1, 0), (0, -1)):
                with self.subTest(klass=klass, x=x, y=y):
                    proof = self.proof()
                    proof["root_children"][-1].update(window_class=klass, x=x, y=y)
                    self.assertEqual(self.observe(proof), proof)
        for field in ("x", "y"):
            for value in (-32769, 32768, True, False, 1.0, "-100", None):
                with self.subTest(field=field, value=value):
                    proof = self.proof()
                    proof["root_children"][-1][field] = value
                    with self.assertRaises(modal.ProofError):
                        modal.validate(proof, proof["action"])

    def test_map_state_is_strict_before_it_can_select_signed_domain(self):
        for state in (False, True, 0.0, "0", None, -1, 3):
            proof = self.proof()
            proof["root_children"][-1]["map_state"] = state
            with self.subTest(state=state), self.assertRaises(modal.ProofError) as caught:
                modal.validate(proof, proof["action"])
            self.assertEqual(caught.exception.call_site, "ATTR_MAP_STATE")

    def test_root_unviewable_is_still_rejected(self):
        proof = self.proof()
        proof["root_children"][-1].update(x=0, y=0, map_state=1)
        with self.assertRaises(modal.ProofError) as caught:
            modal.validate(proof, proof["action"])
        self.assertEqual(caught.exception.call_site, "ROOT_CHILD_MAP_STATE")

    def test_mapped_root_coordinates_and_extents_are_unchanged(self):
        for klass in (1, 2):
            for change in ({"x": -1}, {"y": -1}, {"x": 1280}, {"y": 900},
                           {"x": 1279, "width": 2}, {"y": 899, "height": 2}):
                proof = self.proof()
                proof["root_children"][-1].update(x=0, y=0, width=1, height=1,
                                                   window_class=klass, map_state=2)
                proof["root_children"][-1].update(change)
                with self.subTest(klass=klass, change=change), self.assertRaises(modal.ProofError):
                    modal.validate(proof, proof["action"])

    def test_unmapped_record_cannot_bypass_size_border_class_or_schema(self):
        for change in ({"width": 0}, {"width": 1281}, {"height": 0}, {"height": 901},
                       {"border": 1}, {"border": -1}, {"window_class": 3},
                       {"event_mask": 1 << 25}, {"pid": True}, {"extra": {"private": "never"}}):
            proof = self.proof()
            proof["root_children"][-1].update(change)
            with self.subTest(change=change), self.assertRaises(modal.ProofError):
                modal.validate(proof, proof["action"])

    def test_mapped_inputonly_overlap_still_rejects_even_away_from_target(self):
        for root in (True, False):
            proof = self.proof()
            if root:
                proof["root_children"][-1].update(x=850, y=500, map_state=2)
            else:
                add_child(proof, _record(91, 500, 200, 1, 1, window_class=2))
            with self.subTest(root=root), self.assertRaises(modal.ProofError) as caught:
                modal.validate(proof, proof["action"])
            self.assertEqual(caught.exception.call_site,
                             "ROOT_STACK_OVERLAP" if root else "INPUTONLY_INTERSECTION")

    def test_unmapped_overlapping_root_is_retained_and_mapping_it_rejects(self):
        proof = self.proof()
        proof["root_children"][-1].update(x=850, y=500)
        self.assertEqual(self.observe(proof), proof)
        proof["root_children"][-1]["map_state"] = 2
        with self.assertRaises(modal.ProofError) as caught:
            modal.validate(proof, proof["action"])
        self.assertEqual(caught.exception.call_site, "ROOT_STACK_OVERLAP")

    def test_every_unmapped_record_field_and_stack_stays_in_equality_binding(self):
        changes = (
            lambda p: p["root_children"][-1].__setitem__("x", -99),
            lambda p: p["root_children"][-1].__setitem__("pid", 123),
            lambda p: p["root_children"][-1].__setitem__("title_sha256", "a" * 64),
            lambda p: p["root_children"][-1].update(x=0, y=0, map_state=2),
            lambda p: p["root_children"].reverse(),
            lambda p: p["root_children"].pop(),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(modal.ProofError) as caught:
                self.observe(self.proof(), change)
            self.assertEqual(caught.exception.call_site, "OBSERVE_SAMPLES")

    def test_unmapped_root_and_unmapped_descendant_cannot_be_focus(self):
        proof = self.proof()
        proof["focus_path"] = [90]
        with self.assertRaises(modal.ProofError):
            self.observe(proof)
        proof = self.proof()
        add_child(proof, _record(91, -1, -1, 1, 1, window_class=2, map_state=0))
        proof["focus_path"] = [56, 91]
        with self.assertRaises(modal.ProofError) as caught:
            modal.validate(proof, proof["action"])
        self.assertEqual(caught.exception.call_site, "FOCUS_MAP_STATE")

    def test_signed_descendant_clipping_and_target_route_remain_strict(self):
        proof = self.proof()
        add_child(proof, _record(91, -1, -1, 1, 1, window_class=2))
        proof["focus_path"] = [56, 91]
        self.assertEqual(self.observe(proof), proof)
        proof["dialog_tree"][-1]["width"] = 2
        proof["dialog_tree"][-1]["height"] = 2
        for key in ("bounding", "input"):
            proof["dialog_tree"][-1]["shape"][key] = [0, 0, 2, 2]
        with self.assertRaises(modal.ProofError) as caught:
            modal.validate(proof, proof["action"])
        self.assertEqual(caught.exception.call_site, "INPUTONLY_INTERSECTION")


if __name__ == "__main__":
    unittest.main()
