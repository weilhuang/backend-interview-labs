package labs.observability;
import org.junit.jupiter.api.*;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.testing.exporter.InMemoryMetricReader;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;
class HttpCallChainTest {
 static InMemorySpanExporter outA=InMemorySpanExporter.create(),outB=InMemorySpanExporter.create();
 static Telemetry a,b;static EventSink logA=new EventSink(null),logB=new EventSink(null);
 static ServletWebServerApplicationContext checkout,inventory;static HttpClient client=HttpClient.newHttpClient();
 static final ObjectMapper json=new ObjectMapper();
 static ServletWebServerApplicationContext app(String role,Telemetry t,EventSink sink,String... extra) {
  List<String> args=new ArrayList<>(List.of("--server.port=0","--server.address=127.0.0.1","--lab.role="+role,"--spring.main.banner-mode=off"));args.addAll(List.of(extra));
  return (ServletWebServerApplicationContext)new SpringApplicationBuilder(ObservabilityApplication.class)
   .initializers(c->{c.getBeanFactory().registerSingleton("telemetry",t);c.getBeanFactory().registerSingleton("eventSink",sink);})
   .run(args.toArray(String[]::new));
 }
 @BeforeAll static void start() {
  b=new Telemetry("inventory",outB,InMemoryMetricReader.create(),Sampler.parentBased(Sampler.alwaysOn()));
  a=new Telemetry("checkout",outA,InMemoryMetricReader.create(),Sampler.parentBased(Sampler.alwaysOn()));
  inventory=app("inventory",b,logB);
  checkout=app("checkout",a,logA,"--lab.inventory=http://127.0.0.1:"+inventory.getWebServer().getPort());
 }
 @AfterAll static void stop() {
  int pa=checkout==null?-1:checkout.getWebServer().getPort(),pb=inventory==null?-1:inventory.getWebServer().getPort();
  if(checkout!=null)checkout.close();if(inventory!=null)inventory.close();if(a!=null)a.close();if(b!=null)b.close();
  for(int port:new int[]{pa,pb}) if(port>0) {
   assertThrows(java.io.IOException.class,()->{try(var socket=new java.net.Socket()){socket.connect(new java.net.InetSocketAddress("127.0.0.1",port),200);}},"HTTP port must be closed after context shutdown");
   System.out.println("C12_PORT_CLEANUP port="+port+" CLOSED");
  }
 }
 @BeforeEach void reset() {a.traces.forceFlush().join(3,TimeUnit.SECONDS);b.traces.forceFlush().join(3,TimeUnit.SECONDS);outA.reset();outB.reset();}
 HttpResponse<String> post(String body,String header) throws Exception {
  var r=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+checkout.getWebServer().getPort()+"/checkout"))
   .header("Content-Type","application/json").header("Authorization","synthetic-token-secret").header("Cookie","synthetic-cookie-secret").header("baggage","email=private@example.invalid");
  if(header!=null)r.header("traceparent",header);
  return client.send(r.POST(HttpRequest.BodyPublishers.ofString(body)).build(),HttpResponse.BodyHandlers.ofString());
 }
 void flush() {assertTrue(a.traces.forceFlush().join(3,TimeUnit.SECONDS).isSuccess());assertTrue(b.traces.forceFlush().join(3,TimeUnit.SECONDS).isSuccess());}
 @Test void twoRealHttpServicesProduceConnectedThreeSpanTraceAndSafeLogs() throws Exception {
  var response=post("{\"sku\":\"book\",\"scenario\":\"ok\"}",null);assertEquals(200,response.statusCode());flush();
  var all=new ArrayList<>(outA.getFinishedSpanItems());all.addAll(outB.getFinishedSpanItems());assertEquals(3,all.size());
  String trace=response.headers().firstValue("X-Trace-Id").orElseThrow();assertTrue(all.stream().allMatch(s->s.getTraceId().equals(trace)));
  var remote=outB.getFinishedSpanItems().getFirst();var child=outA.getFinishedSpanItems().stream().filter(s->s.getKind()==SpanKind.CLIENT).findFirst().orElseThrow();
  assertEquals(child.getSpanId(),remote.getParentSpanId());
  for(String line:java.util.stream.Stream.concat(logA.recent().stream(),logB.recent().stream()).toList()) {
   assertFalse(line.contains("synthetic-token-secret"));assertFalse(line.contains("synthetic-cookie-secret"));assertFalse(line.contains("private@example.invalid"));json.readTree(line);
  }
 }
 @Test void failedInventoryMarksRealServerAndClientErrors() throws Exception {
  assertEquals(503,post("{\"sku\":\"book\",\"scenario\":\"fail\"}",null).statusCode());flush();
  assertEquals(2,outA.getFinishedSpanItems().size());assertEquals(1,outB.getFinishedSpanItems().size());
  assertTrue(outA.getFinishedSpanItems().stream().allMatch(s->s.getStatus().getStatusCode()==StatusCode.ERROR));
  assertEquals(StatusCode.ERROR,outB.getFinishedSpanItems().getFirst().getStatus().getStatusCode());
 }
 @Test void boundedReadRetryIsTwoAttemptsButOneCheckout() throws Exception {
  var r=post("{\"sku\":\"book\",\"scenario\":\"retry\"}",null);assertEquals(200,r.statusCode());assertEquals(2,json.readTree(r.body()).get("attempts").asInt());flush();
  assertEquals(3,outA.getFinishedSpanItems().size());assertEquals(2,outB.getFinishedSpanItems().size());
  assertEquals(1,outA.getFinishedSpanItems().stream().filter(s->s.getKind()==SpanKind.SERVER).count());
 }
 @Test void malformedHeaderDoesNotBreakBusinessRequest() throws Exception {
  assertEquals(200,post("{\"sku\":\"pen\",\"scenario\":\"ok\"}","malformed").statusCode());flush();assertEquals(3,outA.getFinishedSpanItems().size()+outB.getFinishedSpanItems().size());
 }
 @Test void badJsonIs400WithoutInventoryAttempt() throws Exception {
  assertEquals(400,post("{broken",null).statusCode());flush();assertEquals(0,outB.getFinishedSpanItems().size());
 }
 @Test void traceHeaderAloneCannotMakeInvalidBusinessInputValid() throws Exception {
  assertEquals(400,post("{\"sku\":\"unknown\",\"scenario\":\"ok\"}","00-0123456789abcdef0123456789abcdef-0123456789abcdef-01").statusCode());flush();assertEquals(0,outB.getFinishedSpanItems().size());
 }
}
