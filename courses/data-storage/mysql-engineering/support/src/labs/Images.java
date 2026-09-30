package labs;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/** 唯一版本清单读取器：导出课程可通过 LAB_REPO_ROOT 指向完整仓库。 */
public final class Images {
    private Images() {}

    public static String mysql() {
        String explicit = System.getenv("LAB_REPO_ROOT");
        Path p =
                Path.of(explicit == null ? System.getProperty("course.root", ".") : explicit)
                        .toAbsolutePath();
        while (p != null) {
            Path ledger = p.resolve("infra/versions.env");
            if (Files.isRegularFile(ledger))
                try (InputStream in = Files.newInputStream(ledger)) {
                    Properties values = new Properties();
                    values.load(in);
                    String image = values.getProperty("MYSQL_IMAGE");
                    if (image == null || image.isBlank()) throw new IOException("缺少 MYSQL_IMAGE");
                    return image;
                } catch (IOException e) {
                    throw new IllegalStateException("读取唯一镜像台账失败", e);
                }
            p = p.getParent();
        }
        throw new IllegalStateException("未找到 infra/versions.env，请设置 LAB_REPO_ROOT 为完整仓库根目录");
    }
}
