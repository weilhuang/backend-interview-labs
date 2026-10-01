package labs.messaging;

import org.apache.rocketmq.client.apis.message.Message;

import java.nio.charset.StandardCharsets;

public final class Lab {
    public enum OrderState {
        UNPAID,
        PAID,
        CANCELLED
    }

    public static Message ordered(String topic, Event event) {
        // 学习区开始
        return RocketClient.PROVIDER
                .newMessageBuilder()
                .setTopic(topic)
                .setKeys(event.id())
                .setMessageGroup(event.order())
                .setBody(event.encode().getBytes(StandardCharsets.UTF_8))
                .build();
        // 学习区结束
    }

    public static Message delayed(String topic, Event event, long deliveryTimestamp) {
        return RocketClient.PROVIDER
                .newMessageBuilder()
                .setTopic(topic)
                .setKeys(event.id())
                .setDeliveryTimestamp(deliveryTimestamp)
                .setBody(event.encode().getBytes(StandardCharsets.UTF_8))
                .build();
    }

    /** 迟到的超时事件不得把已支付订单改成取消；生产环境使用数据库条件更新。 */
    public static OrderState cancelIfUnpaid(OrderState state) {
        return state == OrderState.UNPAID ? OrderState.CANCELLED : state;
    }
}
