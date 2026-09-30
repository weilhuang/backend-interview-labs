package labs.foundation;

import java.util.*;

/** 教学双向链表及队列应用；节点不向调用方暴露。 */
public final class LinkedAlgorithms<E> {
    private static final class Link<E> {
        E value;
        Link<E> previous, next;

        Link(E value) {
            this.value = value;
        }
    }

    private Link<E> first, last;
    private int size;

    public int size() {
        return size;
    }

    public void addFirst(E value) {
        if (size == 4096) throw new IllegalStateException("最多4096项");
        Link<E> node = new Link<>(value);
        node.next = first;
        if (first == null) last = node;
        else first.previous = node;
        first = node;
        size++;
    }

    public void addLast(E value) {
        if (size == 4096) throw new IllegalStateException("最多4096项");
        Link<E> node = new Link<>(value);
        node.previous = last;
        if (last == null) first = node;
        else last.next = node;
        last = node;
        size++;
    }

    public E removeFirst() {
        // 作答开始
        if (first == null) throw new NoSuchElementException("链表为空");
        Link<E> removed = first;
        first = removed.next;
        if (first == null) last = null;
        else first.previous = null;
        removed.next = null;
        size--;
        return removed.value;
        // 作答结束
    }

    public E removeLast() {
        if (last == null) throw new NoSuchElementException("链表为空");
        Link<E> removed = last;
        last = removed.previous;
        if (last == null) first = null;
        else last.next = null;
        removed.previous = null;
        size--;
        return removed.value;
    }

    public E get(int index) {
        Objects.checkIndex(index, size);
        Link<E> node;
        if (index < size / 2) {
            node = first;
            for (int i = 0; i < index; i++) node = node.next;
        } else {
            node = last;
            for (int i = size - 1; i > index; i--) node = node.previous;
        }
        return node.value;
    }

    public boolean invariants() {
        if (size == 0) return first == null && last == null;
        if (first == null || last == null || first.previous != null || last.next != null)
            return false;
        int count = 0;
        Link<E> previous = null;
        for (Link<E> n = first; n != null; n = n.next) {
            if (n.previous != previous || ++count > size) return false;
            previous = n;
        }
        return count == size && previous == last;
    }

    public static List<Integer> bfs(Map<Integer, List<Integer>> graph, int start) {
        List<Integer> result = new ArrayList<>();
        Deque<Integer> queue = new ArrayDeque<>();
        Set<Integer> seen = new HashSet<>();
        seen.add(start);
        queue.add(start);
        while (!queue.isEmpty()) {
            int node = queue.removeFirst();
            result.add(node);
            if (result.size() > 10000) throw new IllegalArgumentException("图超出10000节点");
            for (int next : graph.getOrDefault(node, List.of()))
                if (seen.add(next)) queue.addLast(next);
        }
        return List.copyOf(result);
    }

    public static List<Integer> windowMaximum(int[] values, int k) {
        // 作答开始
        if (values.length == 0 && k == 0) return List.of();
        if (k < 1 || k > values.length) throw new IllegalArgumentException("非空窗口须为1至数组长度");
        Deque<Integer> queue = new ArrayDeque<>();
        List<Integer> result = new ArrayList<>();
        for (int i = 0; i < values.length; i++) {
            while (!queue.isEmpty() && queue.peekFirst() <= i - k) queue.removeFirst();
            while (!queue.isEmpty() && values[queue.peekLast()] <= values[i]) queue.removeLast();
            queue.addLast(i);
            if (i >= k - 1) result.add(values[queue.peekFirst()]);
        }
        return List.copyOf(result);
        // 作答结束
    }
}
