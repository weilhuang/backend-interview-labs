package labs.distributed;

import java.util.concurrent.atomic.AtomicLong;

public final class Usage {
  public static void main(String[] args) throws Exception {
    var guard = new Lab.Guard(new AtomicLong()::get);
    for (int i = 0; i < 4; i++) {
      try {
        guard.call(
            () -> {
              throw new java.io.IOException("受控下游故障");
            });
      } catch (java.io.IOException expected) {
        System.out.println(expected.getMessage());
      }
    }
    System.out.println("真实熔断器状态：" + guard.breaker.getState());
    guard.breaker.transitionToHalfOpenState();
    guard.call(() -> "探测一成功");
    guard.call(() -> "探测二成功");
    System.out.println("恢复状态：" + guard.breaker.getState());
  }
}
