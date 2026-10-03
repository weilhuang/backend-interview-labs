package labs;

/** C11-02 的练习边界：进程存活与可接单就绪是两个判断。 */
public final class CloudPolicy {
    private CloudPolicy() {}
    public static boolean ready(boolean dependencyHealthy, boolean seeded, boolean draining) {
        return dependencyHealthy && seeded && !draining;
    }
}
