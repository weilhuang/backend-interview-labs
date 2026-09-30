package labs.messaging;

import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerRecord;

import java.sql.Connection;
import java.util.concurrent.TimeUnit;

/** 数据库 outbox 发布器；确认后标记仍有重复窗口，必须由下游 inbox 去重。 */
public final class Lab {
    public static void enqueue(Inbox database, Event event) throws Exception {
        try (Connection c = database.connection()) {
            c.setAutoCommit(false);
            try (var business = c.prepareStatement("INSERT INTO source_orders VALUES (?, ?)");
                    var outbox =
                            c.prepareStatement(
                                    "INSERT INTO outbox(event_id,payload) VALUES (?,?)")) {
                business.setString(1, event.order());
                business.setLong(2, event.cents());
                business.executeUpdate();
                outbox.setString(1, event.id());
                outbox.setString(2, event.encode());
                outbox.executeUpdate();
                c.commit();
            } catch (Exception failure) {
                c.rollback();
                throw failure;
            }
        }
    }

    public static void publish(
            Inbox database, Producer<String, String> producer, String topic, FailurePoint failure)
            throws Exception {
        // 学习区开始
        try (Connection c = database.connection();
                var select =
                        c.prepareStatement(
                                "SELECT event_id,payload FROM outbox WHERE sent=FALSE ORDER BY"
                                    + " event_id");
                var rows = select.executeQuery()) {
            while (rows.next()) {
                Event event = Event.decode(rows.getString(2));
                producer.send(new ProducerRecord<>(topic, event.order(), event.encode()))
                        .get(15, TimeUnit.SECONDS);
                failure.hit(FailurePoint.AFTER_PUBLISH_BEFORE_MARK);
                try (var mark =
                        c.prepareStatement("UPDATE outbox SET sent=TRUE WHERE event_id=?")) {
                    mark.setString(1, event.id());
                    mark.executeUpdate();
                }
            }
        }
        // 学习区结束
    }

    public static void deadLetter(
            Producer<String, String> producer, String dlq, String original, String error)
            throws Exception {
        producer.send(new ProducerRecord<>(dlq, "解析失败", error + "|" + original))
                .get(15, TimeUnit.SECONDS);
    }
}
