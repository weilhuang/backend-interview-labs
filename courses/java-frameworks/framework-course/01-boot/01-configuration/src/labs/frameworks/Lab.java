package labs.frameworks;

import jakarta.validation.constraints.*;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.context.properties.*;
import org.springframework.validation.annotation.Validated;

@SpringBootConfiguration
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
@EnableConfigurationProperties(Lab.Limits.class)
public class Lab {
  @Validated
  @ConfigurationProperties("orders")
  public static class Limits {
    @Min(1)
    @Max(1000)
    private int maxQuantity = 100;

    @NotBlank private String displayName = "订单实验室";

    public int getMaxQuantity() {
      return maxQuantity;
    }

    public void setMaxQuantity(int value) {
      maxQuantity = value;
    }

    public String getDisplayName() {
      return displayName;
    }

    public void setDisplayName(String value) {
      displayName = value;
    }

    public void requireAllowed(int quantity) {
      // 练习区开始
      if (quantity < 1 || quantity > maxQuantity) throw new IllegalArgumentException("购买数量超出配置范围");
      // 练习区结束
    }
  }

  public static void main(String[] args) {
    SpringApplication app = new SpringApplication(Lab.class);
    app.setWebApplicationType(WebApplicationType.NONE);
    try (var context = app.run(args)) {
      System.out.println("最大购买数量：" + context.getBean(Limits.class).getMaxQuantity());
    }
  }
}
