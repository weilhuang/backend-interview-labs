// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
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
        if (!(other instanceof TenantKey that)) return false;
        return userId == that.userId && tenant.equals(that.tenant);
    }
    @Override public int hashCode() {
        return 31 * tenant.hashCode() + Long.hashCode(userId);
    }
}
