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
        assertFalse(
                RocketAdminResult.succeeded("clusterList", 0, "#Cluster Name #Broker Name", ""));
        assertFalse(
                RocketAdminResult.succeeded(
                        "clusterList", 137, "LabCluster broker-a 0 127.0.0.1:10911 V5_3_2", ""));
        assertTrue(
                RocketAdminResult.succeeded(
                        "clusterList", 0, "LabCluster broker-a 0 127.0.0.1:10911 V5_3_2", ""));
    }

    @Test
    void 管理工具使用独立小堆且参数不拼入shell() {
        String[] command = RocketRuntime.adminCommand("updateSubGroup", "-g", "group name; false");
        assertEquals("sh", command[0]);
        assertEquals("-c", command[1]);
        assertTrue(command[2].contains("-Xmx128m"));
        assertTrue(command[2].contains("org.apache.rocketmq.tools.command.MQAdminStartup \"$@\""));
        assertFalse(command[2].contains("tools.sh"));
        assertFalse(command[2].contains("group name"));
        assertEquals("group name; false", command[6]);
        String startup = RocketRuntime.startupScript();
        assertTrue(startup.contains("ROCKETMQ_%s_EXIT=%s"));
        assertTrue(startup.contains("tail -n 40"));
        assertTrue(startup.contains("-Xmx128m"));
        assertTrue(startup.contains("useEndpointPortFromRequest\":true"));
        assertTrue(startup.contains("timerWheelEnable=true\n"));
        // ProxyConfig独立读取namesrvAddr，不能只在Broker配置里设置。
        assertTrue(startup.contains("\"namesrvAddr\":\"127.0.0.1:9876\""));
    }

    @Test
    void 随机映射端口要求独立ClusterProxy且监督全部进程() {
        String startup = RocketRuntime.startupScript();
        assertFalse(startup.contains("--enable-proxy"));
        assertTrue(startup.contains("sh mqproxy -pm cluster -pc /tmp/lab-proxy.json"));
        assertTrue(startup.contains("\"proxyMode\":\"CLUSTER\""));
        assertTrue(startup.contains("-Xmx256m"));
        assertTrue(startup.contains("storePathCommitLog=/home/rocketmq/store/commitlog"));
        assertTrue(
                startup.contains("timeout -k 2 \"$remaining\" sh /tmp/lab-admin.sh clusterList"));
        assertTrue(startup.contains("registration_deadline="));
        assertTrue(startup.indexOf("ROCKETMQ_BROKER_REGISTERED") < startup.indexOf("sh mqproxy"));
        assertFalse(startup.contains("@@ADMIN_SCRIPT@@"));
        assertTrue(startup.contains("-g CID_DefaultHeartBeatSyncerTopic -d true"));
        assertTrue(
                startup.indexOf("-g CID_DefaultHeartBeatSyncerTopic")
                        < startup.indexOf("sh mqproxy"));
        for (String process : java.util.List.of("NAMESRV", "BROKER", "PROXY"))
            assertTrue(startup.contains("check_process " + process));
        String[] files = RocketRuntime.fileLogsCommand();
        assertEquals("sh", files[0]);
        assertEquals("-c", files[1]);
        assertTrue(files[2].contains("rocketmqlogs/proxy.log"));
        assertTrue(files[2].contains("tail -c 6000"));
    }

    @Test
    void 失败诊断只保留有界日志尾部() {
        assertEquals("short", RocketRuntime.tail("short", 20));
        assertTrue(RocketRuntime.tail("old".repeat(100) + "ROOT_CAUSE", 20).endsWith("ROOT_CAUSE"));
        assertTrue(RocketRuntime.tail("old".repeat(100) + "ROOT_CAUSE", 20).length() < 50);
    }
}
