package labs.distributed;

import static labs.distributed.grpc.RpcFailureObserver.call;
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.*;
import io.grpc.stub.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import labs.distributed.grpc.Lab;
import labs.distributed.grpc.RpcFailureObserver;
import labs.distributed.grpc.protocol.*;
import org.junit.jupiter.api.Test;

class GrpcTest {
  /** 每个端点分别记录，每次RPC通过独立metadata编号对应，错误不会留给下一次调用。 */
  static final class ObservedEndpoint implements AutoCloseable {
    private final RpcFailureObserver failures = new RpcFailureObserver();
    private final Lab.Endpoint endpoint;
    final Channel channel;

    ObservedEndpoint(BindableService service) throws java.io.IOException {
      endpoint = new Lab.Endpoint(service, failures);
      channel = ClientInterceptors.intercept(endpoint.channel, failures);
    }

    InventoryGrpc.InventoryBlockingStub client(String trace, long budgetMillis) {
      return Lab.client(endpoint.channel, trace, budgetMillis).withInterceptors(failures);
    }

    int port() {
      return endpoint.port();
    }

    @Override
    public void close() {
      endpoint.close();
    }
  }

  private static StatusRuntimeException expectedStatus(
      Status.Code expected, org.junit.jupiter.api.function.Executable action) {
    var failure = RpcFailureObserver.checked(assertThrows(StatusRuntimeException.class, action));
    // 不把建连/服务不可用等意外RPC状态改写成断言失败；保留真实状态供门禁拒绝。
    if (failure.getStatus().getCode() != expected) throw failure;
    return failure;
  }

  Lab.Backend backend() {
    return new Lab.Backend() {
      public int quote(String sku) {
        return 12;
      }

      public int reserve(String key, String sku, int quantity) {
        return 12 - quantity;
      }
    };
  }

  @Test
  void 真实网络响应传播上下文且验证参数() throws Exception {
    try (var endpoint = new ObservedEndpoint(new Lab.Service(backend()))) {
      assertTrue(endpoint.port() > 0);
      var stub = endpoint.client("trace-42", 3000);
      var reply = call(() -> stub.quote(QuoteRequest.newBuilder().setSku("book").build()));
      assertEquals(12, reply.getAvailable());
      assertEquals("trace-42", reply.getTraceId());
      assertTrue(reply.getRemainingMillis() > 0 && reply.getRemainingMillis() <= 3000);
      var invalid =
          expectedStatus(
              Status.Code.INVALID_ARGUMENT,
              () ->
                  stub.reserve(
                      ReserveRequest.newBuilder()
                          .setKey("valid-key")
                          .setSku("book")
                          .setQuantity(0)
                          .build()));
      assertEquals(Status.Code.INVALID_ARGUMENT, invalid.getStatus().getCode());
      var missing =
          expectedStatus(
              Status.Code.INVALID_ARGUMENT,
              () ->
                  InventoryGrpc.newBlockingStub(endpoint.channel)
                      .withDeadlineAfter(2, TimeUnit.SECONDS)
                      .quote(QuoteRequest.newBuilder().setSku("book").build()));
      assertEquals(Status.Code.INVALID_ARGUMENT, missing.getStatus().getCode());
    }
  }

  @Test
  void 截止传播取消并清理服务端挂起资源() throws Exception {
    var service = new Lab.Service(backend());
    try (var endpoint = new ObservedEndpoint(service)) {
      // 先完成握手，取消测试不将建连时间误认成业务执行时间。
      call(
          () ->
              endpoint
                  .client("warm", 5000)
                  .quote(QuoteRequest.newBuilder().setSku("book").build()));
      var failure =
          expectedStatus(
              Status.Code.DEADLINE_EXCEEDED,
              () ->
                  endpoint
                      .client("cancel", 400)
                      .quote(QuoteRequest.newBuilder().setSku("wait").build()));
      assertEquals(Status.Code.DEADLINE_EXCEEDED, failure.getStatus().getCode());
      assertTrue(service.waiting.await(2, TimeUnit.SECONDS));
      assertTrue(service.cancelled.await(2, TimeUnit.SECONDS));
      assertEquals(0, service.activeWaits.get());
    }
  }

  @Test
  void 两跳调用继承更短的上游截止而不重置总预算() throws Exception {
    try (var downstream = new ObservedEndpoint(new Lab.Service(backend()))) {
      var gateway =
          new InventoryGrpc.InventoryImplBase() {
            @Override
            public void quote(QuoteRequest request, StreamObserver<InventoryReply> observer) {
              try {
                var result =
                    call(() -> downstream.client(Lab.TRACE_CONTEXT.get(), 8000).quote(request));
                observer.onNext(result);
                observer.onCompleted();
              } catch (StatusRuntimeException failure) {
                observer.onError(failure);
              }
            }
          };
      try (var upstream = new ObservedEndpoint(gateway)) {
        var reply =
            call(
                () ->
                    upstream
                        .client("two-hops", 4000)
                        .quote(QuoteRequest.newBuilder().setSku("book").build()));
        assertEquals("two-hops", reply.getTraceId());
        assertTrue(reply.getRemainingMillis() > 0 && reply.getRemainingMillis() <= 4000);
      }
    }
  }

  @Test
  void 手动流控只交付请求数量且取消可结束流() throws Throwable {
    var service = new Lab.Service(backend());
    try (var endpoint = new ObservedEndpoint(service)) {
      Metadata headers = new Metadata();
      headers.put(Lab.TRACE_HEADER, "stream");
      AtomicReference<ClientCallStreamObserver<WatchRequest>> control = new AtomicReference<>();
      AtomicInteger received = new AtomicInteger();
      CountDownLatch one = new CountDownLatch(1);
      AtomicReference<Throwable> streamFailure = new AtomicReference<>();
      InventoryGrpc.newStub(endpoint.channel)
          .withInterceptors(MetadataUtils.newAttachHeadersInterceptor(headers))
          .withDeadlineAfter(5, TimeUnit.SECONDS)
          .watch(
              WatchRequest.newBuilder().setCount(128).build(),
              new ClientResponseObserver<WatchRequest, InventoryReply>() {
                public void beforeStart(ClientCallStreamObserver<WatchRequest> stream) {
                  stream.disableAutoRequestWithInitial(0);
                  control.set(stream);
                }

                public void onNext(InventoryReply reply) {
                  received.incrementAndGet();
                  one.countDown();
                }

                public void onError(Throwable failure) {
                  streamFailure.set(failure);
                  one.countDown();
                }

                public void onCompleted() {
                  one.countDown();
                }
              });
      control.get().request(1);
      assertTrue(one.await(4, TimeUnit.SECONDS));
      if (streamFailure.get() != null) {
        throw RpcFailureObserver.originalFailure(streamFailure.get());
      }
      assertEquals(1, received.get());
      control.get().cancel("消费者结束订阅", null);
      assertTrue(service.cancelled.await(3, TimeUnit.SECONDS));
      assertTrue(service.emitted.get() <= 128);
    }
  }

  @Test
  void 未知字段可透传而旧编号不会被复用() throws Exception {
    var bytes = new java.io.ByteArrayOutputStream();
    var output = com.google.protobuf.CodedOutputStream.newInstance(bytes);
    output.writeString(1, "book");
    output.writeString(99, "未来字段");
    output.flush();
    var oldReader = QuoteRequest.parseFrom(bytes.toByteArray());
    assertEquals("book", oldReader.getSku());
    assertTrue(QuoteRequest.parseFrom(oldReader.toByteArray()).getUnknownFields().hasField(99));
  }
}
