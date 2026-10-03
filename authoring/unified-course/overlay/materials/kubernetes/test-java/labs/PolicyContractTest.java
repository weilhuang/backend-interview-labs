package labs;
import java.nio.file.*;
import java.util.*;
/** 无测试框架依赖的可见运行验证入口；必须JDK21真实执行后才能宣称通过。 */
public final class PolicyContractTest {
    private static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception{
        for(int bits=0;bits<32;bits++){
            boolean initialized=(bits&1)!=0,dependency=(bits&2)!=0,seeded=(bits&4)!=0,draining=(bits&8)!=0,forced=(bits&16)!=0;
            check(ProbePolicy.ready(initialized,dependency,seeded,draining,forced)==(initialized&&dependency&&seeded&&!draining&&!forced),"readiness truth table row "+bits);
        }
        check(!ProbePolicy.startup(false)&&ProbePolicy.startup(true),"startup gate");
        check(ProbePolicy.live(false,false)&&ProbePolicy.live(false,true),"dependency is not liveness");
        check(!ProbePolicy.live(true,false)&&!ProbePolicy.live(true,true),"local failure is liveness");
        Path dir=Files.createTempDirectory("c11-config-test");
        try{
            Path secret=dir.resolve("password"),banner=dir.resolve("banner"),release=dir.resolve("release");
            Files.writeString(secret,"synthetic-only-0000000000000000");Files.writeString(banner,"banner-v1");Files.writeString(release,"v1");
            var env=new HashMap<String,String>(Map.of("REDIS_HOST","redis","REDIS_PASSWORD_FILE",secret.toString(),"BANNER_FILE",banner.toString(),"RELEASE_FILE",release.toString()));
            var c=AppConfig.load(env);check(c.redisHost().equals("redis")&&c.redisPort()==6379,"service DNS config");
            check(!c.toString().contains(c.redisPassword()),"configuration redaction");
            Files.writeString(banner,"banner-v2");env.put("GREETING","hello-v2");
            check(c.banner().equals("banner-v2")&&c.greeting().equals("hello-v1"),"file reload versus env snapshot");
            for(String bad:List.of("localhost","127.0.0.1","","redis;cat")){
                env.put("REDIS_HOST",bad);boolean rejected=false;try{AppConfig.load(env);}catch(IllegalArgumentException e){rejected=true;}check(rejected,"invalid host not rejected");
            }
            env.put("REDIS_HOST","redis");env.put("REDIS_PORT","70000");boolean rejected=false;
            try{AppConfig.load(env);}catch(IllegalArgumentException e){rejected=true;}check(rejected,"invalid port not rejected");
        }finally{try(var paths=Files.walk(dir)){for(Path p:paths.sorted(Comparator.reverseOrder()).toList())Files.deleteIfExists(p);}}
        System.out.println("PASS: Java policy/config contracts (not Kubernetes E2E)");
    }
}
