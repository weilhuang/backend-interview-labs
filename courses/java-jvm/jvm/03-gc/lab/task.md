# C03-03 · 受控分配与GC停顿证据

## 企业场景与进入条件

生产停顿告警往往同时伴随流量、分配率、堆大小变化。要比较GC，先保证同一业务负载，再区分GC停顿与请求延迟。本节是小规模可复现实验，不是JMH或生产容量结论。预计150分钟。

## 可执行目标与合同

run(rounds,blockSize,liveBlocks)：rounds为0..4096，blockSize为1..65536，liveBlocks为1..8，其余抛IllegalArgumentException。总分配最大256MiB，业务payload长期存活上限512KiB（分配替换瞬间还可能有一个额外新块）。Result返回校验和、累计分配字节、槽位保留payload上界。校验和是每轮首尾字节之和再加最后ring每块首字节；4轮、4字节、2槽返回(17,16,8)。

scripts/lab.py gc分别在32MiB堆的隔离JVM中运行G1、Serial同一4096轮负载，最多30秒每次、日志最多约4MiB轮转。报告取nearest-rank分位数，样本不足明确标注。

分类：A为公开契约与资源回归；O为运行观察与解释；R为固定真实源码阅读；T为显式缩小的教学模型。测试通过不意味着O/R完成。JDK21为主线，Gradle8.10.2、JUnit5.11.4；无前端、无Docker、无真实业务数据。

## 机制图解

```text
固定输入 -> 新byte[] -> 写入全部内容 -> 有界环形槽
                              |             |
                              v             v
                           校验和       替换旧引用
                              |             |
                              +---- 业务结果 + GC日志

同负载 + 同堆 + 同JDK + 同CPU配额 -> 才能比较本次观察
```

## 编码与验证步骤

1. 在课程根运行python scripts/lab.py doctor，确认完整JDK21。缺环境记INVALID_ENV，不判断知识水平。
2. 打开本题src与test全部文件，先运行调用端、读成功与失败样例。作者源码是完整解；学习者副本占位区才是待实现区域，答案也直接在本页下方。
3. 只修改答案区，保持公开合同。先运行本题测试，再补边界/异常测试；不要改掉断言消灭失败。
4. 课程根运行./gradlew :jvm-03-gc-lab:test 与 :jvm-03-gc-lab:run。Windows使用gradlew.bat。首次联网下载依赖与编码错误分开处理。
5. 观察入口：python scripts/lab.py gc。记录JDK完整版本、命令、输入、预期、实际和边界。新证据输出build/evidence，不覆盖此前结果。

## 完整调用示例

以下调用端文件、src下辅助类、test下所有测试均对学习者可见；没有隐藏评分逻辑。

```java
package labs.jvm;

public final class AllocationWorkloadUsage {
    public static void main(String[] args) {
        int rounds = args.length == 0 ? 4096 : Integer.parseInt(args[0]);
        System.out.println("受控分配=" + AllocationWorkload.run(rounds, 65536, 8));
    }
}
```

## 渐进提示（可选，不锁答案）

<div class="hint" title="H1：先明确不变量">把合同拆为正常、边界、异常、清理四类，先找哪个可见测试证明当前机制。</div>
<div class="hint" title="H2：用最小反例">比较本题说明中的易错边界与完整测试；写一个能区分两种实现的最小输入。</div>
<div class="hint" title="H3：对照步骤">按下面标准解的逐步解释检查状态变化，先定位错误层，再决定是否重写。</div>

## 标准解与逐步解释

[可单独打开完整标准解](solutions/AllocationWorkload.java.txt)。同一实现也在这里完整展示，无须切分支、解锁或先通过题目。

```java
package labs.jvm;

public final class AllocationWorkload {
    public record Result(long checksum, long allocatedBytes, int peakPayloadBytes) {}

    private AllocationWorkload() {}

    public static Result run(int rounds, int blockSize, int liveBlocks) {
        // 作答开始
        if (rounds < 0
                || rounds > 4096
                || blockSize < 1
                || blockSize > 65536
                || liveBlocks < 1
                || liveBlocks > 8) throw new IllegalArgumentException("参数超出安全预算");
        byte[][] ring = new byte[liveBlocks][];
        long checksum = 0;
        for (int i = 0; i < rounds; i++) {
            byte[] block = new byte[blockSize];
            java.util.Arrays.fill(block, (byte) (i % 127));
            ring[i % liveBlocks] = block;
            checksum += Byte.toUnsignedInt(block[0]) + Byte.toUnsignedInt(block[blockSize - 1]);
        }
        // 有意让有界存活集参与结果，避免把GC观察误读成纯分配优化。
        for (byte[] block : ring) if (block != null) checksum += Byte.toUnsignedInt(block[0]);
        return new Result(
                checksum, (long) rounds * blockSize, Math.min(rounds, liveBlocks) * blockSize);
        // 作答结束
    }
}
```

1. 边界校验保证实验不会变成无限分配或人为OOM。ring长度由liveBlocks决定，替换下标i%liveBlocks，不按总请求数增长容器。
2. 每个byte[]都写入，并参与校验和及末尾存活集读回；这降低“没有业务作用的分配被优化”的误判风险，但仍不能仅由Java代码断言优化器实际分配次数。
3. 累计分配字节是业务请求的payload统计；peakPayloadBytes是环槽保留上界，均不包含对象头、数组表或VM本身，更不是进程RSS。
4. GC脚本比较输出完全一致，是A；pause samples/p50/p95/p99是O。输出wall包含JVM启动，分配速率仅粗略指标，没有测量请求P99延迟。零停顿样本表示证据不足，不是“这个GC没有停顿”。
5. 复杂度O(rounds*blockSize)，保留空间O(liveBlocks*blockSize)。循环手写填充是可接受替代，不强求Arrays.fill；固定种子oracle只比较业务结果，不比较哪台机器更快。

## 源码与证据

固定OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。[真实源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/hotspot/share/gc/g1/g1CollectedHeap.cpp)；符号：G1CollectedHeap::do_collection_pause_at_safepoint。完整出处和补充规范见课程根[源码阅读清单](../../../docs/源码阅读清单.md)。

定位暂停入口与日志事件，记录gcId、GC cause、堆前后。用日志关联源码阶段，而非臆造JVM断点已执行。对照Serial的GenCollectedHeap收集入口，说明本例不是完整收集器实现。

R证据至少包含项目/版本/SHA、文件与符号、输入、关键分支、状态值、结论及反例。源码网页定位不等于已实际断点；本课程没有伪造截图。若IDE默认打开供应商补丁版源码，请另记录该版本，不冒充GA调试已完成。

## 面试问答与迁移

- 问：平均停顿更低能说明P99请求更低吗？答：不能，采样分布、排队、业务服务时间和GC并发CPU争用都可能不同。需要稳定负载、请求时间线、多个fork和足够尾样本。
- 问：增大堆为什么有时有利有时不利？答：可降低回收频率但改变单次工作量、存活集与内存压力；必须结合收集器与SLA，不用“大堆肯定快”作答案。
- 问：G1与Serial的区别怎么有证据地讲？答：阅读固定源码GC入口，结合日志事件区分分代区域/并行或并发工作与单线程收集，不能把所有阶段一概称“并发无停顿”。
- 问：为什么不用System.gc保证每轮一致？答：这改变了实验负载且语义受VM参数影响；显式GC不是业务回收保证。若研究显式GC，应单独声明变量。
- 迁移：保持总分配相同，改变存活槽数，做3次独立JVM对照并解释样本不足与波动，不设性能倍数门槛。

## 完成与复盘

A必须真正通过；O/R提交证据并按根目录[评阅标准](../../../docs/评阅标准.md)评阅。记录H0独立/H1-H4提示、首次失败、改动原因、24小时后换条件回测。至少能用一个反例解释结论边界。课程不以关键词计分，也不承诺面试结果。
