package labs.capstone.protocol;

import static io.grpc.MethodDescriptor.generateFullMethodName;

/**
 * <pre>
 * 字段编号是线上的兼容契约；变更语义时新增字段，不能复用旧编号。
 * </pre>
 */
@javax.annotation.Generated(
    value = "by gRPC proto compiler (version 1.71.0)",
    comments = "Source: delivery.proto")
@io.grpc.stub.annotations.GrpcGenerated
public final class DeliveryGrpc {

  private DeliveryGrpc() {}

  public static final java.lang.String SERVICE_NAME = "capstone.v1.Delivery";

  // Static method descriptors that strictly reflect the proto.
  private static volatile io.grpc.MethodDescriptor<labs.capstone.protocol.OrderEvent,
      labs.capstone.protocol.Receipt> getApplyMethod;

  @io.grpc.stub.annotations.RpcMethod(
      fullMethodName = SERVICE_NAME + '/' + "Apply",
      requestType = labs.capstone.protocol.OrderEvent.class,
      responseType = labs.capstone.protocol.Receipt.class,
      methodType = io.grpc.MethodDescriptor.MethodType.UNARY)
  public static io.grpc.MethodDescriptor<labs.capstone.protocol.OrderEvent,
      labs.capstone.protocol.Receipt> getApplyMethod() {
    io.grpc.MethodDescriptor<labs.capstone.protocol.OrderEvent, labs.capstone.protocol.Receipt> getApplyMethod;
    if ((getApplyMethod = DeliveryGrpc.getApplyMethod) == null) {
      synchronized (DeliveryGrpc.class) {
        if ((getApplyMethod = DeliveryGrpc.getApplyMethod) == null) {
          DeliveryGrpc.getApplyMethod = getApplyMethod =
              io.grpc.MethodDescriptor.<labs.capstone.protocol.OrderEvent, labs.capstone.protocol.Receipt>newBuilder()
              .setType(io.grpc.MethodDescriptor.MethodType.UNARY)
              .setFullMethodName(generateFullMethodName(SERVICE_NAME, "Apply"))
              .setSampledToLocalTracing(true)
              .setRequestMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.capstone.protocol.OrderEvent.getDefaultInstance()))
              .setResponseMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.capstone.protocol.Receipt.getDefaultInstance()))
              .setSchemaDescriptor(new DeliveryMethodDescriptorSupplier("Apply"))
              .build();
        }
      }
    }
    return getApplyMethod;
  }

  private static volatile io.grpc.MethodDescriptor<labs.capstone.protocol.ProbeRequest,
      labs.capstone.protocol.Receipt> getProbeMethod;

  @io.grpc.stub.annotations.RpcMethod(
      fullMethodName = SERVICE_NAME + '/' + "Probe",
      requestType = labs.capstone.protocol.ProbeRequest.class,
      responseType = labs.capstone.protocol.Receipt.class,
      methodType = io.grpc.MethodDescriptor.MethodType.UNARY)
  public static io.grpc.MethodDescriptor<labs.capstone.protocol.ProbeRequest,
      labs.capstone.protocol.Receipt> getProbeMethod() {
    io.grpc.MethodDescriptor<labs.capstone.protocol.ProbeRequest, labs.capstone.protocol.Receipt> getProbeMethod;
    if ((getProbeMethod = DeliveryGrpc.getProbeMethod) == null) {
      synchronized (DeliveryGrpc.class) {
        if ((getProbeMethod = DeliveryGrpc.getProbeMethod) == null) {
          DeliveryGrpc.getProbeMethod = getProbeMethod =
              io.grpc.MethodDescriptor.<labs.capstone.protocol.ProbeRequest, labs.capstone.protocol.Receipt>newBuilder()
              .setType(io.grpc.MethodDescriptor.MethodType.UNARY)
              .setFullMethodName(generateFullMethodName(SERVICE_NAME, "Probe"))
              .setSampledToLocalTracing(true)
              .setRequestMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.capstone.protocol.ProbeRequest.getDefaultInstance()))
              .setResponseMarshaller(io.grpc.protobuf.ProtoUtils.marshaller(
                  labs.capstone.protocol.Receipt.getDefaultInstance()))
              .setSchemaDescriptor(new DeliveryMethodDescriptorSupplier("Probe"))
              .build();
        }
      }
    }
    return getProbeMethod;
  }

  /**
   * Creates a new async stub that supports all call types for the service
   */
  public static DeliveryStub newStub(io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<DeliveryStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<DeliveryStub>() {
        @java.lang.Override
        public DeliveryStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new DeliveryStub(channel, callOptions);
        }
      };
    return DeliveryStub.newStub(factory, channel);
  }

  /**
   * Creates a new blocking-style stub that supports all types of calls on the service
   */
  public static DeliveryBlockingV2Stub newBlockingV2Stub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<DeliveryBlockingV2Stub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<DeliveryBlockingV2Stub>() {
        @java.lang.Override
        public DeliveryBlockingV2Stub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new DeliveryBlockingV2Stub(channel, callOptions);
        }
      };
    return DeliveryBlockingV2Stub.newStub(factory, channel);
  }

  /**
   * Creates a new blocking-style stub that supports unary and streaming output calls on the service
   */
  public static DeliveryBlockingStub newBlockingStub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<DeliveryBlockingStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<DeliveryBlockingStub>() {
        @java.lang.Override
        public DeliveryBlockingStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new DeliveryBlockingStub(channel, callOptions);
        }
      };
    return DeliveryBlockingStub.newStub(factory, channel);
  }

  /**
   * Creates a new ListenableFuture-style stub that supports unary calls on the service
   */
  public static DeliveryFutureStub newFutureStub(
      io.grpc.Channel channel) {
    io.grpc.stub.AbstractStub.StubFactory<DeliveryFutureStub> factory =
      new io.grpc.stub.AbstractStub.StubFactory<DeliveryFutureStub>() {
        @java.lang.Override
        public DeliveryFutureStub newStub(io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
          return new DeliveryFutureStub(channel, callOptions);
        }
      };
    return DeliveryFutureStub.newStub(factory, channel);
  }

  /**
   * <pre>
   * 字段编号是线上的兼容契约；变更语义时新增字段，不能复用旧编号。
   * </pre>
   */
  public interface AsyncService {

    /**
     */
    default void apply(labs.capstone.protocol.OrderEvent request,
        io.grpc.stub.StreamObserver<labs.capstone.protocol.Receipt> responseObserver) {
      io.grpc.stub.ServerCalls.asyncUnimplementedUnaryCall(getApplyMethod(), responseObserver);
    }

    /**
     */
    default void probe(labs.capstone.protocol.ProbeRequest request,
        io.grpc.stub.StreamObserver<labs.capstone.protocol.Receipt> responseObserver) {
      io.grpc.stub.ServerCalls.asyncUnimplementedUnaryCall(getProbeMethod(), responseObserver);
    }
  }

  /**
   * Base class for the server implementation of the service Delivery.
   * <pre>
   * 字段编号是线上的兼容契约；变更语义时新增字段，不能复用旧编号。
   * </pre>
   */
  public static abstract class DeliveryImplBase
      implements io.grpc.BindableService, AsyncService {

    @java.lang.Override public final io.grpc.ServerServiceDefinition bindService() {
      return DeliveryGrpc.bindService(this);
    }
  }

  /**
   * A stub to allow clients to do asynchronous rpc calls to service Delivery.
   * <pre>
   * 字段编号是线上的兼容契约；变更语义时新增字段，不能复用旧编号。
   * </pre>
   */
  public static final class DeliveryStub
      extends io.grpc.stub.AbstractAsyncStub<DeliveryStub> {
    private DeliveryStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected DeliveryStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new DeliveryStub(channel, callOptions);
    }

    /**
     */
    public void apply(labs.capstone.protocol.OrderEvent request,
        io.grpc.stub.StreamObserver<labs.capstone.protocol.Receipt> responseObserver) {
      io.grpc.stub.ClientCalls.asyncUnaryCall(
          getChannel().newCall(getApplyMethod(), getCallOptions()), request, responseObserver);
    }

    /**
     */
    public void probe(labs.capstone.protocol.ProbeRequest request,
        io.grpc.stub.StreamObserver<labs.capstone.protocol.Receipt> responseObserver) {
      io.grpc.stub.ClientCalls.asyncUnaryCall(
          getChannel().newCall(getProbeMethod(), getCallOptions()), request, responseObserver);
    }
  }

  /**
   * A stub to allow clients to do synchronous rpc calls to service Delivery.
   * <pre>
   * 字段编号是线上的兼容契约；变更语义时新增字段，不能复用旧编号。
   * </pre>
   */
  public static final class DeliveryBlockingV2Stub
      extends io.grpc.stub.AbstractBlockingStub<DeliveryBlockingV2Stub> {
    private DeliveryBlockingV2Stub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected DeliveryBlockingV2Stub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new DeliveryBlockingV2Stub(channel, callOptions);
    }

    /**
     */
    public labs.capstone.protocol.Receipt apply(labs.capstone.protocol.OrderEvent request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getApplyMethod(), getCallOptions(), request);
    }

    /**
     */
    public labs.capstone.protocol.Receipt probe(labs.capstone.protocol.ProbeRequest request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getProbeMethod(), getCallOptions(), request);
    }
  }

  /**
   * A stub to allow clients to do limited synchronous rpc calls to service Delivery.
   * <pre>
   * 字段编号是线上的兼容契约；变更语义时新增字段，不能复用旧编号。
   * </pre>
   */
  public static final class DeliveryBlockingStub
      extends io.grpc.stub.AbstractBlockingStub<DeliveryBlockingStub> {
    private DeliveryBlockingStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected DeliveryBlockingStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new DeliveryBlockingStub(channel, callOptions);
    }

    /**
     */
    public labs.capstone.protocol.Receipt apply(labs.capstone.protocol.OrderEvent request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getApplyMethod(), getCallOptions(), request);
    }

    /**
     */
    public labs.capstone.protocol.Receipt probe(labs.capstone.protocol.ProbeRequest request) {
      return io.grpc.stub.ClientCalls.blockingUnaryCall(
          getChannel(), getProbeMethod(), getCallOptions(), request);
    }
  }

  /**
   * A stub to allow clients to do ListenableFuture-style rpc calls to service Delivery.
   * <pre>
   * 字段编号是线上的兼容契约；变更语义时新增字段，不能复用旧编号。
   * </pre>
   */
  public static final class DeliveryFutureStub
      extends io.grpc.stub.AbstractFutureStub<DeliveryFutureStub> {
    private DeliveryFutureStub(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      super(channel, callOptions);
    }

    @java.lang.Override
    protected DeliveryFutureStub build(
        io.grpc.Channel channel, io.grpc.CallOptions callOptions) {
      return new DeliveryFutureStub(channel, callOptions);
    }

    /**
     */
    public com.google.common.util.concurrent.ListenableFuture<labs.capstone.protocol.Receipt> apply(
        labs.capstone.protocol.OrderEvent request) {
      return io.grpc.stub.ClientCalls.futureUnaryCall(
          getChannel().newCall(getApplyMethod(), getCallOptions()), request);
    }

    /**
     */
    public com.google.common.util.concurrent.ListenableFuture<labs.capstone.protocol.Receipt> probe(
        labs.capstone.protocol.ProbeRequest request) {
      return io.grpc.stub.ClientCalls.futureUnaryCall(
          getChannel().newCall(getProbeMethod(), getCallOptions()), request);
    }
  }

  private static final int METHODID_APPLY = 0;
  private static final int METHODID_PROBE = 1;

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
        case METHODID_APPLY:
          serviceImpl.apply((labs.capstone.protocol.OrderEvent) request,
              (io.grpc.stub.StreamObserver<labs.capstone.protocol.Receipt>) responseObserver);
          break;
        case METHODID_PROBE:
          serviceImpl.probe((labs.capstone.protocol.ProbeRequest) request,
              (io.grpc.stub.StreamObserver<labs.capstone.protocol.Receipt>) responseObserver);
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
          getApplyMethod(),
          io.grpc.stub.ServerCalls.asyncUnaryCall(
            new MethodHandlers<
              labs.capstone.protocol.OrderEvent,
              labs.capstone.protocol.Receipt>(
                service, METHODID_APPLY)))
        .addMethod(
          getProbeMethod(),
          io.grpc.stub.ServerCalls.asyncUnaryCall(
            new MethodHandlers<
              labs.capstone.protocol.ProbeRequest,
              labs.capstone.protocol.Receipt>(
                service, METHODID_PROBE)))
        .build();
  }

  private static abstract class DeliveryBaseDescriptorSupplier
      implements io.grpc.protobuf.ProtoFileDescriptorSupplier, io.grpc.protobuf.ProtoServiceDescriptorSupplier {
    DeliveryBaseDescriptorSupplier() {}

    @java.lang.Override
    public com.google.protobuf.Descriptors.FileDescriptor getFileDescriptor() {
      return labs.capstone.protocol.DeliveryOuterClass.getDescriptor();
    }

    @java.lang.Override
    public com.google.protobuf.Descriptors.ServiceDescriptor getServiceDescriptor() {
      return getFileDescriptor().findServiceByName("Delivery");
    }
  }

  private static final class DeliveryFileDescriptorSupplier
      extends DeliveryBaseDescriptorSupplier {
    DeliveryFileDescriptorSupplier() {}
  }

  private static final class DeliveryMethodDescriptorSupplier
      extends DeliveryBaseDescriptorSupplier
      implements io.grpc.protobuf.ProtoMethodDescriptorSupplier {
    private final java.lang.String methodName;

    DeliveryMethodDescriptorSupplier(java.lang.String methodName) {
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
      synchronized (DeliveryGrpc.class) {
        result = serviceDescriptor;
        if (result == null) {
          serviceDescriptor = result = io.grpc.ServiceDescriptor.newBuilder(SERVICE_NAME)
              .setSchemaDescriptor(new DeliveryFileDescriptorSupplier())
              .addMethod(getApplyMethod())
              .addMethod(getProbeMethod())
              .build();
        }
      }
    }
    return result;
  }
}
