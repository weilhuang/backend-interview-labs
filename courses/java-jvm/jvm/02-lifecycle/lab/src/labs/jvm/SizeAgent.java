package labs.jvm;

import java.lang.instrument.Instrumentation;

/** 仅供本课程自建隔离进程使用的浅大小观察探针。 */
public final class SizeAgent {
    private static Instrumentation instrumentation;

    public static void premain(String arguments, Instrumentation instance) {
        instrumentation = instance;
    }

    public static long shallowSize(Object value) {
        if (instrumentation == null) {
            throw new IllegalStateException("请通过课程layout脚本启动，不使用动态附加");
        }
        return instrumentation.getObjectSize(value);
    }
}
