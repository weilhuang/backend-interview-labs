package labs.observability;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.MetricReader;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter;
import java.time.Duration;
import java.net.URI;

/** No global SDK: each service owns and closes its own provider. */
public final class Telemetry implements AutoCloseable {
    public final OpenTelemetrySdk sdk;
    public final SdkTracerProvider traces;
    public final SdkMeterProvider meters;
    public final TraceBridge bridge;
    public final RequestMetrics metrics;
    public Telemetry(String service, SpanExporter exporter, MetricReader reader, Sampler sampler) {
        Resource resource = Resource.create(Attributes.of(AttributeKey.stringKey("service.name"), service));
        traces = SdkTracerProvider.builder().setResource(resource).setSampler(sampler)
            .addSpanProcessor(BatchSpanProcessor.builder(exporter).setMaxQueueSize(128)
                .setMaxExportBatchSize(32).setScheduleDelay(Duration.ofMillis(100))
                .setExporterTimeout(Duration.ofSeconds(2)).build()).build();
        meters = SdkMeterProvider.builder().setResource(resource).registerMetricReader(reader).build();
        sdk = OpenTelemetrySdk.builder().setTracerProvider(traces).setMeterProvider(meters).build();
        bridge = new TraceBridge(sdk.getTracer("labs.observability", "1.0"));
        metrics = new RequestMetrics(sdk.meterBuilder("labs.observability").setInstrumentationVersion("1.0").build());
    }
    public static Telemetry otlp(String service, String endpoint, double ratio) {
        endpoint = normalizeEndpoint(endpoint);
        return new Telemetry(service,
            OtlpHttpSpanExporter.builder().setEndpoint(endpoint+"/v1/traces").setTimeout(Duration.ofSeconds(2)).build(),
            PeriodicMetricReader.builder(OtlpHttpMetricExporter.builder().setEndpoint(endpoint+"/v1/metrics")
                .setTimeout(Duration.ofSeconds(2)).build()).setInterval(Duration.ofSeconds(2)).build(),
            Sampler.parentBased(Sampler.traceIdRatioBased(ratio)));
    }
    public void close() { traces.close(); meters.close(); }
    static String normalizeEndpoint(String endpoint) {
        URI u=URI.create(endpoint);
        if (!"http".equals(u.getScheme()) || u.getHost()==null || !java.util.Set.of("127.0.0.1","localhost","collector").contains(u.getHost())
            || u.getUserInfo()!=null || u.getQuery()!=null || u.getFragment()!=null
            || !(u.getPath().isEmpty() || u.getPath().equals("/")) || u.getPort()==0 || u.getPort()>65535)
            throw new IllegalArgumentException("fixture OTLP endpoint must be a local HTTP base URL");
        return u.getScheme()+"://"+u.getRawAuthority();
    }
}
