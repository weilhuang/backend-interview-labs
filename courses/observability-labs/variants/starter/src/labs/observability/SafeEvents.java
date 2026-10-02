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
        throw new UnsupportedOperationException("C12-01: 请构造白名单 JSON 事件");
    }
    static String identifier(String id, int length) {
        return id != null && id.matches("[0-9a-f]{"+length+"}") ? id : "";
    }
}
