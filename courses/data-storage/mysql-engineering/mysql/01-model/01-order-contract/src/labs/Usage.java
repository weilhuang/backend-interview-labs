package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println("已支付总分=" + OrderQueries.paidTotal(c, 7));
            System.out.println("销售数量=" + OrderQueries.quantities(c, 7));
        }
    }
}
