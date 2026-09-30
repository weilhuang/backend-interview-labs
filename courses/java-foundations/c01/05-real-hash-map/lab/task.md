# C01-05 · 真实HashMap扩容、树化与拆分

## 企业场景与进入条件

“链长8就树化”是常见面试误说，本节从真实JDK源码和受控输入追到分支。先修C01-04；210分钟。

## 合同、输入输出与修改范围

collisionMap用固定初始容量16，最多256个合成键，hash交替0/64且ID不同。先插12键使原桶碰撞，确认查询，再扩到60项触发扩容拆分。JUnit只测试公开行为，不反射JDK私有结构；真实分支证据由scripts/trace_hashmap.py独立收集。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
putVal -> 桶空? / equals? / 链 / 树
链过阈值 -> treeifyBin
             | 容量<64 -> resize
             | 容量>=64 -> 真树化
resize64->128 -> (hash & 64) -> 低链6 / 高链6 -> 可退化链
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-05-real-hash-map-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/HashMapRoutesTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/HashMapRoutes.java的作答区；每完成一个方法运行./gradlew :c01-05-real-hash-map-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class HashMapRoutesUsage {
    public static void main(String[] args) {
        var map = HashMapRoutes.collisionMap(12);
        System.out.println("碰撞插入后可查询=" + HashMapRoutes.verifyLookups(map, 12));
        HashMapRoutes.growForSplit(map);
        System.out.println(
                "扩容后条目=" + map.size() + "，原键仍可查=" + HashMapRoutes.verifyLookups(map, 12));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/HashMapRoutes.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

public final class HashMapRoutes {
    private HashMapRoutes() {}

    public record Key(int id, int forcedHash) {
        @Override
        public int hashCode() {
            return forcedHash;
        }
    }

    public static Map<Key, Integer> collisionMap(int count) {
        // 作答开始
        if (count < 0 || count > 256) throw new IllegalArgumentException("碰撞样本须为0至256");
        Map<Key, Integer> map = new HashMap<>(16);
        for (int i = 0; i < count; i++) map.put(new Key(i, (i % 2) * 64), i);
        return map;
        // 作答结束
    }

    public static boolean verifyLookups(Map<Key, Integer> map, int count) {
        for (int i = 0; i < count; i++)
            if (!Objects.equals(i, map.get(new Key(i, (i % 2) * 64)))) return false;
        return true;
    }

    public static Map<Key, Integer> growForSplit(Map<Key, Integer> map) {
        for (int i = 12; i < 60; i++) map.put(new Key(i, i + 1), i);
        return map;
    }
}
```

1. Key重写hashCode但保留record按id和forcedHash的equals，构造同桶不同键。容量16时0/64低位相同，容量128时新增位将其分开。
2. 21源码TREEIFY_THRESHOLD=8、MIN_TREEIFY_CAPACITY=64、UNTREEIFY_THRESHOLD=6。计数条件要结合putVal循环的binCount初值和添加节点时机，不能简单说第8个必树化。
3. treeifyBin容量不足先resize，足够时替换TreeNode并建树；getNode发现TreeNode转getTreeNode/find。非Comparable键还可能需要双侧搜索与tie-break，别武断把所有树查找写成严格O(log N)。
4. split用旧容量位把树桶拆成lo/hi，计数不大于6时untreeify。本输入刻意6+6；普通散列键后来增长触发resize。
5. 公开测试全过不证明本机走过树化，必须另读真实调试记录；若JDI环境受阻写BLOCKED，不制造截图。GA参考SHA与当前补丁运行src.zip也分别记录。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/HashMap.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：putVal、treeifyBin、TreeNode.find/getTreeNode、TreeNode.split、resize。

记录输入序号、table.length、size、threshold、hash/bit、调用栈与分支；脚本不修改JDK模块开放设置。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：为何碰撞时优先扩容？答：小表可能只是容量不足，新增索引位就能分散，无需付树节点成本。
问：树节点一定按hash形成唯一顺序？答：相同hash还需equals/Comparable/tie-break分支，身份排序不作为公共迭代合同。
问：拆分后两侧长度都6会怎样？答：目标21实现可退化为链，但这不是Map公共API。
迁移：把低/高分配改7+5，在实际源码查看两侧不同结果；不要改自动测试去固定JDK私有节点类。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
