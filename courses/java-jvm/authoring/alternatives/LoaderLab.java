package labs.jvm;

import java.util.Objects;

public final class LoaderLab {
    private LoaderLab() {}

    public static ClassLoader isolated(String binaryName, byte[] classBytes, ClassLoader parent) {
        // 作答开始
        Objects.requireNonNull(binaryName, "类名不能为空");
        Objects.requireNonNull(classBytes, "字节码不能为空");
        if (binaryName.startsWith("java.")) throw new IllegalArgumentException("禁止覆盖平台类");
        byte[] copy = java.util.Arrays.copyOf(classBytes, classBytes.length);
        return new ClassLoader(parent) {
            @Override
            protected Class<?> loadClass(String name, boolean resolve)
                    throws ClassNotFoundException {
                synchronized (getClassLoadingLock(name)) {
                    Class<?> type = findLoadedClass(name);
                    if (type == null) {
                        if (name.equals(binaryName)) type = defineClass(name, copy, 0, copy.length);
                        else type = super.loadClass(name, false);
                    }
                    if (resolve) resolveClass(type);
                    return type;
                }
            }
        };
        // 作答结束
    }

    public static int twice(int x) {
        return x * 2;
    }
}
