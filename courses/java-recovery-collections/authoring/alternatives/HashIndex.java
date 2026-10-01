package labs;
public final class HashIndex {
    private HashIndex() {}
    public static int spread(int hash) {
        return hash ^ (hash >>> 16);
    }
    public static int index(int hash, int capacity) {
        if (capacity <= 0 || (capacity & (capacity - 1)) != 0)
            throw new IllegalArgumentException("capacity must be a positive power of two");
        return Integer.remainderUnsigned(spread(hash), capacity);
    }
}
