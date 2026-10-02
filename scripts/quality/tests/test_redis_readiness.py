"""Redis fixture boundary regressions; synthetic XML/static evidence, never Docker proof."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import academy_gate as gate


class RedisReadinessBoundaryTests(unittest.TestCase):
    fixture_error = "labs.support.RedisLab$FixtureReadinessException"

    def suite(self, failures):
        root = ET.Element("testsuite", tests=str(len(failures)), failures=str(len(failures)), errors="0")
        for index, (kind, detail) in enumerate(failures):
            case = ET.SubElement(root, "testcase", name=f"case{index}")
            ET.SubElement(case, "failure", type=kind).text = detail
        return root

    def inspect(self, failures):
        return gate.inspect_junit_failures(
            self.suite(failures), Path("TEST-labs.ReplicationIntegrationTest.xml"), "redis/05-replication")

    def test_readiness_timeout_is_explicit_infrastructure_failure(self):
        with self.assertRaisesRegex(gate.GateError, "infrastructure failure"):
            self.inspect([(self.fixture_error, "primary.crash后、promote前: connection/PING timeout")])

    def test_wrapped_readiness_timeout_cannot_borrow_todo(self):
        with self.assertRaisesRegex(gate.GateError, "infrastructure failure"):
            self.inspect([("java.lang.UnsupportedOperationException",
                "TODO\nSuppressed: " + self.fixture_error + ": readiness timeout")])

    def test_plain_handshake_timeout_remains_unclassified(self):
        with self.assertRaisesRegex(gate.GateError, "unclassified failure"):
            self.inspect([("redis.clients.jedis.exceptions.JedisConnectionException",
                "Caused by: java.net.SocketTimeoutException: Read timed out")])

    def test_other_testcase_todo_does_not_hide_handshake_timeout(self):
        with self.assertRaisesRegex(gate.GateError, "unclassified failure"):
            self.inspect([("java.lang.UnsupportedOperationException", "TODO"),
                ("redis.clients.jedis.exceptions.JedisConnectionException", "handshake timeout")])

    def test_actual_student_todo_remains_attributable(self):
        self.assertEqual(1, self.inspect([("java.lang.UnsupportedOperationException",
            "TODO：按中文步骤实现核心方法\n at labs.Replication.promoteIsolatedReplica(Replication.java:24)")]))

    def test_only_surviving_replica_uses_ready_connection_and_promote_runs_once(self):
        course = gate.REPO / "courses/data-storage/redis-engineering"
        test = (course / "redis/05-replication/test/labs/ReplicationIntegrationTest.java").read_text()
        self.assertEqual(1, test.count(".connectReady("))
        self.assertEqual(1, test.count("Replication.promoteIsolatedReplica(r)"))
        crash = test.index("primary.crash();")
        ready = test.index("replica.connectReady(")
        promote = test.index("Replication.promoteIsolatedReplica(r)")
        role = test.index('assertEquals("master", Replication.info(r.info("replication")).get("role")')
        writable = test.index('r.set(key, "提升后可写")')
        self.assertLess(crash, ready)
        self.assertLess(ready, promote)
        self.assertLess(promote, role)
        self.assertLess(role, writable)
        # Stopped primary still uses the original one-shot connection inside assertThrows.
        self.assertIn('try (var p = primary.connect()) { p.ping(); }', test[crash:ready])
        # role=slave after CONFIG SET replica-read-only no cannot satisfy independent role=master.

    def test_readiness_helper_does_not_call_student_code_or_extend_socket_timeouts(self):
        course = gate.REPO / "courses/data-storage/redis-engineering"
        support = (course / "support/src/labs/support/RedisLab.java").read_text()
        self.assertIn("new Jedis(container.getHost(), mappedPort, 500, 500)", support)
        self.assertIn("catch (JedisConnectionException unavailable)", support)
        self.assertNotIn("promoteIsolatedReplica", support)
        self.assertNotIn("replicaofNoOne", support)
        self.assertNotIn("configSet", support)


if __name__ == "__main__":
    unittest.main()
