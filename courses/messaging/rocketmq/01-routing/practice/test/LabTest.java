import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.*;

import org.apache.rocketmq.client.apis.message.Message;
import org.apache.rocketmq.client.apis.producer.Producer;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicReference;

class LabTest {
    @Test
    void 键和标签与事件契约一致() throws Exception {
        Event event = new Event("e1", "o1", 1, 100);
        AtomicReference<Message> sent = new AtomicReference<>();
        // 测试替身仅记录调用，不能替代真实BrokerTest的确认和投递断言。
        Producer producer =
                (Producer)
                        Proxy.newProxyInstance(
                                Producer.class.getClassLoader(),
                                new Class<?>[] {Producer.class},
                                (proxy, method, arguments) -> {
                                    if (method.getName().equals("send"))
                                        sent.set((Message) arguments[0]);
                                    return null;
                                });
        Lab.publish(producer, "topic", event);
        Message message = sent.get();
        assertNotNull(message);
        assertEquals(java.util.List.of("e1"), java.util.List.copyOf(message.getKeys()));
        assertEquals("order", message.getTag().orElseThrow());
        assertEquals("topic", message.getTopic());
    }

    @Test
    void 管理命令打印异常却退出零仍应判失败() {
        assertFalse(
                RocketAdminResult.succeeded(
                        "updateTopic", 0, "", "org.example.SubCommandException: command failed"));
        assertFalse(
                RocketAdminResult.succeeded(
                        "topicStatus", 0, "#Broker Name #QID #Min Offset #Max Offset", ""));
        assertFalse(
                RocketAdminResult.succeeded(
                        "printMsg",
                        0,
                        "minOffset=0, maxOffset=1\n",
                        "org.example.MQClientException: 读取失败"));
        assertTrue(
                RocketAdminResult.succeeded(
                        "updateTopic", 0, "create topic to 127.0.0.1:10911 success.", ""));
        assertTrue(
                RocketAdminResult.succeeded(
                        "updateSubGroup",
                        0,
                        "create subscription group to 127.0.0.1:10911 success.",
                        ""));
        assertTrue(
                RocketAdminResult.succeeded("topicStatus", 0, "broker-a 0 0 1 2026-09-30\n", ""));
        assertTrue(
                RocketAdminResult.succeeded(
                        "printMsg", 0, "minOffset=0, maxOffset=0, MessageQueue\n", ""));
    }
}
