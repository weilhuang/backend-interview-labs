package labs.observability;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapGetter;
import java.util.Map;
import java.util.HashMap;

/** C12-05: 只传播 trace context；baggage、认证和 Cookie 从未复制。 */
public class TraceBridge {
    private final Tracer tracer;
    private static final TextMapGetter<Map<String,String>> GETTER = new TextMapGetter<>() {
        public Iterable<String> keys(Map<String,String> carrier) { return carrier.keySet(); }
        public String get(Map<String,String> carrier, String key) { return carrier.get(key); }
    };
    public TraceBridge(Tracer tracer) { this.tracer = tracer; }
    public Context extract(Map<String,String> incoming) {
        throw new UnsupportedOperationException("请按中文步骤完成此方法");
    }
    public Span server(String operation, Map<String,String> incoming) {
        return tracer.spanBuilder(operation).setSpanKind(SpanKind.SERVER).setParent(extract(incoming)).startSpan();
    }
    public Span client(String operation) {
        return tracer.spanBuilder(operation).setSpanKind(SpanKind.CLIENT).setParent(Context.current()).startSpan();
    }
    public Map<String,String> inject(Context context) {
        Map<String,String> result = new HashMap<>();
        W3CTraceContextPropagator.getInstance().inject(context, result, Map::put);
        return Map.copyOf(result);
    }
}
