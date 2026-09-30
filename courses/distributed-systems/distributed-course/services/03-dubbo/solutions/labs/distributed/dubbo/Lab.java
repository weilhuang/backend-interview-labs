package labs.distributed.dubbo;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.dubbo.config.*;
import org.apache.dubbo.rpc.*;

public final class Lab {
  public static final class Provider implements Inventory {
    private final String id;
    private final Inventory persistent;
    public final AtomicInteger writes = new AtomicInteger();
    public final java.util.concurrent.CountDownLatch waiting =
        new java.util.concurrent.CountDownLatch(1);
    public final java.util.concurrent.CountDownLatch release =
        new java.util.concurrent.CountDownLatch(1);

    public Provider(String id) {
      this(id, null);
    }

    public Provider(String id, Inventory persistent) {
      this.id = id;
      this.persistent = persistent;
    }

    @Override
    public String quote(String sku) {
      if (sku == null || sku.isBlank()) throw new IllegalArgumentException("商品编号不能为空");
      if (sku.equals("wait")) {
        waiting.countDown();
        try {
          if (!release.await(3, TimeUnit.SECONDS)) throw new IllegalStateException("故障注入等待到期");
        } catch (InterruptedException interrupted) {
          Thread.currentThread().interrupt();
          throw new IllegalStateException("提供者等待被中断", interrupted);
        }
      }
      var attachment = RpcContext.getServerAttachment();
      return id
          + ":"
          + sku
          + ":"
          + attachment.getAttachment("trace-id")
          + ":"
          + attachment.getAttachment("budget-ms")
          + ":"
          + (persistent == null ? "fixture" : persistent.quote(sku));
    }

    @Override
    public int reserve(String key, String sku, int quantity) {
      if (key == null
          || key.isBlank()
          || key.length() > 64
          || sku == null
          || sku.isBlank()
          || sku.length() > 40
          || quantity < 1
          || quantity > 1000) {
        throw new IllegalArgumentException("预留请求参数非法");
      }
      if (persistent != null) return persistent.reserve(key, sku, quantity);
      // 本节fixture保留非幂等副作用观察点；C10-08注入真实MySQL幂等实现。
      return writes.incrementAndGet();
    }
  }

  private static int freePort() {
    try (var socket = new java.net.ServerSocket(0, 1, java.net.InetAddress.getByName("::1"))) {
      return socket.getLocalPort();
    } catch (java.io.IOException failure) {
      throw new IllegalStateException("无法分配本机实验端口", failure);
    }
  }

  public static ApplicationConfig application(
      org.apache.dubbo.rpc.model.ApplicationModel model, String name) {
    ApplicationConfig application = new ApplicationConfig(model, name);
    application.setQosEnable(false);
    application.setEnableFileCache(false);
    application.setRegisterMode("interface");
    application.setMetadataType("local");
    return application;
  }

  public static final class Server implements AutoCloseable {
    private final org.apache.dubbo.rpc.model.FrameworkModel framework =
        new org.apache.dubbo.rpc.model.FrameworkModel();
    private final org.apache.dubbo.rpc.model.ApplicationModel model = framework.newApplication();
    public final ServiceConfig<Inventory> service = new ServiceConfig<>(model.getDefaultModule());

    public Server(Provider provider, String registryAddress) {
      model.getApplicationConfigManager().setApplication(application(model, "inventory-provider"));
      RegistryConfig registry = new RegistryConfig(model, registryAddress);
      registry.setCheck(true);
      service.setRegistry(registry);
      ProtocolConfig protocol = new ProtocolConfig("dubbo", freePort());
      protocol.setScopeModel(model);
      protocol.setHost("::1");
      protocol.setThreads(8);
      service.setProtocol(protocol);
      service.setInterface(Inventory.class);
      service.setRef(provider);
      service.setFilter("lab-budget");
      service.setTimeout(2000);
      try {
        service.export();
      } catch (RuntimeException | Error failure) {
        framework.destroy();
        throw failure;
      }
    }

    public String address() {
      return service.getExportedUrls().stream()
          .filter(url -> url.getProtocol().equals("dubbo"))
          .findFirst()
          .orElseThrow()
          .toFullString();
    }

    @Override
    public void close() {
      service.unexport();
      framework.destroy();
    }
  }

  public static final class Client implements AutoCloseable {
    private final org.apache.dubbo.rpc.model.FrameworkModel framework =
        new org.apache.dubbo.rpc.model.FrameworkModel();
    private final org.apache.dubbo.rpc.model.ApplicationModel model = framework.newApplication();
    private final ReferenceConfig<Inventory> reference =
        new ReferenceConfig<>(model.getDefaultModule());
    public final Inventory proxy;

    public Client(String address, boolean registry) {
      model.getApplicationConfigManager().setApplication(application(model, "inventory-consumer"));
      reference.setInterface(Inventory.class);
      reference.setScope("remote");
      reference.setCheck(true);
      reference.setTimeout(2000);
      reference.setRetries(0);
      reference.setCluster("failfast");
      reference.setLoadbalance("roundrobin");
      reference.setParameters(Map.of("enable-timeout-countdown", "true"));
      if (registry) reference.setRegistry(new RegistryConfig(model, address));
      else {
        reference.setRegistry(new RegistryConfig(model, "N/A"));
        reference.setUrl(address);
      }
      try {
        proxy = reference.get();
      } catch (RuntimeException | Error failure) {
        framework.destroy();
        throw failure;
      }
    }

    public String quote(String sku, String trace, Duration budget, int maxAttempts) {
      if (budget.isNegative()
          || budget.isZero()
          || budget.compareTo(Duration.ofSeconds(5)) > 0
          || maxAttempts < 1
          || maxAttempts > 3) {
        throw new IllegalArgumentException("总预算在0到5秒之间，尝试次数在1到3之间");
      }
      long end = System.nanoTime() + budget.toNanos();
      RpcException last = null;
      // 练习区开始
      for (int attempt = 0; attempt < maxAttempts; attempt++) {
        long remaining = TimeUnit.NANOSECONDS.toMillis(end - System.nanoTime());
        if (remaining <= 0) break;
        try {
          attach(trace, remaining);
          return proxy.quote(sku);
        } catch (RpcException failure) {
          if (failure.isBiz()) throw failure;
          last = failure;
        } finally {
          RpcContext.removeClientAttachment();
        }
      }
      throw new RpcException(RpcException.TIMEOUT_EXCEPTION, "只读调用重试预算耗尽", last);
      // 练习区结束
    }

    public int reserve(String key, String sku, int quantity, String trace, long millis) {
      // 写操作只有一次调用。未知结果应按业务键查询，不靠盲重试制造副作用。
      try {
        attach(trace, millis);
        return proxy.reserve(key, sku, quantity);
      } finally {
        RpcContext.removeClientAttachment();
      }
    }

    private static void attach(String trace, long millis) {
      if (millis < 1 || millis > 5000) throw new IllegalArgumentException("调用预算非法");
      RpcContext.getClientAttachment()
          .setAttachment("trace-id", trace)
          .setAttachment("budget-ms", Long.toString(millis))
          .setAttachment("timeout", Long.toString(millis));
    }

    @Override
    public void close() {
      reference.destroy();
      framework.destroy();
    }
  }
}
