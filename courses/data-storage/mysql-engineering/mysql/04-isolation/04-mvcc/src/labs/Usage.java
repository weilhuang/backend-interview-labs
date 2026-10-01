package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            try (java.sql.Connection other = Db.local()) {
                System.out.println(
                        IsolationLab.observe(
                                c, other, java.sql.Connection.TRANSACTION_REPEATABLE_READ));
            }
        }
    }
}
