package labs.identity;
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Path;
import java.util.Collections;
import java.util.jar.JarFile;
import org.junit.jupiter.api.Test;

/** 新门禁：不是源码字符串猜测，Java执行时核对实际加载类的来源与生产jar内容。 */
class ProductionPolicyOriginTest {
    @Test void loadedPolicyComesFromExactlyTheLearnerJar() throws Exception {
        Path expected=Path.of(System.getProperty("identity.expectedPolicyJar")).toRealPath();
        Path actual=Path.of(Policy.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
        assertEquals(expected,actual,"服务必须实际加载学员模块唯一Policy jar");
        var locations=Collections.list(Policy.class.getClassLoader().getResources("labs/identity/Policy.class"));
        assertEquals(1,locations.size(),"不能有资源服务本地副本、test副本或第二个依赖覆盖Policy");
        assertTrue(locations.getFirst().toString().startsWith("jar:"),"不能悄悄改成IDE输出目录");
    }
    @Test void productionJarContainsNoReferenceAnswers() throws Exception {
        assertThrows(NoSuchMethodException.class,()->Policy.class.getDeclaredMethod(
            "authorizeExplicit",Policy.Subject.class,String.class,Policy.Resource.class));
        try(var jar=new JarFile(System.getProperty("identity.expectedPolicyJar"))){
            var names=jar.stream().map(e->e.getName()).toList();
            assertTrue(names.contains("labs/identity/Policy.class"));
            assertTrue(names.stream().noneMatch(n->n.contains("reference/")||n.contains("answer")
                ||n.contains("Explicit")||n.contains("Solution")||n.endsWith("Test.class")),
                "答案目录、替代实现和测试不能进入生产Policy jar");
        }
    }
}
