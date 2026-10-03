package labs.identity;
import com.nimbusds.jose.*;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.*;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.*;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
final class TokenFixture implements AutoCloseable {
    static final String ISSUER="https://issuer.fixture.invalid";
    final RSAKey k1, k2, attacker;
    final HttpServer server;
    final AtomicInteger requests=new AtomicInteger();
    volatile List<RSAKey> published;
    volatile boolean unavailable;
    TokenFixture() throws Exception {
        k1=new RSAKeyGenerator(2048).keyID("k1").generate();
        k2=new RSAKeyGenerator(2048).keyID("k2").generate();
        attacker=new RSAKeyGenerator(2048).keyID("k1").generate();
        published=List.of(k1);
        server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/jwks",exchange->{
            requests.incrementAndGet();
            String body=new JWKSet(published.stream().map(x -> (JWK)x.toPublicJWK()).toList()).toString();
            byte[] bytes=body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type","application/json");
            exchange.sendResponseHeaders(unavailable?503:200,bytes.length);
            try(var out=exchange.getResponseBody()){out.write(bytes);}
        });
        server.start();
    }
    String url(){return "http://127.0.0.1:"+server.getAddress().getPort()+"/jwks";}
    String token(Map<String,Object> overrides,RSAKey key, String kid) throws Exception {
        Instant now=Instant.now();
        var builder=new JWTClaimsSet.Builder().issuer(ISSUER).audience("orders-api").subject("fixture-alice")
            .expirationTime(Date.from(now.plusSeconds(300))).notBeforeTime(Date.from(now.minusSeconds(1)))
            .claim("typ","Bearer").claim("tenant_id","tenant-a").claim("tenant_roles",Map.of("tenant-a",List.of("reader")));
        overrides.forEach(builder::claim);
        var signed=new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).type(JOSEObjectType.JWT).keyID(kid).build(),builder.build());
        signed.sign(new RSASSASigner(key));return signed.serialize();
    }
    String token(Map<String,Object> overrides) throws Exception {return token(overrides,k1,"k1");}
    @Override public void close(){server.stop(0);}
    static final class MutableClock extends Clock {
        private Instant now=Instant.now();
        void advance(){now=now.plusSeconds(2);}
        @Override public ZoneId getZone(){return ZoneOffset.UTC;}
        @Override public Clock withZone(ZoneId zone){return this;}
        @Override public Instant instant(){return now;}
    }
}
