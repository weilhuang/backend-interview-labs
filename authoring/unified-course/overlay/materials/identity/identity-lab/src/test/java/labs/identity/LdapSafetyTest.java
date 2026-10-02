package labs.identity;
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
class LdapSafetyTest {
    @Test void injectionAndEmptyBindRemainRejected() {
        assertEquals("(&(objectClass=inetOrgPerson)(uid=\\2a\\29\\28|\\28uid=\\2a\\29\\29))",LdapSafety.uidFilter("*)(|(uid=*))"));
        assertEquals("(&(objectClass=inetOrgPerson)(uid=\\e6\\9d\\8e))",LdapSafety.uidFilter("李"));
        assertThrows(IllegalArgumentException.class,()->LdapSafety.requireNonEmptyPassword(new char[0]));
        assertThrows(IllegalArgumentException.class,()->LdapSafety.uidFilter(""));
    }
}
