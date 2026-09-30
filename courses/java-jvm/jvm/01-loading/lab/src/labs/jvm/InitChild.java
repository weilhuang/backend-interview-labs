package labs.jvm;

public class InitChild extends InitParent {
    public static final int CONSTANT = 7;

    static {
        InitTrace.events.add("子类");
    }
}
