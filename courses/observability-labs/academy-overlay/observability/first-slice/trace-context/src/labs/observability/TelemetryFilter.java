package labs.observability;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.stereotype.Component;
import org.springframework.core.env.Environment;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;
import java.util.Map;
import java.util.HashMap;
import java.time.Instant;
import java.io.IOException;

@Component
public final class TelemetryFilter extends OncePerRequestFilter {
    private final Telemetry telemetry; private final SafeEvents events; private final EventSink sink; private final String role;
    public TelemetryFilter(Telemetry t, SafeEvents e, EventSink s, Environment env) {
        telemetry=t;events=e;sink=s;role=env.getProperty("lab.role","checkout");
    }
    protected boolean shouldNotFilter(HttpServletRequest request) { return !request.getRequestURI().startsWith("/checkout") && !request.getRequestURI().startsWith("/inventory/"); }
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException,IOException {
        Map<String,String> incoming=new HashMap<>();
        for(String key: java.util.List.of("traceparent","tracestate")) {
            String value=request.getHeader(key); if(value!=null) incoming.put(key,value);
        }
        Span span=telemetry.bridge.server(request.getMethod(),incoming);
        span.setAttribute("http.request.method",request.getMethod()); span.setAttribute("url.scheme","http");
        response.setHeader("X-Trace-Id",span.getSpanContext().getTraceId());
        long start=System.nanoTime(); int status=500;
        try(Scope ignored=span.makeCurrent()) {
            chain.doFilter(request,response); status=response.getStatus();
        } finally {
            long elapsed=Math.max(0,System.nanoTime()-start);
            Object matched=request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            String route=Routes.safe(matched==null?null:matched.toString());
            span.updateName(request.getMethod()+" "+route);
            if(!route.equals("UNMATCHED")) span.setAttribute("http.route",route);
            span.setAttribute("http.response.status_code",status);
            if(status>=500) { span.setStatus(StatusCode.ERROR); span.setAttribute("error.type",Integer.toString(status)); }
            telemetry.metrics.observe(request.getMethod(),route,status,elapsed);
            sink.accept(events.encode(Instant.now(),role,route,status,span.getSpanContext().getTraceId(),span.getSpanContext().getSpanId(),elapsed,Map.of()));
            span.end();
        }
    }
}
