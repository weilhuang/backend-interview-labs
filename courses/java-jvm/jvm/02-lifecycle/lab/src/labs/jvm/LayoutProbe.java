package labs.jvm;

/** 数值依赖VM布局；不在正确性测试中固定对象大小。 */
public final class LayoutProbe {
    private record Sample(long number, Object reference) {}

    public static void main(String[] args) {
        System.out.println("VM=" + System.getProperty("java.vm.name"));
        System.out.println("版本=" + Runtime.version());
        System.out.println("架构=" + System.getProperty("os.arch"));
        System.out.println("Object浅大小=" + SizeAgent.shallowSize(new Object()));
        System.out.println("byte[0]浅大小=" + SizeAgent.shallowSize(new byte[0]));
        System.out.println("byte[1]浅大小=" + SizeAgent.shallowSize(new byte[1]));
        System.out.println("Object[3]浅大小=" + SizeAgent.shallowSize(new Object[3]));
        System.out.println("record浅大小=" + SizeAgent.shallowSize(new Sample(7, new byte[1024])));
        System.out.println("浅大小不包含引用对象；探针会改变逃逸条件，不能据此证明JIT消除了分配");
    }
}
