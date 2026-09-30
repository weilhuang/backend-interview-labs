package labs.messaging;

import java.util.regex.Pattern;

/** 官方mqadmin可能打印异常后退出零，必须按固定版本的真实输出判定操作成功。 */
public final class RocketAdminResult {
  private static final Pattern STACK_TRACE =
      Pattern.compile("(?m)^(?:[\\w$]+\\.)*[\\w$]*(?:Exception|Error)(?::|\\s|$)");
  private static final Pattern COMMIT_LOG_MAX_OFFSET =
      Pattern.compile("(?m)^commitLogMaxOffset\\h*:\\h*([0-9]+)\\h*$");

  private RocketAdminResult() {}

  public static boolean succeeded(String command, long exitCode, String stdout, String stderr) {
    String combined = stdout + "\n" + stderr;
    if (exitCode != 0
        || STACK_TRACE.matcher(combined).find()
        || combined.contains("command failed")
        || combined.contains("Caused by:")) {
      return false;
    }
    return switch (command) {
      case "clusterList" ->
          stdout
              .lines()
              .anyMatch(
                  line ->
                      line.trim()
                          .matches("LabCluster\\s+broker-a\\s+0\\s+127\\.0\\.0\\.1:10911\\s+.*"));
      case "updateTopic" -> stdout.contains("create topic to ") && stdout.contains(" success.");
      case "updateSubGroup" ->
          stdout.contains("create subscription group to ") && stdout.contains(" success.");
      case "topicStatus" ->
          stdout
              .lines()
              .anyMatch(line -> line.trim().matches("broker-a\\s+\\d+\\s+\\d+\\s+\\d+.*"));
      case "printMsg" -> stdout.contains("minOffset=") && stdout.contains("maxOffset=");
      case "brokerStatus" -> {
        try {
          commitLogMaxOffset(stdout);
          yield true;
        } catch (IllegalArgumentException invalid) {
          yield false;
        }
      }
      default -> throw new IllegalArgumentException("未登记管理命令的成功判据：" + command);
    };
  }

  /** 官方brokerStatus的已写物理上界，不是文件预分配容量或ConsumeQueue逻辑位点。 */
  public static long commitLogMaxOffset(String stdout) {
    var matches = COMMIT_LOG_MAX_OFFSET.matcher(stdout);
    if (!matches.find()) throw new IllegalArgumentException("缺少commitLogMaxOffset数据行");
    long offset = Long.parseLong(matches.group(1));
    if (matches.find()) throw new IllegalArgumentException("commitLogMaxOffset数据行不唯一");
    return offset;
  }
}
