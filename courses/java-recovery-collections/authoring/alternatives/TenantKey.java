package labs;
import java.util.Objects;
public final class TenantKey {
    private final String tenant;
    private final long userId;
    public TenantKey(String tenant, long userId) {
        Objects.requireNonNull(tenant, "tenant");
        if (tenant.isBlank() || userId <= 0) throw new IllegalArgumentException("invalid identity");
        this.tenant = tenant;
        this.userId = userId;
    }
    public String tenant() { return tenant; }
    public long userId() { return userId; }
    @Override public boolean equals(Object other) {
        if (this == other) return true;
        if (other == null || other.getClass() != TenantKey.class) return false;
        TenantKey that = (TenantKey) other;
        return userId == that.userId && tenant.equals(that.tenant);
    }
    @Override public int hashCode() {
        return Objects.hash(tenant, userId);
    }
}
