# 02 · 解析边界与稳定去重

## 依赖与完整项目结构

本题依赖完整 JDK21、Gradle Wrapper8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4。编译使用 --release21；无需为每题新建工程或单独安装Gradle。课程根README列出完整目录与环境步骤。

```text
02-parse-ids/
+-- task.md                       # 题目、提示、源码讲解、标准答案
+-- task-info.yaml                # Academy 文件与占位区配置
+-- src/labs/IdParser.java             # 你需要实现的公开接口
+-- src/labs/IdParserUsage.java        # 完整 main 调用端
+-- test/IdParserTest.java             # 完整契约测试，全部可见
+-- test/IdParserExamplesTest.java     # 可扩展的使用样例测试
```

预计 40 分钟。先独立写 15–20 分钟，再按需展开提示；完成后运行检查、口述设计、补一条自己的边界测试。

## 业务背景与目标

输入是逗号分隔的正 int ID；允许 token 两端 ASCII 空白、前导零，去重后保留首次出现顺序。空白整串返回新的可变空列表；不允许符号、小数、非 ASCII 数字、空 token、0、溢出。非法格式抛 IllegalArgumentException（NumberFormatException 是其子类）；null 抛 NullPointerException。

## 示例

"3,1,03,2" → [3,1,2]；"1," 必须失败

## 实作要求

只修改实现文件的答案占位区域，保留公开 API。可在可见的 IdParserExamplesTest.java 中补充自己的 @Test；所有测试代码均可见；参考样例不会代替完整契约测试。先把输入、输出、异常和是否修改状态写成小清单。先写直观正确实现，再讨论优化。编译通过不等于通过契约。

## 三阶提示

### 提示1

String.split 默认会丢掉结尾空串，想想 limit 参数

### 提示2

查重与输出顺序需要同时满足；比较 HashSet 和 LinkedHashSet

### 提示3

解析后去重，而不是原始字符串去重：03 和 3 是同一个 ID

## 源码伴读（固定版本）

打开 [OpenJDK 21 GA，jdk-21+35](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/lang/String.java)，使用 IDE 搜索相关方法。先预测行为，再从分支、字段和调用关系找证据。不能只背结论；记录“类/方法 → 条件 → 状态变化 → 与本题的差异”。

## 源码定位、实验与证据

- 精确定位：String.split(String,int) 与 split(String)
- 可复现实验：用 JShell 比较 "1,".split(",") 和 "1,".split(",",-1) 的长度；再看 ",1" 和 ""。
- 验收证据：记录 limit 三类（正、零、负）的差异。说明本题为什么先判断整体空白，以及前导零何时变成数值身份。

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
public final class IdParserUsage {
    private IdParserUsage() {}

    public static void main(String[] args) {
        List<Integer> ids = IdParser.parse("3, 1,03,2");
        System.out.println("解析后的 ID=" + ids);
    }
}
```

期望输出：

```text
解析后的 ID=[3, 1, 2]
```

## 写代码、使用接口、验证结果

在课程根目录执行（普通学员副本初始失败是预期行为）：

```sh
./gradlew :java-pilot-01-recovery-02-parse-ids:test
./gradlew :java-pilot-01-recovery-02-parse-ids:run
```

1. 先读完整调用端和两份测试，列出正常路径、边界及异常
2. 自己填写答案区，先跑 test，再跑 run 对照上面的输出
3. 在 ExamplesTest 增加一个尚未覆盖的边界；解释为何预期如此
4. 有错误先判断是编译、契约、状态变更还是输出理解错误，再修改实现
5. 测试和调用端都正确后，按下面的源码机制口述，再与标准答案对照

## 核心原理与源码解释

```text
字符串 --> 按逗号保留空字段 --> trim --> 数字校验 --> int解析
                                                      |
                  输出首次出现顺序 <--- LinkedHashSet去重
```

解析器要明确区分文本形式和数值身份：03 与 3 是不同文本，却是同一个 ID。先解析再去重，才能得到符合业务的结果。split 的第二参数为负时保留结尾空字段；默认 split 丢掉结尾空串，会让 "1," 假装成为合法输入。ASCII 数字限制避免接收符号、指数写法和其他语言数字字符。

LinkedHashSet 同时提供 equals/hashCode 意义上的去重与插入顺序。返回 ArrayList 是为了给调用端一个独立、可变的序列。总成本主要随字符数和不同 ID 数量增长；散列表操作使用的是预期复杂度，不是对恶意散列分布的绝对保证。

## 标准答案与逐步解析

以下是本题公开的完整标准答案。建议独立尝试后再对照；答案随课程提供，不依赖隐藏文件、外部教师目录或折叠渲染功能。不同写法只要满足契约与复杂度要求也可以。

```java
// 标准实现位于作者占位区；学员填写同一公开接口，题面末尾提供完整答案与解析。
package labs;
import java.util.*;
public final class IdParser {
    private IdParser() {}
    public static List<Integer> parse(String input) {
        Objects.requireNonNull(input, "input");
        if (input.isBlank()) return new ArrayList<>();
        Set<Integer> seen = new LinkedHashSet<>();
        for (String token : input.split(",", -1)) {
            String value = token.trim();
            if (value.isEmpty() || !value.chars().allMatch(c -> c >= '0' && c <= '9'))
                throw new IllegalArgumentException("expected decimal ID");
            int id = Integer.parseInt(value);
            if (id <= 0) throw new IllegalArgumentException("ID must be positive");
            seen.add(id);
        }
        return new ArrayList<>(seen);
    }
}
```

对照顺序：先看输入校验与异常，再看核心状态更新，再看返回值和是否泄漏可变视图；最后用完整契约测试逐项证明行为。本题另一种正确写法及错误变体用于作者质量回归，不是对学员实现风格的强制要求。

## 面试题递进与参考表达

### 1. 机制：为什么不能先对原始 token 去重？

参考表达：03 与 3 会被误当成两个 ID。

### 2. 边界：空白整串和尾逗号有什么不同？

参考表达：前者明确定义为空列表；后者含一个缺失字段，必须拒绝。

### 3. 取舍：TreeSet 是否可替换 LinkedHashSet？

参考表达：不能直接替换，因为排序会破坏首次出现顺序。

### 4. 追问：错误需要指出第几个字段怎么办？

参考表达：改为带索引迭代并封装字段位置与原因为解析错误；不要悄悄跳过非法字段。
