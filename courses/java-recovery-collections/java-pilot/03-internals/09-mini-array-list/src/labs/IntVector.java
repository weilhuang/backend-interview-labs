package labs;
import java.util.Arrays;
public final class IntVector {
    private int[] data = new int[0];
    private int size;
    public int size() { return size; }
    public int capacity() { return data.length; }
    public void add(int value) {
        if (size == data.length) data = Arrays.copyOf(data, data.length == 0 ? 1 : Math.multiplyExact(data.length, 2));
        data[size++] = value;
    }
    public int get(int index) { check(index); return data[index]; }
    public int removeAt(int index) {
        check(index);
        int old = data[index];
        System.arraycopy(data, index + 1, data, index, size - index - 1);
        data[--size] = 0;
        return old;
    }
    private void check(int index) {
        if (index < 0 || index >= size) throw new IndexOutOfBoundsException(index);
    }
}
