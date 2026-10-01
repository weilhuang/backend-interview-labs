package labs.capstone;

import static labs.capstone.Model.*;

import io.grpc.*;
import io.grpc.stub.StreamObserver;

import labs.capstone.protocol.*;

import java.io.IOException;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** 真正的HTTP/2 gRPC边界；结果未知的超时不能解释为数据库未提交。 */
public final class DeliveryRpc implements AutoCloseable {
    private final Server server;
    public final AtomicReference<Fault> nextFault = new AtomicReference<>(Fault.NONE);
    // 仅测试代码设置故障事件号，HTTP接口不会开放这个开关。
    public final AtomicReference<String> failBeforeEvent = new AtomicReference<>();

    public DeliveryRpc(Database db, int port) throws IOException {
        DeliveryStore store = new DeliveryStore(db);
        server =
                ServerBuilder.forPort(port)
                        .addService(
                                new DeliveryGrpc.DeliveryImplBase() {
                                    @Override
                                    public void apply(
                                            OrderEvent message, StreamObserver<Receipt> observer) {
                                        try {
                                            Event event = from(message);
                                            if (event.eventId().equals(failBeforeEvent.get())) {
                                                observer.onError(
                                                        Status.UNAVAILABLE
                                                                .withDescription("指定事件的RPC故障注入")
                                                                .asRuntimeException());
                                                return;
                                            }
                                            boolean duplicate =
                                                    store.apply(
                                                            event, nextFault.getAndSet(Fault.NONE));
                                            observer.onNext(
                                                    Receipt.newBuilder()
                                                            .setEventId(event.eventId())
                                                            .setDuplicate(duplicate)
                                                            .setStatus(event.status())
                                                            .build());
                                            observer.onCompleted();
                                        } catch (IllegalArgumentException | Conflict invalid) {
                                            observer.onError(
                                                    Status.INVALID_ARGUMENT
                                                            .withDescription(invalid.getMessage())
                                                            .asRuntimeException());
                                        } catch (Unknown lost) {
                                            observer.onError(
                                                    Status.DEADLINE_EXCEEDED
                                                            .withDescription(lost.getMessage())
                                                            .asRuntimeException());
                                        } catch (SQLException unavailable) {
                                            observer.onError(
                                                    Status.UNAVAILABLE
                                                            .withDescription("投影数据库暂不可用")
                                                            .asRuntimeException());
                                        }
                                    }

                                    @Override
                                    public void probe(
                                            ProbeRequest request,
                                            StreamObserver<Receipt> observer) {
                                        try {
                                            db.scalar("SELECT 1");
                                            observer.onNext(
                                                    Receipt.newBuilder()
                                                            .setStatus("READY")
                                                            .build());
                                            observer.onCompleted();
                                        } catch (SQLException failure) {
                                            observer.onError(
                                                    Status.UNAVAILABLE.asRuntimeException());
                                        }
                                    }
                                })
                        .build()
                        .start();
    }

    public int port() {
        return server.getPort();
    }

    public static OrderEvent to(Event e) {
        return OrderEvent.newBuilder()
                .setEventId(e.eventId())
                .setRequestId(e.requestId())
                .setSku(e.sku())
                .setQuantity(e.quantity())
                .setVersion(e.version())
                .setStatus(e.status())
                .build();
    }

    public static Event from(OrderEvent e) {
        return new Event(
                e.getEventId(),
                e.getRequestId(),
                e.getSku(),
                e.getQuantity(),
                e.getStatus(),
                e.getVersion());
    }

    public void close() {
        server.shutdown();
        boolean interrupted = false;
        try {
            if (!server.awaitTermination(3, TimeUnit.SECONDS)) {
                server.shutdownNow();
                if (!server.awaitTermination(2, TimeUnit.SECONDS))
                    throw new IllegalStateException("RPC线程未在关闭预算内退出");
            }
        } catch (InterruptedException e) {
            interrupted = true;
            server.shutdownNow();
        } finally {
            if (interrupted) Thread.currentThread().interrupt();
        }
    }
}
