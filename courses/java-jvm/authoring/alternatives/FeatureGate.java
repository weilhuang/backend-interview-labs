package labs.jvm;

import java.util.*;

public final class FeatureGate {
    public enum State {
        FINAL,
        PREVIEW,
        INCUBATOR,
        REMOVED
    }

    public record Feature(
            String name, int firstRelease, int targetRelease, State state, String module) {
        public Feature {
            Objects.requireNonNull(name);
            Objects.requireNonNull(state);
            if (firstRelease < 1 || targetRelease < firstRelease)
                throw new IllegalArgumentException("版本区间非法");
        }
    }

    private FeatureGate() {}

    public static List<String> compileFlags(Feature feature, int compilerRelease) {
        // 作答开始
        Objects.requireNonNull(feature);
        if (compilerRelease != feature.targetRelease())
            throw new IllegalArgumentException("必须使用目标版本编译器复核");
        if (feature.state() == State.REMOVED) throw new IllegalStateException("已移除，不能靠编译开关恢复");
        List<String> flags =
                new ArrayList<>(List.of("--release", Integer.toString(compilerRelease)));
        switch (feature.state()) {
            case PREVIEW -> flags.add("--enable-preview");
            case INCUBATOR -> {
                flags.add("--add-modules");
                flags.add(Objects.requireNonNull(feature.module()));
            }
            case FINAL -> {}
            case REMOVED -> throw new IllegalStateException("已移除");
        }
        return List.copyOf(flags);
        // 作答结束
    }

    public static List<Feature> jdk25Matrix() {
        return List.of(
                new Feature("record patterns", 19, 25, State.FINAL, null),
                new Feature("module imports", 23, 25, State.FINAL, null),
                new Feature("compact source files", 21, 25, State.FINAL, null),
                new Feature("scoped values", 20, 25, State.FINAL, null),
                new Feature("structured concurrency", 19, 25, State.PREVIEW, null),
                new Feature("primitive patterns", 23, 25, State.PREVIEW, null),
                new Feature("vector API", 16, 25, State.INCUBATOR, "jdk.incubator.vector"),
                new Feature("32-bit x86 port", 1, 25, State.REMOVED, null));
    }
}
