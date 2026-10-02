package labs.observability;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class TelemetryEndpointTest {
 @Test void normalizesOnlyAnOptionalTrailingSlash() {
  assertEquals("http://localhost:4318",Telemetry.normalizeEndpoint("http://localhost:4318/"));
  assertEquals("http://collector:4318",Telemetry.normalizeEndpoint("http://collector:4318"));
 }
 @Test void rejectsUserInfoQueryFragmentAndNonBasePaths() {
  for(String u:java.util.List.of("http://user@localhost:4318","http://localhost:4318?x=1","http://localhost:4318#x","http://localhost:4318/path","https://localhost:4318","http://outside.invalid:4318","http://localhost:0"))
   assertThrows(IllegalArgumentException.class,()->Telemetry.normalizeEndpoint(u));
 }
}
