package labs.distributed.outbox;

public record Event(String id, String sku, long version, int available) {
  public Event {
    if (id == null
        || !id.matches("[a-zA-Z0-9_-]{1,64}")
        || sku == null
        || !sku.matches("[a-zA-Z0-9_-]{1,40}")
        || version < 1
        || version > 9_007_199_254_740_991L
        || available < 0) throw new IllegalArgumentException("事件字段非法");
  }

  public String encode() {
    return id + "|" + sku + "|" + version + "|" + available;
  }

  public static Event decode(String value) {
    if (value == null || value.length() > 200) throw new IllegalArgumentException("事件过长或为空");
    String[] fields = value.split("\\|", -1);
    if (fields.length != 4) throw new IllegalArgumentException("事件字段数量不符");
    return new Event(fields[0], fields[1], Long.parseLong(fields[2]), Integer.parseInt(fields[3]));
  }
}
