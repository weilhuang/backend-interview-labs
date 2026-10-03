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
 public static final String REQUIRED_GO_VERSION = "1.27.1";
 public static void requireToolchainVersion(Result version) {
  String exact = "go version go" + Pattern.quote(REQUIRED_GO_VERSION) + " [A-Za-z0-9_]+/[A-Za-z0-9_]+\\s*";
  if(version.exitCode()!=0 || !Pattern.matches(exact,version.output()))
   throw new IllegalStateException("INVALID_ENV: 本题只接受Go " + REQUIRED_GO_VERSION + "，实际输出：\n"+version.output());
 }
 public static Result execute(Path go,Path project,Path work,Duration timeout) throws Exception {
  if(!Files.isRegularFile(go)||!Files.isExecutable(go)) throw new IllegalStateException("INVALID_ENV: 请设置GO_EXECUTABLE为官方Go编译器的完整路径："+go);
  if(!Files.isRegularFile(project.resolve("go.mod"))) throw new IllegalStateException("INVALID_ENV: 找不到本题go.mod："+project);
  if(timeout.isZero()||timeout.isNegative()||timeout.compareTo(Duration.ofSeconds(90))>0) throw new IllegalArgumentException("Go检查总预算必须在0至90秒之间");
  long deadline=System.nanoTime()+timeout.toNanos();Files.createDirectories(work);
  Result version=process(List.of(go.toString(),"version"),project,work.resolve("version.log"),Duration.ofNanos(Math.min(Duration.ofSeconds(10).toNanos(),timeout.toNanos())),work);
  requireToolchainVersion(version);long remaining=deadline-System.nanoTime();
  if(remaining<=0) throw new IllegalStateException("CHECK_TIMEOUT: Go工具链核查已耗尽预算");
  return process(List.of(go.toString(),"test","-buildvcs=false","-mod=readonly","-tags=nomsgpack","-p=1","-count=1","-timeout=45s","-v","./..."),project,work.resolve("go-tests.log"),Duration.ofNanos(remaining),work);
 }
 private static Result process(List<String> command,Path project,Path log,Duration timeout,Path work) throws Exception {
  ProcessBuilder builder=new ProcessBuilder(command).directory(project.toFile()).redirectErrorStream(true).redirectOutput(log.toFile());
  builder.environment().put("GOTOOLCHAIN","local");builder.environment().put("GOWORK","off");builder.environment().put("GOENV","off");builder.environment().put("GOFLAGS","");
  builder.environment().put("GOPROXY","off");builder.environment().put("GOSUMDB","off");builder.environment().put("GOCACHE",work.resolve("go-cache").toString());String cache=System.getProperty("go.moduleCache",System.getenv("GO_MODULE_CACHE"));
  if(cache==null || cache.isBlank() || !Path.of(cache).isAbsolute() || !Files.isDirectory(Path.of(cache)))
   throw new IllegalStateException("INVALID_ENV: 设置GO_MODULE_CACHE为已准备并校验的模块缓存绝对路径；检查不联网补依赖");
  builder.environment().put("GOMODCACHE",cache);builder.environment().put("GOPATH",work.resolve("go-path").toString());builder.environment().put("GIN_MODE","release");builder.environment().put("GOMAXPROCS","2");
  Process process=builder.start();
  try {
   if(!process.waitFor(timeout.toMillis(),TimeUnit.MILLISECONDS)) {process.descendants().forEach(ProcessHandle::destroyForcibly);process.destroyForcibly();process.waitFor(5,TimeUnit.SECONDS);throw new IllegalStateException("CHECK_TIMEOUT: Go检查超时；查看 "+log);}
   return new Result(process.exitValue(),Files.readString(log,StandardCharsets.UTF_8));
  } catch(InterruptedException interrupted) {process.descendants().forEach(ProcessHandle::destroyForcibly);process.destroyForcibly();Thread.currentThread().interrupt();throw interrupted;}
 }
 public static void requirePassed(Result result) {
  if(result.exitCode()!=0) throw new AssertionError("Go业务测试失败；请看下方本题合同反馈。环境/编译失败需先修复环境。\n"+result.output());
  if(result.output().contains("--- SKIP:")||result.output().contains("[no test files]")) throw new AssertionError("NOT_RUN: Go测试包含跳过或无测试包，不能记为通过\n"+result.output());
  List<String> required=List.of("TestRequestContract","TestContextContract","TestRouting","TestActualHTTP","TestServiceResultPreserved","TestClientCancellation","TestConcurrentMemoryStore","TestOutputFailure","TestCallerHTTP","TestMainProcess","TestGinPipeline");
  for(String name:required) {String regex="(?m)^--- PASS: "+Pattern.quote(name)+" ";if(!Pattern.compile(regex).matcher(result.output()).find()) throw new AssertionError("NOT_RUN: 缺少已执行并通过的测试 "+name+"\n"+result.output());}
  List<String> cases=List.of("TestRequestContract/mixed_malformed_oversize","TestRequestContract/mixed_unknown_oversize","TestRequestContract/mixed_extra_value_oversize","TestRequestContract/mixed_media_oversize","TestContextContract/canceled_after_store_success","TestContextContract/deadline_after_store_success","TestActualHTTP/unicode_trim_quantity_7","TestActualHTTP/preserve_case_internal_space_quantity_99","TestRequestContract/valid","TestRequestContract/trim","TestRequestContract/quantity_max","TestRequestContract/exact_byte_limit","TestRequestContract/over_byte_limit","TestRequestContract/large_value","TestRequestContract/missing_media","TestRequestContract/wrong_media","TestRequestContract/trailing_semicolon_media","TestRequestContract/malformed_json","TestRequestContract/empty_body","TestRequestContract/unknown_field","TestRequestContract/extra_value","TestRequestContract/extra_scalar","TestRequestContract/garbage_tail","TestRequestContract/wrong_type","TestRequestContract/null_object","TestRequestContract/missing_quantity","TestRequestContract/zero_quantity","TestRequestContract/negative_quantity","TestRequestContract/large_quantity","TestRequestContract/blank_sku","TestRequestContract/sku_32_runes","TestRequestContract/sku_33_runes","TestContextContract/inherits_and_releases","TestContextContract/already_canceled","TestContextContract/zero_budget","TestContextContract/downstream_deadline","TestContextContract/internal_error_redacted","TestContextContract/wrapped_cancellation","TestGinPipeline/unauthorized_stops_chain","TestGinPipeline/next_unwinds","TestGinPipeline/unknown_error_redacted","TestGinPipeline/committed_response_not_overwritten","TestGinPipeline/panic_sanitized","TestGinPipeline/health_is_public");
  for(String name:cases) {String regex="(?m)^\\s+--- PASS: "+Pattern.quote(name)+" ";if(!Pattern.compile(regex).matcher(result.output()).find()) throw new AssertionError("NOT_RUN: 缺少合同子例 "+name);}
 }
}
