import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

@Timeout(5)
class AllocationWorkloadTest {
    @Test
    void exactResultAndBounds() {
        assertEquals(new AllocationWorkload.Result(17, 16, 8), AllocationWorkload.run(4, 4, 2));
        assertEquals(new AllocationWorkload.Result(0, 0, 0), AllocationWorkload.run(0, 10, 2));
        var r = AllocationWorkload.run(300, 128, 3);
        assertEquals(38400, r.allocatedBytes());
        assertEquals(384, r.peakPayloadBytes());
    }

    @Test
    void invalidInputs() {
        assertThrows(IllegalArgumentException.class, () -> AllocationWorkload.run(-1, 1, 1));
        assertThrows(IllegalArgumentException.class, () -> AllocationWorkload.run(4097, 1, 1));
        assertThrows(IllegalArgumentException.class, () -> AllocationWorkload.run(1, 0, 1));
        assertThrows(IllegalArgumentException.class, () -> AllocationWorkload.run(1, 65537, 1));
        assertThrows(IllegalArgumentException.class, () -> AllocationWorkload.run(1, 1, 9));
    }

    @Test
    void fixedSeedOracle() {
        var random = new java.util.Random(304);
        for (int t = 0; t < 40; t++) {
            int n = random.nextInt(500),
                    size = 1 + random.nextInt(100),
                    live = 1 + random.nextInt(8);
            long expected = 0;
            for (int i = 0; i < n; i++) expected += 2 * (i % 127);
            for (int i = Math.max(0, n - live); i < n; i++) expected += i % 127;
            assertEquals(
                    expected, AllocationWorkload.run(n, size, live).checksum(), "固定种子结果不依赖GC选择");
        }
    }
}
