package labs;

/** 调用前用 Schema.main 显式重置合成数据；密码从环境读取。 */
public final class Usage {
    public static void main(String[] args) throws Exception {
        try (java.sql.Connection c = Db.local()) {
            System.out.println("索引前=" + IndexLab.explain(c, false));
            IndexLab.addIndex(c);
            System.out.println("索引后=" + IndexLab.explain(c, true));
            System.out.println("结果=" + IndexLab.result(c));
        }
    }
}
