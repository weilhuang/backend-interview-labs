import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.TopWords;
import labs.TopWords.Count;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class TopWordsTest {
  @Test
  void ranksCountThenWord() {
    assertEquals(
        List.of(new Count("b", 3), new Count("a", 2), new Count("c", 2)),
        TopWords.top(List.of("c", "b", "a", "b", " C ", "A", "b"), 9));
  }

  @Test
  void truncatesAndIgnoresBlank() {
    assertEquals(List.of(new Count("a", 1)), TopWords.top(List.of("b", " ", "a", "	"), 1));
    assertEquals(List.of(), TopWords.top(List.of("a"), 0));
    assertEquals(List.of(), TopWords.top(List.of(), 9));
  }

  @Test
  void localeIndependent() {
    var old = Locale.getDefault();
    try {
      Locale.setDefault(Locale.forLanguageTag("tr-TR"));
      assertEquals(List.of(new Count("i", 2)), TopWords.top(List.of("I", "i"), 9));
    } finally {
      Locale.setDefault(old);
    }
  }

  @Test
  void validatesEvenWithZeroK() {
    assertThrows(NullPointerException.class, () -> TopWords.top(null, 0));
    assertThrows(NullPointerException.class, () -> TopWords.top(Arrays.asList("x", null), 0));
    assertThrows(IllegalArgumentException.class, () -> TopWords.top(List.of(), -1));
  }

  @Test
  void inputAndOutputIsolation() {
    var a = new ArrayList<>(List.of("b", "a"));
    var r = TopWords.top(a, 8);
    r.clear();
    assertEquals(List.of("b", "a"), a);
    assertEquals(2, TopWords.top(a, 8).size());
  }
}
