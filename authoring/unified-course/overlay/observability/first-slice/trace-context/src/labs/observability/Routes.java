package labs.observability;
import java.util.Set;
public final class Routes {
    private static final Set<String> KNOWN = Set.of("/checkout", "/inventory/{sku}", "/ready");
    private Routes() {}
    /** Only a framework-matched template is permitted, never request URI or query. */
    public static String safe(String matchedTemplate) {
        return KNOWN.contains(matchedTemplate == null ? "" : matchedTemplate) ? matchedTemplate : "UNMATCHED";
    }
}
