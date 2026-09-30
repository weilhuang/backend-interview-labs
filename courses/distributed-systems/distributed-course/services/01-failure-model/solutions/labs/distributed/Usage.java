package labs.distributed;

import java.util.List;

public final class Usage {
  public static void main(String[] args) {
    var result =
        Lab.simulate(
            List.of(
                new Lab.Scheduled(0, Lab.Event.SEND),
                new Lab.Scheduled(10, Lab.Event.COMMIT),
                new Lab.Scheduled(20, Lab.Event.TIMEOUT),
                new Lab.Scheduled(30, Lab.Event.REPLY)));
    result.trace().forEach(System.out::println);
    System.out.println("超时后必须查询业务结果，不能断言服务端回滚");
  }
}
