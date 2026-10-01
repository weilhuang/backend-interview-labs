import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

@Timeout(5)
class FeatureGateTest {
    @Test
    void finalDoesNotEnablePreview() {
        var feature = new FeatureGate.Feature("正式", 21, 25, FeatureGate.State.FINAL, null);
        assertEquals(java.util.List.of("--release", "25"), FeatureGate.compileFlags(feature, 25));
        assertThrows(IllegalArgumentException.class, () -> FeatureGate.compileFlags(feature, 21));
    }

    @Test
    void previewAndIncubatorAreDifferent() {
        var preview = new FeatureGate.Feature("预览", 21, 25, FeatureGate.State.PREVIEW, null);
        assertEquals(
                java.util.List.of("--release", "25", "--enable-preview"),
                FeatureGate.compileFlags(preview, 25));
        var incubator =
                new FeatureGate.Feature(
                        "孵化", 16, 25, FeatureGate.State.INCUBATOR, "jdk.incubator.vector");
        assertEquals(
                java.util.List.of("--release", "25", "--add-modules", "jdk.incubator.vector"),
                FeatureGate.compileFlags(incubator, 25));
    }

    @Test
    void removedAndMetadata() {
        var removed = new FeatureGate.Feature("移除", 1, 25, FeatureGate.State.REMOVED, null);
        assertThrows(IllegalStateException.class, () -> FeatureGate.compileFlags(removed, 25));
        assertThrows(
                IllegalArgumentException.class,
                () -> new FeatureGate.Feature("错误", 26, 25, FeatureGate.State.FINAL, null));
        assertEquals(8, FeatureGate.jdk25Matrix().size(), "这是版本快照完整性检查，不能证明官方状态正确");
    }
}
