import static org.junit.jupiter.api.Assertions.*;

import labs.PublicationLab;

import org.junit.jupiter.api.*;

import java.util.*;
import java.util.concurrent.*;

@Timeout(10)
class PublicationLabTest {
    @Test
    void publishedSnapshotDoesNotAliasCaller() {
        var routes = new ArrayList<>(List.of("/orders"));
        var lab = new PublicationLab();
        lab.publish(new PublicationLab.Snapshot(1, routes));
        routes.clear();
        assertEquals(List.of("/orders"), lab.current().routes(), "发布的数据不能被调用者继续修改");
        assertThrows(
                UnsupportedOperationException.class, () -> lab.current().routes().add("/admin"));
        assertThrows(NullPointerException.class, () -> lab.publish(null));
        assertThrows(
                IllegalArgumentException.class, () -> new PublicationLab.Snapshot(-1, List.of()));
    }

    @Test
    void publishedPairRemainsOneSnapshot() throws Exception {
        var lab = new PublicationLab();
        var entered = new CountDownLatch(1);
        try (var pool = Executors.newSingleThreadExecutor()) {
            Future<PublicationLab.Snapshot> read =
                    pool.submit(
                            () -> {
                                entered.countDown();
                                return lab.current();
                            });
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            var snapshot = read.get(2, TimeUnit.SECONDS);
            assertEquals(snapshot.version() == 0 ? List.of() : List.of("/v1"), snapshot.routes());
        }
        lab.publish(new PublicationLab.Snapshot(1, List.of("/v1")));
        assertEquals(1, lab.current().version());
    }

    @Test
    void eachAcceptedCallHasUniqueSequence() throws Exception {
        var lab = new PublicationLab();
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(4)) {
            var results = new ArrayList<Future<List<Integer>>>();
            for (int t = 0; t < 4; t++)
                results.add(
                        pool.submit(
                                () -> {
                                    start.await();
                                    var out = new ArrayList<Integer>();
                                    for (int i = 0; i < 100; i++) out.add(lab.accept());
                                    return out;
                                }));
            start.countDown();
            var seen = new HashSet<Integer>();
            for (var f : results) seen.addAll(f.get(3, TimeUnit.SECONDS));
            assertEquals(400, seen.size());
            assertEquals(400, lab.accepted());
            assertTrue(seen.contains(1));
            assertTrue(seen.contains(400));
        }
    }

    @Test
    void volatileDoesNotMakeReadModifyWriteAtomic() throws Exception {
        assertEquals(1, PublicationLab.forcedLostUpdate());
    }
}
