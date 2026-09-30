package labs.capstone;

/** 金额和支付不在本实验内；库存单位只能是整数。 */
public final class Model {
    private Model() {}

    public record Command(String requestId, String sku, int quantity) {}

    public record Order(String requestId, String sku, int quantity, String status, long version) {}

    public record Event(
            String eventId,
            String requestId,
            String sku,
            int quantity,
            String status,
            long version) {
        public static Event of(Order order) {
            return new Event(
                    order.requestId() + ":" + order.version(),
                    order.requestId(),
                    order.sku(),
                    order.quantity(),
                    order.status(),
                    order.version());
        }
    }

    public record Stock(String sku, int initial, int available) {}

    public record Delivery(String eventId, String requestId, String status, long version) {}

    public static final class Conflict extends RuntimeException {
        public Conflict(String message) {
            super(message);
        }
    }

    public static final class Unknown extends RuntimeException {
        public Unknown(String message) {
            super(message);
        }
    }

    public enum Fault {
        NONE,
        AFTER_ORDER_COMMIT,
        AFTER_KAFKA_ACK,
        AFTER_INBOX_COMMIT,
        AFTER_RPC_ACK
    }
}
