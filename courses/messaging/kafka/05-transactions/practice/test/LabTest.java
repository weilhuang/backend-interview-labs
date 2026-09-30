import static org.junit.jupiter.api.Assertions.*;

import labs.messaging.Lab;

import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;

class LabTest {
    @Test
    void 提交与中止调用合同() throws Exception {
        for (boolean abort : new boolean[] {false, true}) {
            try (var producer =
                            new MockProducer<String, String>(
                                    true, new StringSerializer(), new StringSerializer());
                    var consumer = new MockConsumer<String, String>(OffsetResetStrategy.EARLIEST)) {
                producer.initTransactions();
                Lab.transform(
                        producer,
                        consumer,
                        new ConsumerRecord<>("input", 0, 7, "o1", "order-1"),
                        "output",
                        abort);
                assertEquals(abort, producer.transactionAborted());
                assertEquals(!abort, producer.transactionCommitted());
                assertEquals(abort ? 0 : 1, producer.history().size());
                if (!abort) {
                    assertEquals("ORDER-1", producer.history().getFirst().value());
                    assertFalse(producer.consumerGroupOffsetsHistory().isEmpty());
                }
            }
        }
    }
}
