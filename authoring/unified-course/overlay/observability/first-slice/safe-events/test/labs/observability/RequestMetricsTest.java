package labs.observability;
import org.junit.jupiter.api.Test;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.data.MetricData;
import io.opentelemetry.sdk.testing.exporter.InMemoryMetricReader;
import io.opentelemetry.api.common.AttributeKey;
import static org.junit.jupiter.api.Assertions.*;
class RequestMetricsTest {
 @Test void exactCountAndSecondsHistogram() {
  InMemoryMetricReader r=InMemoryMetricReader.create();
  try(SdkMeterProvider p=SdkMeterProvider.builder().registerMetricReader(r).build()) {
   RequestMetrics m=new RequestMetrics(p.get("test"));
   m.observe("POST","/checkout",200,5_000_000);m.observe("POST","/checkout",200,10_000_000);m.observe("POST","/checkout",200,250_000_000);
   var all=r.collectAllMetrics();
   var counter=all.stream().filter(x->x.getName().equals("lab.http.requests")).findFirst().orElseThrow();
   assertEquals(3,counter.getLongSumData().getPoints().iterator().next().getValue());
   var hist=all.stream().filter(x->x.getName().equals("http.server.request.duration")).findFirst().orElseThrow();
   var point=hist.getHistogramData().getPoints().iterator().next();
   assertEquals("s",hist.getUnit());assertEquals(3,point.getCount());assertEquals(.265,point.getSum(),1e-12);
   assertEquals(RequestMetrics.BUCKETS,point.getBoundaries());
   // OTEL counts are non-cumulative: .005 bucket=1, .01 bucket=1, .25 bucket=1.
   assertEquals(1L,point.getCounts().get(0));assertEquals(1L,point.getCounts().get(1));assertEquals(1L,point.getCounts().get(6));
   long cumulative=0;for(long bucket:point.getCounts()) cumulative+=bucket;assertEquals(point.getCount(),cumulative);
  }
 }
 @Test void tenThousandIdsCannotCreateTenThousandSeries() {
  InMemoryMetricReader r=InMemoryMetricReader.create();
  try(SdkMeterProvider p=SdkMeterProvider.builder().registerMetricReader(r).build()) {
   RequestMetrics m=new RequestMetrics(p.get("test"));
   for(int id=0;id<10_000;id++) m.observe("GET","/inventory/"+id,200,1);
   MetricData counter=r.collectAllMetrics().stream().filter(x->x.getName().equals("lab.http.requests")).findFirst().orElseThrow();
   assertEquals(1,counter.getLongSumData().getPoints().size());
   assertNull(counter.getLongSumData().getPoints().iterator().next().getAttributes().get(AttributeKey.stringKey("http.route")));
   assertEquals(10_000,counter.getLongSumData().getPoints().iterator().next().getValue());
  }
 }
 @Test void onlyAllowlistedAttributesAndUnknownMethod() {
  RequestMetrics m=new RequestMetrics(io.opentelemetry.api.OpenTelemetry.noop().getMeter("test"));
  var a=m.attributes("ATTACK-METHOD","/inventory/{sku}",503);
  assertEquals("_OTHER",a.get(AttributeKey.stringKey("http.request.method")));
  assertEquals("503",a.get(AttributeKey.stringKey("error.type")));
  assertEquals(5,a.size()); assertNull(a.get(AttributeKey.stringKey("user_id")));
 }
 @Test void successfulResponseHasNoErrorType() {
  var a=new RequestMetrics(io.opentelemetry.api.OpenTelemetry.noop().getMeter("test")).attributes("GET","/checkout",200);
  assertNull(a.get(AttributeKey.stringKey("error.type")));
 }
 @Test void invalidObservationDoesNotIncrement() {
  InMemoryMetricReader r=InMemoryMetricReader.create();
  try(SdkMeterProvider p=SdkMeterProvider.builder().registerMetricReader(r).build()) {
   RequestMetrics m=new RequestMetrics(p.get("test"));
   assertThrows(IllegalArgumentException.class,()->m.observe("GET","/checkout",200,-1));
   assertTrue(r.collectAllMetrics().stream().allMatch(x->x.getLongSumData().getPoints().isEmpty()));
  }
 }
}
