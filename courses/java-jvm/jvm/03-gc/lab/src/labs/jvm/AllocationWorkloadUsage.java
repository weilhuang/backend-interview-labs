package labs.jvm;

public final class AllocationWorkloadUsage {
    public static void main(String[] args) {
        int rounds = args.length == 0 ? 4096 : Integer.parseInt(args[0]);
        System.out.println("受控分配=" + AllocationWorkload.run(rounds, 65536, 8));
    }
}
