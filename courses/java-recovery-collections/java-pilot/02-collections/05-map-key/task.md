# 05 · 不可变 Map Key 的身份契约

## 依赖与完整项目结构

本题使用完整 JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4，编译使用 --release21。源码仓库自带 Gradle Wrapper；Academy 导入课程由 IDE 管理 Gradle。无需为每题新建工程，具体入口见下面的运行说明。

```text
05-map-key/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/TenantKey.java             # 你需要实现的公开接口
+-- src/labs/TenantKeyUsage.java        # 完整 main 调用端
+-- test/TenantKeyTest.java             # 完整契约测试，全部可见
+-- test/TenantKeyExamplesTest.java     # 可扩展的使用样例测试
```

预计 45 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

tenant 与 userId 共同定义身份，tenant 区分大小写，保留原样，不隐式 trim；构造器已经校验。实现 equals 与 hashCode，不要求不同 key 的 hashCode 都不同。不能改变类的不可变结构。

## 示例

两个 new TenantKey("acme",7) 能查到同一个 HashMap 条目

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 TenantKeyExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

先排除 null 和不兼容类型

### 提示2

两个身份字段都必须参与 equals

### 提示3

同一个 tenant 内容可能来自不同 String 实例，不能用 ==

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/HashMap.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：HashMap.hash、getNode、putVal
- 可复现实验：用两个不同实例但身份相同的 TenantKey 进行 put/get；再用 tenant 分别为 Aa 与 BB 的 key。
- 验收证据：标出先比较 hash、再比较 ==/equals 的分支。写出只实现 equals 而不匹配 hashCode 为什么会出错；不得声称不同 key 必须有不同 hash。

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
public final class TenantKeyUsage {
    private TenantKeyUsage() {}

    public static void main(String[] args) {
        Map<TenantKey, String> users = new HashMap<>();
        users.put(new TenantKey("acme", 7), "用户甲");
        TenantKey equivalent = new TenantKey(new String("acme"), 7);
        System.out.println("查到用户=" + users.get(equivalent));
        System.out.println("条目数量=" + users.size());
    }
}
```

期望输出：

```text
查到用户=用户甲
条目数量=1
```

## 写代码、使用接口、验证结果

**Academy 导入或预览模式**：用题面底部的 **Check** 验证答案；打开 `src/labs/TenantKeyUsage.java`，点击 `main` 旁的运行图标执行调用示例。也可在 Gradle 工具窗口选择本题模块的 `test` 或 `run` 任务。未完成 TODO 时，测试或调用失败是预期行为。

**源码仓库或普通 Gradle 学员副本模式**：仅在包含 `gradlew`、`gradlew.bat` 和 `gradle/wrapper/gradle-wrapper.jar` 的工程根目录执行下面命令。普通学员副本由 `authoring/materialize_learner.py` 生成。

实际验证的 Academy 官方导出 ZIP 和干净导入目录不包含上述三个 Wrapper 文件，不能直接在该导入目录执行 `./gradlew`。以下命令保留给源码与普通 Gradle 工程入口：

```sh
./gradlew :java-pilot-02-collections-05-map-key:test
./gradlew :java-pilot-02-collections-05-map-key:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区；Academy 模式先点 Check 再运行 Usage，源码模式先跑 test 再跑 run，对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
tenant + userId
       |
   hashCode --> 桶位置 --> 比较hash --> 比较equals --> 命中
                碰撞可以发生；不相等的键仍能共存
```

equals 定义业务身份，hashCode 必须与该身份保持一致：相等对象必须有相同 hash，不相等对象可以碰撞。String 内容比较用 equals，而不是比较两个引用是否恰好指向同一对象。TenantKey 为 final，身份字段也是 final，避免子类型扩展相等语义导致对称性问题。

HashMap.put 将计算的 hash 与节点一起保存。若插入后修改影响哈希的字段，新查询会计算另一份 hash，可能连原来的桶都找不到。final 引用本身不等于深不可变；本题的 String 和 long 刚好不会暴露可变身份组件。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.Objects;
public final class TenantKey {
    private final String tenant;
    private final long userId;
    public TenantKey(String tenant, long userId) {
        Objects.requireNonNull(tenant, "tenant");
        if (tenant.isBlank() || userId <= 0) throw new IllegalArgumentException("invalid identity");
        this.tenant = tenant;
        this.userId = userId;
    }
    public String tenant() { return tenant; }
    public long userId() { return userId; }
    @Override public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof TenantKey that)) return false;
        return userId == that.userId && tenant.equals(that.tenant);
    }
    @Override public int hashCode() {
        return 31 * tenant.hashCode() + Long.hashCode(userId);
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：equals 与 hashCode 谁先用？

参考表达：HashMap 先根据散列定位，再以 hash 和引用/equals 验证候选节点。

### 2. 边界：Aa 与 BB 可能同 hash，是否违规？

参考表达：不违规；不同对象允许相同 hash，equals 仍要区分。

### 3. 取舍：把所有 hashCode 都返回1行不行？

参考表达：契约未必被破坏，但会恶化分布与性能，不是合格的工程实现。

### 4. 追问：字段如果换成 List 怎么办？

参考表达：需要防御性复制并明确是否把列表内容作为身份，不能只加 final 就宣称不可变。
