package labs.observability;
import java.time.Instant;
import java.util.Map;
public final class Usage {
 public static void main(String[] args) {
  String event=new SafeEvents().encode(Instant.parse("2026-10-01T00:00:00Z"),"checkout","/checkout",200,
   "0123456789abcdef0123456789abcdef","0123456789abcdef",12_000_000,Map.of("Authorization","synthetic-secret"));
  System.out.println(event);
  System.out.println("上面是固定输入示例，不是服务或后端实测记录");
 }
}
