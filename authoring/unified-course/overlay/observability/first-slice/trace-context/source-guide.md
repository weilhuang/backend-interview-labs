# 版本与源码路线

以下链接是本草稿采用的官方版本来源，当前构建、完整依赖解析和来源复核尚未执行。指定版本不等于宣称最新或没有漏洞，滚动文档与固定版本源码必须分开。

## Java 冻结来源

- [Spring Boot v3.5.16依赖定义](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot-dependencies/build.gradle)：OpenTelemetry BOM为1.49.0，保持与统一课程一致
- [Boot 3.5观测文档](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)：Micrometer与OTEL社区插桩是不同接入方案；本切片显式手工SDK，不暗中混用两套自动HTTP插桩
- [OTEL1.49.0 W3CTraceContextPropagator](https://github.com/open-telemetry/opentelemetry-java/blob/v1.49.0/api/all/src/main/java/io/opentelemetry/api/trace/propagation/W3CTraceContextPropagator.java)：沿 extract → traceparent有效性 → remote SpanContext → Context 读。找出全零ID为什么无效，再回到 malformed测试
- [OTEL1.49.0 BatchSpanProcessor](https://github.com/open-telemetry/opentelemetry-java/blob/v1.49.0/sdk/trace/src/main/java/io/opentelemetry/sdk/trace/export/BatchSpanProcessor.java)：先看onEnd入队、worker取批、export超时和shutdown；解释“有界队列保护业务”与“可能丢span”为什么同时成立
- [OTEL1.49.0 DoubleHistogramBuilder](https://github.com/open-telemetry/opentelemetry-java/blob/v1.49.0/api/all/src/main/java/io/opentelemetry/api/metrics/DoubleHistogramBuilder.java)：setExplicitBucketBoundariesAdvice提供边界建议，SDK/View可以改变聚合，不能只看API名字就断言后端图的桶
- [OTEL1.49.0 MetricData](https://github.com/open-telemetry/opentelemetry-java/blob/v1.49.0/sdk/metrics/src/main/java/io/opentelemetry/sdk/metrics/data/MetricData.java)：测试通过getHistogramData检查聚合结果，不拿打印出的字符串代替断言

本草稿通过上面的官方链接定位源码，不附未经当前核对的第三方源码副本。源码阅读顺序是“测试行为 → 我们的调用点 → 固定版本符号 → 回到错误解”，不是先读完整框架。

## 协议与语义

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)：traceparent与tracestate格式；SDK处理协议合法性。远端上下文仍是不可信输入
- [HTTP metric语义](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/)：http.server.request.duration单位秒；http.route应来自低基数框架模板，不能用原始URI替代。滚动文档会新增属性，本实验仅用固定SDK支持的稳定API，不引用尚未冻结的alpha常量库
- [HTTP span语义](https://opentelemetry.io/docs/specs/semconv/http/http-spans/)：客户端与服务器错误状态规则不同。课程手工插桩仅覆盖此受控同步路径，不声称完整替代生产HTTP instrumentation
- [OTEL Java SDK](https://opentelemetry.io/docs/languages/java/sdk/)：API与SDK、provider、reader、exporter分工

## Collector 与后端

- [Collector-contrib v0.123.0 release](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.123.0)
- [0.123.0 transform配置](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.123.0/processor/transformprocessor/README.md)：此版本组件为alpha；allowlist语法需真实binary validate并保存执行证据
- [0.123.0 exporterhelper](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.123.0/exporter/exporterhelper/README.md)：sending_queue与retry_on_failure语义，批次上限不是持久化承诺
- [Jaeger2.6入门](https://www.jaegertracing.io/docs/2.6/getting-started/)：all-in-one使用临时内存存储，本提案不需要新增共享ES作为trace库
- [Logstash8.18 JSON过滤器](https://www.elastic.co/guide/en/logstash/8.18/plugins-filters-json.html) 与 [ES输出](https://www.elastic.co/guide/en/logstash/8.18/plugins-outputs-elasticsearch.html)：解析失败标签、document_id和索引写入行为
- [Elastic License2.0](https://www.elastic.co/licensing/elastic-license)：默认发行版许可不能直接写成纯Apache2；组件许可证与再分发要求仍需镜像归档审计
- [SkyWalking10.3.0 OTLP trace](https://skywalking.apache.org/docs/main/v10.3.0/en/setup/backend/otlp-trace/) 与 [OTLP metrics](https://skywalking.apache.org/docs/main/v10.3.0/en/setup/backend/opentelemetry-receiver/)：版本锁定，不能用next页面能力替代
- [SkyWalking10.3.0 storage](https://skywalking.apache.org/docs/main/v10.3.0/en/setup/backend/backend-storage/)：未来复用ES前按具体版本矩阵复核

## 镜像与依赖冻结限制

Compose仅引用唯一台账的镜像变量，本草稿不包含已核验的镜像manifest或第二份版本台账。需审核exact tag/digest、目标架构、许可、漏洞和资源成本，再由统一owner写入唯一台账。列在manifest中的架构也必须分别运行验证。

完整Gradle依赖锁尚未提供，不能从部分坐标推导或补造。后续必须在获准环境中重新解析、冻结完整依赖图并复测。

Elastic源码目录、默认容器发行许可及依赖组件许可属于不同层次。应按具体发行版本复核许可与SBOM，不能把整个ELK发行物概括成纯Apache2。当前这项审查为NOT_RUN。
