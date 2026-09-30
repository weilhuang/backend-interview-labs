package labs.capstone;

/** 学习起点保持可编译；运行时明确指出尚未实现，不返回伪造业务数据。 */
public final class Exercise {
    private Exercise() {}

    public static <T> T unimplemented() {
        throw new UnsupportedOperationException("请实现本阶段学习区");
    }
}
