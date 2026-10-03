package labs;
import java.util.Map;

/** 无第三方测试库的可见断言；由统一课程adapter调用，不是另建Gradle课程。 */
public final class PolicyContractTest {
    private static void check(boolean value, String why) { if (!value) throw new AssertionError(why); }
    public static void main(String[] args) {
        int count=0;
        for (boolean dep : new boolean[]{false,true}) for (boolean seed : new boolean[]{false,true}) for (boolean drain : new boolean[]{false,true}) {
            check(CloudPolicy.ready(dep,seed,drain)==(dep && seed && !drain),
                "ready requires dependency+seed and rejects draining: dep="+dep+" seed="+seed+" drain="+drain); count++;
        }
        var configured=Map.of("REDIS_HOST","redis","REDIS_PORT","6379");
        check(AddressPolicy.host(configured).equals("redis"),"container must use injected service DNS"); count++;
        check(AddressPolicy.port(configured)==6379,"must use injected container port");count++;
        check(AddressPolicy.host(Map.of("REDIS_HOST","inventory-blue","REDIS_PORT","16379")).equals("inventory-blue"),"explicit endpoint injection must work");count++;
        check(AddressPolicy.port(Map.of("REDIS_HOST","inventory-blue","REDIS_PORT","16379"))==16379,"explicit port injection must work");count++;
        for (String bad : new String[]{"0","65536","NaN"}) {
            boolean failed=false;
            try {AddressPolicy.port(Map.of("REDIS_PORT",bad));} catch(IllegalArgumentException e){failed=true;}
            check(failed,"invalid port must fail clearly: "+bad);count++;
        }
        System.out.println("PASS "+count+" policy cases");
    }
}
