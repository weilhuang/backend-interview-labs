package labs.messaging;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

/** 所有实验镜像只从仓库共享台账读取。 */
public final class Images {
    private Images() {}

    public static String get(String key) {
        Path path = Path.of(System.getProperty("lab.versions", "../../infra/versions.env"));
        Properties versions = new Properties();
        try (var input = Files.newInputStream(path)) {
            versions.load(input);
        } catch (IOException failure) {
            throw new IllegalStateException("找不到共享镜像台账，请从课程根运行并检查 lab.versions", failure);
        }
        String value = versions.getProperty(key);
        if (value == null || value.isBlank() || value.contains(":latest")) {
            throw new IllegalArgumentException("镜像键缺失或未固定版本：" + key);
        }
        return value;
    }
}
