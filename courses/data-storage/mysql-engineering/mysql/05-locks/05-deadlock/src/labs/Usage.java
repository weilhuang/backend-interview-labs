package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            Db.transaction(
                    c,
                    tx -> {
                        LockLab.swapOne(tx, 101, 102);
                        return null;
                    });
            System.out.println("总库存=" + Db.scalar(c, "SELECT SUM(quantity) FROM c06_stock"));
        }
    }
}
