package labs.distributed.grpc.protocol;

import static io.grpc.MethodDescriptor.generateFullMethodName;

/**
 * <pre>
 * 字段编号是兼容契约，删除字段必须保留编号，不能改作其他含义。
 * </pre>
 */
@javax.annotation.Generated(
    value = "by gRPC proto compiler (version 1.71.0)",
    comments = "Source: inventory.proto")
@io.grpc.stub.annotations.GrpcGenerated
public final class InventoryGrpc {

  private InventoryGrpc() {}

  public static final java.lang.String SERVICE_NAME = "inventory.v1.Inventory";

  // Static method descriptors that strictly reflect the proto.
  private static volatile io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.QuoteRequest,
      labs.distributed.grpc.protocol.InventoryReply> getQuoteMethod;

  @io.grpc.stub.annotations.RpcMethod(
      fullMethodName = SERVICE_NAME + '/' + "Quote",
      requestType = labs.distributed.grpc.protocol.QuoteRequest.class,
      responseType = labs.distributed.grpc.protocol.InventoryReply.class,
      methodType = io.grpc.MethodDescriptor.MethodType.UNARY)
  public static io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.QuoteRequest,
      labs.distributed.grpc.protocol.InventoryReply> getQuoteMethod() {
    io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.QuoteRequest, labs.distributed.grpc.protocol.InventoryReply> getQuoteMethod;
    if ((getQuoteMethod = InventoryGrpc.getQuoteMethod) == null) {
      synchronized (InventoryGrpc.class) {
        if ((getQuoteMethod = InventoryGrpc.getQuoteMethod) == null) {
          InventoryGrpc.getQuoteMethod = getQuoteMethod =
              io.grpc.MethodDescriptor.<labs.distributed.grpc.protocol.QuoteRequest, labs.distributed.grpc.protocol.InventoryReply>newBuilder()
              .setType(io.grpc.MethodDescriptor.MethodType.UNARY)
              .setFullMethodName(generateFullMethodName(SERVICE_NAME, "Quote"))
              .setSampledToLocalTracing(true)
              .setRequestMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.distributed.grpc.protocol.QuoteRequest.getDefaultInstance()))
              .setResponseMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.distributed.grpc.protocol.InventoryReply.getDefaultInstance()))
              .setSchemaDescriptor(new InventoryMethodDescriptorSupplier("Quote"))
              .build();
        }
      }
    }
    return getQuoteMethod;
  }

  private static volatile io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.ReserveRequest,
      labs.distributed.grpc.protocol.InventoryReply> getReserveMethod;

  @io.grpc.stub.annotations.RpcMethod(
      fullMethodName = SERVICE_NAME + '/' + "Reserve",
      requestType = labs.distributed.grpc.protocol.ReserveRequest.class,
      responseType = labs.distributed.grpc.protocol.InventoryReply.class,
      methodType = io.grpc.MethodDescriptor.MethodType.UNARY)
  public static io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.ReserveRequest,
      labs.distributed.grpc.protocol.InventoryReply> getReserveMethod() {
    io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.ReserveRequest, labs.distributed.grpc.protocol.InventoryReply> getReserveMethod;
    if ((getReserveMethod = InventoryGrpc.getReserveMethod) == null) {
      synchronized (InventoryGrpc.class) {
        if ((getReserveMethod = InventoryGrpc.getReserveMethod) == null) {
          InventoryGrpc.getReserveMethod = getReserveMethod =
              io.grpc.MethodDescriptor.<labs.distributed.grpc.protocol.ReserveRequest, labs.distributed.grpc.protocol.InventoryReply>newBuilder()
              .setType(io.grpc.MethodDescriptor.MethodType.UNARY)
              .setFullMethodName(generateFullMethodName(SERVICE_NAME, "Reserve"))
              .setSampledToLocalTracing(true)
              .setRequestMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.distributed.grpc.protocol.ReserveRequest.getDefaultInstance()))
              .setResponseMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.distributed.grpc.protocol.InventoryReply.getDefaultInstance()))
              .setSchemaDescriptor(new InventoryMethodDescriptorSupplier("Reserve"))
              .build();
        }
      }
    }
    return getReserveMethod;
  }

  private static volatile io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.WatchRequest,
      labs.distributed.grpc.protocol.InventoryReply> getWatchMethod;

  @io.grpc.stub.annotations.RpcMethod(
      fullMethodName = SERVICE_NAME + '/' + "Watch",
      requestType = labs.distributed.grpc.protocol.WatchRequest.class,
      responseType = labs.distributed.grpc.protocol.InventoryReply.class,
      methodType = io.grpc.MethodDescriptor.MethodType.SERVER_STREAMING)
  public static io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.WatchRequest,
      labs.distributed.grpc.protocol.InventoryReply> getWatchMethod() {
    io.grpc.MethodDescriptor<labs.distributed.grpc.protocol.WatchRequest, labs.distributed.grpc.protocol.InventoryReply> getWatchMethod;
    if ((getWatchMethod = InventoryGrpc.getWatchMethod) == null) {
      synchronized (InventoryGrpc.class) {
        if ((getWatchMethod = InventoryGrpc.getWatchMethod) == null) {
          InventoryGrpc.getWatchMethod = getWatchMethod =
              io.grpc.MethodDescriptor.<labs.distributed.grpc.protocol.WatchRequest, labs.distributed.grpc.protocol.InventoryReply>newBuilder()
              .setType(io.grpc.MethodDescriptor.MethodType.SERVER_STREAMING)
              .setFullMethodName(generateFullMethodName(SERVICE_NAME, "Watch"))
              .setSampledToLocalTracing(true)
              .setRequestMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.distributed.grpc.protocol.WatchRequest.getDefaultInstance()))
              .setResponseMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.distributed.grpc.protocol.InventoryReply.getDefaultInstance()))
              .setSchemaDescriptor(new InventoryMethodDescriptorSupplier("Watch"))
              .build();
        }
      }
    }
    return getWatchMethod;
  }

  /**
   * Creates a new async stub that supports all call types for the service
   */
  public static InventoryStub newStub(io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<InventoryStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<InventoryStub>() {
        @java.lang.Override
        public InventoryStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new InventoryStub(channel, callOptions);
        }
      };
    return InventoryStub.newStub(factory, channel);
  }

  /**
   * Creates a new blocking-style stub that supports all types of calls on the service
   */
  public static InventoryBlockingV2Stub newBlockingV2Stub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<InventoryBlockingV2Stub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<InventoryBlockingV2Stub>() {
        @java.lang.Override
        public InventoryBlockingV2Stub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new InventoryBlockingV2Stub(channel, callOptions);
        }
      };
    return InventoryBlockingV2Stub.newStub(factory, channel);
  }

  /**
   * Creates a new blocking-style stub that supports unary and streaming output calls on the service
   */
  public static InventoryBlockingStub newBlockingStub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<InventoryBlockingStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<InventoryBlockingStub>() {
        @java.lang.Override
        public InventoryBlockingStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new InventoryBlockingStub(channel, callOptions);
        }
      };
    return InventoryBlockingStub.newStub(factory, channel);
  }

  /**
   * Creates a new ListenableFuture-style stub that supports unary calls on the service
   */
  public static InventoryFutureStub newFutureStub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<InventoryFutureStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<InventoryFutureStub>() {
        @java.lang.Override
        public InventoryFutureStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new InventoryFutureStub(channel, callOptions);
        }
      };
    return InventoryFutureStub.newStub(factory, channel);
  }

  /**
   * <pre>
   * 字段编号是兼容契约，删除字段必须保留编号，不能改作其他含义。
   * </pre>
   */
  public interface AsyncService {

    /**
     */
    default void quote(labs.distributed.grpc.protocol.QuoteRequest request,
        io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply> responseObserver) {
      io.grpc.stub.ServerCalls.asyncUnimplementedUnaryCall(getQuoteMethod(), responseObserver);
    }

    /**
     */
    default void reserve(labs.distributed.grpc.protocol.ReserveRequest request,
        io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply> responseObserver) {
      io.grpc.stub.ServerCalls.asyncUnimplementedUnaryCall(getReserveMethod(), responseObserver);
    }

    /**
     */
    default void watch(labs.distributed.grpc.protocol.WatchRequest request,
        io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply> responseObserver) {
      io.grpc.stub.ServerCalls.asyncUnimplementedUnaryCall(getWatchMethod(), responseObserver);
    }
  }

  /**
   * Base class for the server implementation of the service Inventory.
   * <pre>
   * 字段编号是兼容契约，删除字段必须保留编号，不能改作其他含义。
   * </pre>
   */
  public static abstract class InventoryImplBase
      implements io.grpc.BindableService, AsyncService {

    @java.lang.Override public final io.grpc.ServerServiceDefinition bindService() {
      return InventoryGrpc.bindService(this);
    }
  }

  /**
   * A stub to allow clients to do asynchronous rpc calls to service Inventory.
   * <pre>
   * 字段编号是兼容契约，删除字段必须保留编号，不能改作其他含义。
   * </pre>
   */
  public static final class InventoryStub
      extends io.grpc.stub.AbstractAsyncStub<InventoryStub> {
    private InventoryStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected InventoryStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new InventoryStub(channel, callOptions);
    }

    /**
     */
    public void quote(labs.distributed.grpc.protocol.QuoteRequest request,
        io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply> responseObserver) {
      io.grpc.stub.ClientCalls.asyncUnaryCall(
          getChannel().newCall(getQuoteMethod(), getCallOptions()), request, responseObserver);
    }

    /**
     */
    public void reserve(labs.distributed.grpc.protocol.ReserveRequest request,
        io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply> responseObserver) {
      io.grpc.stub.ClientCalls.asyncUnaryCall(
          getChannel().newCall(getReserveMethod(), getCallOptions()), request, responseObserver);
    }

    /**
     */
    public void watch(labs.distributed.grpc.protocol.WatchRequest request,
        io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply> responseObserver) {
      io.grpc.stub.ClientCalls.asyncServerStreamingCall(
          getChannel().newCall(getWatchMethod(), getCallOptions()), request, responseObserver);
    }
  }

  /**
   * A stub to allow clients to do synchronous rpc calls to service Inventory.
   * <pre>
   * 字段编号是兼容契约，删除字段必须保留编号，不能改作其他含义。
   * </pre>
   */
  public static final class InventoryBlockingV2Stub
      extends io.grpc.stub.AbstractBlockingStub<InventoryBlockingV2Stub> {
    private InventoryBlockingV2Stub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected InventoryBlockingV2Stub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new InventoryBlockingV2Stub(channel, callOptions);
    }

    /**
     */
    public labs.distributed.grpc.protocol.InventoryReply quote(labs.distributed.grpc.protocol.QuoteRequest request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getQuoteMethod(), getCallOptions(), request);
    }

    /**
     */
    public labs.distributed.grpc.protocol.InventoryReply reserve(labs.distributed.grpc.protocol.ReserveRequest request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getReserveMethod(), getCallOptions(), request);
    }

    /**
     */
    @io.grpc.ExperimentalApi("https://github.com/grpc/grpc-java/issues/10918")
    public io.grpc.stub.BlockingClientCall<?, labs.distributed.grpc.protocol.InventoryReply>
        watch(labs.distributed.grpc.protocol.WatchRequest request) {
      return io.grpc.stub.ClientCalls.blockingV2ServerStreamingCall(
          getChannel(), getWatchMethod(), getCallOptions(), request);
    }
  }

  /**
   * A stub to allow clients to do limited synchronous rpc calls to service Inventory.
   * <pre>
   * 字段编号是兼容契约，删除字段必须保留编号，不能改作其他含义。
   * </pre>
   */
  public static final class InventoryBlockingStub
      extends io.grpc.stub.AbstractBlockingStub<InventoryBlockingStub> {
    private InventoryBlockingStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected InventoryBlockingStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new InventoryBlockingStub(channel, callOptions);
    }

    /**
     */
    public labs.distributed.grpc.protocol.InventoryReply quote(labs.distributed.grpc.protocol.QuoteRequest request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getQuoteMethod(), getCallOptions(), request);
    }

    /**
     */
    public labs.distributed.grpc.protocol.InventoryReply reserve(labs.distributed.grpc.protocol.ReserveRequest request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getReserveMethod(), getCallOptions(), request);
    }

    /**
     */
    public java.util.Iterator<labs.distributed.grpc.protocol.InventoryReply> watch(
        labs.distributed.grpc.protocol.WatchRequest request) {
      return io.grpc.stub.ClientCalls.blockingServerStreamingCall(
          getChannel(), getWatchMethod(), getCallOptions(), request);
    }
  }

  /**
   * A stub to allow clients to do ListenableFuture-style rpc calls to service Inventory.
   * <pre>
   * 字段编号是兼容契约，删除字段必须保留编号，不能改作其他含义。
   * </pre>
   */
  public static final class InventoryFutureStub
      extends io.grpc.stub.AbstractFutureStub<InventoryFutureStub> {
    private InventoryFutureStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected InventoryFutureStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new InventoryFutureStub(channel, callOptions);
    }

    /**
     */
    public com.google.common.util.concurrent.ListenableFuture<labs.distributed.grpc.protocol.InventoryReply> quote(
        labs.distributed.grpc.protocol.QuoteRequest request) {
      return io.grpc.stub.ClientCalls.futureUnaryCall(
          getChannel().newCall(getQuoteMethod(), getCallOptions()), request);
    }

    /**
     */
    public com.google.common.util.concurrent.ListenableFuture<labs.distributed.grpc.protocol.InventoryReply> reserve(
        labs.distributed.grpc.protocol.ReserveRequest request) {
      return io.grpc.stub.ClientCalls.futureUnaryCall(
          getChannel().newCall(getReserveMethod(), getCallOptions()), request);
    }
  }

  private static final int METHODID_QUOTE = 0;
  private static final int METHODID_RESERVE = 1;
  private static final int METHODID_WATCH = 2;

  private static final class MethodHandlers<Req, Resp> implements
      io.grpc.stub.ServerCalls.UnaryMethod<Req, Resp>,
      io.grpc.stub.ServerCalls.ServerStreamingMethod<Req, Resp>,
      io.grpc.stub.ServerCalls.ClientStreamingMethod<Req, Resp>,
      io.grpc.stub.ServerCalls.BidiStreamingMethod<Req, Resp> {
    private final AsyncService serviceImpl;
    private final int methodId;

    MethodHandlers(AsyncService serviceImpl, int methodId) {
      this.serviceImpl = serviceImpl;
      this.methodId = methodId;
    }

    @java.lang.Override
    @java.lang.SuppressWarnings("unchecked")
    public void invoke(Req request, io.grpc.stub.StreamObserver<Resp> responseObserver) {
      switch (methodId) {
        case METHODID_QUOTE:
          serviceImpl.quote((labs.distributed.grpc.protocol.QuoteRequest) request,
              (io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply>) responseObserver);
          break;
        case METHODID_RESERVE:
          serviceImpl.reserve((labs.distributed.grpc.protocol.ReserveRequest) request,
              (io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply>) responseObserver);
          break;
        case METHODID_WATCH:
          serviceImpl.watch((labs.distributed.grpc.protocol.WatchRequest) request,
              (io.grpc.stub.StreamObserver<labs.distributed.grpc.protocol.InventoryReply>) responseObserver);
          break;
        default:
          throw new AssertionError();
      }
    }

    @java.lang.Override
    @java.lang.SuppressWarnings("unchecked")
    public io.grpc.stub.StreamObserver<Req> invoke(
        io.grpc.stub.StreamObserver<Resp> responseObserver) {
      switch (methodId) {
        default:
          throw new AssertionError();
      }
    }
  }

  public static final io.grpc.ServerServiceDefinition bindService(AsyncService service) {
    return io.grpc.ServerServiceDefinition.builder(getServiceDescriptor())
        .addMethod(
          getQuoteMethod(),
          io.grpc.stub.ServerCalls.asyncUnaryCall(
            new MethodHandlers<
              labs.distributed.grpc.protocol.QuoteRequest,
              labs.distributed.grpc.protocol.InventoryReply>(
                service, METHODID_QUOTE)))
        .addMethod(
          getReserveMethod(),
          io.grpc.stub.ServerCalls.asyncUnaryCall(
            new MethodHandlers<
              labs.distributed.grpc.protocol.ReserveRequest,
              labs.distributed.grpc.protocol.InventoryReply>(
                service, METHODID_RESERVE)))
        .addMethod(
          getWatchMethod(),
          io.grpc.stub.ServerCalls.asyncServerStreamingCall(
            new MethodHandlers<
              labs.distributed.grpc.protocol.WatchRequest,
              labs.distributed.grpc.protocol.InventoryReply>(
                service, METHODID_WATCH)))
        .build();
  }

  private static abstract class InventoryBaseDescriptorSupplier
      implements io.grpc.protobuf.ProtoFileDescriptorSupplier, io.grpc.protobuf.ProtoServiceDescriptorSupplier {
    InventoryBaseDescriptorSupplier() {}

    @java.lang.Override
    public com.google.protobuf.Descriptors.FileDescriptor getFileDescriptor() {
      return labs.distributed.grpc.protocol.InventoryOuterClass.getDescriptor();
    }

    @java.lang.Override
    public com.google.protobuf.Descriptors.ServiceDescriptor getServiceDescriptor() {
      return getFileDescriptor().findServiceByName("Inventory");
    }
  }

  private static final class InventoryFileDescriptorSupplier
      extends InventoryBaseDescriptorSupplier {
    InventoryFileDescriptorSupplier() {}
  }

  private static final class InventoryMethodDescriptorSupplier
      extends InventoryBaseDescriptorSupplier
      implements io.grpc.protobuf.ProtoMethodDescriptorSupplier {
    private final java.lang.String methodName;

    InventoryMethodDescriptorSupplier(java.lang.String methodName) {
      this.methodName = methodName;
    }

    @java.lang.Override
    public com.google.protobuf.Descriptors.MethodDescriptor getMethodDescriptor() {
      return getServiceDescriptor().findMethodByName(methodName);
    }
  }

  private static volatile io.grpc.ServiceDescriptor serviceDescriptor;

  public static io.grpc.ServiceDescriptor getServiceDescriptor() {
    io.grpc.ServiceDescriptor result = serviceDescriptor;
    if (result == null) {
      synchronized (InventoryGrpc.class) {
        result = serviceDescriptor;
        if (result == null) {
          serviceDescriptor = result = io.grpc.ServiceDescriptor.newBuilder(SERVICE_NAME)
              .setSchemaDescriptor(new InventoryFileDescriptorSupplier())
              .addMethod(getQuoteMethod())
              .addMethod(getReserveMethod())
              .addMethod(getWatchMethod())
              .build();
        }
      }
    }
    return result;
  }
}
