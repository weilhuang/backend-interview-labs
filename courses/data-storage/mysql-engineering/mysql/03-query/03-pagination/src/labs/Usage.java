package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println(
                    "第一页之后="
                            + QueryLab.after(
                                    c,
                                    7,
                                    new QueryLab.Cursor(
                                            java.time.Instant.parse("2025-01-01T00:00:00Z"), 1),
                                    10));
        }
    }
}
