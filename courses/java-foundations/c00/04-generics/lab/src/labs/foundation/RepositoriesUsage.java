package labs.foundation;

public final class RepositoriesUsage {
    public static void main(String[] args) {
        var repo = new Repositories.MemoryRepository<String, Order>(Order::id);
        repo.saveAll(java.util.List.of(new Order("A", "甲", 200, Order.Status.PAID)));
        System.out.println("查找=" + repo.find("A"));
        System.out.println(
                "汇总=" + Repositories.streamTotals(java.util.List.of(repo.find("A").orElseThrow())));
    }
}
