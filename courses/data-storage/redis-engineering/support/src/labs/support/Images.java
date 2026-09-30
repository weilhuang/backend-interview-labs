package labs.support;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

/** 镜像只读仓库台账；独立导出时可用LAB_VERSIONS指定原始台账。 */
public final class Images {
  private Images() {}

  public static String get(String name) {
    String explicit = System.getenv("LAB_VERSIONS");
    Path start = Path.of(System.getProperty("course.root", ".")).toAbsolutePath();
    Path file = explicit == null ? null : Path.of(explicit);
    for (Path p = start; file == null && p != null; p = p.getParent()) {
      Path candidate = p.resolve("infra/versions.env");
      if (Files.isRegularFile(candidate)) file = candidate;
    }
    if (file == null)
      throw new IllegalStateException("未找到infra/versions.env；请在完整仓库运行或设置LAB_VERSIONS");
    Properties properties = new Properties();
    try (var in = Files.newInputStream(file)) {
      properties.load(in);
    } catch (IOException e) {
      throw new IllegalStateException("镜像台账读取失败：" + file, e);
    }
    String image = properties.getProperty(name);
    if (image == null || image.isBlank() || image.contains("latest"))
      throw new IllegalStateException("镜像键缺失或未冻结：" + name);
    return image;
  }
}
