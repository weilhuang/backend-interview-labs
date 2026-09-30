# C01-03 · 双向链表、BFS与单调队列

## 企业场景与进入条件

消息队列需要两端操作，图遍历和窗口最大值也能借队列高效表达。先修链接结构与C00算法；210分钟。

## 合同、输入输出与修改范围

教学双向链表允许null，支持两端添加/删除和下标读取，空删抛NoSuchElementException，最多4096项；invariants验证首尾与前后链。BFS图允许环，按邻接列表次序首次访问，最多10000节点。windowMaximum空数组仅k=0合法，非空1<=k<=length。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
null <- 首节点 <-> 中间节点 <-> 尾节点 -> null
删除首节点 -> 新首.previous=null；删到空 -> 首尾都null
BFS: 已见集合 + FIFO
窗口: 下标队列，队首未过期，值从前到后递减
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-03-linked-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/LinkedAlgorithmsTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/LinkedAlgorithms.java的作答区；每完成一个方法运行./gradlew :c01-03-linked-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class LinkedAlgorithmsUsage {
    public static void main(String[] args) {
        var deque = new LinkedAlgorithms<String>();
        deque.addFirst("A");
        deque.addLast("B");
        System.out.println("出队=" + deque.removeFirst());
        System.out.println("窗口最大=" + LinkedAlgorithms.windowMaximum(new int[] {1, 3, 2, 5}, 2));
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/LinkedAlgorithms.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

/** 教学双向链表及队列应用；节点不向调用方暴露。 */
public final class LinkedAlgorithms<E> {
    private static final class Link<E> {
        E value;
        Link<E> previous, next;

        Link(E value) {
            this.value = value;
        }
    }

    private Link<E> first, last;
    private int size;

    public int size() {
        return size;
    }

    public void addFirst(E value) {
        if (size == 4096) throw new IllegalStateException("最多4096项");
        Link<E> node = new Link<>(value);
        node.next = first;
        if (first == null) last = node;
        else first.previous = node;
        first = node;
        size++;
    }

    public void addLast(E value) {
        if (size == 4096) throw new IllegalStateException("最多4096项");
        Link<E> node = new Link<>(value);
        node.previous = last;
        if (last == null) first = node;
        else last.next = node;
        last = node;
        size++;
    }

    public E removeFirst() {
        // 作答开始
        if (first == null) throw new NoSuchElementException("链表为空");
        Link<E> removed = first;
        first = removed.next;
        if (first == null) last = null;
        else first.previous = null;
        removed.next = null;
        size--;
        return removed.value;
        // 作答结束
    }

    public E removeLast() {
        if (last == null) throw new NoSuchElementException("链表为空");
        Link<E> removed = last;
        last = removed.previous;
        if (last == null) first = null;
        else last.next = null;
        removed.previous = null;
        size--;
        return removed.value;
    }

    public E get(int index) {
        Objects.checkIndex(index, size);
        Link<E> node;
        if (index < size / 2) {
            node = first;
            for (int i = 0; i < index; i++) node = node.next;
        } else {
            node = last;
            for (int i = size - 1; i > index; i--) node = node.previous;
        }
        return node.value;
    }

    public boolean invariants() {
        if (size == 0) return first == null && last == null;
        if (first == null || last == null || first.previous != null || last.next != null)
            return false;
        int count = 0;
        Link<E> previous = null;
        for (Link<E> n = first; n != null; n = n.next) {
            if (n.previous != previous || ++count > size) return false;
            previous = n;
        }
        return count == size && previous == last;
    }

    public static List<Integer> bfs(Map<Integer, List<Integer>> graph, int start) {
        List<Integer> result = new ArrayList<>();
        Deque<Integer> queue = new ArrayDeque<>();
        Set<Integer> seen = new HashSet<>();
        seen.add(start);
        queue.add(start);
        while (!queue.isEmpty()) {
            int node = queue.removeFirst();
            result.add(node);
            if (result.size() > 10000) throw new IllegalArgumentException("图超出10000节点");
            for (int next : graph.getOrDefault(node, List.of()))
                if (seen.add(next)) queue.addLast(next);
        }
        return List.copyOf(result);
    }

    public static List<Integer> windowMaximum(int[] values, int k) {
        // 作答开始
        if (values.length == 0 && k == 0) return List.of();
        if (k < 1 || k > values.length) throw new IllegalArgumentException("非空窗口须为1至数组长度");
        Deque<Integer> queue = new ArrayDeque<>();
        List<Integer> result = new ArrayList<>();
        for (int i = 0; i < values.length; i++) {
            while (!queue.isEmpty() && queue.peekFirst() <= i - k) queue.removeFirst();
            while (!queue.isEmpty() && values[queue.peekLast()] <= values[i]) queue.removeLast();
            queue.addLast(i);
            if (i >= k - 1) result.add(values[queue.peekFirst()]);
        }
        return List.copyOf(result);
        // 作答结束
    }
}
```

1. 空链首次插入同时设置首尾；移除最后一个也要同时清空。只改first不改新首previous会留下逻辑坏链，测试直接检测声明不变量。
2. get从较近一端定位仍最坏O(N)。拥有节点引用时局部接链O(1)，不能把带定位的插入也泛称常数时间。
3. BFS入队时标seen，避免有环图重复无限入队；出队顺序依赖明确邻接顺序，不依赖HashMap遍历。
4. 单调队列存下标便于淘汰过期，<=i-k表示已离开窗口；后端淘汰更小或相等值，每个元素进出至多一次。保留相等值也是合法替代，只要过期处理正确。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/LinkedList.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：linkFirst、unlinkFirst、node；ArrayDeque双端操作。

定位成本与接链成本分开记录；不得将教学节点模型称完整LinkedList。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：链表比数组插入快吗？答：要计入定位成本、缓存局部性与节点开销，场景决定。
问：窗口最大值为何不能只保存最大数？答：它过期后还要知道候选，且重复值需要位置。
问：BFS何时找到最短路？答：无权/等权边按层遍历才有该结论，带权需另选算法。
迁移：给链表增加removeAt并覆盖首、中、尾、单节点；给BFS返回父节点路径。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
