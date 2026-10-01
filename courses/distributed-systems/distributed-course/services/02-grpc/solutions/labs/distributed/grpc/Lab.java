package labs.distributed.grpc;

import io.grpc.*;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.stub.MetadataUtils;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.net.InetSocketAddress;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import labs.distributed.grpc.protocol.*;

/** 真实回环TCP和HTTP/2；明文仅用于本机实验，生产身份与TLS不在此省略为默认安全。 */
public final class Lab {
  public static final Metadata.Key<String> TRACE_HEADER =
      Metadata.Key.of("x-trace-id", Metadata.ASCII_STRING_MARSHALLER);
  public static final Context.Key<String> TRACE_CONTEXT = Context.key("实验追踪标识");

  public interface Backend {
    int quote(String sku);

    int reserve(String key, String sku, int quantity);
  }

  public static final class TraceInterceptor implements ServerInterceptor {
    @Override
    public <Q, S> ServerCall.Listener<Q> interceptCall(
        ServerCall<Q, S> call, Metadata headers, ServerCallHandler<Q, S> next) {
      // 练习区开始
      String trace = headers.get(TRACE_HEADER);
      if (trace == null || !trace.matches("[a-zA-Z0-9_-]{1,64}")) {
        call.close(Status.INVALID_ARGUMENT.withDescription("追踪标识缺失或非法"), new Metadata());
        return new ServerCall.Listener<>() {};
      }
      return Contexts.interceptCall(
          Context.current().withValue(TRACE_CONTEXT, trace), call, headers, next);
      // 练习区结束
    }
  }

  public static class Service extends InventoryGrpc.InventoryImplBase {
    private final Backend backend;
    public final CountDownLatch waiting = new CountDownLatch(1);
    public final CountDownLatch cancelled = new CountDownLatch(1);
    public final AtomicInteger activeWaits = new AtomicInteger();
    public final AtomicInteger emitted = new AtomicInteger();

    public Service(Backend backend) {
      this.backend = backend;
    }

    @Override
    public void quote(QuoteRequest request, StreamObserver<InventoryReply> observer) {
      if (request.getSku().isBlank()) {
        observer.onError(Status.INVALID_ARGUMENT.withDescription("商品编号不能为空").asRuntimeException());
        return;
      }
      if (request.getSku().equals("wait")) {
        // 故障注入：等待取消事件而不占用一个阻塞线程。
        activeWaits.incrementAndGet();
        Context.current()
            .addListener(
                context -> {
                  activeWaits.decrementAndGet();
                  cancelled.countDown();
                },
                Runnable::run);
        waiting.countDown();
        return;
      }
      respond(observer, request.getSku(), () -> backend.quote(request.getSku()));
    }

    @Override
    public void reserve(ReserveRequest request, StreamObserver<InventoryReply> observer) {
      // 练习区开始
      if (request.getKey().isBlank()
          || request.getKey().length() > 64
          || request.getSku().isBlank()
          || request.getQuantity() < 1
          || request.getQuantity() > 1000) {
        observer.onError(
            Status.INVALID_ARGUMENT.withDescription("幂等键、商品和数量必须合法").asRuntimeException());
        return;
      }
      respond(
          observer,
          request.getSku(),
          () -> backend.reserve(request.getKey(), request.getSku(), request.getQuantity()));
      // 练习区结束
    }

    protected void respond(
        StreamObserver<InventoryReply> observer,
        String sku,
        java.util.function.IntSupplier action) {
      try {
        if (Context.current().isCancelled()) return;
        int available = action.getAsInt();
        observer.onNext(reply(sku, available));
        observer.onCompleted();
      } catch (java.util.concurrent.RejectedExecutionException rejected) {
        observer.onError(Status.RESOURCE_EXHAUSTED.withDescription("服务容量已满").asRuntimeException());
      } catch (IllegalArgumentException conflict) {
        observer.onError(
            Status.FAILED_PRECONDITION.withDescription(conflict.getMessage()).asRuntimeException());
      } catch (IllegalStateException unavailable) {
        observer.onError(Status.UNAVAILABLE.withDescription("库存服务暂时不可用").asRuntimeException());
      }
    }

    @Override
    public void watch(WatchRequest request, StreamObserver<InventoryReply> observer) {
      var output = (ServerCallStreamObserver<InventoryReply>) observer;
      if (request.getCount() < 1 || request.getCount() > 128) {
        output.onError(Status.INVALID_ARGUMENT.withDescription("最多订阅128条").asRuntimeException());
        return;
      }
      output.setOnCancelHandler(cancelled::countDown);
      AtomicInteger sent = new AtomicInteger();
      output.setOnReadyHandler(
          () -> {
            // 练习区开始
            while (output.isReady() && !output.isCancelled() && sent.get() < request.getCount()) {
              int index = sent.incrementAndGet();
              output.onNext(
                  reply("商品-" + index, index).toBuilder().setPayload("数".repeat(16_384)).build());
              emitted.incrementAndGet();
            }
            if (sent.get() == request.getCount() && !output.isCancelled()) output.onCompleted();
            // 练习区结束
          });
    }
  }

  public static InventoryReply reply(String sku, int available) {
    Deadline deadline = Context.current().getDeadline();
    return InventoryReply.newBuilder()
        .setSku(sku)
        .setAvailable(available)
        .setTraceId(TRACE_CONTEXT.get() == null ? "" : TRACE_CONTEXT.get())
        .setRemainingMillis(
            deadline == null ? -1 : Math.max(0, deadline.timeRemaining(TimeUnit.MILLISECONDS)))
        .build();
  }

  public static InventoryGrpc.InventoryBlockingStub client(
      ManagedChannel channel, String trace, long budgetMillis) {
    if (budgetMillis <= 0) throw new IllegalArgumentException("调用预算必须为正");
    Metadata metadata = new Metadata();
    metadata.put(TRACE_HEADER, trace);
    // 应用层不为写操作配置自动重试。只读重试在C10-05采用总预算循环。
    return InventoryGrpc.newBlockingStub(channel)
        .withInterceptors(MetadataUtils.newAttachHeadersInterceptor(metadata))
        .withDeadlineAfter(budgetMillis, TimeUnit.MILLISECONDS);
  }

  public static final class Endpoint implements AutoCloseable {
    private final Server server;
    public final ManagedChannel channel;

    public Endpoint(BindableService service) throws java.io.IOException {
      this(service, new ServerInterceptor[0]);
    }

    /** 额外拦截器包在练习拦截器外侧，供同JVM测试保留原始服务端异常。 */
    public Endpoint(BindableService service, ServerInterceptor... observers)
        throws java.io.IOException {
      server =
          NettyServerBuilder.forAddress(new InetSocketAddress("127.0.0.1", 0))
              .maxInboundMessageSize(1024 * 1024)
              .addService(
                  ServerInterceptors.intercept(
                      ServerInterceptors.intercept(service, new TraceInterceptor()), observers))
              .build()
              .start();
      channel =
          NettyChannelBuilder.forAddress("127.0.0.1", server.getPort())
              .usePlaintext()
              .disableRetry()
              .maxInboundMessageSize(1024 * 1024)
              .build();
    }

    public int port() {
      return server.getPort();
    }

    @Override
    public void close() {
      channel.shutdownNow();
      server.shutdownNow();
      try {
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)
            || !server.awaitTermination(5, TimeUnit.SECONDS)) {
          throw new IllegalStateException("RPC资源未在关闭预算内退出");
        }
      } catch (InterruptedException failure) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("RPC关闭等待被中断", failure);
      }
    }
  }
}
