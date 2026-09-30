package lab.support;

import java.util.Set;

/** 只验证版本读取器，不启动 Docker，不等同于 Testcontainers 集成测试。 */
public final class LabImagesProbe {
    public static void main(String[] args) {
        for (String key : Set.of("MYSQL_IMAGE", "REDIS_IMAGE", "KAFKA_IMAGE", "JAVA_BUILD_IMAGE", "ROCKETMQ_IMAGE", "TESTCONTAINERS_RYUK_IMAGE", "TESTCONTAINERS_TINY_IMAGE")) {
            String image = LabImages.image(key);
            if (image == null || image.contains(":latest")) {
                throw new AssertionError("版本读取失败：" + key);
            }
            System.out.println(key + "=" + image);
        }
        try {
            LabImages.image("UNKNOWN_IMAGE");
            throw new AssertionError("未知镜像键必须失败");
        } catch (IllegalArgumentException expected) {
            System.out.println("共享版本读取与未知键拒绝检查通过；未运行容器集成测试。");
        }
    }
}
