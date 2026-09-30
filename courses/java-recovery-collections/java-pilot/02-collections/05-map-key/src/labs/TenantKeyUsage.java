package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class TenantKeyUsage {
    private TenantKeyUsage() {}

    public static void main(String[] args) {
        Map<TenantKey, String> users = new HashMap<>();
        users.put(new TenantKey("acme", 7), "用户甲");
        TenantKey equivalent = new TenantKey(new String("acme"), 7);
        System.out.println("查到用户=" + users.get(equivalent));
        System.out.println("条目数量=" + users.size());
    }
}
