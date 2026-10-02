package labs.observability;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.env.Environment;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.Map;
import java.util.Set;

@RestController @ConditionalOnProperty(name="lab.role",havingValue="checkout",matchIfMissing=true)
public final class CheckoutController {
    private final Telemetry telemetry; private final HttpClient client; private final URI inventory;
    public CheckoutController(Telemetry t, Environment env) {
        telemetry=t;client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build();
        inventory=URI.create(env.getProperty("lab.inventory","http://127.0.0.1:18082"));
        if(!Set.of("127.0.0.1","localhost","inventory").contains(inventory.getHost()) || inventory.getUserInfo()!=null || !"http".equals(inventory.getScheme())) throw new IllegalArgumentException("local inventory only");
    }
    public record Checkout(String sku,String scenario) {}
    @PostMapping("/checkout") public ResponseEntity<Map<String,Object>> checkout(@RequestBody Checkout command) {
        if(!Set.of("book","pen").contains(command.sku()==null?"":command.sku()) || !Set.of("ok","fail","retry").contains(command.scenario()==null?"":command.scenario()))
            return ResponseEntity.badRequest().body(Map.of("result","invalid_input"));
        int attempts=command.scenario().equals("retry")?2:1;
        for(int attempt=1;attempt<=attempts;attempt++) {
            Span child=telemetry.bridge.client("GET /inventory/{sku}");
            child.setAttribute("http.request.method","GET"); child.setAttribute("server.address",inventory.getHost());
            child.setAttribute("server.port",inventory.getPort()); child.setAttribute("lab.attempt",attempt);
            try(Scope scope=child.makeCurrent()) {
                HttpRequest.Builder request=HttpRequest.newBuilder(inventory.resolve("/inventory/"+command.sku()+"?scenario="+command.scenario()+"&attempt="+attempt))
                    .timeout(Duration.ofSeconds(2)).GET();
                telemetry.bridge.inject(Context.current()).forEach(request::header);
                HttpResponse<String> result=client.send(request.build(),HttpResponse.BodyHandlers.ofString());
                child.setAttribute("http.response.status_code",result.statusCode());
                if(result.statusCode()>=400) { child.setStatus(StatusCode.ERROR); child.setAttribute("error.type",Integer.toString(result.statusCode())); }
                if(result.statusCode()==200) return ResponseEntity.ok(Map.of("result","confirmed","attempts",attempt));
                if(result.statusCode()!=503) break;
            } catch(InterruptedException failure) {
                Thread.currentThread().interrupt();child.setStatus(StatusCode.ERROR);child.setAttribute("error.type","interrupted");break;
            } catch(java.io.IOException failure) {
                child.setStatus(StatusCode.ERROR);child.setAttribute("error.type","transport");break;
            } finally { child.end(); }
        }
        return ResponseEntity.status(503).body(Map.of("result","inventory_unavailable"));
    }
}
