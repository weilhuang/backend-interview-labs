import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.TopWords;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

// Visible sample. Add your own boundary tests here; keep hidden contract checks unchanged.
@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class TopWordsExamplesTest {
  @Test
  void workedExample() {
    assertEquals(List.of(new TopWords.Count("b", 2)), TopWords.top(List.of("b", "a", "b"), 1));
  }
}
