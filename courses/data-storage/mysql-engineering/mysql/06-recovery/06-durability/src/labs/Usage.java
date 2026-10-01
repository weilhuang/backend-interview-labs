package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println(RecoveryLab.inspect(c));
            RecoveryLab.confirmed(c, 99);
            System.out.println(
                    "确认记录=" + Db.scalar(c, "SELECT COUNT(*) FROM c06_recovery WHERE id=99"));
        }
    }
}
