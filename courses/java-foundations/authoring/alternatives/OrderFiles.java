package labs.foundation;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class OrderFiles {
    private OrderFiles() {}

    public static void summarize(Reader input, Writer output) throws IOException {
        // 作答开始
        try (BufferedReader reader = new BufferedReader(Objects.requireNonNull(input));
                Writer writer = Objects.requireNonNull(output)) {
            List<String> lines = new ArrayList<>();
            String line;
            while ((line = reader.readLine()) != null) {
                if (lines.size() == 10000) throw new IOException("文件超过10000行");
                lines.add(line);
            }
            Map<String, Long> totals = new TreeMap<>();
            for (Order o : OrderCodec.parseBatch(lines))
                if (o.status() == Order.Status.PAID)
                    totals.merge(o.customer(), o.cents(), Math::addExact);
            for (String customer : totals.keySet())
                writer.write(customer + "|" + totals.get(customer) + "\n");
        }
        // 作答结束
    }

    public static void report(Path directory, String inputName, String outputName)
            throws IOException {
        Path in = child(directory, inputName), out = child(directory, outputName);
        if (in.equals(out)) throw new IllegalArgumentException("输入输出不得相同");
        try (Reader input = Files.newBufferedReader(in, StandardCharsets.UTF_8)) {
            summarize(input, Files.newBufferedWriter(out, StandardCharsets.UTF_8));
        }
    }

    private static Path child(Path directory, String name) {
        Objects.requireNonNull(directory);
        Objects.requireNonNull(name);
        if (!name.matches("[A-Za-z0-9._-]+") || name.equals(".") || name.equals(".."))
            throw new IllegalArgumentException("只允许沙箱内直接文件名");
        Path path = directory.resolve(name);
        if (Files.isSymbolicLink(path)) throw new IllegalArgumentException("实验不跟随符号链接");
        return path;
    }
}
