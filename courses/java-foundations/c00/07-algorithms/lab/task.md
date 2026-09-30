# C00-07 · 七类编码模式与不变量

## 企业场景与进入条件

面试编码要能识别结构而非背整题。七个独立方法分别练计数、双指针、滑窗、二分、栈、树BFS与DP；每个都能单独调用。先修C00-01至06；240分钟，可拆多次。

## 合同、输入输出与修改范围

count按Locale.ROOT转小写统计，null词拒绝。twoSumSorted要求升序且用两个不同位置，和用long。longestAtMostTwo按Unicode码点计算最长至多两类窗口。lowerBound返回首个>=key位置或length。balanced仅接收圆括号。BFS按左右顺序，最多10000节点。minimumCoins为无限硬币最少数，amount0..10000、币值全正，不可达-1。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
计数: 值 -> 次数
双指针: 小和移左，大和移右
滑窗: 扩右 -> 超两类时缩左 -> 更新最长
二分: [left,right)保持答案在内
栈: 左括号入，右括号配对
树: 队列逐层推进
DP: dp[x]=min(dp[x-coin]+1)
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c00-07-algorithms-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/AlgorithmsTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/Algorithms.java的作答区；每完成一个方法运行./gradlew :c00-07-algorithms-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class AlgorithmsUsage {
    public static void main(String[] args) {
        System.out.println("两类字符最长窗口=" + Algorithms.longestAtMostTwo("eceba"));
        System.out.println("下界=" + Algorithms.lowerBound(new int[] {1, 2, 2, 4}, 2));
        System.out.println("最少硬币=" + Algorithms.minimumCoins(6, new int[] {1, 3, 4}));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/Algorithms.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

public final class Algorithms {
    private Algorithms() {}

    public static Map<String, Integer> count(List<String> words) {
        Map<String, Integer> result = new TreeMap<>();
        for (String word : words)
            result.merge(Objects.requireNonNull(word).toLowerCase(Locale.ROOT), 1, Math::addExact);
        return result;
    }

    public static boolean twoSumSorted(int[] a, long target) {
        // 作答开始
        int left = 0, right = a.length - 1;
        while (left < right) {
            long sum = (long) a[left] + a[right];
            if (sum == target) return true;
            if (sum < target) left++;
            else right--;
        }
        return false;
        // 作答结束
    }

    public static int longestAtMostTwo(String text) {
        // 作答开始
        int[] points = text.codePoints().toArray();
        Map<Integer, Integer> counts = new HashMap<>();
        int left = 0, best = 0;
        for (int right = 0; right < points.length; right++) {
            counts.merge(points[right], 1, Integer::sum);
            while (counts.size() > 2) {
                int p = points[left++];
                int remaining = counts.get(p) - 1;
                if (remaining == 0) counts.remove(p);
                else counts.put(p, remaining);
            }
            best = Math.max(best, right - left + 1);
        }
        return best;
        // 作答结束
    }

    public static int lowerBound(int[] sorted, int key) {
        // 作答开始
        int left = 0, right = sorted.length;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (sorted[mid] < key) left = mid + 1;
            else right = mid;
        }
        return left;
        // 作答结束
    }

    public static boolean balanced(String text) {
        Deque<Character> stack = new ArrayDeque<>();
        for (char c : text.toCharArray()) {
            if (c == '(') stack.push(c);
            else if (c == ')') {
                if (stack.isEmpty()) return false;
                stack.pop();
            } else throw new IllegalArgumentException("仅允许圆括号");
        }
        return stack.isEmpty();
    }

    public record Node(int value, Node left, Node right) {}

    public static List<Integer> breadthFirst(Node root) {
        if (root == null) return List.of();
        List<Integer> result = new ArrayList<>();
        Deque<Node> queue = new ArrayDeque<>();
        queue.add(root);
        while (!queue.isEmpty()) {
            Node node = queue.remove();
            result.add(node.value());
            if (result.size() > 10000) throw new IllegalArgumentException("树超过10000节点");
            if (node.left() != null) queue.add(node.left());
            if (node.right() != null) queue.add(node.right());
        }
        return List.copyOf(result);
    }

    public static int minimumCoins(int amount, int[] coins) {
        // 作答开始
        if (amount < 0 || amount > 10000) throw new IllegalArgumentException("金额须为0至10000");
        for (int coin : coins) if (coin <= 0) throw new IllegalArgumentException("币值必须为正");
        int[] dp = new int[amount + 1];
        Arrays.fill(dp, amount + 1);
        dp[0] = 0;
        for (int value = 1; value <= amount; value++)
            for (int coin : coins)
                if (coin <= value) dp[value] = Math.min(dp[value], dp[value - coin] + 1);
        return dp[amount] > amount ? -1 : dp[amount];
        // 作答结束
    }
}
```

1. 双指针的淘汰依据依赖排序前提；不排序又照搬移动规则会丢答案。先提升到long再相加，避免int溢出后才转long。
2. 滑窗计数归零必须移除key，否则distinct大小不再表示当前窗口类别数。用codePoints不把emoji拆成两个UTF-16单元。每个位置至多进出一次，时间O(N)。
3. 二分使用半开区间与left+(right-left)/2，sorted[mid]<key才丢左半；等于key时保留左侧重复值。O(log N)基于区间每步收缩，不靠计时证明。
4. 栈配对与BFS维护不同不变量，不混成一个“用栈队列都一样”的模板。BFS空间依赖最大层宽。
5. DP先设dp[0]=0，其余amount+1代表不可达，枚举最后一枚硬币；贪心在1/3/4凑6时会错。O(amount*币种数)时间、O(amount)空间。
6. 固定种子随机小样本与暴力枚举/BFS oracle对照；测试证明样本下合同，不能代替算法证明。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/ArrayDeque.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：addLast、pollFirst、push/pop；Arrays.binarySearch。

比较公共API与本题lowerBound合同：binarySearch对重复值不承诺首个位置，不直接拿它做错误oracle。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：二分循环为何用<而不是<=？答：区间定义不同，没有脱离不变量的万能符号。
问：滑窗能处理任意负权和限制吗？答：不是；本题计数窗口可单调收缩，换成含负数的和约束需另分析。
问：DP和贪心如何选择？答：先找最优子结构/交换论证，不能只因贪心代码短就用。
迁移：分别改成三类窗口、upperBound、最少硬币方案重建；逐项写新不变量，禁止一次写成巨型函数。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
