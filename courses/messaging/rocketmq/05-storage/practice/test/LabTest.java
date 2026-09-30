import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import labs.messaging.*;
import org.junit.jupiter.api.Test;

class LabTest {
  @Test
  void 模型不能混淆刷盘和复制() {
    assertTrue(Lab.risk(new Lab.Durability(false, 2)).contains("未刷盘"));
    assertTrue(Lab.risk(new Lab.Durability(true, 1)).contains("单机"));
    assertTrue(Lab.risk(new Lab.Durability(true, 2)).contains("故障域"));
    assertThrows(IllegalArgumentException.class, () -> Lab.risk(new Lab.Durability(true, 0)));
  }

  @Test
  void 重复恢复记录不能掩盖缺失消息() {
    Event e1 = new Event("e1", "o1", 1, 100);
    assertEquals(List.of("e2"), Lab.missing(Set.of("e1", "e2"), List.of(e1, e1)));
    assertTrue(Lab.missing(Set.of("e1"), List.of(e1)).isEmpty());
    assertEquals(List.of("a", "b"), Lab.missing(Set.of("b", "a"), List.of()));
  }

  @Test
  void 预分配容量不能冒充已写消息段() {
    String first = "/home/rocketmq/store/commitlog/00000000000000000000";
    String next = "/home/rocketmq/store/commitlog/00000000001073741824";
    String listing = next + "\n" + first + "\n";
    assertEquals(List.of(first), RocketRuntime.writtenCommitLogFiles(listing, 1889));
    assertEquals(List.of(first), RocketRuntime.writtenCommitLogFiles(listing, 1073741824L));
    assertEquals(List.of(first, next), RocketRuntime.writtenCommitLogFiles(listing, 1073741825L));
    assertThrows(
        IllegalArgumentException.class,
        () -> RocketRuntime.writtenCommitLogFiles(next + "\n", 1889));
  }

  @Test
  void 没有真实数据文件或已写位点必须失败() {
    String first = "/home/rocketmq/store/commitlog/00000000000000000000";
    assertThrows(
        IllegalArgumentException.class, () -> RocketRuntime.writtenCommitLogFiles(first, 0));
    assertThrows(
        IllegalArgumentException.class, () -> RocketRuntime.writtenCommitLogFiles(first, -1));
    for (String invalid :
        List.of("", "/tmp/00000000000000000000", first + ".bak", first + "\nwarning")) {
      assertThrows(
          IllegalArgumentException.class, () -> RocketRuntime.writtenCommitLogFiles(invalid, 1889));
    }
  }

  @Test
  void 管理输出必须包含唯一真实物理位点而非成功退出码() {
    String status = "commitLogMinOffset              : 0\ncommitLogMaxOffset              : 1889\n";
    assertEquals(1889, RocketAdminResult.commitLogMaxOffset(status));
    assertTrue(RocketAdminResult.succeeded("brokerStatus", 0, status, ""));
    assertFalse(RocketAdminResult.succeeded("brokerStatus", 1, status, ""));
    assertFalse(
        RocketAdminResult.succeeded("brokerStatus", 0, status, "java.lang.Exception: failed"));
    for (String invalid :
        List.of(
            "",
            "# commitLogMaxOffset: 1889",
            "maxOffset: 1889",
            "commitLogMaxOffset: -1",
            "commitLogMaxOffset: 9223372036854775808",
            status + status)) {
      assertFalse(RocketAdminResult.succeeded("brokerStatus", 0, invalid, ""));
      assertThrows(
          IllegalArgumentException.class, () -> RocketAdminResult.commitLogMaxOffset(invalid));
    }
  }
}
