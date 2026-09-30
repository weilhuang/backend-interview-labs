import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.IdParser;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class IdParserExamplesTest {
  @Test
  void workedExample() {
    assertEquals(List.of(3, 1), IdParser.parse("3,1,3"));
  }
}
