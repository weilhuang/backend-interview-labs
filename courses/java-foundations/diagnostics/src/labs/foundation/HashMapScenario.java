package labs.foundation;

import java.util.HashMap;

/** 只在合成Map上调试真实JDK分支，不访问业务进程。 */
public final class HashMapScenario {
    public static HashMap<HashMapRoutes.Key, Integer> target;
    public static int phase;

    public static void begin() {}

    public static void main(String[] args) {
        target = new HashMap<>(16);
        begin();
        for (int i = 0; i < 12; i++) {
            phase = i + 1;
            target.put(new HashMapRoutes.Key(i, (i % 2) * 64), i);
        }
        phase = 100;
        if (!HashMapRoutes.verifyLookups(target, 12)) {
            throw new AssertionError("树化后查找结果错误");
        }
        for (int i = 12; i < 60; i++) {
            phase = i + 1;
            target.put(new HashMapRoutes.Key(i, i + 1), i);
        }
        phase = 200;
        if (!HashMapRoutes.verifyLookups(target, 12)) {
            throw new AssertionError("拆分后查找结果错误");
        }
        System.out.println("真实HashMap场景结束，条目=" + target.size());
    }
}
