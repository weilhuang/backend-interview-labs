package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println(StockLab.reserve(Db::local, "usage-one", 101, 1));
            System.out.println(
                    "剩余=" + Db.scalar(c, "SELECT quantity FROM c06_stock WHERE sku=101"));
        }
    }
}
