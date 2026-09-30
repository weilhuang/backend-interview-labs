package labs;

public final class AtomicLedgerUsage {
    public static void main(String[] args) {
        var ledger = new AtomicLedger(3);
        System.out.println("预留2=" + ledger.reserve(2));
        System.out.println("再次预留2=" + ledger.reserve(2));
        var slot = new AtomicLedger.VersionedSlot("A");
        var old = slot.snapshot();
        slot.replace(old, "B");
        slot.replace(slot.snapshot(), old.value());
        System.out.println("旧版本更新=" + slot.replace(old, "C"));
        var counts = new AtomicLedger.Counters();
        counts.increment("订单");
        System.out.println("计数=" + counts.snapshot());
    }
}
