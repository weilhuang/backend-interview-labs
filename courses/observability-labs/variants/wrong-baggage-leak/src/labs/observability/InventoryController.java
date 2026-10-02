package labs.observability;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import java.util.Map;
@RestController @ConditionalOnProperty(name="lab.role",havingValue="inventory")
public final class InventoryController {
    @GetMapping("/inventory/{sku}") public ResponseEntity<Map<String,Object>> get(@PathVariable String sku,
        @RequestParam(defaultValue="ok") String scenario,@RequestParam(defaultValue="1") int attempt) {
        if(!java.util.Set.of("book","pen").contains(sku)) return ResponseEntity.notFound().build();
        boolean failed=scenario.equals("fail") || (scenario.equals("retry")&&attempt==1);
        return ResponseEntity.status(failed?503:200).body(Map.of("available",!failed));
    }
}
