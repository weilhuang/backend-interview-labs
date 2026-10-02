package labs.observability;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** C12-01: 只序列化已定义字段。请求头和任意 message 都不是日志字段。 */
public class SafeEvents {
    private final ObjectMapper json = new ObjectMapper();
    public String encode(Instant time, String service, String route, int status,
                         String traceId, String spanId, long elapsedNanos,
                         Map<String, String> untrustedHeaders) {
        if (time == null || elapsedNanos < 0 || status < 100 || status > 599)
            throw new IllegalArgumentException("invalid event metadata");
        if (!service.matches("checkout|inventory")) throw new IllegalArgumentException("service");
        Map<String,Object> event = new LinkedHashMap<>();
        event.put("@timestamp", time.toString());
        event.put("event_id", UUID.randomUUID().toString());
        event.put("headers", untrustedHeaders);
        event.put("event", "http.completed");
        event.put("service", service);
        event.put("route", Routes.safe(route));
        event.put("status", status);
        event.put("trace_id", identifier(traceId,32));
        event.put("span_id", identifier(spanId,16));
        event.put("duration_ms", elapsedNanos / 1_000_000.0);
        // Deliberately never iterate untrustedHeaders, even for a harmless-looking name.
        try { return json.writeValueAsString(event); }
        catch (JsonProcessingException failure) { throw new IllegalStateException("event encoding", failure); }
    }
    static String identifier(String id, int length) {
        return id != null && id.matches("[0-9a-f]{"+length+"}") ? id : "";
    }
}
