package labs.jvm;

public final class MigrationReportUsage {
    public static void main(String[] args) {
        var order =
                new MigrationReport.Order(
                        "A",
                        300,
                        java.time.Instant.parse("2024-03-10T05:00:00Z"),
                        MigrationReport.Status.PAID);
        System.out.println(
                "纽约营业日总额="
                        + MigrationReport.total(
                                java.util.List.of(order),
                                java.time.LocalDate.of(2024, 3, 10),
                                java.time.ZoneId.of("America/New_York")));
        System.out.println(
                "缺失结果="
                        + MigrationReport.explain(
                                MigrationReport.outcome(java.util.List.of(order), "B")));
    }
}
