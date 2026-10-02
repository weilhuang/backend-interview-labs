# 统一课程的可复现作者输入

这里维护经过评审的扩展源码增量，不提交一份只能复制使用、无法重建的生成课程根。

## 单一构建入口

```bash
python -m pip install -r scripts/quality/requirements.txt
PYTHONDONTWRITEBYTECODE=1 python scripts/build_unified_course.py \
  --output build/backend-interview \
  --report build/unified-generation.json
```

目标目录和报告必须尚不存在，脚本不会覆盖学习者作答。它只组装文件与做静态核对，不运行 Java、Go、Docker、IDE，不解析或生成依赖锁，不下载工具。

1. 从仓库中九份 V1 作者源、统一环境模板、已有严格锁，通过原 `scripts/unify_course.py` 生成 V1 根
2. 要求完整 V1 输出与 `manifest.json` 的 `base_generated_manifest` 逐路径、逐字节一致
3. 只应用 `overlay_manifest` 声明的文件；缺文件、多文件、改动、符号链接或不安全路径均拒绝
4. 要求完整结果与 `expected_manifest` 一致，验证 15 章节、100 题、159 区、107 份最终模块锁
5. 按实际文件签名/字节检查任务二进制资产，要求显式布尔值 `is_binary: true`，拒绝二进制练习区
6. 校验 `authoring/public-build-contract.json` 的全部源码、课程映射和 110 个可编辑文件绑定；原生验收再独立消费这一合同

`overlay/` 是扩展课文、答案、代码、可见测试、桥接适配器、锁、地图和公开整合文档的维护源。原来的九份 V1 源仍在 `courses/`；不要在生成目录修改后忘记更新作者输入。Java、Go、Dockerfile 和 YAML 的练习区按相同 UTF-16 合同投影，除此之外的字节不变。

## 显式更新流程

编辑源后，先在独立新目录重新组装和评审变化，再更新 manifest 的输入与输出 hash。清单不是签名，也不是运行证据。不要仅为绕过 drift 检查而重算清单，不要让 CI 自动接纳新清单或在普通验收中写依赖锁。

原始整合输入封存清单 SHA256 为 `4bf64648e4cfe1d022fe58d6773900dbb5f32b2c92cc33edf49a021573a29be2`。公开版本的明确变化列在 `public_transformations`：移除机器路径和私有标题、明确范围、修复多语言 learner 投影、为16道扩展题补充官方参考链接，以及依据真实导出失败为六个Go任务PNG补上显式二进制标记。旧运行证据只绑定旧全树；本版业务源码和测试保真不等于本版重新执行通过。

## 依赖与运行边界

JDK21、Gradle8.10.2、Go1.27.1、Gin1.12.0及模块锁保持评审基线。镜像以生成课程 `shared/versions.env` 为唯一执行台账。C12 三项外部镜像值仍未冻结，完整扩展基础设施门禁仍 fail-closed。

正式导出由 Actions 的单一官方课程工作流执行。静态重建成功不能当作 Academy Check、Reset、Docker、Kubernetes、真实观测后端或完整 V1+V2 验收通过。
