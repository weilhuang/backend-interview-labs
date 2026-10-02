import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
public class GoTestBridgeTest {
 @Test void rejectsFalseGreen() {
  for(String output:java.util.List.of("", "--- SKIP: TestContract (0s)", "? pkg [no test files]", "--- PASS: TestContract (0s)"))
   assertThrows(AssertionError.class,()->GoTestBridge.requirePassed(new GoTestBridge.Result(0,output)));
  assertThrows(AssertionError.class,()->GoTestBridge.requirePassed(new GoTestBridge.Result(1,"failed")));
 }
 @Test void exactVersionOnly() {
  assertDoesNotThrow(()->GoTestBridge.requireToolchainVersion(new GoTestBridge.Result(0,"go version go1.27.1 linux/amd64\n")));
  for(String v:java.util.List.of("1.27.0","1.27.10","1.27.1rc1"))
   assertThrows(IllegalStateException.class,()->GoTestBridge.requireToolchainVersion(new GoTestBridge.Result(0,"go version go"+v+" linux/amd64")));
 }
}
