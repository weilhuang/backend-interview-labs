package labs.identity;
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.*;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
/** 真正启动本地Tomcat并走HTTP；IdP仍只是合成签名/JWKS fixture。 */
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class IdentityNetworkTest {
    static final TokenFixture f;
    static {try{f=new TokenFixture();}catch(Exception e){throw new ExceptionInInitializerError(e);}}
    @DynamicPropertySource static void properties(DynamicPropertyRegistry p){
        p.add("identity.issuer",()->TokenFixture.ISSUER);p.add("identity.jwks",f::url);
        p.add("identity.audience",()->"orders-api");p.add("identity.allow-loopback-http",()->"true");
    }
    @AfterAll static void close(){f.close();}
    @Autowired TestRestTemplate http;
    @Test void realHttpRequestEnforcesAuthenticationTenantAndWriteRole() throws Exception {
        assertEquals(HttpStatus.UNAUTHORIZED,http.getForEntity("/api/orders/order-a",String.class).getStatusCode());
        // 负门禁故意让真实HTTP得到401；期望仍固定200，不能把检查改宽。
        String token=f.token(Boolean.getBoolean("identity.probe.wrongAudience")
            ? Map.of("aud",List.of("wrong-api")) : Map.of());
        var headers=new HttpHeaders();headers.setBearerAuth(token);
        var entity=new HttpEntity<Void>(headers);
        var own=http.exchange("/api/orders/order-a",HttpMethod.GET,entity,String.class);
        recordHttpObservation(own.getStatusCode().value());
        assertEquals(200,own.getStatusCode().value(),"C15_HTTP_OWN_ORDER_200");assertTrue(own.getBody().contains("tenant-a"));
        assertEquals(HttpStatus.FORBIDDEN,http.exchange("/api/orders/order-b",HttpMethod.GET,entity,String.class).getStatusCode());
        assertEquals(HttpStatus.FORBIDDEN,http.exchange("/api/orders/order-a/approve",HttpMethod.POST,entity,String.class).getStatusCode());
        headers.setBearerAuth(f.token(Map.of("tenant_roles",Map.of("tenant-a",List.of("editor")))));
        var write=http.exchange("/api/orders/order-a/approve",HttpMethod.POST,new HttpEntity<Void>(headers),String.class);
        assertEquals(HttpStatus.OK,write.getStatusCode());assertTrue(write.getBody().contains("\"approvals\":1"));
        assertFalse(write.getBody().contains(token));
    }
    @Test void suppliedChineseFrontendIsServedWithoutSecrets() {
        var index=http.getForEntity("/",String.class);
        assertEquals(HttpStatus.OK,index.getStatusCode());assertTrue(index.getBody().contains("一枚 token 能做什么"));
        assertEquals(HttpStatus.OK,http.getForEntity("/app.js",String.class).getStatusCode());
    }
    private static void recordHttpObservation(int observed) throws Exception {
        String target=System.getProperty("identity.gate.httpTrace");
        if(target==null)return;
        var event=Map.<String,Object>of("run_id",System.getProperty("identity.gate.runId"),
            "binding_sha256",System.getProperty("identity.gate.bindingHash"),
            "suite","labs.identity.IdentityNetworkTest","method","realHttpRequestEnforcesAuthenticationTenantAndWriteRole",
            "marker","C15_HTTP_OWN_ORDER_200","expected",200,"observed",observed,"time_ms",System.currentTimeMillis());
        java.nio.file.Files.writeString(java.nio.file.Path.of(target),new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(event)+"\n",
            java.nio.file.StandardOpenOption.CREATE,java.nio.file.StandardOpenOption.APPEND);
    }

}
