package labs.identity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
/** Spring 过滤器与控制器集成：真实签名、真实本地HTTP JWKS；MockMvc不是外部网络E2E。 */
@SpringBootTest
@AutoConfigureMockMvc
class IdentityHttpTest {
    static final TokenFixture f;
    static {try{f=new TokenFixture();}catch(Exception e){throw new ExceptionInInitializerError(e);}}
    @DynamicPropertySource static void properties(DynamicPropertyRegistry p){
        p.add("identity.issuer",()->TokenFixture.ISSUER);p.add("identity.jwks",f::url);
        p.add("identity.audience",()->"orders-api");p.add("identity.allow-loopback-http",()->"true");
    }
    @AfterAll static void close(){f.close();}
    @Autowired MockMvc mvc;
    @Test void noTokenIs401() throws Exception {mvc.perform(get("/api/orders/order-a")).andExpect(status().isUnauthorized());}
    @Test void readerCanReadOwnTenant() throws Exception {mvc.perform(get("/api/orders/order-a").header("Authorization","Bearer "+f.token(Map.of())))
        .andExpect(status().isOk()).andExpect(jsonPath("$.tenant").value("tenant-a"));}
    @Test void readerCannotWriteAndStateStaysUnchanged() throws Exception {
        String token=f.token(Map.of());
        mvc.perform(post("/api/orders/order-a/approve").header("Authorization","Bearer "+token)).andExpect(status().isForbidden());
        mvc.perform(get("/api/orders/order-a").header("Authorization","Bearer "+token)).andExpect(jsonPath("$.approvals").value(0));
    }
    @Test void crossTenantAdminDeniedEvenWithForgedHeaders() throws Exception {
        String token=f.token(Map.of("tenant_roles",Map.of("tenant-a",List.of("admin"))));
        mvc.perform(get("/api/orders/order-b").header("Authorization","Bearer "+token).header("X-Tenant","tenant-b").header("X-Role","admin"))
            .andExpect(status().isForbidden());
    }
    @Test void rolesFromOtherTenantDoNotLeak() throws Exception {
        String token=f.token(Map.of("tenant_roles",Map.of("tenant-b",List.of("admin")),"realm_access",Map.of("roles",List.of("admin"))));
        mvc.perform(get("/api/orders/order-a").header("Authorization","Bearer "+token)).andExpect(status().isForbidden());
    }
    @Test void wrongAudienceFailsBeforeBusinessAuthorization() throws Exception {
        mvc.perform(get("/api/orders/order-a").header("Authorization","Bearer "+f.token(Map.of("aud",List.of("other-api")))))
            .andExpect(status().isUnauthorized());
    }
    @Test void editorCanApproveOwnTenantAndMutationIsVisible() throws Exception {
        String token=f.token(Map.of("tenant_id","tenant-b","tenant_roles",Map.of("tenant-b",List.of("editor"))));
        mvc.perform(post("/api/orders/order-b/approve").header("Authorization","Bearer "+token))
            .andExpect(status().isOk()).andExpect(jsonPath("$.approvals").value(1));
        mvc.perform(get("/api/orders/order-b").header("Authorization","Bearer "+token))
            .andExpect(status().isOk()).andExpect(jsonPath("$.approvals").value(1));
    }

}
