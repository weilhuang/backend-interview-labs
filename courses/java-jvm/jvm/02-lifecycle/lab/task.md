# C03-02 · 引用类型、资源与有界生命周期

## 企业场景与进入条件

订单批处理把已结束请求的byte[]留在长期Map里会导致业务存活范围扩大。文件句柄又不是“等待GC就会及时释放”的资源。本节把保留预算、别名、关闭和引用类型放在一条可测链上。先修：Map、try-with-resources；预计120分钟。

## 可执行目标与合同

实现单线程BoundedStore：容量1至1048576字节；最多256个条目、键最多128个UTF-16单元，空数组也占条目预算；put替换旧值时按净增长计费；超过预算抛IllegalStateException且原状态不变；键和值null拒绝；输入和输出byte[]防御性复制；remove不存在键无影响；close可重复，清空业务引用和计数；关闭后get/put/remove抛IllegalStateException。retainedBytes只计算payload字节，不代表真实堆占用。

输入容量4、放入2字节，结果2；删除后0。Test中显式Reference.enqueue用于验证队列协议，绝不称为GC清除证据。

分类：A为公开契约与资源回归；O为运行观察与解释；R为固定真实源码阅读；T为显式缩小的教学模型。测试通过不意味着O/R完成。JDK21为主线，Gradle8.10.2、JUnit5.11.4；无前端、无Docker、无真实业务数据。

## 机制图解

```text
业务根 -> Map -> byte[]
            |
            +-- remove/clear -> 断开业务强引用

强引用存在 -> 对象仍可达
弱/软/虚引用 -> VM规则 + 引用队列 -> 观察
文件资源 -> close -> 操作系统资源及时归还
```

## 编码与验证步骤

**Academy官方归档导入模式**：用本题Check检查作答，打开对应Usage.java的main运行按钮，或用IDE的Gradle工具窗口执行test/run。Academy2026.9官方导出实际会剔除gradlew、gradlew.bat与gradle-wrapper.jar，仅保留properties；不要在缺少Wrapper的导入目录照抄终端./gradlew命令。项目SDK与Gradle JVM均用完整JDK21。

**源码仓库或普通Gradle学员副本模式**：以下./gradlew命令针对含Wrapper的课程根，Windows用gradlew.bat。完整CLI与诊断教程保留；首次依赖解析失败应区分环境问题与作答失败。

1. 在课程根运行python scripts/lab.py doctor，确认完整JDK21。缺环境记INVALID_ENV，不判断知识水平。
2. 打开本题src与test全部文件，先运行调用端、读成功与失败样例。作者源码是完整解；学习者副本占位区才是待实现区域，答案也直接在本页下方。
3. 只修改答案区，保持公开合同。先运行本题测试，再补边界/异常测试；不要改掉断言消灭失败。
4. 课程根运行./gradlew :jvm-02-lifecycle-lab:test 与 :jvm-02-lifecycle-lab:run。Windows使用gradlew.bat。首次联网下载依赖与编码错误分开处理。
5. 观察入口：python scripts/lab.py layout。本课程自建premain探针用Instrumentation.getObjectSize观察近似浅大小，分别记录默认/关闭压缩对象引用配置；VM.flags由PrintFlagsFinal获取，不要求jcmd附加。不得把大小当规范、深大小或字段偏移；探针会改变对象逃逸条件。记录JDK完整版本、命令、输入、预期、实际和边界。新证据输出build/evidence，不覆盖此前结果。

## 完整调用示例

以下调用端文件、src下辅助类、test下所有测试均对学习者可见；没有隐藏评分逻辑。

```java
package labs.jvm;

public final class BoundedStoreUsage {
    public static void main(String[] args) {
        try (var s = new BoundedStore(4)) {
            s.put("订单", new byte[] {1, 2});
            System.out.println("保留字节=" + s.retainedBytes());
            s.remove("订单");
            System.out.println("释放业务引用后=" + s.retainedBytes());
        }
    }
}
```

## 渐进提示（可选，不锁答案）

<div class="hint" title="H1：先明确不变量">把合同拆为正常、边界、异常、清理四类，先找哪个可见测试证明当前机制。</div>
<div class="hint" title="H2：用最小反例">比较本题说明中的易错边界与完整测试；写一个能区分两种实现的最小输入。</div>
<div class="hint" title="H3：对照步骤">按下面标准解的逐步解释检查状态变化，先定位错误层，再决定是否重写。</div>

## 标准解与逐步解释

[可单独打开完整标准解](solutions/BoundedStore.java.txt)。同一实现也在这里完整展示，无须切分支、解锁或先通过题目。

```java
package labs.jvm;

import java.util.*;

public final class BoundedStore implements AutoCloseable {
    private final int limit;
    private final Map<String, byte[]> entries = new HashMap<>();
    private int used;
    private boolean closed;

    public BoundedStore(int limit) {
        if (limit < 1 || limit > 1024 * 1024) throw new IllegalArgumentException("容量须为1至1048576字节");
        this.limit = limit;
    }

    public void put(String key, byte[] value) {
        // 作答开始
        ensureOpen();
        Objects.requireNonNull(key, "键不能为空");
        Objects.requireNonNull(value, "值不能为空");
        if (key.length() > 128) throw new IllegalArgumentException("键最多128个UTF-16单元");
        if (!entries.containsKey(key) && entries.size() >= 256)
            throw new IllegalStateException("条目数上限256");
        int old = entries.containsKey(key) ? entries.get(key).length : 0;
        long next = (long) used - old + value.length;
        if (next > limit) throw new IllegalStateException("超出业务保留预算");
        entries.put(key, value.clone());
        used = (int) next;
        // 作答结束
    }

    public byte[] get(String key) {
        ensureOpen();
        byte[] value = entries.get(Objects.requireNonNull(key));
        return value == null ? null : value.clone();
    }

    public int retainedBytes() {
        return used;
    }

    public void remove(String key) {
        ensureOpen();
        byte[] old = entries.remove(Objects.requireNonNull(key));
        if (old != null) used -= old.length;
    }

    @Override
    public void close() {
        // 作答开始
        entries.clear();
        used = 0;
        closed = true;
        // 作答结束
    }

    private void ensureOpen() {
        if (closed) throw new IllegalStateException("存储已关闭");
    }
}
```

1. 先检查打开状态与输入，再计算used-old+new。使用long中间值防止算术溢出；拒绝发生在写Map之前，从而保持失败原子性。
2. 写入和读出都复制数组，保证外部别名不改变内部内容。只写入复制而读取直接暴露数组仍然错误。新数据分配可能失败，本实验不制造OOM。
3. close只保证业务结构不再持有payload，不承诺对象在某个毫秒被GC。JVM还有线程栈、临时值、其他引用；弱引用测试必须有reachabilityFence解释活跃强引用范围。
4. SoftReference回收由内存需求驱动，不适合做有确定容量/SLA的缓存。WeakReference不阻止回收，PhantomReference.get始终null、配队列做清理通知；都不能代替显式资源生命周期。
5. put/get复制成本O(B)，Map定位在常规hash假设下平均O(1)；close O(N)。替代实现可保存只读ByteBuffer，但仍需控制底层数组所有权。本类非线程安全；并发化需要把预算与更新作为整体保护。

## 源码与证据

固定OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。[真实源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/lang/ref/Reference.java)；符号：Reference.enqueue、Reference.get、Reference.reachabilityFence。完整出处和补充规范见课程根[源码阅读清单](../../../docs/源码阅读清单.md)。

对照显式enqueue与ReferenceHandler相关路径，记录队列状态和referent。断点观测不得把调试器持有对象引起的可达性变化忽略。对象布局只提交“已观察参数/推测/未证实”表；HotSpot markWord.hpp与oop.hpp仅作为21源码伴读，不在自动测试里固定布局。

R证据至少包含项目/版本/SHA、文件与符号、输入、关键分支、状态值、结论及反例。源码网页定位不等于已实际断点；本课程没有伪造截图。若IDE默认打开供应商补丁版源码，请另记录该版本，不冒充GA调试已完成。

## 面试问答与迁移

- 问：内存泄漏和存活集增长如何区别？答：先给出业务应结束的寿命，再找到根到对象的保留链。仅看堆上涨不能排除合法缓存、暂态分配或GC尚未发生。追问：统计byte[]很多够吗？不够，还要引用来源与持续样本。
- 问：对象一定在堆上吗？答：语言语义不要求每个new都对应一个可观察独立堆分配。逃逸分析可支持标量替换；不能凭代码猜优化一定发生。
- 问：对象头固定多少字节？答：依赖VM、架构、压缩指针、对齐、版本。先记录java -version与VM.flags；不要把课堂常见数值当规范保证。
- 问：try-with-resources遇到双重异常？答：保留业务异常为主，close异常通过suppressed记录；测试直接读取两者。不能在finally重新throw掩盖根因。
- 迁移：给存储新增按租户预算，测试替换、拒绝和close后两个计数一致；仍不能用强制GC作正确性断言。

## 完成与复盘

A必须真正通过；O/R提交证据并按根目录[评阅标准](../../../docs/评阅标准.md)评阅。记录H0独立/H1-H4提示、首次失败、改动原因、24小时后换条件回测。至少能用一个反例解释结论边界。课程不以关键词计分，也不承诺面试结果。
