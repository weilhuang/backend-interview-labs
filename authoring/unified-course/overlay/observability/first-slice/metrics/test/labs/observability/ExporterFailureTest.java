package labs.observability;
import org.junit.jupiter.api.Test;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import io.opentelemetry.sdk.testing.exporter.InMemoryMetricReader;
import java.util.Collection;
import java.time.Duration;
import java.nio.file.Files;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
class ExporterFailureTest {
 @Test void exporterOutageCannotBlockRequestThreadAtQueueCapacity() {
  // A controlled exporter that never completes. This tests SDK queuing, not a real Collector.
  SpanExporter stuck=new SpanExporter(){
   public CompletableResultCode export(Collection<SpanData> spans){return new CompletableResultCode();}
   public CompletableResultCode flush(){return CompletableResultCode.ofSuccess();}
   public CompletableResultCode shutdown(){return CompletableResultCode.ofSuccess();}
  };
  try(Telemetry t=new Telemetry("checkout",stuck,InMemoryMetricReader.create(),Sampler.alwaysOn())) {
   assertTimeoutPreemptively(Duration.ofSeconds(3),()->{for(int i=0;i<1000;i++)t.bridge.server("fixture",Map.of()).end();});
  }
 }
 @Test void unwritableLogDestinationHasVisibleFailureCounter() throws Exception {
  var directory=Files.createTempDirectory("event-sink-test");
  try {
   var sink=new EventSink(directory);sink.accept("{\"fixture\":true}");
   assertEquals(1,sink.writeFailures());assertEquals(1,sink.recent().size());
  }finally{Files.delete(directory);}
 }
}
