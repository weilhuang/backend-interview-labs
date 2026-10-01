package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class LabTest {
  @Test
  void 提交成功但响应丢失仍是未知() {
    var result =
        Lab.simulate(
            List.of(
                new Lab.Scheduled(0, Lab.Event.SEND),
                new Lab.Scheduled(2, Lab.Event.COMMIT),
                new Lab.Scheduled(5, Lab.Event.TIMEOUT)));
    assertEquals(Lab.Knowledge.UNKNOWN, result.caller());
    assertEquals(1, result.committedWrites());
  }

  @Test
  void 延迟响应不能复活已经结束的调用() {
    var result =
        Lab.simulate(
            List.of(
                new Lab.Scheduled(0, Lab.Event.SEND),
                new Lab.Scheduled(3, Lab.Event.TIMEOUT),
                new Lab.Scheduled(9, Lab.Event.REPLY)));
    assertEquals(Lab.Knowledge.UNKNOWN, result.caller());
  }

  @Test
  void 相同未知状态可对应不同服务端事实() {
    for (int writes : List.of(0, 1)) {
      var events = new java.util.ArrayList<Lab.Scheduled>();
      events.add(new Lab.Scheduled(0, Lab.Event.SEND));
      if (writes == 1) events.add(new Lab.Scheduled(1, Lab.Event.COMMIT));
      events.add(new Lab.Scheduled(2, Lab.Event.DISCONNECT));
      var result = Lab.simulate(events);
      assertEquals(Lab.Knowledge.UNKNOWN, result.caller());
      assertEquals(writes, result.committedWrites());
    }
  }

  @Test
  void 预算预留和零边界() {
    assertEquals(
        Duration.ofMillis(70),
        Lab.downstreamBudget(Duration.ofMillis(100), Duration.ofMillis(30), Duration.ofMillis(80)));
    assertEquals(
        Duration.ZERO,
        Lab.downstreamBudget(Duration.ofMillis(20), Duration.ofMillis(30), Duration.ofSeconds(1)));
    assertThrows(
        IllegalArgumentException.class,
        () -> Lab.downstreamBudget(Duration.ofSeconds(-1), Duration.ZERO, Duration.ZERO));
  }

  @Test
  void 盲目重发可能二次提交() {
    var result =
        Lab.simulate(
            List.of(
                new Lab.Scheduled(0, Lab.Event.SEND),
                new Lab.Scheduled(1, Lab.Event.COMMIT),
                new Lab.Scheduled(2, Lab.Event.TIMEOUT),
                new Lab.Scheduled(3, Lab.Event.SEND),
                new Lab.Scheduled(4, Lab.Event.COMMIT),
                new Lab.Scheduled(5, Lab.Event.REPLY)));
    assertEquals(2, result.committedWrites());
    assertEquals(Lab.Knowledge.SUCCEEDED, result.caller());
    assertThrows(IllegalArgumentException.class,
        () -> Lab.simulate(List.of(new Lab.Scheduled(-1, Lab.Event.SEND))));
  }
}
