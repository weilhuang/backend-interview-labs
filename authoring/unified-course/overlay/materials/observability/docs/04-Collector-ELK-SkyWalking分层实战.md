# C12-02/06/07/10 后端实战准备与真实验收边界

## 当前实现的层次

已提供Java API/SDK、两个HTTP服务、公开测试和真实后端查询脚本的源代码；本轮未编译或运行Java，也未启动Collector、Jaeger、Prometheus、ELK、SkyWalking。没有 Docker daemon、安装、真实账号或付费服务操作。配置存在不等于配置被真实二进制接受。

## Profile A：OTEL 指标与链路

`infra/collector.yaml`：OTLP/HTTP receiver → memory_limiter → allowlist transform → batch → traces 的 Jaeger exporter / metrics 的 Prometheus exporter。只声明 exporter 而不挂 pipeline 没有效果。队列64个批次、每批最多256是不同维度的预算；这是内存队列，不是断电持久化保证。SDK另有128 spans队列和2秒导出超时。

Compose 只引用统一台账变量，所有宿主发布端口绑定127.0.0.1，容器网络internal，单服务内存与CPU有界。OTLP/gRPC的无TLS只用于隔离教学网络；生产需身份验证、TLS和访问控制评估。

审核后步骤：
1. owner 把批准的新镜像写入唯一 `infra/versions.env`，同步发行 `shared/versions.env`；候选JSON不是运行版本源
2. 运行冻结 Collector 的 `validate --config`，保存版本、退出码、stdout/stderr。当前 NOT_RUN
3. 用带课程唯一项目名的 Compose 启动 otel profile，逐一检查 health、Jaeger API、Prometheus ready，而不把 depends_on 当业务ready
4. 启动两个Java服务，运行 `python scripts/verify_backend.py --output evidence/real-backend.json`
5. 真实查询 exact trace ID 后检查 span数量、父子ID、实际错误标签；再以相同时间窗核查指标增量
6. 只关闭该项目创建的服务和卷；禁止全局 prune，保存销毁清单

资源预算为初步估算：Collector256MiB、Jaeger512MiB、Prometheus256MiB，另加两个Java服务各384MiB及运行余量。Jaeger默认内存存储会随重启丢失，不能把它当生产持久化。Prometheus限1h/128MB。镜像下载大小和各架构实际运行均待实测；没有云费用承诺。

## Profile B：保留 ELK 的独立日志课

业务JSON文件 → Logstash json/date过滤 → Elasticsearch严格mapping → Kibana查询。应用只有一个业务事件文件来源；不并行启用“文件ELK + OTEL日志自动采集 + 第二agent日志”制造三份重复。框架console日志不混进本课业务NDJSON。

`infra/logstash.conf`首先设置skip_on_invalid_json=true，避免默认解析失败WARN输出原始message；必须同时加载logstash.yml，禁止会在脱敏前打印完整event的DEBUG/TRACE。Ruby先移除原始事件及metadata，再验证受控字段。非法JSON/时间/类型输入直接丢弃，仅在Logstash自身日志留下固定C12_REJECTED_INVALID_EVENT标记，不保存原文。event_id作为document_id使同一文件重采覆盖同一文档。index成功之后仍要验证全索引match_all的可搜索结果、exact hits.total和完整mapping。

配置需要已授权的本地ES TLS端点、CA和专用写入身份；凭证只能在安全环境注入，不能写进课程或证据。当前没有为此创建账号、密钥或关闭安全设置。ELK文档基线使用8.18系列；镜像版本、digest、平台与许可须审核后由唯一台账指定，不因Spring的Java客户端版本就推断任意ES兼容。

ELK后续真实用例：两个正确事件可查、坏JSON/时间/类型输入丢弃、重复event_id不增文档数、字段未知不扩mapping、事件时间排序、采集重启与sincedb。必须扫描ES响应、mapping、旧隔离路径以及Logstash自身stdout/stderr和所有轮转日志；缺少任何通道都不能算安全验证完成。ELK初步建议另留6GiB内存及数GiB磁盘，实际镜像层和堆大小未测。

## Profile C：SkyWalking 的对照，不混插桩

固定10.3.0文档表明：OTLP traces 转为 Zipkin 数据路径，需要 otlp-traces handler 与 Zipkin receiver/query，查询走 Lens；它不是 next 文档中新增的原生OTLP存储路径。OTLP metrics 使用受支持的MAL规则，不能假设本课任意指标自动形成SkyWalking服务指标。

先做 SkyWalking Java agent + OAP/UI 的原生HTTP/SQL链路，再单独做OTEL互操作对照；每轮只能选一种自动agent。当前手工OTEL应用不能随意再挂自动OTEL/SkyWalking探针后把重复span算成成功。

OAP/UI镜像、Java agent版本、Spring/Tomcat/JDBC插件支持、Lens镜像与各平台真实性仍待单独冻结/验证，故 profile C 当前 DESIGNED。没有已经批准的ES镜像可直接复用；只有核查10.3.0官方storage支持且真实运行通过，才可共用**服务**，还需隔离索引/角色/配额；不能因为“ES-compatible”就擅自接入OpenSearch或任意版本。

## 故障恢复需保留的证据

- Collector停止：业务持续成功且请求耗时有界；SDK导出失败可见；恢复后的新trace可查询；明确报告丢失窗口
- Jaeger停止：Collector queue_size/send_failed/refused/dropped计数和日志随时间保存；恢复前后查同一已知trace。队列耗尽或超过30秒重试预算时不能宣称无损
- 头采样0：SDK没有记录的span永远不会被尾采样追回；对照日志仍在、指标仍增加
- 时钟偏移：span父子关系仍为因果依据，不能仅凭跨机绝对时间排序断言“请求先收到后发送”
- 重试：库存是只读GET，最多两次；checkout是一次业务操作。非幂等POST不能照搬该策略
- 高基数：将raw ID作标签的错误解必须被独立series数量断言杀死

所有后端真实用例见 `infra/backend-cases.json`；每条最终记录实际版本、架构、命令、起止时间、证据文件hash、是否跳过和退出码。O类人工解释不能伪装成自动绿勾。

## 已提供但尚未执行的真实负例断言入口

- Collector隔离验证需要--isolation-record，记录本实验范围、collector服务、health端点、stop/network-isolate动作、带时区的开始时间及操作者证据SHA256。脚本只接受起止两次ECONNREFUSED；HTTP404/503代表端点有响应，超时仍属无法判定，不能算停机成功。即使20次请求成功，也不证明全时段停机或零丢失
- ELK输入infra/elk-fixture-cases.ndjson为合成输入，共6行。正常2条、同ID重放1条、坏JSON/坏时间/缺ID各1条。非法输入不得进ES或保存原文；自身日志应只有3个固定拒绝标记
- assert_elk_evidence.py必须收到--collection-manifest、--logstash-stdout、--logstash-stderr和至少一个--logstash-log。manifest记录run_id、采集起止时间、无轮转缺口、实际logger级别、config.debug=false、每个文件名/hash，以及全索引match_all/track_total_hits=true/size足够/时间升序的原始查询
- --quarantine指向本轮检查的空隔离文件，确认没有继续落盘旧原文。查询必须exact total=2且完整返回2条、所有分片成功；仅有一页2条不算去重成功。文件hash和元数据只能验证材料自洽，真实采集来源仍需操作者执行记录审阅
- verify_backend.py仅覆盖HTTP响应及Jaeger链路语义：服务、SERVER/CLIENT、唯一ID/根、无环父子关系、错误标签、重试尝试数和同进程时间跨度。指标查询尚未实现，单列NOT_RUN；跨服务绝对时间不用于否定父子因果关系

Logstash插件源码依据：[json filter v3.2.1](https://github.com/logstash-plugins/logstash-filter-json/blob/v3.2.1/lib/logstash/filters/json.rb)明确包含默认WARN原文和DEBUG完整event路径；[Ruby filter v3.1.8](https://github.com/logstash-plugins/logstash-filter-ruby/blob/v3.1.8/lib/logstash/filters/ruby.rb)支持event.cancel。当前只核对源码与配置，仍未运行真实Logstash，最终冻结的插件版本必须再验。

元数据格式见infra/elk-collection.example.json及infra/collector-isolation.example.json。示例中的REPLACE占位符必须替换为本轮真实记录与hash；模板本身不是采集证据，不应通过验证。
