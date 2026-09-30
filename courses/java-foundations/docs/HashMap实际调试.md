# 真实HashMap断点证据 · 作者实跑

状态：OBSERVED；时间2026-09-30T14:28:08Z；环境Linux-6.18.44-x86_64-with-glibc2.41，Temurin21.0.12.1+1。由JDI启动本课程自己的64MiB合成子进程，内部20秒/外部25秒预算，未附加真实业务进程或开放模块。这里是实际调试文本，不是预测表或伪造截图。

## 输入与真实关键状态

初始HashMap容量参数16，12个不同ID的键按hash0/64交替；之后加入不同散列键使size达到49并继续到60。phase=1..12/13..60为输入序号，100/200为查找阶段。

```text
phase=9 method=java.util.HashMap.treeifyBin capacity=16 size=8 threshold=12 hash=0
phase=10 method=java.util.HashMap.treeifyBin capacity=32 size=9 threshold=24 hash=64
phase=11 method=java.util.HashMap.treeifyBin capacity=64 size=10 threshold=48 hash=0
phase=11 method=java.util.HashMap$TreeNode.treeify capacity=64 size=10 threshold=48
phase=49 method=java.util.HashMap$TreeNode.split capacity=128 size=49 threshold=96 index=0 bit=64
phase=49 method=java.util.HashMap$TreeNode.untreeify capacity=128 size=49 threshold=96 split_bit=64 split_lc=6 split_hc=6
phase=49 method=java.util.HashMap$TreeNode.untreeify capacity=128 size=49 threshold=96 split_bit=64 split_lc=6 split_hc=6
TARGET_STDOUT=真实HashMap场景结束，条目=60
```

还实际观测到getTreeNode和find入口，发生于capacity64、size12、threshold48的查找阶段。调试器只保留目标HashMap身份或键类型匹配的TreeNode，避免把JDK内部其他Map缓存当本例证据。

## 可推导结论

- 第9个碰撞键进入treeifyBin时table16，第10个时table32，两次容量不足，走扩容路线
- 第11个时容量64，进入TreeNode.treeify，不能说“链长8就一定树化”；入口size仍为10，因为putVal在树化调用返回后才增加size，phase与size不是同一个时点计数
- size49超过threshold48触发64到128扩容，split参数bit64与index0吻合旧容量新增位
- 实际untreeify入口的父帧状态lc=6、hc=6，证明此输入在两侧各6节点时走链化分支
- 子进程最终打印条目60，JUnit另验证扩容前后全部原键可查询；结构观察和公共合同是两条证据

## 版本与边界

GA阅读固定tag jdk-21+35、SHA890adb6410dab4606a4f26a942aed02fb2f55387。运行却是当前Temurin补丁，运行包src.zip SHA256=2fb0fb7eef6330656944cdd42a3ba36ea819deab00acf958468feb002bdf11e2，二者没有混称。动态脚本依赖JDK自带JDI，不需要另装软件或JDK。

原始文本位于本次build/hashmap-trace/run-1790778488340838806/trace.log，SHA256=bb2b0cb6fd84945422ffc1fc7731f8ec9c5509c8be41941a6cc6ee45b440c8a7。每次新运行独立目录；原始日志不依赖网络，摘要随课程保留。首次脚本开发时发现重复resume可越过ClassPrepare设置时机，已改由VMStartEvent单次恢复并重新取得真实证据；不通过重试掩盖未修复的时序错误。

本例不是所有JDK版本的公共Map合同；换成7+5或其他容量需重新观察。用户自己的IDE断点操作与课程Academy界面验收仍未由此证明。
