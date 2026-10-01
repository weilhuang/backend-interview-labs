package labs.foundation;

public final class LinkedAlgorithmsUsage {
    public static void main(String[] args) {
        var deque = new LinkedAlgorithms<String>();
        deque.addFirst("A");
        deque.addLast("B");
        System.out.println("出队=" + deque.removeFirst());
        System.out.println("窗口最大=" + LinkedAlgorithms.windowMaximum(new int[] {1, 3, 2, 5}, 2));
    }
}
