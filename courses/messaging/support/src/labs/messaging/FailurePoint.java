package labs.messaging;

/** 确定性故障屏障：注入异常模拟此刻进程停止，不伪装成真正操作系统崩溃。 */
public enum FailurePoint {
    NONE,
    BEFORE_EFFECT,
    AFTER_EFFECT_BEFORE_OFFSET,
    AFTER_PUBLISH_BEFORE_MARK;

    public void hit(FailurePoint point) {
        if (this == point) throw new SimulatedCrash(point.name());
    }

    public static final class SimulatedCrash extends RuntimeException {
        public SimulatedCrash(String point) {
            super("已到达故障屏障：" + point);
        }
    }
}
