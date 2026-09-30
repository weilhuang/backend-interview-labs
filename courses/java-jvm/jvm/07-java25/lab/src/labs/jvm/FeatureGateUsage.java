package labs.jvm;

public final class FeatureGateUsage {
    public static void main(String[] args) {
        for (var f : FeatureGate.jdk25Matrix())
            System.out.println(f.name() + "：" + f.state() + "，目标=" + f.targetRelease());
        System.out.println("JDK25为自选资料附录：已有环境才运行 scripts/version25.py；否则NOT_RUN，不影响毕业");
    }
}
