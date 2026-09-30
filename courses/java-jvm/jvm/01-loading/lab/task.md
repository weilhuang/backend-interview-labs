# C03-01 · 字节码、初始化与加载器命名空间

## 企业场景与进入条件

企业插件宿主需要按租户隔离实现类，但平台类型与共享API必须保持同一身份。今天先在合成插件类上验证命名空间，不编写可从任意路径加载第三方代码的插件系统。先修：类、继承、异常；预计120分钟。

## 可执行目标与合同

实现 LoaderLab.isolated：只对一个指定二进制名称采用子优先，其他类委派给父加载器；相同加载器重复请求返回同一Class；传入字节数组须防御性复制；java.开头的目标一律拒绝；null类名/字节抛NullPointerException。数组内容不是有效类文件时由JVM抛LinkageError子类，不把验证器失败转成null。

先运行LoaderLabUsage，预期两倍=6、常量=7且事件为空，主动初始化后为[父类, 子类]。twice(-2)=-4。只改变isolation答案区；LoadTarget与InitTrace等是完整可见fixture。测试使用每次独立JVM，初始化计数不在同一Class中随意重置后重用。

分类：A为公开契约与资源回归；O为运行观察与解释；R为固定真实源码阅读；T为显式缩小的教学模型。测试通过不意味着O/R完成。JDK21为主线，Gradle8.10.2、JUnit5.11.4；无前端、无Docker、无真实业务数据。

## 机制图解

```text
调用方请求名称
  |
  v
已定义? -是-> 返回同一Class
  |
  否
  v
指定插件? -否-> 父加载器 -> 平台/API
  |
  是
  v
defineClass -> 链接 -> 首次主动使用 -> 初始化

同一名字 + 不同定义加载器 -> 不同运行期类型
```

## 编码与验证步骤

1. 在课程根运行python scripts/lab.py doctor，确认完整JDK21。缺环境记INVALID_ENV，不判断知识水平。
2. 打开本题src与test全部文件，先运行调用端、读成功与失败样例。作者源码是完整解；学习者副本占位区才是待实现区域，答案也直接在本页下方。
3. 只修改答案区，保持公开合同。先运行本题测试，再补边界/异常测试；不要改掉断言消灭失败。
4. 课程根运行./gradlew :jvm-01-loading-lab:test 与 :jvm-01-loading-lab:run。Windows使用gradlew.bat。首次联网下载依赖与编码错误分开处理。
5. 观察入口：python scripts/lab.py bytecode。记录JDK完整版本、命令、输入、预期、实际和边界。新证据输出build/evidence，不覆盖此前结果。

## 完整调用示例

以下调用端文件、src下辅助类、test下所有测试均对学习者可见；没有隐藏评分逻辑。

```java
package labs.jvm;

public final class LoaderLabUsage {
    public static void main(String[] args) throws Exception {
        System.out.println("两倍=" + LoaderLab.twice(3));
        System.out.println("常量=" + InitChild.CONSTANT + "，初始化事件=" + InitTrace.events);
        Class.forName("labs.jvm.InitChild", true, LoaderLab.class.getClassLoader());
        System.out.println("主动初始化=" + InitTrace.events);
    }
}
```

## 渐进提示（可选，不锁答案）

<div class="hint" title="H1：先明确不变量">把合同拆为正常、边界、异常、清理四类，先找哪个可见测试证明当前机制。</div>
<div class="hint" title="H2：用最小反例">比较本题说明中的易错边界与完整测试；写一个能区分两种实现的最小输入。</div>
<div class="hint" title="H3：对照步骤">按下面标准解的逐步解释检查状态变化，先定位错误层，再决定是否重写。</div>

## 标准解与逐步解释

[可单独打开完整标准解](solutions/LoaderLab.java.txt)。同一实现也在这里完整展示，无须切分支、解锁或先通过题目。

```java
package labs.jvm;

import java.util.Objects;

public final class LoaderLab {
    private LoaderLab() {}

    public static ClassLoader isolated(String binaryName, byte[] classBytes, ClassLoader parent) {
        // 作答开始
        Objects.requireNonNull(binaryName, "类名不能为空");
        Objects.requireNonNull(classBytes, "字节码不能为空");
        if (binaryName.startsWith("java.")) throw new IllegalArgumentException("禁止覆盖平台类");
        byte[] copy = classBytes.clone();
        return new ClassLoader(parent) {
            @Override
            protected Class<?> loadClass(String name, boolean resolve)
                    throws ClassNotFoundException {
                synchronized (getClassLoadingLock(name)) {
                    Class<?> type = findLoadedClass(name);
                    if (type == null)
                        type =
                                name.equals(binaryName)
                                        ? defineClass(name, copy, 0, copy.length)
                                        : super.loadClass(name, false);
                    if (resolve) resolveClass(type);
                    return type;
                }
            }
        };
        // 作答结束
    }

    public static int twice(int x) {
        return x * 2;
    }
}
```

1. java文件编译成class并不意味着其中所有类都已经初始化。加载建立类型表示；链接包含验证、准备、解析（解析可延后）；初始化执行静态字段赋值与静态块。
2. 编译期常量可能内联到调用方。读InitChild.CONSTANT不是一个可用于证明InitChild已经初始化的证据。Class.forName(...,false,loader)与true明确区分。
3. 先findLoadedClass，再按特例defineClass，否则父委派；锁住getClassLoadingLock(name)防止同名并发定义。父委派是ClassLoader默认策略，不是JVM禁止所有子优先加载器。
4. 复制字节数组隔离调用方修改。测试中的不同Class、isInstance=false揭示“类名一样就能强转”这个错误。
5. isolated构造额外空间O(B)，首次定义验证复杂度由VM决定；本课不承诺class加载固定O(1)。替代方案用URLClassLoader与受控父链，但要补close、包密封、模块与签名边界。本解只隔离一个合成类型，不处理完整插件依赖图。

## 源码与证据

固定OpenJDK21 GA tag jdk-21+35，commit 890adb6410dab4606a4f26a942aed02fb2f55387。[真实源文件](https://github.com/openjdk/jdk/blob/890adb6410dab4606a4f26a942aed02fb2f55387/src/java.base/share/classes/java/lang/ClassLoader.java)；符号：ClassLoader.loadClass(String,boolean)、findLoadedClass、defineClass。完整出处和补充规范见课程根[源码阅读清单](../../../docs/源码阅读清单.md)。

在loadClass的findLoadedClass后、parent.loadClass分支、resolveClass分支记录name、parent、返回Class的classLoader。输入LoadTarget与java.lang.String各一次；比较本课子优先特例与真实默认父优先分支。初始化机制另见JVMS5.5，不把Java层ClassLoader当作完整VM初始化实现。

R证据至少包含项目/版本/SHA、文件与符号、输入、关键分支、状态值、结论及反例。源码网页定位不等于已实际断点；本课程没有伪造截图。若IDE默认打开供应商补丁版源码，请另记录该版本，不冒充GA调试已完成。

## 面试问答与迁移

- 问：NoClassDefFoundError和ClassNotFoundException区别？答：显式加载查找失败常以后者报告；链接/初始化失败后再次使用可出现前者。不要只按“文件不在”解释全部错误。追问：初始化异常后重试为什么不同？记录第一次与再次使用的因果链。
- 问：为什么两个相同字节码的对象不能强转？答：类型身份包含定义加载器，测试直接验证；名字字符串相同不足以赋值兼容。共享接口若也被隔离会发生什么？同样产生两个接口类型。
- 问：双亲委派为什么有价值？答：共享核心API身份、避免重复平台定义。边界：本题有意仅对子目标打破默认委派；不是完整安全沙箱。
- 问：javap看到imul能说明JIT最后执行乘法指令吗？答：不能。javap展示class指令，JIT可能常量折叠或替换机器指令。必须另取机器码或JIT证据。
- 迁移：新增第二个插件类但共享一个父接口，证明跨插件对象可按共享接口调用；补测试说明哪些类必须父加载。

## 完成与复盘

A必须真正通过；O/R提交证据并按根目录[评阅标准](../../../docs/评阅标准.md)评阅。记录H0独立/H1-H4提示、首次失败、改动原因、24小时后换条件回测。至少能用一个反例解释结论边界。课程不以关键词计分，也不承诺面试结果。
