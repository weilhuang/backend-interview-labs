package labs.jvm;

public final class LoaderLabUsage {
    public static void main(String[] args) throws Exception {
        System.out.println("两倍=" + LoaderLab.twice(3));
        System.out.println("常量=" + InitChild.CONSTANT + "，初始化事件=" + InitTrace.events);
        Class.forName("labs.jvm.InitChild", true, LoaderLab.class.getClassLoader());
        System.out.println("主动初始化=" + InitTrace.events);
    }
}
