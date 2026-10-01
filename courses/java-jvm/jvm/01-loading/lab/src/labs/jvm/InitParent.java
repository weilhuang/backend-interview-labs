package labs.jvm;

public class InitParent {
    static {
        InitTrace.events.add("父类");
    }
}
