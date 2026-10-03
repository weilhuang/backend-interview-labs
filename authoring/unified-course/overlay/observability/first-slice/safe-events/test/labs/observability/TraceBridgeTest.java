package labs.observability;
import org.junit.jupiter.api.Test;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import java.util.Map;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;
class TraceBridgeTest {
 private static final String VALID="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01";
 @Test void propagationKeepsTraceAndParentChildIdsAcrossServiceBoundary() {
  var out=InMemorySpanExporter.create();
  try(var p=SdkTracerProvider.builder().addSpanProcessor(SimpleSpanProcessor.create(out)).build()) {
   TraceBridge bridge=new TraceBridge(p.get("test")); Span a=bridge.server("checkout",Map.of("traceparent",VALID));
   try(Scope ignored=a.makeCurrent()) {
    Span client=bridge.client("inventory-client");
    try(Scope c=client.makeCurrent()) {
     Span b=bridge.server("inventory",bridge.inject(Context.current()));b.end();
    }finally{client.end();}
   }finally{a.end();}
   var spans=out.getFinishedSpanItems();assertEquals(3,spans.size());
   assertEquals(1,spans.stream().map(s->s.getTraceId()).distinct().count());
   var inv=spans.stream().filter(s->s.getName().equals("inventory")).findFirst().orElseThrow();
   var cli=spans.stream().filter(s->s.getName().equals("inventory-client")).findFirst().orElseThrow();
   assertEquals(cli.getSpanId(),inv.getParentSpanId());assertEquals(a.getSpanContext().getSpanId(),cli.getParentSpanId());
   assertFalse(Span.current().getSpanContext().isValid());
  }
 }
 @Test void malformedTraceparentStartsSafeNewRoot() {
  try(var p=SdkTracerProvider.builder().build()) {
   TraceBridge b=new TraceBridge(p.get("test"));
   for(String header:java.util.List.of("nonsense","00-"+"0".repeat(32)+"-0123456789abcdef-01","00-0123456789abcdef0123456789abcdef-"+"0".repeat(16)+"-01","ff-0123456789abcdef0123456789abcdef-0123456789abcdef-01","00-XYZ-0123456789abcdef-01")) {
    assertFalse(Span.fromContext(b.extract(Map.of("traceparent",header))).getSpanContext().isValid());
    Span s=b.server("safe",Map.of("traceparent",header));assertTrue(s.getSpanContext().isValid());s.end();
   }
  }
 }
 @Test void headerNamesAreCanonicalAndBaggageNeverPropagates() {
  try(var p=SdkTracerProvider.builder().build()) {
   TraceBridge b=new TraceBridge(p.get("test"));
   var headers=b.inject(b.extract(Map.of("traceparent",VALID,"baggage","email=private@example.invalid","authorization","secret","cookie","secret")));
   assertEquals(java.util.Set.of("traceparent"),headers.keySet());assertFalse(headers.toString().contains("secret"));
  }
 }
 @Test void validTraceContextIsNotAnAuthorizationDecision() {
  try(var p=SdkTracerProvider.builder().build()) {
   TraceBridge b=new TraceBridge(p.get("test"));
   assertTrue(Span.fromContext(b.extract(Map.of("traceparent",VALID))).getSpanContext().isValid());
   assertEquals(1,b.inject(b.extract(Map.of("traceparent",VALID))).size()); // no user/role/permission emerges
  }
 }
 @Test void parentBasedSamplingLossCannotBeRecoveredByCollector() {
  var out=InMemorySpanExporter.create();
  try(var p=SdkTracerProvider.builder().setSampler(Sampler.parentBased(Sampler.alwaysOn())).addSpanProcessor(SimpleSpanProcessor.create(out)).build()) {
   TraceBridge b=new TraceBridge(p.get("test"));Span s=b.server("unsampled",Map.of("traceparent",VALID.substring(0,53)+"00"));
   assertFalse(s.isRecording());assertTrue(s.getSpanContext().isValid());s.end();assertEquals(0,out.getFinishedSpanItems().size());
  }
 }
 @Test void explicitContextWrapCrossesExecutorAndScopeIsCleaned() throws Exception {
  ExecutorService executor=Executors.newSingleThreadExecutor();
  try(var p=SdkTracerProvider.builder().build()) {
   TraceBridge b=new TraceBridge(p.get("test"));Span span=b.server("root",Map.of());
   try(Scope s=span.makeCurrent()) {
    Context captured=Context.current();
    assertEquals(span.getSpanContext().getTraceId(),executor.submit(captured.wrap((Callable<String>)()->Span.current().getSpanContext().getTraceId())).get());
   }finally{span.end();}
   assertFalse(executor.submit(()->Span.current().getSpanContext().isValid()).get());
  }finally{executor.shutdownNow();}
 }
}
