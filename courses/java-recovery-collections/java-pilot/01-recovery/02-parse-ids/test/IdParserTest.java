import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import labs.IdParser;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(value = 3, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
class IdParserTest {
  @Test
  void preservesFirstAppearance() {
    assertEquals(List.of(3, 1, 2), IdParser.parse("3, 1,3,02,2"));
  }

  @Test
  void blankAndMutable() {
    assertEquals(List.of(), IdParser.parse(" \t\n "));
    var a = IdParser.parse("1");
    a.add(2);
    assertEquals(List.of(1, 2), a);
  }

  @Test
  void rejectsMissingTokens() {
    for (String s : List.of(",1", "1,", "1,,2", ","))
      assertThrows(IllegalArgumentException.class, () -> IdParser.parse(s), s);
  }

  @Test
  void rejectsInvalidAndOverflow() {
    for (String s : List.of("0", "-1", "+1", "1.0", "x", "2147483648", "١"))
      assertThrows(IllegalArgumentException.class, () -> IdParser.parse(s), s);
    assertThrows(NullPointerException.class, () -> IdParser.parse(null));
  }

  @Test
  void boundaries() {
    assertEquals(List.of(1, Integer.MAX_VALUE), IdParser.parse("0001,2147483647"));
  }
}
