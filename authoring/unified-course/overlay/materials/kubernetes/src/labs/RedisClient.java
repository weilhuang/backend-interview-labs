package labs;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** 仅为教学实现 RESP2 的最小子集；生产请用维护中的连接池客户端。每次调用都有有界超时。 */
public final class RedisClient {
    private final String host, password;
    private final int port, timeoutMillis;
    public RedisClient(String host, int port, String password, int timeoutMillis) {
        this.host = host; this.port = port; this.password = password; this.timeoutMillis = timeoutMillis;
    }
    public static final class Failure extends IOException {
        public final String layer;
        public Failure(String layer) { super("dependency failure at " + layer); this.layer = layer; }
    }
    public Object command(String... args) throws Failure {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), timeoutMillis);
            socket.setSoTimeout(timeoutMillis);
            var out = socket.getOutputStream();
            var in = new BufferedInputStream(socket.getInputStream());
            if (!password.isEmpty()) {
                write(out, new String[]{"AUTH", password});
                if (!"OK".equals(read(in, 0))) throw new Failure("AUTH");
            }
            write(out, args);
            return read(in, 0);
        } catch (UnknownHostException e) { throw new Failure("DNS");
        } catch (SocketTimeoutException e) { throw new Failure("TIMEOUT");
        } catch (ConnectException | NoRouteToHostException e) { throw new Failure("CONNECT");
        } catch (Failure e) { throw e;
        } catch (IOException e) { throw new Failure("PROTOCOL"); }
    }
    private static void write(OutputStream out, String[] args) throws IOException {
        out.write(("*" + args.length + "\r\n").getBytes(StandardCharsets.US_ASCII));
        for (String arg : args) {
            byte[] b = arg.getBytes(StandardCharsets.UTF_8);
            out.write(("$" + b.length + "\r\n").getBytes(StandardCharsets.US_ASCII));
            out.write(b); out.write('\r'); out.write('\n');
        }
        out.flush();
    }
    private static String line(InputStream in) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\r') {
                if (in.read() != '\n') throw new Failure("PROTOCOL");
                return result.toString(StandardCharsets.UTF_8);
            }
            if (result.size() >= 65536) throw new Failure("PROTOCOL");
            result.write(c);
        }
        throw new EOFException();
    }
    private static Object read(InputStream in, int depth) throws IOException {
        if (depth > 4) throw new Failure("PROTOCOL");
        int type = in.read();
        String value = line(in);
        try {
            return switch (type) {
                case '+' -> value;
                case '-' -> throw new Failure(value.startsWith("NOAUTH") || value.startsWith("WRONGPASS") ? "AUTH" : "PROTOCOL");
                case ':' -> Long.valueOf(value);
                case '$' -> {
                    int length = Integer.parseInt(value);
                    if (length == -1) yield null;
                    if (length < 0 || length > 65536) throw new Failure("PROTOCOL");
                    byte[] bytes = in.readNBytes(length);
                    if (bytes.length != length || in.read() != '\r' || in.read() != '\n') throw new Failure("PROTOCOL");
                    yield new String(bytes, StandardCharsets.UTF_8);
                }
                case '*' -> {
                    int count = Integer.parseInt(value);
                    if (count < 0 || count > 128) throw new Failure("PROTOCOL");
                    List<Object> items = new ArrayList<>();
                    for (int n = 0; n < count; n++) items.add(read(in, depth + 1));
                    yield items;
                }
                default -> throw new Failure("PROTOCOL");
            };
        } catch (NumberFormatException e) { throw new Failure("PROTOCOL"); }
    }
}
