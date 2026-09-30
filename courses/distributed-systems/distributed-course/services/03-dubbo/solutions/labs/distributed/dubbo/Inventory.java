package labs.distributed.dubbo;

/** 两种RPC共享业务语义，线协议和错误呈现仍需分别演进。 */
public interface Inventory {
  String quote(String sku);

  int reserve(String key, String sku, int quantity);
}
