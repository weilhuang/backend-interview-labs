# 10 · HashMap 扰动与桶索引 · 教师解析

参考实现位于作者模式任务的 src，占位区由 Academy 预览/导出时替换。请先练习再看。

跟读 hash、putVal、resize、treeifyBin。阐明 h^(h>>>16) 缓解低位分布问题，但不消除碰撞。扩容分裂由 oldCapacity 那一位决定。树化阈值 8 不代表第 8 个节点总会树化，还要看插入路径和最小树化容量 64。

## 源码定位

https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java

## 关键反例

hash=0x00010000,capacity=16 → index=1

## 评分

- 契约与边界 40%
- 实现与测试 30%
- 复杂度和源码证据 20%
- 两分钟表达 10%

参考实现不代表唯一正确实现；复杂度、线程安全与失败原子性需人工复核。
