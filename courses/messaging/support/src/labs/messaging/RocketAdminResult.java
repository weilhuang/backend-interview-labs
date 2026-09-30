package labs.messaging;

import java.util.regex.Pattern;

/** 官方mqadmin可能打印异常后退出零，必须按固定版本的真实输出判定操作成功。 */
public final class RocketAdminResult {
    private static final Pattern STACK_TRACE =
            Pattern.compile("(?m)^(?:[\\w$]+\\.)*[\\w$]*(?:Exception|Error)(?::|\\s|$)");

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
            case "updateTopic" ->
                    stdout.contains("create topic to ") && stdout.contains(" success.");
            case "updateSubGroup" ->
                    stdout.contains("create subscription group to ")
                            && stdout.contains(" success.");
            case "topicStatus" ->
                    stdout.lines()
                            .anyMatch(
                                    line ->
                                            line.trim()
                                                    .matches("broker-a\\s+\\d+\\s+\\d+\\s+\\d+.*"));
            case "printMsg" -> stdout.contains("minOffset=") && stdout.contains("maxOffset=");
            default -> throw new IllegalArgumentException("未登记管理命令的成功判据：" + command);
        };
    }
}
