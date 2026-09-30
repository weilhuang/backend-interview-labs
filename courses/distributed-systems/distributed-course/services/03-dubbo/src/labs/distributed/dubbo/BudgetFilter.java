package labs.distributed.dubbo;

import org.apache.dubbo.common.extension.Activate;
import org.apache.dubbo.rpc.*;

/** 输入附件是不可信数据；追踪标识不当作身份，预算不允许无限放大。 */
@Activate(group = "provider")
public final class BudgetFilter implements Filter {
  @Override
  public Result invoke(Invoker<?> invoker, Invocation invocation) throws RpcException {
    // 练习区开始
    String trace = invocation.getAttachment("trace-id");
    String budget = invocation.getAttachment("budget-ms");
    if (trace == null || !trace.matches("[a-zA-Z0-9_-]{1,64}")) {
      throw new RpcException(RpcException.BIZ_EXCEPTION, "追踪标识缺失或非法");
    }
    long millis;
    try {
      millis = Long.parseLong(budget);
    } catch (RuntimeException failure) {
      throw new RpcException(RpcException.BIZ_EXCEPTION, "预算格式非法");
    }
    if (millis < 1 || millis > 5000) {
      throw new RpcException(RpcException.BIZ_EXCEPTION, "预算超出允许范围");
    }
    return invoker.invoke(invocation);
    // 练习区结束
  }
}
