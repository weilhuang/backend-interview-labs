package labs.identity;
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.*;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
class IdentityTokenDecoderTest {
    TokenFixture f; TokenFixture.MutableClock clock; JwtDecoder decoder;
    @BeforeEach void before() throws Exception {
        f=new TokenFixture();clock=new TokenFixture.MutableClock();
        decoder=IdentityTokenDecoder.create(TokenFixture.ISSUER,f.url(),"orders-api",true,clock);
    }
    @AfterEach void after(){f.close();}
    @Test void validatesRealSignatureAndTrustedClaims() throws Exception {
        assertEquals("fixture-alice",decoder.decode(f.token(Map.of())).getSubject());assertEquals(1,f.requests.get());
    }
    @Test void rejectsWrongIssuerAudienceExpiryFutureNbfAndIdToken() throws Exception {
        List<Map<String,Object>> cases=List.of(Map.of("iss","https://evil.invalid"),Map.of("aud",List.of("other-api")),
            Map.of("exp",Date.from(Instant.now().minusSeconds(10))),Map.of("nbf",Date.from(Instant.now().plusSeconds(600))),Map.of("typ","ID"));
        for(var c:cases){String token=f.token(c);assertThrows(JwtException.class,()->decoder.decode(token),"C15-06 "+c.keySet());}
    }
    @Test void rejectsForgedSignature() throws Exception {
        String token=f.token(Map.of(),f.attacker,"k1");assertThrows(JwtException.class,()->decoder.decode(token));
    }
    @Test void rotationRefreshesOnceAndOverlapsOldKey() throws Exception {
        decoder.decode(f.token(Map.of()));clock.advance();f.published=List.of(f.k1,f.k2);
        assertEquals("fixture-alice",decoder.decode(f.token(Map.of(),f.k2,"k2")).getSubject());
        decoder.decode(f.token(Map.of()));assertEquals(2,f.requests.get());
    }
    @Test void unknownKidsCannotExhaustRemoteWithUnboundedFetches() throws Exception {
        decoder.decode(f.token(Map.of()));
        for(int i=0;i<20;i++){String token=f.token(Map.of(),f.k2,"unknown-"+i);assertThrows(JwtException.class,()->decoder.decode(token));}
        assertEquals(1,f.requests.get(),"一秒内共用全局远程预算，与攻击者kid数量无关");
    }
    @Test void jwksOutageRejectsUnknownKeyButKnownCachedKeyStillVerifies() throws Exception {
        decoder.decode(f.token(Map.of()));clock.advance();f.unavailable=true;
        String token=f.token(Map.of(),f.k2,"k2");assertThrows(JwtException.class,()->decoder.decode(token));
        assertEquals("fixture-alice",decoder.decode(f.token(Map.of())).getSubject());
    }
    @Test void insecureNonLoopbackEndpointIsRejected() {
        assertThrows(IllegalArgumentException.class,()->IdentityTokenDecoder.create(TokenFixture.ISSUER,"http://example.com/jwks","orders-api",true,clock));
        assertThrows(IllegalArgumentException.class,()->IdentityTokenDecoder.create(TokenFixture.ISSUER,f.url(),"orders-api",false,clock));
    }
    @Test void missingExpiryIsRejected() throws Exception {
        var claims=new java.util.HashMap<String,Object>();claims.put("exp",null);
        String token=f.token(claims);assertThrows(JwtException.class,()->decoder.decode(token));
    }
    @Test void noneAndAlgorithmConfusionAreRejected() throws Exception {
        var claims=new com.nimbusds.jwt.JWTClaimsSet.Builder().issuer(TokenFixture.ISSUER).subject("fixture")
            .audience("orders-api").expirationTime(Date.from(Instant.now().plusSeconds(300))).claim("typ","Bearer").build();
        String plain=new com.nimbusds.jwt.PlainJWT(claims).serialize();
        assertThrows(JwtException.class,()->decoder.decode(plain));
        var hmac=new com.nimbusds.jwt.SignedJWT(new com.nimbusds.jose.JWSHeader.Builder(com.nimbusds.jose.JWSAlgorithm.HS256).keyID("k1").build(),claims);
        hmac.sign(new com.nimbusds.jose.crypto.MACSigner(new byte[32]));
        assertThrows(JwtException.class,()->decoder.decode(hmac.serialize()));
        assertEquals(0,f.requests.get(),"不允许的算法在远程读取前拒绝");
    }
    @Test void attackerJkuCannotChooseTrustSource() throws Exception {
        var original=com.nimbusds.jwt.SignedJWT.parse(f.token(Map.of()));
        var forged=new com.nimbusds.jwt.SignedJWT(new com.nimbusds.jose.JWSHeader.Builder(com.nimbusds.jose.JWSAlgorithm.RS256)
            .type(com.nimbusds.jose.JOSEObjectType.JWT).keyID("k1").jwkURL(java.net.URI.create("http://127.0.0.1:1/attacker")).build(),original.getJWTClaimsSet());
        forged.sign(new com.nimbusds.jose.crypto.RSASSASigner(f.attacker));
        assertThrows(JwtException.class,()->decoder.decode(forged.serialize()));assertEquals(1,f.requests.get());
    }

}
