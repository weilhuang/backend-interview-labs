package labs.capstone;

import static org.junit.jupiter.api.Assertions.*;

import io.grpc.*;
import io.grpc.stub.StreamObserver;

import labs.capstone.protocol.*;

import org.junit.jupiter.api.Test;

import java.util.concurrent.TimeUnit;

/** 真正的回环HTTP/2传输；只证明协议和deadline，MySQL接收效果仍由容器测试证明。 */
class WireTest {
    @Test
    void 真实gRPC传输保留事件身份且遵守截止时间() throws Exception {
        Server server =
                ServerBuilder.forPort(0)
                        .addService(
                                new DeliveryGrpc.DeliveryImplBase() {
                                    @Override
                                    public void apply(
                                            OrderEvent request, StreamObserver<Receipt> observer) {
                                        if (request.getEventId().equals("timeout:1")) return;
                                        observer.onNext(
                                                Receipt.newBuilder()
                                                        .setEventId(request.getEventId())
                                                        .setStatus(request.getStatus())
                                                        .build());
                                        observer.onCompleted();
                                    }
                                })
                        .build()
                        .start();
        ManagedChannel channel =
                ManagedChannelBuilder.forAddress("127.0.0.1", server.getPort())
                        .usePlaintext()
                        .build();
        try {
            var client = DeliveryGrpc.newBlockingStub(channel);
            var result =
                    client.withDeadlineAfter(3, TimeUnit.SECONDS)
                            .apply(
                                    OrderEvent.newBuilder()
                                            .setEventId("Case:1")
                                            .setStatus("RESERVED")
                                            .build());
            assertEquals("Case:1", result.getEventId());
            assertEquals("RESERVED", result.getStatus());
            StatusRuntimeException failure =
                    assertThrows(
                            StatusRuntimeException.class,
                            () ->
                                    client.withDeadlineAfter(100, TimeUnit.MILLISECONDS)
                                            .apply(
                                                    OrderEvent.newBuilder()
                                                            .setEventId("timeout:1")
                                                            .build()));
            assertEquals(Status.Code.DEADLINE_EXCEEDED, failure.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
            assertTrue(channel.awaitTermination(3, TimeUnit.SECONDS));
            assertTrue(server.awaitTermination(3, TimeUnit.SECONDS));
        }
    }
}
