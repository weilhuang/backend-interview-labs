package labs.foundation;

public final class AlgorithmsUsage {
    public static void main(String[] args) {
        System.out.println("两类字符最长窗口=" + Algorithms.longestAtMostTwo("eceba"));
        System.out.println("下界=" + Algorithms.lowerBound(new int[] {1, 2, 2, 4}, 2));
        System.out.println("最少硬币=" + Algorithms.minimumCoins(6, new int[] {1, 3, 4}));
    }
}
