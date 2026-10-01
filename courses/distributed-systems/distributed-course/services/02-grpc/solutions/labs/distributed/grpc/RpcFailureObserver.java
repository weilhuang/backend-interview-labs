package labs.distributed.grpc;

import io.grpc.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

/** 同JVM测试诊断：仍走真实TCP，仅将同一次失败RPC的原始服务端异常带回测试线程。 不凭UNKNOWN状态或服务端日志猜测原因；正常状态、连接故障和其他RPC互不污染。 */
public final class RpcFailureObserver implements ServerInterceptor, ClientInterceptor {
  private static final Metadata.Key<String> CALL_ID =
      Metadata.Key.of("x-test-rpc-id", Metadata.ASCII_STRING_MARSHALLER);
  private final AtomicLong sequence = new AtomicLong();
  private final ConcurrentHashMap<String, AtomicReference<Throwable>> calls =
      new ConcurrentHashMap<>();

  private static final class ObservedFailure extends RuntimeException {
    ObservedFailure(Throwable cause) {
      super(cause);
    }
  }

  public static Throwable originalFailure(Throwable failure) {
    if (failure instanceof StatusRuntimeException status
        && status.getCause() instanceof ObservedFailure observed) {
      return observed.getCause();
    }
    return failure;
  }

  public static StatusRuntimeException checked(StatusRuntimeException failure) {
    Throwable original = originalFailure(failure);
    if (original instanceof Error error) throw error;
    if (original != failure) throw (RuntimeException) original;
    return failure;
  }

  public static <T> T call(Supplier<T> action) {
    try {
      return action.get();
    } catch (StatusRuntimeException failure) {
      throw checked(failure);
    }
  }

  @Override
  public <Q, S> ClientCall<Q, S> interceptCall(
      MethodDescriptor<Q, S> method, CallOptions options, Channel next) {
    return new ForwardingClientCall.SimpleForwardingClientCall<>(next.newCall(method, options)) {
      @Override
      public void start(Listener<S> listener, Metadata headers) {
        String id = Long.toString(sequence.incrementAndGet());
        AtomicReference<Throwable> observed = new AtomicReference<>();
        calls.put(id, observed);
        headers.put(CALL_ID, id);
        try {
          super.start(
              new ForwardingClientCallListener.SimpleForwardingClientCallListener<>(listener) {
                @Override
                public void onClose(Status status, Metadata trailers) {
                  calls.remove(id, observed);
                  Throwable failure = observed.get();
                  super.onClose(
                      !status.isOk() && failure != null
                          ? status.withCause(new ObservedFailure(failure))
                          : status,
                      trailers);
                }
              },
              headers);
        } catch (RuntimeException | Error failure) {
          calls.remove(id, observed);
          throw failure;
        }
      }
    };
  }

  @Override
  public <Q, S> ServerCall.Listener<Q> interceptCall(
      ServerCall<Q, S> call, Metadata headers, ServerCallHandler<Q, S> next) {
    String id = headers.get(CALL_ID);
    AtomicReference<Throwable> observed = id == null ? null : calls.get(id);
    ServerCall.Listener<Q> listener = observe(observed, () -> next.startCall(call, headers));
    return new ForwardingServerCallListener.SimpleForwardingServerCallListener<>(listener) {
      @Override
      public void onMessage(Q request) {
        observe(observed, () -> super.onMessage(request));
      }

      @Override
      public void onHalfClose() {
        observe(observed, super::onHalfClose);
      }

      @Override
      public void onCancel() {
        observe(observed, super::onCancel);
      }

      @Override
      public void onComplete() {
        observe(observed, super::onComplete);
      }

      @Override
      public void onReady() {
        observe(observed, super::onReady);
      }
    };
  }

  private static <T> T observe(AtomicReference<Throwable> observed, Supplier<T> action) {
    try {
      return action.get();
    } catch (RuntimeException | Error failure) {
      if (observed != null) observed.compareAndSet(null, failure);
      throw failure;
    }
  }

  private static void observe(AtomicReference<Throwable> observed, Runnable action) {
    observe(
        observed,
        () -> {
          action.run();
          return null;
        });
  }
}
