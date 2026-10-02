if not __debug__: raise SystemExit("拒绝Python优化模式，不能移除静态契约断言")
from pathlib import Path
import shutil,json
R=Path(__file__).resolve().parents[1];base=R/'observability-lab/src/main/java'
variants={}
def create(name,changes,test,expect):
 d=R/'variants'/name/'src';shutil.copytree(base,d,dirs_exist_ok=True)
 for file,fn in changes.items():
  p=d/'labs/observability'/file;p.write_text(fn(p.read_text()))
 variants[name]={'path':str(d.relative_to(R)),'tests':test,'expected':expect}
def body(s,signature,replacement):
 i=s.index(signature);begin=s.index('{',i)+1;level=1;j=begin
 while level:
  level += (s[j]=='{')-(s[j]=='}');j+=1
 return s[:begin]+'\n'+replacement+'\n    '+s[j-1:]
create('reference-map',{},['labs.observability.*'],'PASS')
def typed(s):
 start=s.index('        Map<String,Object> event =');end=s.index('    static String identifier')
 return s[:start]+'''        Event event = new Event(time.toString(),UUID.randomUUID().toString(),"http.completed",service,
            Routes.safe(route),status,identifier(traceId,32),identifier(spanId,16),elapsedNanos/1_000_000.0);
        try { return json.writeValueAsString(event); }
        catch (JsonProcessingException failure) { throw new IllegalStateException("event encoding",failure); }
    }
    record Event(@com.fasterxml.jackson.annotation.JsonProperty("@timestamp") String timestamp,
        String event_id,String event,String service,String route,int status,String trace_id,String span_id,double duration_ms) {}
'''+s[end:]
def switchattrs(s):
 return s.replace('String known = Set.of("GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS","CONNECT","TRACE").contains(method) ? method : "_OTHER";', '''String known = switch(method) {
            case "GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS","CONNECT","TRACE" -> method;
            default -> "_OTHER";
        };''')
def insensitive(s):
 return s.replace('return carrier.get(key);', 'return carrier.entrySet().stream().filter(e -> e.getKey().equalsIgnoreCase(key)).map(Map.Entry::getValue).findFirst().orElse(null);')
create('reference-typed',{'SafeEvents.java':typed,'RequestMetrics.java':switchattrs,'TraceBridge.java':insensitive},['labs.observability.*'],'PASS')
create('starter',{'SafeEvents.java':lambda s:body(s,'public String encode(', '        throw new UnsupportedOperationException("C12-01: 请构造白名单 JSON 事件");'),'RequestMetrics.java':lambda s:body(s,'public void observe(', '        throw new UnsupportedOperationException("C12-03: 请记录计数与秒直方图");'),'TraceBridge.java':lambda s:body(s,'public Context extract(', '        throw new UnsupportedOperationException("C12-05: 请使用 SDK 提取上下文");')},['labs.observability.SafeEventsTest','labs.observability.RequestMetricsTest','labs.observability.TraceBridgeTest'],'EXPECTED_TEST_FAILURE')
create('wrong-header-leak',{'SafeEvents.java':lambda s:s.replace('event.put("event", "http.completed");','event.put("headers", untrustedHeaders);\n        event.put("event", "http.completed");')},['labs.observability.SafeEventsTest'],'EXPECTED_TEST_FAILURE')
create('wrong-json-concatenation',{'SafeEvents.java':lambda s:s.replace('return json.writeValueAsString(event);','json.writeValueAsString(event); return "{\\\"route\\\":\\\""+route+"\\\"}";')},['labs.observability.SafeEventsTest'],'EXPECTED_TEST_FAILURE')
create('wrong-high-cardinality',{'RequestMetrics.java':lambda s:s.replace('String safe = Routes.safe(route);','String safe = route;')},['labs.observability.RequestMetricsTest'],'EXPECTED_TEST_FAILURE')
create('wrong-millisecond-unit',{'RequestMetrics.java':lambda s:s.replace('elapsedNanos / 1_000_000_000.0','elapsedNanos / 1_000_000.0')},['labs.observability.RequestMetricsTest'],'EXPECTED_TEST_FAILURE')
create('wrong-double-count',{'RequestMetrics.java':lambda s:s.replace('requests.add(1, labels)','requests.add(2, labels)')},['labs.observability.RequestMetricsTest'],'EXPECTED_TEST_FAILURE')
create('wrong-new-trace-every-hop',{'TraceBridge.java':lambda s:s.replace('.setParent(extract(incoming))','.setNoParent()')},['labs.observability.TraceBridgeTest'],'EXPECTED_TEST_FAILURE')
create('wrong-baggage-leak',{'TraceBridge.java':lambda s:s.replace('W3CTraceContextPropagator.getInstance()', 'io.opentelemetry.context.propagation.TextMapPropagator.composite(W3CTraceContextPropagator.getInstance(),io.opentelemetry.api.baggage.propagation.W3CBaggagePropagator.getInstance())')},['labs.observability.TraceBridgeTest'],'EXPECTED_TEST_FAILURE')
create('wrong-retry-all-failures',{'CheckoutController.java':lambda s:s.replace('command.scenario().equals("retry")?2:1','2')},['labs.observability.HttpCallChainTest'],'EXPECTED_TEST_FAILURE')
from variant_contracts import enrich
variants=enrich(variants,R)
(R/'manifest/variants.json').write_text(json.dumps(variants,indent=2)+'\n')
print('variants:',len(variants))
