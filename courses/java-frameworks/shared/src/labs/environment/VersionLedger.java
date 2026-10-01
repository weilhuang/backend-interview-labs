package labs.environment;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Properties;

/** 自动生成的镜像台账读取器；版本值只能由仓库 infra/versions.env 生成。 */
public final class VersionLedger {
    private VersionLedger() {}

    public static Path locate() {
        String explicit = System.getProperty("lab.versions");
        if (explicit == null || explicit.isBlank()) explicit = System.getenv("LAB_SHARED_VERSIONS");
        // 兼容旧 Redis 学员副本；新说明统一使用 LAB_SHARED_VERSIONS。
        if (explicit == null || explicit.isBlank()) explicit = System.getenv("LAB_VERSIONS");
        if (explicit != null && !explicit.isBlank()) return requireFile(Path.of(explicit));
        String repository = System.getenv("LAB_REPO_ROOT");
        if (repository != null && !repository.isBlank()) {
            return requireFile(Path.of(repository).resolve("infra/versions.env"));
        }
        Path start = Path.of(System.getProperty("course.root", ".")).toAbsolutePath().normalize();
        Path snapshot = null;
        for (Path directory = start; directory != null; directory = directory.getParent()) {
            Path source = directory.resolve("infra/versions.env");
            if (Files.isRegularFile(source)) return source;
            Path candidate = directory.resolve("shared/versions.env");
            if (snapshot == null && Files.isRegularFile(candidate)) snapshot = candidate;
        }
        if (snapshot != null) return snapshot;
        throw new IllegalStateException("未找到镜像台账：请保留课程 shared 目录，或设置 LAB_SHARED_VERSIONS / LAB_REPO_ROOT");
    }

    private static Path requireFile(Path file) {
        Path normalized = file.toAbsolutePath().normalize();
        if (!Files.isRegularFile(normalized)) {
            throw new IllegalStateException("显式指定的镜像台账不存在，禁止静默回退：" + normalized);
        }
        return normalized;
    }

    public static String get(String key) {
        Path file = locate();
        try {
            byte[] bytes = Files.readAllBytes(file);
            verifySnapshot(file, bytes);
            Properties values = new Properties();
            try (var input = new ByteArrayInputStream(bytes)) {
                values.load(input);
            }
            String image = values.getProperty(key);
            if (image == null || image.isBlank() || image.matches(".*\\s+.*")
                    || image.endsWith(":latest") || (!image.contains(":") && !image.contains("@"))) {
                throw new IllegalStateException("镜像台账缺少固定版本键：" + key);
            }
            return image;
        } catch (IOException e) {
            throw new IllegalStateException("镜像台账读取失败：" + file, e);
        }
    }

    private static void verifySnapshot(Path file, byte[] bytes) throws IOException {
        Path checksum = file.resolveSibling(file.getFileName() + ".sha256");
        boolean snapshot = file.getParent().getFileName().toString().equals("shared")
                && file.getFileName().toString().equals("versions.env");
        if (!Files.isRegularFile(checksum)) {
            if (snapshot) throw new IllegalStateException("课程镜像快照缺少 SHA256：" + checksum);
            return;
        }
        String expected = Files.readString(checksum, StandardCharsets.UTF_8).trim().split("\\s+")[0];
        try {
            String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            if (!expected.matches("[0-9a-f]{64}") || !expected.equals(actual)) {
                throw new IllegalStateException("课程镜像快照 SHA256 不一致，请从原仓库重新生成：" + file);
            }
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("JDK 不提供 SHA-256", e);
        }
    }
}
