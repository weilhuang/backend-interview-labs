import static org.junit.jupiter.api.Assertions.*;

import labs.jvm.*;

import org.junit.jupiter.api.*;

@Timeout(5)
class MigrationReportTest {
    private MigrationReport.Order order(String id, long cents, String instant) {
        return new MigrationReport.Order(
                id, cents, java.time.Instant.parse(instant), MigrationReport.Status.PAID);
    }

    @Test
    void daylightSavingAndEndExclusive() {
        var day = java.time.LocalDate.of(2024, 3, 10);
        var zone = java.time.ZoneId.of("America/New_York");
        var orders =
                java.util.List.of(
                        order("前", 100, "2024-03-10T04:59:59Z"),
                        order("起", 10, "2024-03-10T05:00:00Z"),
                        order("末", 20, "2024-03-11T03:59:59Z"),
                        order("后", 200, "2024-03-11T04:00:00Z"));
        assertEquals(30, MigrationReport.total(orders, day, zone), "夏令日为23小时，不能把一天写死86400秒");
    }

    @Test
    void overlapDayAndFilters() {
        var orders =
                java.util.List.of(
                        order("a", 2, "2024-11-03T05:30:00Z"),
                        order("b", 3, "2024-11-03T06:30:00Z"),
                        new MigrationReport.Order(
                                "c",
                                9,
                                java.time.Instant.parse("2024-11-03T06:30:00Z"),
                                MigrationReport.Status.PENDING));
        assertEquals(
                5,
                MigrationReport.total(
                        orders,
                        java.time.LocalDate.of(2024, 11, 3),
                        java.time.ZoneId.of("America/New_York")));
        assertTrue(MigrationReport.find(orders, "不存在").isEmpty());
        assertEquals("a", MigrationReport.explain(MigrationReport.outcome(orders, "a")));
        assertEquals("不存在未找到", MigrationReport.explain(MigrationReport.outcome(orders, "不存在")));
        assertEquals("待付款", MigrationReport.label(MigrationReport.Status.PENDING));
    }

    @Test
    void emptyOverflowAndInvalid() {
        var day = java.time.LocalDate.of(2024, 1, 1);
        var zone = java.time.ZoneOffset.UTC;
        assertEquals(0, MigrationReport.total(java.util.List.of(), day, zone));
        assertThrows(
                ArithmeticException.class,
                () ->
                        MigrationReport.total(
                                java.util.List.of(
                                        order("a", Long.MAX_VALUE, "2024-01-01T00:00:00Z"),
                                        order("b", 1, "2024-01-01T00:00:00Z")),
                                day,
                                zone));
        assertThrows(IllegalArgumentException.class, () -> order("x", -1, "2024-01-01T00:00:00Z"));
    }
}
