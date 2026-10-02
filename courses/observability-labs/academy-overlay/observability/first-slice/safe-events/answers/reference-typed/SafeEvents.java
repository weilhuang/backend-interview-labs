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
        Event event = new Event(time.toString(),UUID.randomUUID().toString(),"http.completed",service,
            Routes.safe(route),status,identifier(traceId,32),identifier(spanId,16),elapsedNanos/1_000_000.0);
        try { return json.writeValueAsString(event); }
        catch (JsonProcessingException failure) { throw new IllegalStateException("event encoding",failure); }
    }
    record Event(@com.fasterxml.jackson.annotation.JsonProperty("@timestamp") String timestamp,
        String event_id,String event,String service,String route,int status,String trace_id,String span_id,double duration_ms) {}
    static String identifier(String id, int length) {
        return id != null && id.matches("[0-9a-f]{"+length+"}") ? id : "";
    }
}
