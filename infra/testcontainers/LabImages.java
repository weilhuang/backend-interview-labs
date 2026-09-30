package lab.support;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.Set;

/** 供后续课程测试源码集引用的共享读取器，不复制镜像版本，不依赖 Testcontainers 本身。 */
public final class LabImages {
    private static final Set<String> KEYS = Set.of(
            "MYSQL_IMAGE", "REDIS_IMAGE", "KAFKA_IMAGE", "JAVA_BUILD_IMAGE");
    private static final Properties VALUES = load();

    private LabImages() { }

    public static String image(String key) {
        if (!KEYS.contains(key)) {
            throw new IllegalArgumentException("未登记的共享镜像键：" + key);
        }
        return VALUES.getProperty(key);
    }

    private static Properties load() {
        Path directory = Path.of(System.getProperty("user.dir")).toAbsolutePath();
        while (directory != null) {
            Path manifest = directory.resolve("infra/versions.env");
            if (Files.isRegularFile(manifest)) {
                Properties result = new Properties();
                try (Reader reader = Files.newBufferedReader(manifest, StandardCharsets.UTF_8)) {
                    result.load(reader);
                } catch (IOException exception) {
                    throw new IllegalStateException("无法读取共享版本台账：" + manifest, exception);
                }
                if (!result.stringPropertyNames().equals(KEYS)) {
                    throw new IllegalStateException("共享版本台账的键不完整或包含未知键");
                }
                for (String key : KEYS) {
                    if (!result.getProperty(key).matches(
                            "[a-z0-9./-]+:\\d+\\.\\d+\\.\\d+[a-zA-Z0-9_.-]*(?:@sha256:[a-f0-9]{64})?")) {
                        throw new IllegalStateException("共享镜像必须锁定完整版本：" + key);
                    }
                }
                return result;
            }
            directory = directory.getParent();
        }
        throw new IllegalStateException("找不到 infra/versions.env；请从完整仓库或课程目录启动测试，不要复制版本常量");
    }
}
