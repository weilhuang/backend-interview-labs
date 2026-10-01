package labs.jvm;

public final class AllocationWorkload {
    public record Result(long checksum, long allocatedBytes, int peakPayloadBytes) {}

    private AllocationWorkload() {}

    public static Result run(int rounds, int blockSize, int liveBlocks) {
        // 作答开始
        if (rounds < 0
                || rounds > 4096
                || blockSize < 1
                || blockSize > 65536
                || liveBlocks < 1
                || liveBlocks > 8) throw new IllegalArgumentException("参数超出安全预算");
        byte[][] ring = new byte[liveBlocks][];
        long checksum = 0;
        for (int i = 0; i < rounds; i++) {
            byte[] block = new byte[blockSize];
            java.util.Arrays.fill(block, (byte) (i % 127));
            ring[i % liveBlocks] = block;
            checksum += Byte.toUnsignedInt(block[0]) + Byte.toUnsignedInt(block[blockSize - 1]);
        }
        // 有意让有界存活集参与结果，避免把GC观察误读成纯分配优化。
        for (byte[] block : ring) if (block != null) checksum += Byte.toUnsignedInt(block[0]);
        return new Result(
                checksum, (long) rounds * blockSize, Math.min(rounds, liveBlocks) * blockSize);
        // 作答结束
    }
}
