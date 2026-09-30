package labs.capstone;

import static labs.capstone.Model.*;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

import java.util.*;

class DeliveryTest {
    @Test
    void 发布确认必须先于标记() throws Exception {
        var calls = new ArrayList<String>();
        DeliveryFlow.publishOne(() -> calls.add("发送确认"), () -> calls.add("数据库标记"), Fault.NONE);
        assertEquals(List.of("发送确认", "数据库标记"), calls);
    }

    @Test
    void Kafka失败不得标记已发送() {
        var calls = new ArrayList<String>();
        assertThrows(
                Exception.class,
                () ->
                        DeliveryFlow.publishOne(
                                () -> {
                                    throw new Exception("网络断开");
                                },
                                () -> calls.add("标记"),
                                Fault.NONE));
        assertTrue(calls.isEmpty());
    }

    @Test
    void 发送确认后的崩溃保留重放窗口() {
        var calls = new ArrayList<String>();
        assertThrows(
                Unknown.class,
                () ->
                        DeliveryFlow.publishOne(
                                () -> calls.add("确认"),
                                () -> calls.add("标记"),
                                Fault.AFTER_KAFKA_ACK));
        assertEquals(List.of("确认"), calls);
    }

    @Test
    void RPC成功后才提交位点() throws Exception {
        var calls = new ArrayList<String>();
        DeliveryFlow.consumeOne(() -> calls.add("RPC"), () -> calls.add("提交"), Fault.NONE);
        assertEquals(List.of("RPC", "提交"), calls);
    }

    @Test
    void RPC超时不等于未提交但绝不推进位点() {
        var calls = new ArrayList<String>();
        assertThrows(
                Exception.class,
                () ->
                        DeliveryFlow.consumeOne(
                                () -> {
                                    throw new Exception("结果未知");
                                },
                                () -> calls.add("提交"),
                                Fault.NONE));
        assertTrue(calls.isEmpty());
    }

    @Test
    void RPC之后崩溃仍允许重复调用() {
        var calls = new ArrayList<String>();
        assertThrows(
                Unknown.class,
                () ->
                        DeliveryFlow.consumeOne(
                                () -> calls.add("RPC"),
                                () -> calls.add("提交"),
                                Fault.AFTER_RPC_ACK));
        assertEquals(List.of("RPC"), calls);
    }

    @Test
    void 协议往返保留身份与版本() {
        Event e = new Event("Case:2", "Case", "book", 3, "CANCELLED", 2);
        assertEquals(e, DeliveryRpc.from(DeliveryRpc.to(e)));
        assertEquals(false, Broker.consumer("x:1", "g").get("enable.auto.commit"));
        assertEquals("all", Broker.producer("x:1").get("acks"));
    }
}
