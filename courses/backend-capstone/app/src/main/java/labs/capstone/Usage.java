package labs.capstone;

import static labs.capstone.Model.*;

import java.util.List;

/** 无外部依赖的完整领域调用；真实HTTP/MQ/RPC调用见脚本与集成测试。 */
public final class Usage {
    public static void main(String[] args) {
        Command command = new Command("demo-001", "book", 2);
        OrderRules.validate(command);
        Order order =
                new Order(command.requestId(), command.sku(), command.quantity(), "RESERVED", 1);
        System.out.println("重复请求返回原订单：" + OrderRules.sameRequest(order, command));
        System.out.println("消息事件：" + Json.write(Event.of(order)));
        System.out.println(
                "Kafka故障时的降级决策：" + RecoveryPolicy.decide(true, true, false, true, 1, 1000));
        System.out.println(
                "审计发现："
                        + Audit.inspect(
                                List.of(new Stock("book", 20, 18)), List.of(order), List.of()));
    }
}
