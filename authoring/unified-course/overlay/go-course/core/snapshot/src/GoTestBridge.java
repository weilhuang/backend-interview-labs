import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

/** 可见的课程检查桥。它执行真实Go测试，不重写答案，不把缺工具/跳过当成功。 */
public final class GoTestBridge {
    public record Result(int exitCode, String output) {}

    public static Result execute(Path go, Path project, Path work, Duration timeout) throws Exception {
        if (!Files.isRegularFile(go) || !Files.isExecutable(go)) {
            throw new IllegalStateException("INVALID_ENV: 请设置GO_EXECUTABLE为官方Go编译器的完整路径：" + go);
        }
        if (!Files.isRegularFile(project.resolve("go.mod"))) {
            throw new IllegalStateException("INVALID_ENV: 找不到本题go.mod：" + project);
        }
        Files.createDirectories(work);
        Result version = process(List.of(go.toString(), "version"), project, work.resolve("version.log"), timeout, work);
        if (version.exitCode() != 0 || !version.output().startsWith("go version go")) {
            throw new IllegalStateException("INVALID_ENV: 此路径不是可用的Go工具链\n" + version.output());
        }
        return process(List.of(go.toString(), "test", "-count=1", "-v", "./..."), project,
                work.resolve("go-tests.log"), timeout, work);
    }

    // 日志写入受控文件，避免子进程输出填满管道；超时清理自己的子进程树。
    private static Result process(List<String> command, Path project, Path log, Duration timeout, Path work) throws Exception {
        ProcessBuilder builder = new ProcessBuilder(command).directory(project.toFile())
                .redirectErrorStream(true).redirectOutput(log.toFile());
        builder.environment().put("GOTOOLCHAIN", "local");
        builder.environment().put("GOPROXY", "off");
        builder.environment().put("GOSUMDB", "off");
        builder.environment().put("GOCACHE", work.resolve("go-cache").toString());
        builder.environment().put("GOMODCACHE", work.resolve("go-mod-cache").toString());
        builder.environment().put("GOMAXPROCS", "2");
        Process process = builder.start();
        try {
            if (!process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
                process.descendants().forEach(ProcessHandle::destroyForcibly);
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
                throw new IllegalStateException("CHECK_TIMEOUT: Go检查超时；查看 " + log);
            }
            return new Result(process.exitValue(), Files.readString(log, StandardCharsets.UTF_8));
        } catch (InterruptedException interrupted) {
            process.descendants().forEach(ProcessHandle::destroyForcibly);
            process.destroyForcibly();
            Thread.currentThread().interrupt();
            throw interrupted;
        }
    }

    public static void requirePassed(Result result) {
        if (result.exitCode() != 0) {
            throw new AssertionError("Go业务测试失败；请看下方C1–C6合同反馈。环境/编译失败需先修复环境。\n" + result.output());
        }
        if (result.output().contains("--- SKIP:") || result.output().contains("[no test files]")) {
            throw new AssertionError("NOT_RUN: Go测试包含跳过或无测试包，不能记为通过\n" + result.output());
        }
        List<String> required = List.of(
                "TestSnapshotContract", "FuzzSnapshotIsolation", "TestDemoJSONEndToEnd",
                "TestDemoOutputFailure", "TestObserveBeforeExercise");
        for (String name : required) {
            String regex = "(?m)^--- PASS: " + Pattern.quote(name) + " ";
            if (!Pattern.compile(regex).matcher(result.output()).find()) {
                throw new AssertionError("NOT_RUN: 缺少已执行并通过的测试 " + name + "\n" + result.output());
            }
        }
        List<String> cases = List.of("CP1_NilInput", "CP1_NonNilEmpty", "CP1_ValueAndOrder",
                "CP1_TopOutputToInput", "CP1_TopInputToOutput", "CP2_LineOutputToInput",
                "CP2_LineInputToOutput", "CP2_TagOutputToInput", "CP2_TagInputToOutput",
                "CP2_MapOutputToInput", "CP2_MapInputToOutput", "CP2_NilNested", "CP2_EmptyNested",
                "CP3_SharedInputContainersSeparate", "CP3_RepeatedCallsSeparate",
                "CP3_NoMutationDuringCall", "CP3_SpareCapacityAppend", "CP3_StringsExact");
        for (String name : cases) {
            String regex = "(?m)^\\s+--- PASS: TestSnapshotContract/" + Pattern.quote(name) + " ";
            if (!Pattern.compile(regex).matcher(result.output()).find()) {
                throw new AssertionError("NOT_RUN: 缺少合同子例 " + name);
            }
        }
    }
}
