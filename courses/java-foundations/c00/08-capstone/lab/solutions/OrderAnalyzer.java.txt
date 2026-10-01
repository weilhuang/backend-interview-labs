package labs.foundation;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class OrderAnalyzer {
    private OrderAnalyzer() {}

    public static String analyze(List<String> lines, Order.Status status) {
        // 作答开始
        Objects.requireNonNull(lines);
        Objects.requireNonNull(status);
        if (lines.size() > 10000) throw new IllegalArgumentException("最多10000行");
        Map<String, Order> unique = new LinkedHashMap<>();
        for (int i = 0; i < lines.size(); i++) {
            Order order = OrderCodec.parse(lines.get(i), i + 1);
            unique.putIfAbsent(order.id(), order);
        }
        Map<String, Long> totals = new TreeMap<>();
        Map<String, Integer> count = new TreeMap<>();
        for (Order order : unique.values())
            if (order.status() == status) {
                totals.merge(order.customer(), order.cents(), Math::addExact);
                count.merge(order.customer(), 1, Integer::sum);
            }
        StringBuilder output = new StringBuilder("客户|总分|笔数\n");
        for (String customer : totals.keySet())
            output.append(customer)
                    .append('|')
                    .append(totals.get(customer))
                    .append('|')
                    .append(count.get(customer))
                    .append('\n');
        return output.toString();
        // 作答结束
    }

    public static int run(String[] args, PrintStream out, PrintStream error) {
        if (args.length != 2) {
            error.println("用法：文件路径 PAID或PENDING；只使用你创建的合成输入");
            return 2;
        }
        try {
            Order.Status status = Order.Status.valueOf(args[1]);
            Path input = Path.of(args[0]);
            if (Files.size(input) > 1024 * 1024) throw new IOException("文件超过1MiB");
            out.print(analyze(Files.readAllLines(input, StandardCharsets.UTF_8), status));
            return 0;
        } catch (IOException e) {
            error.println("文件错误：" + e.getMessage());
            return 3;
        } catch (IllegalArgumentException | ArithmeticException e) {
            error.println("输入错误：" + e.getMessage());
            return 4;
        }
    }

    public static void main(String[] args) {
        System.exit(run(args, System.out, System.err));
    }
}
