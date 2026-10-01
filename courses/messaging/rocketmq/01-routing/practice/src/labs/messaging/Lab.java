package labs.messaging;

import org.apache.rocketmq.client.apis.producer.Producer;
import org.apache.rocketmq.client.apis.producer.SendReceipt;

public final class Lab {
    public static SendReceipt publish(Producer producer, String topic, Event event)
            throws Exception {
        // 学习区开始
        return producer.send(RocketClient.message(topic, event));
        // 学习区结束
    }
}
