package labs.distributed;

import static org.junit.jupiter.api.Assertions.*;

import labs.distributed.support.Images;
import org.junit.jupiter.api.Test;

/** 地址变换契约快测；实际端口发布与XA恢复仍由Docker集成验证。 */
class EndpointTest {
  @Test
  void 显式切换重启后端口同时保留驱动参数和IPv6主机() {
    assertEquals(
        "jdbc:mysql://localhost:50001/distributed_lab?useSSL=false&allowPublicKeyRetrieval=true",
        Images.withMappedPort(
            "jdbc:mysql://localhost:40001/distributed_lab?useSSL=false&allowPublicKeyRetrieval=true",
            50001));
    assertEquals(
        "jdbc:mysql://[::1]:50002/lab?connectionTimeZone=UTC",
        Images.withMappedPort("jdbc:mysql://[::1]:40002/lab?connectionTimeZone=UTC", 50002));
    assertThrows(
        IllegalArgumentException.class,
        () -> Images.withMappedPort("jdbc:mysql://localhost:40001/lab", 0));
    assertThrows(
        IllegalArgumentException.class, () -> Images.withMappedPort("jdbc:h2:mem:test", 50001));
  }
}
