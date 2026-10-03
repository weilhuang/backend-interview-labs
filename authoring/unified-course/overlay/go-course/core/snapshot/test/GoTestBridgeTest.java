import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/** 对判分桥本身的防假绿测试；这些不替代Go业务测试。 */
public class GoTestBridgeTest {
    @Test void nonzeroFails(){assertThrows(AssertionError.class,()->GoTestBridge.requirePassed(new GoTestBridge.Result(1,"failed")));}
    @Test void emptyOutputIsNotPass(){assertThrows(AssertionError.class,()->GoTestBridge.requirePassed(new GoTestBridge.Result(0,"")));}
    @Test void skippedIsNotPass(){assertThrows(AssertionError.class,()->GoTestBridge.requirePassed(new GoTestBridge.Result(0,"--- SKIP: TestSnapshotContract (0s)")));}
    @Test void noTestsIsNotPass(){assertThrows(AssertionError.class,()->GoTestBridge.requirePassed(new GoTestBridge.Result(0,"? package [no test files]")));}
    @Test void topLevelsWithoutCasesAreNotPass(){assertThrows(AssertionError.class,()->GoTestBridge.requirePassed(new GoTestBridge.Result(0,"--- PASS: TestSnapshotContract (0s)\n--- PASS: FuzzSnapshotIsolation (0s)\n--- PASS: TestDemoJSONEndToEnd (0s)\n--- PASS: TestDemoOutputFailure (0s)\n--- PASS: TestObserveBeforeExercise (0s)\n")));}
}
