package labs.capstone;

import java.util.concurrent.CountDownLatch;

/** 独立进程：订单HTTP服务不能共享接收端的本地事务。 */
public final class DeliveryMain {
    public static void main(String[] args) throws Exception {
        Config config = Config.environment();
        Database db = new Database(config.jdbc(), config.user(), config.password());
        db.initialize();
        DeliveryRpc rpc = new DeliveryRpc(db, config.rpcPort());
        CountDownLatch stopped = new CountDownLatch(1);
        java.lang.Runtime.getRuntime()
                .addShutdownHook(
                        new Thread(
                                () -> {
                                    try {
                                        rpc.close();
                                    } finally {
                                        db.close();
                                        stopped.countDown();
                                    }
                                },
                                "课程RPC关闭"));
        System.out.println("配送读模型gRPC已监听：" + rpc.port());
        stopped.await();
    }
}
