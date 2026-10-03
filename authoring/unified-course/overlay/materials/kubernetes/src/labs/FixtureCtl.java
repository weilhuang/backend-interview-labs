package labs;
import java.nio.file.*;
import java.util.Set;
/** 只能通过已验证的课程pod exec调用，没有公开故障注入HTTP端点。 */
public final class FixtureCtl {
    public static void main(String[] args) throws Exception {
        if(args.length!=2 || !Set.of("not-ready","not-live").contains(args[0]) || !Set.of("on","off").contains(args[1])) throw new IllegalArgumentException("unsupported fixture");
        Path root=Path.of("/tmp/course-flags");Files.createDirectories(root);Path p=root.resolve(args[0]);
        if(args[1].equals("on"))Files.writeString(p,"synthetic\n");else Files.deleteIfExists(p);
        System.out.println("{\"fixture\":\""+args[0]+"\",\"state\":\""+args[1]+"\"}");
    }
}
