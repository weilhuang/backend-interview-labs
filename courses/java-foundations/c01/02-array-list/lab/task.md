# C01-02 · 泛型动态数组与过期引用

## 企业场景与进入条件

实现教学动态数组来理解扩容、搬移和过期引用；不是照抄JDK全部List功能。先修数组/泛型；180分钟。

## 合同、输入输出与修改范围

MiniArrayList<E>支持add/get/set/remove、size/capacity/snapshot，允许null，索引必须0..size-1，set/remove返回旧值。最多4096项；闲置槽必须为null，unusedSlotsCleared是公开教学诊断接口。未实现Iterator、List全部方法、序列化、线程安全。

本题在独立完整工程中运行：src是实现与调用方，test是全部公开测试，common是本课程内的完整领域checkpoint。只改答案区，接口和测试合同不变；可在test补自己的回归。标准解始终直接可读，未隐藏测试或答案。

## 概念与ASCII图

```text
有效区 [0,size) | 闲置区 [size,capacity)
add满 -> 新数组 -> 拷贝有效区 -> 插入
remove(i) -> 左移(i+1..size-1) -> size-1 -> 尾槽=null
```

## 分步使用与验证

运行路线先区分：以下./gradlew命令适用于带Wrapper的源码仓库课程目录。若从Academy官方ZIP导入，用本题Check、Usage main运行按钮或IDE Gradle工具窗口的对应任务；Academy2026.9官方ZIP实际会剔除Wrapper脚本和JAR，不能承诺导入目录的终端./gradlew可用。完整CLI学习仍保留，使用源码仓库路线。

1. 在本课程根设完整JDK21；运行./gradlew :c01-02-array-list-lab:run看真实调用，Windows改用gradlew.bat。
2. 打开下方完整调用端与test/MiniArrayListTest.java，预测正常、边界、异常结果。作者源码是标准解；学习者占位副本才是练习起点。
3. 填写src/labs/foundation/MiniArrayList.java的作答区；每完成一个方法运行./gradlew :c01-02-array-list-lab:test，先看到最小失败，再修复，不删断言。
4. 新增一条与本页易错点不同的回归。工具缺失记INVALID_ENV，没运行记NOT_RUN，不能用静态解析代替真实运行。
5. 提交源码阅读/观察表与本页迁移练习。A为自动契约，O为解释/观察，R为真实源码，T为显式教学子集；A绿不代表O/R或独立掌握完成。

主线JDK21、Gradle8.10.2、JUnit5.11.4，无前端/Docker/外部服务。测试限定合成输入和临时目录，不访问真实业务数据。

## 完整调用示例

```java
package labs.foundation;

public final class MiniArrayListUsage {
    public static void main(String[] args) {
        var values = new MiniArrayList<String>();
        values.add("订单A");
        values.add("订单B");
        System.out.println("删除=" + values.remove(0));
        System.out.println("剩余=" + values.snapshot() + "，容量=" + values.capacity());
    }
}
```

## 可选提示

<div class="hint" title="H1：合同与不变量">把正常、边界、异常与失败后状态分别列出，先判断哪条可见测试在区分它们。</div>
<div class="hint" title="H2：最小反例">先从本页机制解释找到一个两三项输入的反例，避免直接加随机压力掩盖错误。</div>
<div class="hint" title="H3：步骤定位">沿下面标准解的步骤检查第一次状态偏离，再决定改哪一段；答案无需先过题即可查看。</div>

## 标准解与逐步解释

[完整实现副本](solutions/MiniArrayList.java.txt)。以下是同一源码的完整内容；common、辅助类、调用端和全部测试均公开。

```java
package labs.foundation;

import java.util.*;

/** 教学数组容器：不实现完整List、迭代器、序列化或线程安全。 */
public final class MiniArrayList<E> {
    private Object[] elements = new Object[0];
    private int size;

    public int size() {
        return size;
    }

    public int capacity() {
        return elements.length;
    }

    public void add(E value) {
        // 作答开始
        if (size == 4096) throw new IllegalStateException("教学上限4096项");
        if (size == elements.length)
            elements =
                    Arrays.copyOf(
                            elements,
                            Math.min(
                                    4096,
                                    Math.max(
                                            1,
                                            elements.length + Math.max(1, elements.length / 2))));
        elements[size++] = value;
        // 作答结束
    }

    @SuppressWarnings("unchecked")
    public E get(int index) {
        Objects.checkIndex(index, size);
        return (E) elements[index];
    }

    public E set(int index, E value) {
        E old = get(index);
        elements[index] = value;
        return old;
    }

    public E remove(int index) {
        // 作答开始
        E old = get(index);
        int moved = size - index - 1;
        if (moved > 0) System.arraycopy(elements, index + 1, elements, index, moved);
        elements[--size] = null;
        return old;
        // 作答结束
    }

    public boolean unusedSlotsCleared() {
        for (int i = size; i < elements.length; i++) if (elements[i] != null) return false;
        return true;
    }

    public List<E> snapshot() {
        List<E> result = new ArrayList<>();
        for (int i = 0; i < size; i++) result.add(get(i));
        return Collections.unmodifiableList(result);
    }
}
```

1. 容量和元素数量分开，空数组第一次add分配至少1。增长几何级数带来摊还O(1)add，但单次扩容仍O(N)。
2. get先校验边界；set复用get取得旧值再替换。remove左移size-index-1项，不能漏掉末尾。
3. size减小不等于引用消失：旧尾槽清null让容器不再持有对象。测试检查声明的教学接口，不通过反射强迫JDK私有布局。
4. 本题Object[]加受控泛型转换是内部实现手段，不把Object暴露给调用方。替代逐项循环搬移也接受。随机对照ArrayList只比已声明公共子集。

## 源码与证据

[OpenJDK21固定源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/util/ArrayList.java)，tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。符号：grow、add、fastRemove、DEFAULTCAPACITY_EMPTY_ELEMENTDATA。

从21固定源码读取延迟分配与清尾动作；教学增长倍数不是标准库保证。

R记录必须含版本/SHA、文件/符号、输入、关键状态、分支、反例与结论。当前补丁JDK的src.zip不是GA原件，动态证据必须分别标识，不能编造断点截图。[源码路线与证据模板](../../../docs/源码与评阅.md)说明如何核对。教学容器只实现已列子集，不称生产级框架。

## 面试问答与迁移

问：ArrayList.add永远O(1)吗？答：摊还成立，扩容那一次为线性；不要把平均摊还和最坏混用。
问：remove清尾引用会立即GC吗？答：只断开这一条保留链，不承诺全局不可达或立刻回收。
问：为什么JDK默认容量与本题不同？答：真实实现有延迟分配哨兵等优化，本题刻意缩小合同。
迁移：新增add(index,value)和批量addAll，测试容量增长、重叠搬移和输入别名。

## 完成标准

关键A全部通过；解释、证据、迁移按[评阅标准](../../../docs/源码与评阅.md)至少达到能讲机制和边界。记录H0独立到H4完整答案、首次失败、修复原因，并在24小时后不看答案完成变式。不能用“看懂了/复制后全绿”代替独立掌握，也不承诺面试结果。
