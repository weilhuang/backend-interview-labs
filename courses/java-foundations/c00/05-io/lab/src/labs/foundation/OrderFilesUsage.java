package labs.foundation;

public final class OrderFilesUsage {
    public static void main(String[] args) throws Exception {
        var out = new java.io.StringWriter();
        OrderFiles.summarize(new java.io.StringReader("A|张三|120|PAID\nB|张三|80|PAID"), out);
        System.out.print("报告：\n" + out);
    }
}
