package labs.distributed;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** 可控事件模型，只证明调用方知识状态，不模拟真实TCP或一致性协议。 */
public final class Lab {
  public enum Event {
    SEND,
    COMMIT,
    REPLY,
    TIMEOUT,
    DISCONNECT
  }

  public enum Knowledge {
    NOT_SENT,
    IN_FLIGHT,
    SUCCEEDED,
    UNKNOWN
  }

  public record Scheduled(long atMillis, Event event) {}

  public record Observation(Knowledge caller, int committedWrites, List<String> trace) {}

  public static Observation simulate(List<Scheduled> schedule) {
    Knowledge state = Knowledge.NOT_SENT;
    int committed = 0;
    long previous = -1;
    List<String> trace = new ArrayList<>();
    for (Scheduled scheduled :
        schedule.stream().sorted(Comparator.comparingLong(Scheduled::atMillis)).toList()) {
      if (scheduled.atMillis() < 0 || scheduled.atMillis() < previous) {
        throw new IllegalArgumentException("事件时间必须非负且单调");
      }
      previous = scheduled.atMillis();
      Event event = scheduled.event();
      // 练习区开始
      switch (event) {
        case SEND -> state = Knowledge.IN_FLIGHT;
        case COMMIT -> committed++;
        case REPLY -> {
          if (state == Knowledge.IN_FLIGHT) {
            state = Knowledge.SUCCEEDED;
          }
        }
        case TIMEOUT, DISCONNECT -> {
          if (state == Knowledge.IN_FLIGHT) {
            state = Knowledge.UNKNOWN;
          }
        }
      }
      // 练习区结束
      trace.add(scheduled.atMillis() + "毫秒 " + event + " 调用方=" + state + " 已提交=" + committed);
    }
    return new Observation(state, committed, List.copyOf(trace));
  }

  public static Duration downstreamBudget(Duration remaining, Duration localReserve, Duration cap) {
    // 练习区开始
    if (remaining.isNegative() || localReserve.isNegative() || cap.isNegative()) {
      throw new IllegalArgumentException("预算不能为负数");
    }
    Duration available = remaining.minus(localReserve);
    if (available.isZero() || available.isNegative()) {
      return Duration.ZERO;
    }
    return available.compareTo(cap) < 0 ? available : cap;
    // 练习区结束
  }
}
