# 10 · HashMap 扰动与桶索引

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
10-hash-index/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/HashIndex.java             # 你需要实现的公开接口
+-- src/labs/HashIndexUsage.java        # 完整 main 调用端
+-- test/HashIndexTest.java             # 完整契约测试，全部可见
+-- test/HashIndexExamplesTest.java     # 可扩展的使用样例测试
```

预计 60 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

实现 OpenJDK21 HashMap 的 int hash 扰动公式和正 2 的幂容量下的桶索引；参数 hash 是原始 hashCode，不处理对象或 null。非法容量抛 IllegalArgumentException。不要用 abs(hash)%capacity。

## 示例

hash=0x00010000,capacity=16 → index=1

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 HashIndexExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

>>> 是无符号右移，>> 会符号扩展

### 提示2

2 的幂容量可以用按位与保留低位

### 提示3

容量翻倍后，一个旧桶的节点只可能留原位或移动 oldCapacity

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/HashMap.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：HashMap.hash（约336行）、putVal（约631行）、resize（约683行）、treeifyBin（约761行）
- 可复现实验：在匹配的 JDK21 调试源码上，令自定义 Key 的 hashCode 恒为 1、equals 按唯一 id，比较 new HashMap<>(64) 与 new HashMap<>(16) 逐个 put 1..12 的过程。在 treeifyBin 和 resize 设断点；另记录旧容量16时 hash=1、17、33 的桶迁移。
- 验收证据：提交逐次插入表：size、table.length、链/树、binCount、是否先扩容。核对 TREEIFY_THRESHOLD=8、MIN_TREEIFY_CAPACITY=64 与实际 put 路径的计数方式；绝不能只写“到8就一定树化”。再从 resize 的 oldCap 位判断推导桶拆分；UNTREEIFY_THRESHOLD=6 的使用场景需单独定位，不能与普通 remove 简单画等号。

固定源码 tag jdk-21+35 对应 commit 890adb6410dab4606a4f26a942aed02fb2f55387。本题固定源码为21 GA；若运行的是21的后续更新，调试器源码与字节码应匹配该更新版本。可以对照差异，但请分别记录源码tag和实际运行时补丁版本。

## 面试表达与复盘

回答以下问题，每项用代码或测试支撑：

1. 你的实现维护什么不变量？失败后会留下什么状态？
2. 时间/空间复杂度是什么？最坏与均摊/预期是否相同？
3. 哪个测试会击穿一个看似合理的错误实现？
4. 与 JDK 实现有哪些差异？如果并发访问会发生什么？

完成后记录：首次测试结果、用了第几阶提示、实际耗时、失败原因、24 小时后能否无提示重写。不要用“测试全绿”替代源码解释与口述验收。


## 完整调用示例

以下文件已经放在工程中，可直接打开或通过本题 run 任务执行：

```java
package labs;

import java.util.*;

// 完整调用端：先构造输入，再调用业务接口，最后打印可核对的结果。
public final class HashIndexUsage {
    private HashIndexUsage() {}

    public static void main(String[] args) {
        int rawHash = 0x00010000;
        System.out.println("扰动后=" + HashIndex.spread(rawHash));
        System.out.println("桶索引=" + HashIndex.index(rawHash, 16));
    }
}
```

期望输出：

```text
扰动后=65537
桶索引=1
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/HashIndexUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-03-internals-10-hash-index:test
./gradlew :java-pilot-03-internals-10-hash-index:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
原hash:  高16位 | 低16位
                 XOR 高16位下移
扰动hash --> 与(capacity-1)按位与 --> 桶索引

容量翻倍: 原桶j --> j 或 j+oldCapacity
                    取决于hash的oldCapacity那一位
```

容量为2的幂时，capacity-1 的低位全是1，按位与就能保留需要的低位形成非负索引。高位右移再异或，把一部分高位信息混入低位，减少某些只在高位不同的 hash 集中到同一个桶；这不是加密哈希，也不能消除碰撞。无符号右移 >>> 对负数尤其重要。

resize 时不是必须对每个节点重新计算 key.hashCode。已有扰动 hash 与 oldCapacity 按位与，就能决定留在旧索引还是搬到旧索引加容量。树化还受容量和具体插入路径约束；TREEIFY_THRESHOLD=8 不等于“任何情况下第8个元素立即树化”。本题只实现扰动和索引，源码实验负责理解完整 HashMap 的其他分支。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
public final class HashIndex {
    private HashIndex() {}
    public static int spread(int hash) {
        return hash ^ (hash >>> 16);
    }
    public static int index(int hash, int capacity) {
        if (capacity <= 0 || (capacity & (capacity - 1)) != 0)
            throw new IllegalArgumentException("capacity must be a positive power of two");
        return spread(hash) & (capacity - 1);
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：为什么不能用abs(hash)%capacity？

参考表达：Integer.MIN_VALUE 的abs仍是负数；本题的位掩码还能直接对应2的幂容量与扩容拆分。

### 2. 边界：容量3为何拒绝？

参考表达：掩码公式假定容量为正2的幂；放宽参数却保留公式会改变分布和合法索引含义。

### 3. 取舍：碰撞多就马上变红黑树吗？

参考表达：不一定；小表优先扩容，是否树化要沿treeifyBin和调用路径解释。

### 4. 追问：HashMap为何仍不能并发读写？

参考表达：桶数组、节点链接、大小等复合状态没有并发协议；换成volatile引用并不能修复整个数据结构。
