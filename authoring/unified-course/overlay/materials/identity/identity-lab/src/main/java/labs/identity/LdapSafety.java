package labs.identity;
import java.nio.charset.StandardCharsets;
/** RFC4515 filter assertion value 转义；不是 DN 转义，也不是完整 LDAP 认证器。 */
public final class LdapSafety {
    private LdapSafety() { }
    public static String uidFilter(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 128) throw new IllegalArgumentException("uid invalid");
        StringBuilder out = new StringBuilder("(&(objectClass=inetOrgPerson)(uid=");
        for (byte raw : uid.getBytes(StandardCharsets.UTF_8)) {
            int b = raw & 255;
            // 非 ASCII UTF8 字节也逐字节十六进制转义，使表示唯一、容易检查。
            if (b == 0 || b == 40 || b == 41 || b == 42 || b == 92 || b >= 128)
                out.append('\\').append(String.format("%02x", b));
            else out.append((char)b);
        }
        return out.append("))").toString();
    }
    public static void requireNonEmptyPassword(char[] password) {
        if (password == null || password.length == 0) throw new IllegalArgumentException("empty bind password rejected");
    }
}
