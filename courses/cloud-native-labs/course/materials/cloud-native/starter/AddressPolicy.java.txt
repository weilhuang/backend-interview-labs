package labs;
import java.util.Map;
public final class AddressPolicy {
    public static String host(Map<String,String> env) { return "localhost"; }
    public static int port(Map<String,String> env) { return 6379; }
}
