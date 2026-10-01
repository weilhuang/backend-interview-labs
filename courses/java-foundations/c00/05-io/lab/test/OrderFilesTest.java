import static org.junit.jupiter.api.Assertions.*;

import labs.foundation.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.*;
import java.util.concurrent.*;

@Timeout(5)
class OrderFilesTest {
    @org.junit.jupiter.api.io.TempDir java.nio.file.Path directory;

    @Test
    void utf8AndEmpty() throws Exception {
        java.nio.file.Files.writeString(
                directory.resolve("in.txt"),
                "A|张三|2|PAID\nB|李四|7|PAID\n",
                java.nio.charset.StandardCharsets.UTF_8);
        OrderFiles.report(directory, "in.txt", "out.txt");
        assertEquals("张三|2\n李四|7\n", java.nio.file.Files.readString(directory.resolve("out.txt")));
        var out = new java.io.StringWriter();
        OrderFiles.summarize(new java.io.StringReader(""), out);
        assertEquals("", out.toString());
    }

    @Test
    void bothCloseAndSuppressed() {
        class Reader extends java.io.Reader {
            java.io.StringReader delegate = new java.io.StringReader("坏行");
            boolean closed;

            public int read(char[] b, int o, int n) throws java.io.IOException {
                return delegate.read(b, o, n);
            }

            public void close() throws java.io.IOException {
                closed = true;
                throw new java.io.IOException("读取端关闭失败");
            }
        }
        class Writer extends java.io.Writer {
            boolean closed;

            public void write(char[] b, int o, int n) {}

            public void flush() {}

            public void close() throws java.io.IOException {
                closed = true;
                throw new java.io.IOException("输出端关闭失败");
            }
        }
        var reader = new Reader();
        var writer = new Writer();
        var e = assertThrows(ParseFailure.class, () -> OrderFiles.summarize(reader, writer));
        assertEquals(2, e.getSuppressed().length);
        assertTrue(reader.closed && writer.closed);
    }

    @Test
    void confinedNamesAndInvalidNoOutput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderFiles.report(directory, "../real.txt", "x.txt"));
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderFiles.report(directory, "x.txt", "x.txt"));
        var out = new java.io.StringWriter();
        assertThrows(
                ParseFailure.class,
                () -> OrderFiles.summarize(new java.io.StringReader("A|甲|1|PAID\n坏行"), out));
        assertEquals("", out.toString());
    }
}
