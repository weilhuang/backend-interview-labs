package labs;

import java.util.List;

public final class PublicationLabUsage {
    public static void main(String[] args) throws Exception {
        var lab = new PublicationLab();
        lab.publish(new PublicationLab.Snapshot(1, List.of("/orders")));
        System.out.println("配置=" + lab.current());
        System.out.println("受理序号=" + lab.accept());
        System.out.println("受控错误计数=" + PublicationLab.forcedLostUpdate());
    }
}
