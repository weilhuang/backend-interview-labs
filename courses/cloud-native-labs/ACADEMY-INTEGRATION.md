# Academy三课作者overlay

`academy-overlay`提供section、lesson和task元数据。它必须由唯一总课程的生成/集成流程使用，不是可独立导入的新课程根。

- 编辑区：Dockerfile、CloudPolicy和AddressPolicy，答案源码与学习者占位文本分开
- 可见文件：中文题目、逐步答案、观察模板、测试契约和完整参考变体
- 占位坐标：按UTF-16单位计算，并验证替换后的学习者投影
- 保持原业务接口：HTTP路径、响应字段、库存与就绪规则不变

当前缺少JUnit桥、总课程Gradle适配及strict dependency locks；原生Check尚未运行。不能把静态元数据通过解释成IDE能完成评分。

## 预览与最终集成的素材路径

`course/materials/cloud-native`是唯一素材源。运行`python3 tools/prepare_academy_metadata.py`会从这里复制三张SVG到`academy-overlay/materials/cloud-native/diagrams`，供直接预览overlay题目使用；修改图片时只修改唯一源，再重新生成。

最终课程只接收`academy-overlay/c11-cloud-native`子树，以及`course/materials/cloud-native`共享工程和限定环境入口，不接收`academy-overlay/materials`预览副本。最终课程布局如下：

```text
<总课程>/
  c11-cloud-native/<lesson>/<task>/task.md
  materials/cloud-native/diagrams/*.svg
```

题目中的`../../../materials/cloud-native/diagrams/...`链接保持相同，因此在overlay预览和最终课程两种布局都有效。不要把它改成指向本源码包的`course`相对路径。

生成器可在仅有交付清单文件的新目录运行，不要求预先存在`qa`目录。默认创建`qa/academy-metadata.json`静态报告，也可用`--report ./local-runs/metadata.json`指定输出。`qa`不属于课程交付清单，报告不会成为原生Check通过证据。
