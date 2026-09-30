# 05 · 不可变 Map Key 的身份契约 · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

从 hash→桶→equals 解释查找过程。可变 key 进入 HashMap 后改变参与哈希的字段可能导致无法查回；final 字段只保证引用不变，若字段是可变对象仍需防御性拷贝。碰撞本身并不违反契约。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java

## 关键反例

两个 new TenantKey("acme",7) 能查到同一个 HashMap 条目

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
