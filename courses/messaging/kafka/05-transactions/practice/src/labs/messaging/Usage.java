package labs.messaging;

/** 独立调用端：传入共享环境端点后发送并读取真实订单事件。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("用法：./gradlew :kafka-05-transactions:run -PappArgs=127.0.0.1:19092");
            System.out.println("无需外部服务的可见检查：./gradlew test；真实服务检查：./gradlew test -PwithDocker");
            return;
        }
        String topic = KafkaSupport.topic(args[0], 1);
        try (var producer = KafkaSupport.producer(args[0]);
                var consumer = KafkaSupport.consumer(args[0], "调用示例-" + topic, "read_committed")) {
            Event event = new Event("演示事件一", "演示订单一", 1, 100);
            producer.send(
                            new org.apache.kafka.clients.producer.ProducerRecord<>(
                                    topic, event.order(), event.encode()))
                    .get();
            consumer.subscribe(java.util.List.of(topic));
            var records = KafkaSupport.read(consumer, 1, java.time.Duration.ofSeconds(30));
            System.out.println("收到真实事件：" + Event.decode(records.getFirst().value()));
        }
    }
}
