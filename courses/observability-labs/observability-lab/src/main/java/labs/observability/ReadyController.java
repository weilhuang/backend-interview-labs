package labs.observability;
import org.springframework.web.bind.annotation.*;
import java.util.Map;
@RestController public final class ReadyController {
 @GetMapping("/ready") public Map<String,String> ready() { return Map.of("status","ready"); }
}
