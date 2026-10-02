package labs.observability;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import java.nio.file.Path;

@SpringBootApplication
public class ObservabilityApplication {
    public static void main(String[] args) { SpringApplication.run(ObservabilityApplication.class,args); }
    @Bean @ConditionalOnMissingBean Telemetry telemetry(Environment env) {
        return Telemetry.otlp(env.getProperty("lab.role","checkout"), env.getProperty("lab.otlp","http://127.0.0.1:4318"),
            Double.parseDouble(env.getProperty("lab.sample-ratio","1.0")));
    }
    @Bean @ConditionalOnMissingBean EventSink eventSink(Environment env) {
        return new EventSink(Path.of(env.getProperty("lab.events","evidence/"+env.getProperty("lab.role","checkout")+".ndjson")));
    }
    @Bean SafeEvents safeEvents() { return new SafeEvents(); }
}
