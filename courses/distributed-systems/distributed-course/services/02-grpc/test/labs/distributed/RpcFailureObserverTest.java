package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import io.grpc.*;
import java.io.IOException;
import labs.distributed.grpc.RpcFailureObserver;
import labs.distributed.grpc.protocol.*;
import org.junit.jupiter.api.Test;

/** 仅验证诊断桥的归因边界；业务合同仍由GrpcTest走真实TCP验证。 */
class RpcFailureObserverTest {
  private static final class Transport extends Channel {
    Metadata headers;
    ClientCall.Listener<InventoryReply> listener;
    StatusRuntimeException failure;

    @Override
    public String authority() {
      return "test-transport";
    }

    @Override
    public <Q, S> ClientCall<Q, S> newCall(MethodDescriptor<Q, S> method, CallOptions options) {
      return new ClientCall<>() {
        @Override
        public void start(Listener<S> responseListener, Metadata requestHeaders) {
          headers = requestHeaders;
          listener =
              new ClientCall.Listener<>() {
                @Override
                public void onClose(Status status, Metadata trailers) {
                  responseListener.onClose(status, trailers);
                }
              };
        }

        @Override
        public void request(int count) {}

        @Override
        public void cancel(String message, Throwable cause) {}

        @Override
        public void halfClose() {}

        @Override
        public void sendMessage(Q request) {}
      };
    }

    Transport(RpcFailureObserver observer) {
      observer
          .interceptCall(InventoryGrpc.getQuoteMethod(), CallOptions.DEFAULT, this)
          .start(
              new ClientCall.Listener<>() {
                @Override
                public void onClose(Status status, Metadata trailers) {
                  failure = status.isOk() ? null : status.asRuntimeException(trailers);
                }
              },
              new Metadata());
    }

    void close(Status status) {
      listener.onClose(status, new Metadata());
    }
  }

  @Test
  void 同一次拦截器异常原样到达测试线程() {
    var observer = new RpcFailureObserver();
    var transport = new Transport(observer);
    var original = new UnsupportedOperationException("请按本步骤合同完成实现");
    assertSame(
        original,
        assertThrows(
            UnsupportedOperationException.class,
            () ->
                observer.interceptCall(
                    null,
                    transport.headers,
                    (call, headers) -> {
                      throw original;
                    })));
    transport.close(Status.UNKNOWN);
    assertSame(
        original,
        assertThrows(
            UnsupportedOperationException.class,
            () ->
                RpcFailureObserver.call(
                    () -> {
                      throw transport.failure;
                    })));
  }

  @Test
  void 业务回调与就绪回调保留原始异常() {
    var observer = new RpcFailureObserver();
    var unary = new Transport(observer);
    var assertion = new AssertionError("业务断言");
    var unaryListener =
        observer.interceptCall(
            null,
            unary.headers,
            (call, headers) ->
                new ServerCall.Listener<>() {
                  @Override
                  public void onHalfClose() {
                    throw assertion;
                  }
                });
    assertSame(assertion, assertThrows(AssertionError.class, unaryListener::onHalfClose));
    unary.close(Status.UNKNOWN);
    assertSame(
        assertion,
        assertThrows(AssertionError.class, () -> RpcFailureObserver.checked(unary.failure)));

    var stream = new Transport(observer);
    var original = new UnsupportedOperationException("watch练习未完成");
    var streamListener =
        observer.interceptCall(
            null,
            stream.headers,
            (call, headers) ->
                new ServerCall.Listener<>() {
                  @Override
                  public void onReady() {
                    throw original;
                  }
                });
    assertSame(
        original, assertThrows(UnsupportedOperationException.class, streamListener::onReady));
    stream.close(Status.UNKNOWN);
    assertSame(original, RpcFailureObserver.originalFailure(stream.failure));
  }

  @Test
  void 没有服务端证据的传输错误保持原样() {
    var observer = new RpcFailureObserver();
    for (Status status : new Status[] {Status.UNKNOWN, Status.UNAVAILABLE}) {
      var transport = new Transport(observer);
      var cause = new IOException("连接失败");
      var network = status.withCause(cause);
      transport.close(network);
      assertSame(network, transport.failure.getStatus());
      assertSame(cause, transport.failure.getCause());
      assertSame(transport.failure, RpcFailureObserver.originalFailure(transport.failure));
      assertSame(
          transport.failure,
          assertThrows(
              StatusRuntimeException.class,
              () ->
                  RpcFailureObserver.call(
                      () -> {
                        throw transport.failure;
                      })));
    }
  }

  @Test
  void 旧请求和并行请求异常不能污染新调用() {
    var observer = new RpcFailureObserver();
    var first = new Transport(observer);
    var concurrent = new Transport(observer);
    var original = new UnsupportedOperationException("旧请求未完成");
    var oldListener =
        observer.interceptCall(
            null,
            first.headers,
            (call, headers) ->
                new ServerCall.Listener<>() {
                  @Override
                  public void onHalfClose() {
                    throw original;
                  }
                });
    assertThrows(UnsupportedOperationException.class, oldListener::onHalfClose);
    concurrent.close(Status.UNAVAILABLE);
    assertSame(concurrent.failure, RpcFailureObserver.originalFailure(concurrent.failure));
    first.close(Status.UNKNOWN);
    assertSame(original, RpcFailureObserver.originalFailure(first.failure));

    var later = new Transport(observer);
    // 关闭后的旧监听器仍持有旧记录，也不能写进新调用的诊断槽。
    assertThrows(UnsupportedOperationException.class, oldListener::onHalfClose);
    later.close(Status.UNAVAILABLE);
    assertNull(later.failure.getCause());
    assertSame(later.failure, RpcFailureObserver.originalFailure(later.failure));
  }
}
