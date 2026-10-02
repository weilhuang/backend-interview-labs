package labs;

import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** 课程已提供的完整调用链。无需学习前端框架、Spring 或第三方 Redis SDK。 */
public final class CloudNativeApp {
    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final Inventory inventory;
    private final Path web;
    private final HttpServer server;
    private final ExecutorService executor = Executors.newFixedThreadPool(8);
    private CloudNativeApp(Map<String, String> env) throws IOException {
        var redis = new RedisClient(AddressPolicy.host(env), AddressPolicy.port(env),
            env.getOrDefault("REDIS_PASSWORD", ""), 600);
        inventory = new Inventory(redis, env.getOrDefault("LAB_NAMESPACE", "c11-demo"));
        web = Path.of(env.getOrDefault("WEB_ROOT", "web"));
        server = HttpServer.create(new InetSocketAddress(env.getOrDefault("BIND_HOST", "0.0.0.0"),
            Integer.parseInt(env.getOrDefault("HTTP_PORT", "8080"))), 32);
        server.createContext("/", this::handle);
        server.setExecutor(executor);
    }
    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("probe")) {
            var connection = (HttpURLConnection) URI.create("http://127.0.0.1:8080/" + args[1]).toURL().openConnection();
            connection.setConnectTimeout(1000); connection.setReadTimeout(1000);
            int code = connection.getResponseCode(); connection.disconnect();
            System.exit(code == 200 ? 0 : 1);
        }
        var app = new CloudNativeApp(System.getenv());
        Runtime.getRuntime().addShutdownHook(new Thread(app::stop, "drain-on-sigterm"));
        app.server.start();
        System.out.println("{\"event\":\"started\",\"port\":" + app.server.getAddress().getPort() + "}");
    }
    private void stop() {
        draining.set(true);
        System.out.println("{\"event\":\"drain_started\"}");
        server.stop(3); // 最多等待3秒；进程总预算由Docker stop_grace_period=6s约束。
        executor.shutdown();
        try { if (!executor.awaitTermination(1, TimeUnit.SECONDS)) executor.shutdownNow(); }
        catch (InterruptedException e) { executor.shutdownNow(); Thread.currentThread().interrupt(); }
        System.out.println("{\"event\":\"shutdown_completed\"}");
    }
    private void handle(HttpExchange x) throws IOException {
        try {
            String path = x.getRequestURI().getPath(), method = x.getRequestMethod();
            if (path.equals("/") && method.equals("GET")) {
                byte[] html = Files.readAllBytes(web.resolve("index.html"));
                x.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
                x.sendResponseHeaders(200, html.length); x.getResponseBody().write(html); return;
            }
            if ((path.equals("/live") || path.equals("/startup")) && method.equals("GET")) {
                reply(x, 200, "{\"status\":\"UP\"}"); return;
            }
            if (path.equals("/ready") && method.equals("GET")) {
                boolean ping = inventory.ping(), seeded = inventory.seeded();
                boolean ready = CloudPolicy.ready(ping, seeded, draining.get());
                reply(x, ready ? 200 : 503, "{\"status\":\"" + (ready ? "READY" : "NOT_READY") + "\",\"seeded\":" + seeded + "}"); return;
            }
            if (path.equals("/downstream-check") && method.equals("GET")) {
                if (!inventory.ping()) throw new RedisClient.Failure("PROTOCOL");
                reply(x, 200, "{\"status\":\"PONG\",\"layer\":\"APPLICATION\"}"); return;
            }
            if (path.equals("/seed") && method.equals("POST")) {
                boolean created = inventory.seed();
                reply(x, 200, "{\"created\":" + created + ",\"stock\":" + inventory.stock() + "}"); return;
            }
            if (path.equals("/stock") && method.equals("GET")) {
                int stock = inventory.stock();
                reply(x, stock < 0 ? 503 : 200, "{\"stock\":" + stock + "}"); return;
            }
            if (path.equals("/orders") && method.equals("POST")) {
                if (draining.get()) { reply(x, 503, "{\"error\":\"DRAINING\"}"); return; }
                Map<String, String> q = query(x.getRequestURI().getRawQuery());
                String id = q.getOrDefault("request_id", "");
                int qty = Integer.parseInt(q.getOrDefault("quantity", "0"));
                if (!id.matches("[a-zA-Z0-9_-]{1,40}") || qty < 1 || qty > 10) throw new IllegalArgumentException();
                String result = inventory.reserve(id, qty);
                String[] parts = result.split("\\|");
                if (parts.length == 2) {
                    reply(x, parts[0].equals("CREATED") ? 201 : 200, "{\"status\":\"" + parts[0] + "\",\"request_id\":\"" + id + "\",\"remaining\":" + parts[1] + "}");
                } else reply(x, result.equals("NOT_SEEDED") ? 503 : 409, "{\"error\":\"" + result + "\"}");
                return;
            }
            if (path.equals("/slow") && method.equals("GET")) {
                int millis = Integer.parseInt(query(x.getRequestURI().getRawQuery()).getOrDefault("millis", "1500"));
                if (millis < 0 || millis > 2000) throw new IllegalArgumentException();
                System.out.println("{\"event\":\"slow_started\"}");
                Thread.sleep(millis); reply(x, 200, "{\"status\":\"COMPLETED\"}"); return;
            }
            reply(x, 404, "{\"error\":\"NOT_FOUND\"}");
        } catch (RedisClient.Failure e) {
            reply(x, 503, "{\"error\":\"DEPENDENCY_UNAVAILABLE\",\"layer\":\"" + e.layer + "\"}");
        } catch (IllegalArgumentException e) {
            reply(x, 400, "{\"error\":\"INVALID_REQUEST\"}");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt(); reply(x, 503, "{\"error\":\"INTERRUPTED\"}");
        } finally { x.close(); }
    }
    private static Map<String, String> query(String raw) {
        Map<String, String> q = new HashMap<>();
        if (raw == null) return q;
        if (raw.length() > 512) throw new IllegalArgumentException();
        for (String pair : raw.split("&")) {
            String[] kv = pair.split("=", 2);
            if (kv.length != 2 || q.put(URLDecoder.decode(kv[0], StandardCharsets.UTF_8),
                    URLDecoder.decode(kv[1], StandardCharsets.UTF_8)) != null) throw new IllegalArgumentException();
        }
        return q;
    }
    private static void reply(HttpExchange x, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        x.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        x.getResponseHeaders().set("Cache-Control", "no-store");
        x.sendResponseHeaders(status, bytes.length); x.getResponseBody().write(bytes);
    }
}
