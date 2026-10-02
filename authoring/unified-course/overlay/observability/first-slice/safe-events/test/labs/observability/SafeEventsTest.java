package labs.observability;
import org.junit.jupiter.api.Test;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
class SafeEventsTest {
 private final SafeEvents events=new SafeEvents(); private final ObjectMapper json=new ObjectMapper();
 private JsonNode parse(String line) {
  JsonNode node=assertDoesNotThrow(()->json.readTree(line));assertNotNull(node);assertTrue(node.isObject());
  java.util.Set<String> actual=new java.util.HashSet<>();node.fieldNames().forEachRemaining(actual::add);
  assertEquals(java.util.Set.of("@timestamp","event_id","event","service","route","status","trace_id","span_id","duration_ms"),actual);
  return node;
 }
 private String encode(String route,Map<String,String> headers) { return events.encode(Instant.parse("2026-10-01T00:00:00Z"),"checkout",route,503,"a".repeat(32),"b".repeat(16),12_500_000,headers); }
 @Test void jsonHasTypedFieldsAndUtcTime() throws Exception {
  JsonNode e=parse(encode("/checkout",Map.of()));
  assertEquals(Instant.parse("2026-10-01T00:00:00Z"),Instant.parse(e.path("@timestamp").asText()));
  assertTrue(e.path("status").isInt()); assertEquals(503,e.path("status").asInt()); assertEquals(12.5,e.path("duration_ms").asDouble());
  assertEquals("a".repeat(32),e.path("trace_id").asText()); assertEquals("b".repeat(16),e.path("span_id").asText());
 }
 @Test void dropsAllHeadersIncludingPiiAndMixedCaseNames() throws Exception {
  String s=encode("/checkout",Map.of("Authorization","Bearer token-secret","Cookie","session-secret","password","pw-secret","X-Email","person@example.invalid","a\r\nb","header-secret"));
  for(String secret:java.util.List.of("token-secret","session-secret","pw-secret","person@example.invalid","header-secret")) assertFalse(s.contains(secret));
  assertEquals(9,parse(s).size());
 }
 @Test void rejectsDynamicPathAndCrlfDoesNotCreateAnEvent() throws Exception {
  String s=encode("/checkout/123\r\n{\"event\":\"forged\"}",Map.of());
  assertFalse(s.contains("\n")); assertFalse(s.contains("\r"));assertEquals("UNMATCHED",parse(s).path("route").asText());
 }
 @Test void eventIdStableWithinALineAndDistinctAcrossEvents() throws Exception {
  String line=encode("/checkout",Map.of()); String id=parse(line).path("event_id").asText();
  assertEquals(id,parse(line).path("event_id").asText()); assertNotEquals(id,parse(encode("/checkout",Map.of())).path("event_id").asText());
 }
 @Test void invalidTraceIdsCannotInjectJson() throws Exception {
  String line=events.encode(Instant.EPOCH,"checkout","/checkout",200,"\"\nsecret","invalid",0,Map.of());
  assertEquals("",parse(line).path("trace_id").asText());assertFalse(line.contains("secret"));
 }
 @Test void durationIsNotComputedFromWallClock() throws Exception {
  String line=events.encode(Instant.parse("1999-01-01T00:00:00Z"),"checkout","/checkout",200,"a".repeat(32),"b".repeat(16),25_000_000,Map.of());
  assertEquals(25,parse(line).path("duration_ms").asDouble());
 }
 @Test void invalidMetadataFailsExplicitly() {
  assertThrows(IllegalArgumentException.class,()->events.encode(Instant.EPOCH,"checkout","/checkout",200,"","",-1,Map.of()));
  assertThrows(IllegalArgumentException.class,()->events.encode(Instant.EPOCH,"checkout","/checkout",999,"","",0,Map.of()));
 }
}
