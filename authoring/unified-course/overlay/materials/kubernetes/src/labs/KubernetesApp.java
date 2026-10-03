package labs;

import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** 完整可见服务，继承C11-01..03的Redis库存与幂等接口，不依赖Spring。 */
public final class KubernetesApp {
    private final AppConfig config;
    private final Inventory inventory;
    private final HttpServer server;
    private final ExecutorService executor = Executors.newFixedThreadPool(8);
    private final AtomicBoolean draining = new AtomicBoolean(false);
    private volatile boolean lastDependencyHealthy = true;
    private final long started = System.nanoTime();
    private KubernetesApp(AppConfig config) throws IOException {
        this.config = config;
        // 本地合成故障随进程重建消失；emptyDir本身不会随容器重启清空。
        Files.deleteIfExists(Path.of("/tmp/course-flags/not-live"));
        inventory = new Inventory(new RedisClient(config.redisHost(), config.redisPort(), config.redisPassword(), 600), config.namespace());
        server = HttpServer.create(new InetSocketAddress("0.0.0.0", 8080), 32);
        server.createContext("/", this::handle);
        server.setExecutor(executor);
    }
    public static void main(String[] args) {
        try {
            var app = new KubernetesApp(AppConfig.load(System.getenv()));
            Runtime.getRuntime().addShutdownHook(new Thread(app::stop, "course-drain"));
            app.server.start();
            System.out.println("{\"event\":\"started\"}");
        } catch (Exception e) {
            // 故意不记录Throwable/环境对象：异常可能含配置路径或敏感输入。
            System.err.println("{\"event\":\"startup_configuration_invalid\"}"); System.exit(2);
        }
    }
    private boolean initialized() { return (System.nanoTime()-started)/1_000_000 >= config.startupDelayMs(); }
    private static boolean flag(String name) { return Files.exists(Path.of("/tmp/course-flags", name)); }
    private boolean dependencyHealthy() {
        try { return lastDependencyHealthy = inventory.ping(); }
        catch (IOException e) { return lastDependencyHealthy = false; }
    }
    private boolean seeded() { try { return inventory.seeded(); } catch (IOException e) { return false; } }
    private void stop() {
        draining.set(true); System.out.println("{\"event\":\"drain_started\"}");
        server.stop(3); executor.shutdown();
        try { if (!executor.awaitTermination(1, TimeUnit.SECONDS)) executor.shutdownNow(); }
        catch (InterruptedException e) { executor.shutdownNow(); Thread.currentThread().interrupt(); }
        System.out.println("{\"event\":\"shutdown_completed\"}");
    }
    private void handle(HttpExchange x) throws IOException {
        try {
            String path=x.getRequestURI().getPath(), method=x.getRequestMethod();
            if (method.equals("GET") && path.equals("/startup")) { health(x,ProbePolicy.startup(initialized())); return; }
            if (method.equals("GET") && path.equals("/live")) {
                // live不访问Redis，否则探针也会被依赖延迟拖住。
                health(x,ProbePolicy.live(!initialized() || flag("not-live"), lastDependencyHealthy)); return;
            }
            if (method.equals("GET") && path.equals("/ready")) {
                health(x,ProbePolicy.ready(initialized(),dependencyHealthy(),seeded(),draining.get(),flag("not-ready") || config.release().equals("broken"))); return;
            }
            if (method.equals("GET") && path.equals("/downstream-check")) {
                health(x, inventory.ping()); return;
            }
            if (method.equals("GET") && path.equals("/info")) {
                reply(x,200,"{\"release\":\""+config.release()+"\",\"greetingEnv\":\""+config.greeting()+"\",\"bannerFile\":\""+config.banner()+"\"}"); return;
            }
            if (method.equals("GET") && path.equals("/")) {
                byte[] html=Files.readAllBytes(Path.of("/opt/app/web/index.html"));
                x.getResponseHeaders().set("Content-Type","text/html; charset=utf-8");
                x.sendResponseHeaders(200,html.length);x.getResponseBody().write(html);return;
            }
            if (method.equals("POST") && path.equals("/seed")) {
                boolean created=inventory.seed();reply(x,200,"{\"created\":"+created+",\"stock\":"+inventory.stock()+"}");return;
            }
            if (method.equals("GET") && path.equals("/stock")) {
                int stock=inventory.stock();reply(x,stock<0?503:200,"{\"stock\":"+stock+"}");return;
            }
            if (method.equals("POST") && path.equals("/orders")) {
                if (!ProbePolicy.ready(initialized(),dependencyHealthy(),seeded(),draining.get(),flag("not-ready") || config.release().equals("broken"))) {
                    reply(x,503,"{\"error\":\"NOT_READY\"}");return;
                }
                var q=query(x.getRequestURI().getRawQuery());String id=q.getOrDefault("request_id","");
                int qty=Integer.parseInt(q.getOrDefault("quantity","0"));
                if (!id.matches("[a-zA-Z0-9_-]{1,40}") || qty<1 || qty>10) throw new IllegalArgumentException();
                String[] parts=inventory.reserve(id,qty).split("\\|");
                if(parts.length==2) reply(x,parts[0].equals("CREATED")?201:200,"{\"status\":\""+parts[0]+"\",\"request_id\":\""+id+"\",\"remaining\":"+parts[1]+"}");
                else reply(x,parts[0].equals("NOT_SEEDED")?503:409,"{\"error\":\""+parts[0]+"\"}");return;
            }
            if(method.equals("GET") && path.equals("/slow")) {
                if(draining.get()){reply(x,503,"{\"error\":\"DRAINING\"}");return;}
                System.out.println("{\"event\":\"slow_started\"}");Thread.sleep(1500);
                reply(x,200,"{\"status\":\"COMPLETED\"}");return;
            }
            reply(x,404,"{\"error\":\"NOT_FOUND\"}");
        } catch(RedisClient.Failure e){reply(x,503,"{\"error\":\"DEPENDENCY_UNAVAILABLE\",\"layer\":\""+e.layer+"\"}");}
        catch(IllegalArgumentException e){reply(x,400,"{\"error\":\"INVALID_REQUEST\"}");}
        catch(InterruptedException e){Thread.currentThread().interrupt();reply(x,503,"{\"error\":\"INTERRUPTED\"}");}
        catch(IOException e){reply(x,503,"{\"error\":\"CONFIG_OR_IO_UNAVAILABLE\"}");}
        finally{x.close();}
    }
    private static Map<String,String> query(String raw){
        var result=new HashMap<String,String>();if(raw==null)return result;
        if(raw.length()>512)throw new IllegalArgumentException();
        for(String pair:raw.split("&")){String[] p=pair.split("=",2);if(p.length!=2 || result.put(URLDecoder.decode(p[0],StandardCharsets.UTF_8),URLDecoder.decode(p[1],StandardCharsets.UTF_8))!=null)throw new IllegalArgumentException();}
        return result;
    }
    private static void health(HttpExchange x,boolean ok)throws IOException{reply(x,ok?200:503,"{\"status\":\""+(ok?"UP":"DOWN")+"\"}");}
    private static void reply(HttpExchange x,int status,String body)throws IOException{
        byte[] bytes=body.getBytes(StandardCharsets.UTF_8);x.getResponseHeaders().set("Content-Type","application/json; charset=utf-8");
        x.getResponseHeaders().set("Cache-Control","no-store");x.sendResponseHeaders(status,bytes.length);x.getResponseBody().write(bytes);
    }
}
