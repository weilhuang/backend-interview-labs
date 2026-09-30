package labs.foundation;

import java.util.*;

/** 教学数组容器：不实现完整List、迭代器、序列化或线程安全。 */
public final class MiniArrayList<E> {
    private Object[] elements = new Object[0];
    private int size;

    public int size() {
        return size;
    }

    public int capacity() {
        return elements.length;
    }

    public void add(E value) {
        // 作答开始
        if (size == 4096) throw new IllegalStateException("教学上限4096项");
        if (size == elements.length)
            elements =
                    Arrays.copyOf(
                            elements,
                            Math.min(
                                    4096,
                                    Math.max(
                                            1,
                                            elements.length + Math.max(1, elements.length / 2))));
        elements[size++] = value;
        // 作答结束
    }

    @SuppressWarnings("unchecked")
    public E get(int index) {
        Objects.checkIndex(index, size);
        return (E) elements[index];
    }

    public E set(int index, E value) {
        E old = get(index);
        elements[index] = value;
        return old;
    }

    public E remove(int index) {
        // 作答开始
        E old = get(index);
        int moved = size - index - 1;
        if (moved > 0) System.arraycopy(elements, index + 1, elements, index, moved);
        elements[--size] = null;
        return old;
        // 作答结束
    }

    public boolean unusedSlotsCleared() {
        for (int i = size; i < elements.length; i++) if (elements[i] != null) return false;
        return true;
    }

    public List<E> snapshot() {
        List<E> result = new ArrayList<>();
        for (int i = 0; i < size; i++) result.add(get(i));
        return Collections.unmodifiableList(result);
    }
}
