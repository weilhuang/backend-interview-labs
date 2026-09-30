package labs.capstone;

import static labs.capstone.Model.*;

import java.util.Objects;

/** C14-01：所有入口共同使用的不变量，禁止只在页面验证。 */
public final class OrderRules {
    private OrderRules() {}

    public static void validate(Command command) {
        // 学习区开始
        Objects.requireNonNull(command, "请求不能为空");
        identifier(command.requestId(), "请求号");
        identifier(command.sku(), "商品号");
        if (command.quantity() < 1 || command.quantity() > 100)
            throw new IllegalArgumentException("数量必须在1到100之间");
        // 学习区结束
    }

    public static void identifier(String value, String label) {
        // 保留大小写；禁用空白和控制字符，避免URL、日志和数据库身份发生歧义。
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,64}"))
            throw new IllegalArgumentException(label + "只允许1到64个字母、数字、下划线或短横线");
    }

    public static Order sameRequest(Order existing, Command command) {
        // 学习区开始
        if (!existing.requestId().equals(command.requestId())
                || !existing.sku().equals(command.sku())
                || existing.quantity() != command.quantity()) throw new Conflict("同一请求号不能换商品或数量");
        return existing;
        // 学习区结束
    }

    public static boolean mayCancel(String status) {
        // 学习区开始
        if (status.equals("RESERVED")) return true;
        if (status.equals("CANCELLED")) return false;
        throw new Conflict("拒绝未知订单状态：" + status);
        // 学习区结束
    }

    public static void validateEvent(Event event) {
        validate(new Command(event.requestId(), event.sku(), event.quantity()));
        if (event.version() < 1
                || !event.eventId().equals(event.requestId() + ":" + event.version()))
            throw new IllegalArgumentException("事件号必须对应请求版本");
        if (!event.status().equals("RESERVED") && !event.status().equals("CANCELLED"))
            throw new IllegalArgumentException("未知事件状态");
        if ((event.status().equals("RESERVED") && event.version() != 1)
                || (event.status().equals("CANCELLED") && event.version() != 2))
            throw new IllegalArgumentException("状态与版本不匹配");
    }
}
