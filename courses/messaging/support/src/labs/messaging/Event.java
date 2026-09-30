package labs.messaging;

/** 合成订单事件；不包含真实个人资料。 */
public record Event(String id, String order, long sequence, long cents) {
    public Event {
        if (id == null
                || id.isBlank()
                || order == null
                || order.isBlank()
                || id.contains("|")
                || order.contains("|")
                || sequence < 0
                || cents < 0) {
            throw new IllegalArgumentException("事件标识、订单标识和金额必须合法");
        }
    }

    public String encode() {
        return "1|" + id + "|" + order + "|" + sequence + "|" + cents;
    }

    public static Event decode(String text) {
        String[] fields = text.split("\\|", -1);
        if (fields.length != 5 || !fields[0].equals("1")) {
            throw new IllegalArgumentException("不支持的事件版本或字段数量");
        }
        return new Event(
                fields[1], fields[2], Long.parseLong(fields[3]), Long.parseLong(fields[4]));
    }
}
