import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.IntVector;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class IntVectorExamplesTest {
  @Test
  void workedExample() {
    var vector = new IntVector();
    vector.add(7);
    assertEquals(7, vector.get(0));
  }
}
