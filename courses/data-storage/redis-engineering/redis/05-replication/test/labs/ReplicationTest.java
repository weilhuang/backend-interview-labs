package labs;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ReplicationTest {
  @Test
  void parsesInfoWithoutAssumingLineOrdering() {
    var result = Replication.info("# Replication\r\nrole:slave\r\nmaster_link_status:up\r\n\r\n");
    assertEquals("slave", result.get("role"));
    assertEquals("up", result.get("master_link_status"));
  }

  @Test
  void ignoresSectionsAndRetainsColonInValues() {
    assertEquals("one:two", Replication.info("# x\nvalue:one:two\nnoise\n").get("value"));
  }
}
