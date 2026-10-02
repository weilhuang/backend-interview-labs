package labs.observability;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import java.util.List;
import java.util.Set;

/** C12-03: OTEL 原生直方图的桶是非累积计数，Prometheus 导出桶才是累积。 */
public class RequestMetrics {
    public static final List<Double> BUCKETS = List.of(.005,.01,.025,.05,.075,.1,.25,.5,.75,1.,2.5,5.,7.5,10.);
    private final LongCounter requests;
    private final DoubleHistogram duration;
    public RequestMetrics(Meter meter) {
        requests = meter.counterBuilder("lab.http.requests").setUnit("{request}").build();
        duration = meter.histogramBuilder("http.server.request.duration").setUnit("s")
            .setExplicitBucketBoundariesAdvice(BUCKETS).build();
    }
    public void observe(String method, String route, int status, long elapsedNanos) {
        throw new UnsupportedOperationException("C12-03: 请记录计数与秒直方图");
    }
    public Attributes attributes(String method, String route, int status) {
        String known = Set.of("GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS","CONNECT","TRACE").contains(method) ? method : "_OTHER";
        AttributesBuilder labels = Attributes.builder().put("http.request.method", known)
            .put("http.response.status_code", status).put("url.scheme", "http");
        String safe = Routes.safe(route);
        if (!safe.equals("UNMATCHED")) labels.put("http.route", safe);
        if (status >= 500) labels.put("error.type", Integer.toString(status));
        return labels.build();
    }
}
