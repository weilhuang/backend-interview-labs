package labs.distributed.capacity;

/** ID位布局练习；工作节点号的租约和重启持久化不由这个纯函数保证。 */
public final class IdLayout {
  public static long compose(long elapsedMillis, int worker, int sequence) {
    // 练习区开始
    if (elapsedMillis < 0
        || elapsedMillis >= (1L << 41)
        || worker < 0
        || worker >= 1024
        || sequence < 0
        || sequence >= 4096) throw new IllegalArgumentException("ID位字段越界");
    return (elapsedMillis << 22) | ((long) worker << 12) | sequence;
    // 练习区结束
  }
}
