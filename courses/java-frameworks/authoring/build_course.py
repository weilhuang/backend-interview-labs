#!/usr/bin/env python3
"""生成本课程自己的元数据与公开标准解；不复用集合题专用验证器。"""
from pathlib import Path
import re,json,shutil
ROOT=Path(__file__).resolve().parents[1]
TASKS=[]
def write(path,text):
 p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text.strip()+'\n',encoding='utf-8')
def task(name,title,lesson,unit,scenario,steps,contract,source,explain,questions,code,tests,usage,extra=None,mutations=None):
 path=f'framework-course/{lesson}/{name}'
 write(path+'/src/labs/frameworks/Lab.java',code)
 write(path+'/test/labs/frameworks/LabTest.java',tests)
 write(path+'/test-resources/mockito-extensions/org.mockito.plugins.MockMaker','mock-maker-subclass')
 write(path+'/src/labs/frameworks/Usage.java',usage)
 for rel,content in (extra or {}).items():write(path+'/'+rel,content)
 TASKS.append(dict(path=path,name=name,title=title,unit=unit,scenario=scenario,steps=steps,contract=contract,source=source,explain=explain,questions=questions,mutations=mutations or []))
def finish():
 import yaml,subprocess,os
 formatter=ROOT/'build/tools/google-java-format-1.24.0-all-deps.jar'
 if os.environ.get('FORMAT_COURSE')=='1':
  if not formatter.exists():raise RuntimeError('缺少已锁定的Java格式化工具')
  java=os.environ.get('JAVA_HOME','')+'/bin/java'
  java_files=[str(p) for p in (ROOT/'framework-course').rglob('*.java') if 'build' not in p.relative_to(ROOT).parts]
  subprocess.run([java,'-jar',str(formatter),'--replace']+java_files,check=True)

 lessons={}
 for item in TASKS:
  path=ROOT/item['path'];lesson=path.parent.name;lessons.setdefault(lesson,[]).append(path.name)
  files=[];solutions=[]
  for file in sorted(path.rglob('*')):
   if not file.is_file() or file.name in ['task.md','task-info.yaml'] or 'build' in file.relative_to(path).parts:continue
   rel=str(file.relative_to(path));entry={'name':rel,'visible':True}
   if file.suffix=='.java':
    content=file.read_text();places=[]
    pattern=r'(?<=// 练习区开始\n)(.*?)(?=\s*// 练习区结束)'
    for match in re.finditer(pattern,content,re.S):
     start,end=match.span(1); body=match.group(1)
     places.append({'offset':len(content[:start].encode('utf-16-le'))//2,'length':len(body.encode('utf-16-le'))//2,'placeholder_text':('// 请补上本步骤所需的注解\n' if body.lstrip().startswith('@') else '        throw new UnsupportedOperationException("请按题目实现本步骤");\n')})
     solutions.append('```java\n'+body.rstrip()+'\n```')
    if places:entry['placeholders']=places
   files.append(entry)
  write(item['path']+'/task-info.yaml',yaml.safe_dump({'type':'edu','custom_name':item['title'],'files':files},allow_unicode=True,sort_keys=False))
  text=f'''# {item['title']}

对应完整课程：{item['unit']}。JDK 21，Spring Boot 3.5.16 / Framework 6.2.19。先修和运行方法见课程首页；本节全部源码、调用方、测试和标准解公开。

## 企业场景

{item['scenario']}

## 实际操作与逐步编码

{item['steps']}

运行本节检查：`./gradlew :{item['name']}:test`。运行完整调用方：`./gradlew :{item['name']}:usage`。服务型示例另可执行 `./gradlew :{item['name']}:run`，停止使用 Ctrl+C。

## 正确性合同

{item['contract']}

## 核心机制与图解

```text
{DIAGRAMS[item['name']]}
```

{item['explain']}

## 固定版本源码阅读

{item['source']}

记录入口、关键分支、输入、状态与版本。不要求背整段源码；必须说明哪条观察支持你的结论。自动测试通过不等于源码讲解已通过人工评阅。

## 渐进提示

1. 先读完整调用方与测试，写出正常、边界和失败的差别
2. 只修改标出的练习区，把合同转化为分支或框架API调用
3. 对照本节真实源码入口，解释是哪一层执行校验或事务/代理行为

## 公开标准解

下面是所有练习区的完整实现；完整文件也在项目中公开。学生起点和标准解分开，不需要解锁。

{chr(10).join(solutions)}

{item['explain']}

## 面试机制 边界与取舍

{item['questions']}

## 独立迁移与验收

不查标准解，修改一个合同边界并增加测试；再解释一个错误实现为什么会被拒绝。完成编码、诊断和追问才能记录掌握，阅读标准解不等于独立掌握。实际构建、集成、界面验收状态见课程根的中文阶段报告。
'''
  text=text.replace('/spring-framework/blob/v6.2.19/', '/spring-framework/blob/6214eae8bd02c2ed7ab382bb8d16a9cc6de49522/').replace('/spring-boot/blob/v3.5.16/', '/spring-boot/blob/0566f6933049aca6bc5ffc6d559fffade9cd2e0c/').replace('/spring-security/blob/6.5.11/', '/spring-security/blob/73b077790fcb04ac3712033d3e939daf42264545/')
  write(item['path']+'/task.md',text)
 for lesson,names in lessons.items():write('framework-course/'+lesson+'/lesson-info.yaml',yaml.safe_dump({'type':'lesson','custom_name':'应用实践' if lesson=='01-boot' else '框架源码与机制','content':names},allow_unicode=True,sort_keys=False))
 write('framework-course/section-info.yaml',yaml.safe_dump({'type':'section','custom_name':'Java框架工程与源码','content':list(lessons)},allow_unicode=True,sort_keys=False))
 additional=[]
 for p in sorted(ROOT.iterdir()):
  if p.is_file() and p.name not in ['course-info.yaml','.courseignore','.gitignore'] and not p.name.startswith('.') and p.suffix != '.log':
   additional.append({'name':p.name})
 for folder in ['gradle','scripts','docs']:
  for p in sorted((ROOT/folder).rglob('*')):
   if p.is_file():
    item={'name':str(p.relative_to(ROOT))}
    if p.suffix=='.jar':item['is_binary']=True
    additional.append(item)
 write('course-info.yaml',yaml.safe_dump({'type':'marketplace','title':'Java框架工程与源码：Spring Boot与Spring','language':'Chinese','summary':'完整V1的框架部分，逐步完成真实配置、HTTP、事务、安全、容器、代理、MVC与自动配置；全项目、测试和标准解公开。完成状态以阶段报告为准。','programming_language':'Java','content':['framework-course'],'environment_settings':{'jvm_language_level':'JDK_21'},'additional_files':additional,'yaml_version':2},allow_unicode=True,sort_keys=False))
 write('authoring/manifest.json',json.dumps(TASKS,ensure_ascii=False,indent=2))
task('01-configuration','01 配置绑定与启动校验','01-boot','C04-01',
'订单服务允许不同环境配置最大购买数量与展示名称。配置错误应在启动时暴露，不能等用户请求时才发现。',
'1. 运行Usage观察真实Spring属性绑定\n2. 实现Limits.requireAllowed，保持数量区间为[1,maxQuantity]\n3. 运行测试验证默认值、外部覆盖、非法配置启动失败\n4. 用断点跟踪绑定器和校验器，而不是手动new替代容器',
'maxQuantity配置范围为1到1000；displayName不能为空。请求数量必须为1到上限，超出抛IllegalArgumentException。启动校验和业务校验都必须存在。',
'[Boot绑定入口](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/context/properties/ConfigurationPropertiesBindingPostProcessor.java)：postProcessBeforeInitialization → bind。另跟踪Binder与ValidationBindHandler。',
'@ConfigurationProperties负责绑定，@Validated触发配置对象校验；业务方法还需校验每次请求。属性来源的覆盖不会自动修复错误数据。字段默认值与外部值通过同一路径进入最终Bean。',
'- 配置绑定与@Value有什么取舍？前者适合一组可校验配置；追问：profile只是文件选择吗？\n- 为什么配置校验不能代替请求校验？两者检查时机和对象不同\n- 线上改配置会立即刷新Bean吗？不能假定普通Boot绑定自动动态刷新，需单独机制与安全回滚',
'''package labs.frameworks;
import jakarta.validation.constraints.*;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.context.properties.*;
import org.springframework.validation.annotation.Validated;
@SpringBootConfiguration
@EnableAutoConfiguration(exclude=DataSourceAutoConfiguration.class)
@EnableConfigurationProperties(Lab.Limits.class)
public class Lab {
 @Validated @ConfigurationProperties("orders")
 public static class Limits {
  @Min(1) @Max(1000) private int maxQuantity=100;
  @NotBlank private String displayName="订单实验室";
  public int getMaxQuantity(){return maxQuantity;}
  public void setMaxQuantity(int value){maxQuantity=value;}
  public String getDisplayName(){return displayName;}
  public void setDisplayName(String value){displayName=value;}
  public void requireAllowed(int quantity){
// 练习区开始
   if(quantity<1 || quantity>maxQuantity) throw new IllegalArgumentException("购买数量超出配置范围");
// 练习区结束
  }
 }
 public static void main(String[] args){
  SpringApplication app=new SpringApplication(Lab.class);app.setWebApplicationType(WebApplicationType.NONE);
  try(var context=app.run(args)){System.out.println("最大购买数量："+context.getBean(Limits.class).getMaxQuantity());}
 }
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 private final ApplicationContextRunner runner=new ApplicationContextRunner().withUserConfiguration(Lab.class);
 @Test void 默认配置可绑定(){runner.run(c->{assertThat(c).hasNotFailed();assertThat(c.getBean(Lab.Limits.class).getMaxQuantity()).isEqualTo(100);});}
 @Test void 外部配置覆盖默认并限制业务(){runner.withPropertyValues("orders.max-quantity=3","orders.display-name=企业订单").run(c->{var x=c.getBean(Lab.Limits.class);x.requireAllowed(1);x.requireAllowed(3);assertThat(x.getDisplayName()).isEqualTo("企业订单");assertThatThrownBy(()->x.requireAllowed(4)).isInstanceOf(IllegalArgumentException.class);assertThatThrownBy(()->x.requireAllowed(0)).isInstanceOf(IllegalArgumentException.class);});}
 @Test void 错误配置导致启动失败(){runner.withPropertyValues("orders.max-quantity=0").run(c->assertThat(c).hasFailed());runner.withPropertyValues("orders.display-name=").run(c->assertThat(c).hasFailed());}
 @Test void 配置文件与命令行的真实优先级(){var app=new org.springframework.boot.SpringApplication(Lab.class);app.setWebApplicationType(org.springframework.boot.WebApplicationType.NONE);app.setDefaultProperties(java.util.Map.of("orders.max-quantity","2"));try(var context=app.run("--spring.profiles.active=lab")){assertThat(context.getBean(Lab.Limits.class).getMaxQuantity()).isEqualTo(5);}try(var context=app.run("--spring.profiles.active=lab","--orders.max-quantity=7")){assertThat(context.getBean(Lab.Limits.class).getMaxQuantity()).isEqualTo(7);}}
 @Test void 默认上界也校验(){var x=new Lab.Limits();assertThatThrownBy(()->x.requireAllowed(101)).isInstanceOf(IllegalArgumentException.class);}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(new String[]{"--orders.max-quantity=3"});}}''',extra={'resources/application-lab.properties':'orders.max-quantity=5\n'},mutations=[['quantity>maxQuantity','quantity>maxQuantity+1']])

task('02-http-contract','02 HTTP校验错误与预置前端','01-boot','C04-02',
'用户在中文订单页提交SKU、数量、单价与请求编号。网络重试不能重复创建订单；相同编号不同内容必须明确冲突。',
'1. 执行run并打开http://127.0.0.1:18084\n2. 先通过页面和Usage调用成功/非法请求\n3. 实现Store.create中的原子幂等决策、金额溢出检查与ID分配\n4. 运行真实随机端口HTTP测试，检查201/200/400/404/409与Location\n5. 在页面尝试重复点击、相同键改参数、非法数量和刷新列表',
'字段不得空白，数量与单价为正；最大数量100。金额用Math.multiplyExact。新建201、同键同内容200且同ID、同键不同内容409、非法请求400、不存在404。列表按ID升序，offset>=0、limit为1到100，默认前20条；请求失败不得新增记录。教学内存存储仅单进程，重启丢失。',
'[MVC入口](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-webmvc/src/main/java/org/springframework/web/servlet/DispatcherServlet.java)：doDispatch。参数解析经RequestResponseBodyMethodProcessor；异常经ExceptionHandlerExceptionResolver。',
'@Valid负责结构约束，Store负责动态数量上限、幂等与溢出。synchronized使同进程的查重和写入成为一个临界区；生产多实例需数据库唯一约束等持久机制。@RestControllerAdvice把预期错误转为稳定响应，不向调用方泄漏堆栈。',
'- POST可以设计成业务幂等吗？可以，但需要明确键作用域/有效期/持久化；追问：服务重启后的保证是什么？\n- 为什么校验注解不放在前端就结束？客户端可绕过，后端仍负责合同\n- 重复请求返回200还是201？由合同定义，本课区别已存在和新建\n- 为什么不用double计算钱？精确单位和溢出合同必须明确',
'''package labs.frameworks;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.net.URI;
import java.util.*;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.http.converter.HttpMessageNotReadableException;
@SpringBootConfiguration
@EnableAutoConfiguration(exclude=DataSourceAutoConfiguration.class)
@Import({Lab.Api.class,Lab.Errors.class})
public class Lab {
 public record Request(@NotBlank String requestId,@NotBlank String sku,@Min(1) int quantity,@Min(1) long unitPriceFen){}
 public record Order(long id,String requestId,String sku,int quantity,long unitPriceFen,long totalFen){}
 public record Creation(Order order,boolean created){}
 public record ErrorBody(String code,String message){}
 public static class Conflict extends RuntimeException{}
 public static class Missing extends RuntimeException{}
 public static class Store {
  private long sequence=0;
  private final Map<String,Order> requests=new HashMap<>();
  public synchronized Creation create(Request r){
// 练习区开始
   if(r.quantity()<1 || r.quantity()>100 || r.unitPriceFen()<1) throw new IllegalArgumentException("数量或金额不合法");
   long total=Math.multiplyExact(r.quantity(),r.unitPriceFen());
   Order old=requests.get(r.requestId());
   if(old!=null){
    if(!old.sku().equals(r.sku()) || old.quantity()!=r.quantity() || old.unitPriceFen()!=r.unitPriceFen()) throw new Conflict();
    return new Creation(old,false);
   }
   Order order=new Order(++sequence,r.requestId(),r.sku(),r.quantity(),r.unitPriceFen(),total);
   requests.put(r.requestId(),order);return new Creation(order,true);
// 练习区结束
  }
  public synchronized List<Order> list(){return requests.values().stream().sorted(Comparator.comparingLong(Order::id)).toList();}
  public synchronized Order get(long id){return requests.values().stream().filter(o->o.id()==id).findFirst().orElseThrow(Missing::new);}
 }
 @Bean Store store(){return new Store();}
 @RestController @RequestMapping("/api/orders")
 public static class Api {
  private final Store store;public Api(Store store){this.store=store;}
  @GetMapping public List<Order> list(@RequestParam(defaultValue="0") int offset,@RequestParam(defaultValue="20") int limit){if(offset<0 || limit<1 || limit>100)throw new IllegalArgumentException("分页参数不合法");return store.list().stream().skip(offset).limit(limit).toList();}
  @GetMapping("/{id}") public Order get(@PathVariable long id){return store.get(id);}
  @PostMapping public ResponseEntity<Order> create(@Valid @RequestBody Request request){
   Creation result=store.create(request);
   return ResponseEntity.status(result.created()?HttpStatus.CREATED:HttpStatus.OK).location(URI.create("/api/orders/"+result.order().id())).body(result.order());
  }
 }
 @RestControllerAdvice
 public static class Errors {
  @ExceptionHandler(Conflict.class) ResponseEntity<ErrorBody> conflict(){return ResponseEntity.status(409).body(new ErrorBody("CONFLICT","请求编号已用于不同订单"));}
  @ExceptionHandler(Missing.class) ResponseEntity<ErrorBody> missing(){return ResponseEntity.status(404).body(new ErrorBody("NOT_FOUND","订单不存在"));}
  @ExceptionHandler({MethodArgumentNotValidException.class,HttpMessageNotReadableException.class,IllegalArgumentException.class,ArithmeticException.class})
  ResponseEntity<ErrorBody> invalid(){return ResponseEntity.badRequest().body(new ErrorBody("INVALID_INPUT","输入不合法或金额溢出"));}
 }
 public static void main(String[] args){SpringApplication app=new SpringApplication(Lab.class);app.setDefaultProperties(Map.of("server.address","127.0.0.1","server.port","18084"));app.run(args);}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.*;
import java.util.*;
import java.util.concurrent.*;
import static org.assertj.core.api.Assertions.*;
@SpringBootTest(classes=Lab.class,webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class LabTest {
 @Autowired TestRestTemplate http; @LocalServerPort int port;
 ResponseEntity<Lab.Order> post(Lab.Request r){return http.postForEntity("/api/orders",r,Lab.Order.class);}
 @Test void 真实HTTP创建重试与冲突(){String k=UUID.randomUUID().toString();var r=new Lab.Request(k,"书",2,150);var first=post(r);assertThat(first.getStatusCode().value()).isEqualTo(201);assertThat(first.getBody().totalFen()).isEqualTo(300);assertThat(first.getHeaders().getLocation().toString()).isEqualTo("/api/orders/"+first.getBody().id());var again=post(r);assertThat(again.getStatusCode().value()).isEqualTo(200);assertThat(again.getBody().id()).isEqualTo(first.getBody().id());var conflict=http.postForEntity("/api/orders",new Lab.Request(k,"另一商品",2,150),Lab.ErrorBody.class);assertThat(conflict.getStatusCode().value()).isEqualTo(409);}
 @Test void 校验错误格式和不存在(){for(var r:List.of(new Lab.Request("a","",1,1),new Lab.Request("a","书",0,1),new Lab.Request("a","书",101,1),new Lab.Request("a","书",2,Long.MAX_VALUE))){var response=http.postForEntity("/api/orders",r,Lab.ErrorBody.class);assertThat(response.getStatusCode().value()).isEqualTo(400);assertThat(response.getBody().code()).isEqualTo("INVALID_INPUT");}assertThat(http.getForEntity("/api/orders/99999999",Lab.ErrorBody.class).getStatusCode().value()).isEqualTo(404);}
 @Test void 同进程并发同键只创建一次() throws Exception {var store=new Lab.Store();try(var pool=Executors.newFixedThreadPool(4)){var calls=new ArrayList<Callable<Lab.Creation>>();for(int i=0;i<20;i++)calls.add(()->store.create(new Lab.Request("same","商品",1,100)));var results=pool.invokeAll(calls);long created=0;for(var f:results)if(f.get().created())created++;assertThat(created).isEqualTo(1);assertThat(store.list()).hasSize(1);}}
 @Test void 中文前端从真实服务返回(){var page=http.getForEntity("/",String.class);assertThat(page.getStatusCode().value()).isEqualTo(200);assertThat(page.getBody()).contains("订单实验室","/api/orders","requestId");}
 @Test void 分页边界由后端校验(){assertThat(http.getForEntity("/api/orders?offset=-1",Lab.ErrorBody.class).getStatusCode().value()).isEqualTo(400);assertThat(http.getForEntity("/api/orders?limit=101",Lab.ErrorBody.class).getStatusCode().value()).isEqualTo(400);assertThat(http.getForEntity("/api/orders?limit=2",Lab.Order[].class).getBody().length).isLessThanOrEqualTo(2);}
 @Test void 非法JSON不会泄漏堆栈(){HttpHeaders h=new HttpHeaders();h.setContentType(MediaType.APPLICATION_JSON);var response=http.postForEntity("/api/orders",new HttpEntity<>("{坏JSON",h),String.class);assertThat(response.getStatusCode().value()).isEqualTo(400);assertThat(response.getBody()).doesNotContain("stackTrace","java.lang");}
}''',
'''package labs.frameworks;
import java.util.Map;
import java.net.*;
import java.net.http.*;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
public class Usage {
 public static void main(String[] args) throws Exception {
  SpringApplication app=new SpringApplication(Lab.class);app.setDefaultProperties(Map.of("server.port","0","server.address","127.0.0.1"));
  try(var context=(ServletWebServerApplicationContext)app.run()){
   int port=context.getWebServer().getPort();var client=HttpClient.newHttpClient();
   var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/orders")).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString("{\\"requestId\\":\\"演示请求\\",\\"sku\\":\\"书\\",\\"quantity\\":2,\\"unitPriceFen\\":150}")).build();
   var response=client.send(request,HttpResponse.BodyHandlers.ofString());
   if(response.statusCode()!=201)throw new AssertionError("真实HTTP创建失败："+response.body());
   System.out.println("真实HTTP创建成功："+response.body());
  }
 }
}''',extra={'resources/static/index.html':'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>订单实验室</title>
<style>body{font:17px system-ui;background:#f3f5f8;color:#17243b;max-width:920px;margin:40px auto;padding:24px}main{background:white;padding:28px;border-radius:18px}label{display:block;margin:14px 0}input{display:block;padding:10px;width:95%;font:inherit}button{padding:10px 18px;font:inherit;margin:8px 8px 8px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f7;padding:16px}#status{min-height:28px}small{color:#52627a}</style></head>
<body><main><h1>订单实验室</h1><p>前端已预置。只需编写后端，再通过这里观察HTTP合同。</p><small>界面版本 0.1.0 · API版本1 · 无Node或前端构建依赖 · 数据只保留在当前服务进程</small>
<form id="form"><label>请求编号<input id="requestId" required value="demo-001"></label><label>商品SKU<input id="sku" required value="BOOK-001"></label><label>数量<input id="quantity" type="number" required min="1" max="100" value="2"></label><label>单价（分）<input id="price" type="number" required min="1" value="150"></label><button id="submit">提交订单</button><button type="button" id="newKey">换一个请求编号</button><button type="button" id="refresh">刷新列表</button></form><p id="status" role="status" aria-live="polite">尚未发送请求</p><pre id="response">请求结果将显示在这里</pre><h2>当前订单</h2><pre id="orders">正在读取订单</pre></main>
<script>
const $=id=>document.getElementById(id);let busy=false;let loadSequence=0;
async function load(){const sequence=++loadSequence;const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),5000);try{const r=await fetch('/api/orders',{signal:controller.signal});if(!r.ok)throw new Error('读取失败，状态码 '+r.status);const raw=await r.text();const rows=JSON.parse(raw);if(sequence===loadSequence)$('orders').textContent=rows.length?raw:'暂无订单';}catch(e){if(sequence===loadSequence)$('orders').textContent='无法读取订单：'+(e.name==='AbortError'?'读取超时':e.message);}finally{clearTimeout(timer);}}
$('form').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;busy=true;$('submit').disabled=true;$('status').textContent='正在提交';const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),5000);try{const body={requestId:$('requestId').value,sku:$('sku').value,quantity:Number($('quantity').value),unitPriceFen:$('price').value};const r=await fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});const raw=await r.text();$('status').textContent='HTTP '+r.status+'：'+(r.ok?'请求成功':'请求被拒绝');$('response').textContent=raw;await load();}catch(e){$('status').textContent=e.name==='AbortError'?'请求超时，结果可能未知；请保持请求编号重试':'网络请求失败';$('response').textContent=e.message;}finally{clearTimeout(timer);busy=false;$('submit').disabled=false;}});
$('newKey').onclick=()=>{$('requestId').value=globalThis.crypto?.randomUUID?.() || ('req-'+Date.now()+'-'+Math.random().toString(16).slice(2));};$('refresh').onclick=load;load();
</script></body></html>'''},mutations=[['return new Creation(old,false);','return new Creation(old,true);'],['r.quantity()>100','r.quantity()>101']])

task('03-transactions','03 JDBC事务与失败原子性','01-boot','C04-03',
'创建订单同时扣库存。写入订单失败时必须恢复库存；不能把方法返回失败却已扣库存的状态留给用户。',
'1. Usage通过真实H2数据库执行一笔订单\n2. 实现Service.place中的TransactionTemplate边界\n3. 在扣库存后注入异常，验证库存与订单同时回滚\n4. 观察相同请求重试与库存不足\n5. 可选MySQL真实集成由共享镜像驱动，Docker未启动不能记录通过',
'数量必须正数；库存初始10。成功创建同时扣减；任何异常全部回滚。相同requestId/quantity重试不重复扣减；同键不同数量冲突失败。H2仅证明本节Spring/JDBC事务，不替代MySQL的MVCC/锁语义。',
'[TransactionTemplate.execute](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-tx/src/main/java/org/springframework/transaction/support/TransactionTemplate.java) → PlatformTransactionManager；[DataSourceTransactionManager](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-jdbc/src/main/java/org/springframework/jdbc/datasource/DataSourceTransactionManager.java)跟踪连接绑定、提交与回滚。',
'事务必须包含读取请求状态、条件扣减和插入订单。数据库连接由Spring绑定到当前事务，JdbcTemplate复用该连接；不是分别new连接。异常必须穿过事务边界才能按规则回滚。重复键竞态的生产处理还需数据库唯一约束和重试设计。',
'- 为什么不能把事务只包在insert上？库存修改会落在事务外\n- TransactionTemplate和@Transactional怎么选？前者边界显式，后者依赖代理；追问自调用\n- 为什么H2通过不能证明MySQL所有行为？实现、方言、锁与隔离不同\n- 库存不足如何防止负库存？条件更新并检查影响行数',
'''package labs.frameworks;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.*;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import javax.sql.DataSource;
@Configuration
public class Lab {
 @Bean DataSource dataSource(){return new EmbeddedDatabaseBuilder().generateUniqueName(true).setType(EmbeddedDatabaseType.H2).addScript("schema.sql").build();}
 @Bean JdbcTemplate jdbc(DataSource ds){return new JdbcTemplate(ds);}
 @Bean TransactionTemplate transactions(DataSource ds){return new TransactionTemplate(new DataSourceTransactionManager(ds));}
 @Bean Service service(JdbcTemplate jdbc,TransactionTemplate tx){return new Service(jdbc,tx);}
 public static class Service {
  final JdbcTemplate jdbc;final TransactionTemplate tx;
  public Service(JdbcTemplate jdbc,TransactionTemplate tx){this.jdbc=jdbc;this.tx=tx;}
  public void place(String requestId,int quantity,boolean failAfterDebit){
// 练习区开始
   if(requestId==null || requestId.isBlank() || quantity<1)throw new IllegalArgumentException("请求编号与数量不合法");
   tx.executeWithoutResult(status->{
    var previous=jdbc.queryForList("select quantity from orders where request_id=?",Integer.class,requestId);
    if(!previous.isEmpty()){if(previous.get(0)!=quantity)throw new IllegalArgumentException("同一编号内容冲突");return;}
    int updated=jdbc.update("update stock set remaining=remaining-? where sku='BOOK' and remaining>=?",quantity,quantity);
    if(updated!=1)throw new IllegalStateException("库存不足");
    if(failAfterDebit)throw new IllegalStateException("模拟扣库存后写入失败");
    jdbc.update("insert into orders(request_id,quantity) values(?,?)",requestId,quantity);
   });
// 练习区结束
  }
  public int remaining(){return jdbc.queryForObject("select remaining from stock where sku='BOOK'",Integer.class);}
  public int orders(){return jdbc.queryForObject("select count(*) from orders",Integer.class);}
 }
 public static void main(String[] args){try(var c=new AnnotationConfigApplicationContext(Lab.class)){var s=c.getBean(Service.class);s.place("示例订单",2,false);System.out.println("剩余库存："+s.remaining()+"，订单数："+s.orders());}}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 AnnotationConfigApplicationContext context;Lab.Service service;
 @BeforeEach void 启动独立数据库(){context=new AnnotationConfigApplicationContext(Lab.class);service=context.getBean(Lab.Service.class);}
 @AfterEach void 关闭(){context.close();}
 @Test void 成功同时更新并重试幂等(){service.place("一",3,false);service.place("一",3,false);assertThat(service.remaining()).isEqualTo(7);assertThat(service.orders()).isEqualTo(1);}
 @Test void 扣减后失败必须全部回滚(){assertThatThrownBy(()->service.place("失败",4,true)).isInstanceOf(IllegalStateException.class);assertThat(service.remaining()).isEqualTo(10);assertThat(service.orders()).isZero();}
 @Test void 库存不足和非法数量不改状态(){assertThatThrownBy(()->service.place("超量",11,false)).isInstanceOf(IllegalStateException.class);assertThatThrownBy(()->service.place("负值",-1,false)).isInstanceOf(IllegalArgumentException.class);assertThat(service.remaining()).isEqualTo(10);assertThat(service.orders()).isZero();}
 @Test void 同键不同数量拒绝(){service.place("一",2,false);assertThatThrownBy(()->service.place("一",3,false)).isInstanceOf(IllegalArgumentException.class);assertThat(service.remaining()).isEqualTo(8);}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(args);}}''',extra={'resources/schema.sql':'''create table stock(sku varchar(64) primary key,remaining integer not null);
create table orders(request_id varchar(128) primary key,quantity integer not null);
insert into stock(sku,remaining) values('BOOK',10);''','integration-test/labs/frameworks/MySqlContractTest.java':'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.support.TransactionTemplate;
import java.nio.file.*;
import java.util.Properties;
import static org.assertj.core.api.Assertions.*;
@Tag("docker") @Testcontainers
class MySqlContractTest {
 static String image(){
  String path=System.getenv("LAB_SHARED_VERSIONS");
  if(path==null)throw new IllegalStateException("请设置LAB_SHARED_VERSIONS为仓库infra/versions.env，不能复制镜像版本");
  try(var in=Files.newInputStream(Path.of(path))){var p=new Properties();p.load(in);String image=p.getProperty("MYSQL_IMAGE");if(image==null || image.isBlank())throw new IllegalStateException("共享镜像台账缺少MYSQL_IMAGE");return image;}catch(java.io.IOException e){throw new IllegalStateException("无法读取共享镜像台账",e);}
 }
 @Container static final MySQLContainer<?> mysql=new MySQLContainer<>(image());
 @Test void 真实MySQL回滚合同(){var ds=new DriverManagerDataSource(mysql.getJdbcUrl(),mysql.getUsername(),mysql.getPassword());var jdbc=new JdbcTemplate(ds);jdbc.execute("create table stock(sku varchar(64) primary key,remaining integer not null)");jdbc.execute("create table orders(request_id varchar(128) primary key,quantity integer not null)");jdbc.update("insert into stock values('BOOK',10)");var s=new Lab.Service(jdbc,new TransactionTemplate(new DataSourceTransactionManager(ds)));assertThatThrownBy(()->s.place("失败",3,true)).isInstanceOf(IllegalStateException.class);assertThat(s.remaining()).isEqualTo(10);s.place("成功",2,false);assertThat(s.remaining()).isEqualTo(8);}
}'''},mutations=[['tx.executeWithoutResult(status->{','((java.util.function.Consumer<Object>)(status->{'],['if(failAfterDebit)throw new IllegalStateException("模拟扣库存后写入失败");','if(failAfterDebit)return;']])
# 第一种变体需要完整语法配对，验证器只使用下列明确可编译变体。
TASKS[-1]['mutations']=TASKS[-1]['mutations'][1:]

task('04-test-layers','04 单元切片与真实HTTP分层测试','01-boot','C04-04',
'报价服务依赖一个价格端口。业务逻辑、控制器映射和真实HTTP各有不同责任，不能用mock通过代替完整联调。',
'1. 先读Unit/Slice/HTTP三层可见测试\n2. 实现Quotes.total的校验、一次取价和精确乘法\n3. 运行测试并指出每层能杀死哪类错误\n4. 改变一个错误映射合同，同时更新对应层的测试，禁止只删断言',
'数量范围1到100；非法数量不能调用价格端口；价格必须为正；使用精确乘法。HTTP非法输入400，下游故障503，正确报价200。所有外部依赖均是本实验显式提供的端口，无第三方访问。',
'[DispatcherServlet.doDispatch](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-webmvc/src/main/java/org/springframework/web/servlet/DispatcherServlet.java)与[SpringBootTestContextBootstrapper](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot-test/src/main/java/org/springframework/boot/test/context/SpringBootTestContextBootstrapper.java)：比较纯对象、MockMvc和真实端口的边界。',
'纯单元使用Mockito检验调用次数与业务边界；MVC切片检验参数/状态码；真实随机端口检验应用装配与HTTP传输。三层测试可能有重复合同，但诊断粒度不同。mock返回值不能证明远端价格服务真的可用。',
'- 单元与集成测试为什么都需要？速度、隔离性与真实性不同\n- 什么情况下mock让你产生错误信心？真实序列化/事务/网络未执行\n- 切片失败而单元通过先查什么？装配、参数转换、异常映射\n- 测试数据为何要隔离？避免顺序依赖与假阳性',
'''package labs.frameworks;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
@SpringBootConfiguration @EnableAutoConfiguration(exclude=DataSourceAutoConfiguration.class) @Import({Lab.Api.class,Lab.Errors.class})
public class Lab {
 public interface Prices {long unitPrice();}
 public static class Quotes {
  final Prices prices;public Quotes(Prices prices){this.prices=prices;}
  public long total(int quantity){
// 练习区开始
   if(quantity<1 || quantity>100)throw new IllegalArgumentException("数量不合法");
   long price=prices.unitPrice();if(price<1)throw new IllegalStateException("价格服务返回错误数据");
   return Math.multiplyExact(price,quantity);
// 练习区结束
  }
 }
 @Bean Prices prices(){return ()->150;}
 @Bean Quotes quotes(Prices p){return new Quotes(p);}
 @RestController public static class Api {final Quotes quotes;public Api(Quotes q){quotes=q;}@GetMapping("/quote") public long quote(@RequestParam int quantity){return quotes.total(quantity);}}
 @RestControllerAdvice public static class Errors {
  @ExceptionHandler({IllegalArgumentException.class,ArithmeticException.class}) ResponseEntity<String> invalid(){return ResponseEntity.badRequest().body("报价参数不合法");}
  @ExceptionHandler(IllegalStateException.class) ResponseEntity<String> unavailable(){return ResponseEntity.status(503).body("报价暂不可用");}
 }
 public static void main(String[] args){var app=new SpringApplication(Lab.class);app.setDefaultProperties(java.util.Map.of("server.address","127.0.0.1","server.port","18084"));app.run(args);}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
class LabTest {
 @Test void 单元测试隔离价格端口(){Lab.Prices p=mock(Lab.Prices.class);when(p.unitPrice()).thenReturn(150L);assertThat(new Lab.Quotes(p).total(2)).isEqualTo(300);verify(p,times(1)).unitPrice();}
 @Test void 非法请求不触碰下游(){Lab.Prices p=mock(Lab.Prices.class);assertThatThrownBy(()->new Lab.Quotes(p).total(0)).isInstanceOf(IllegalArgumentException.class);verifyNoInteractions(p);}
 @Test void 边界与异常(){assertThatThrownBy(()->new Lab.Quotes(()->0).total(2)).isInstanceOf(IllegalStateException.class);assertThatThrownBy(()->new Lab.Quotes(()->Long.MAX_VALUE).total(2)).isInstanceOf(ArithmeticException.class);assertThat(new Lab.Quotes(()->1).total(100)).isEqualTo(100);assertThatThrownBy(()->new Lab.Quotes(()->1).total(101)).isInstanceOf(IllegalArgumentException.class);}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){var q=new Lab.Quotes(()->150);System.out.println("两件商品报价："+q.total(2)+"分");}}''',extra={'test/labs/frameworks/MvcSliceTest.java':'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
@WebMvcTest(Lab.Api.class) @Import(Lab.Errors.class)
class MvcSliceTest {
 @Autowired MockMvc mvc;@MockitoBean Lab.Quotes quotes;
 @Test void 切片检查映射与参数() throws Exception {when(quotes.total(2)).thenReturn(300L);mvc.perform(get("/quote").param("quantity","2")).andExpect(status().isOk()).andExpect(content().string("300"));verify(quotes).total(2);}
 @Test void 切片检查失败映射() throws Exception {when(quotes.total(2)).thenThrow(new IllegalStateException());mvc.perform(get("/quote").param("quantity","2")).andExpect(status().isServiceUnavailable());mvc.perform(get("/quote").param("quantity","坏参数")).andExpect(status().isBadRequest());}
}''','test/labs/frameworks/HttpIntegrationTest.java':'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import static org.assertj.core.api.Assertions.*;
@SpringBootTest(classes=Lab.class,webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpIntegrationTest {
 @Autowired TestRestTemplate http;
 @Test void 真实HTTP与应用装配(){var r=http.getForEntity("/quote?quantity=2",Long.class);assertThat(r.getStatusCode().value()).isEqualTo(200);assertThat(r.getBody()).isEqualTo(300L);assertThat(http.getForEntity("/quote?quantity=0",String.class).getStatusCode().value()).isEqualTo(400);}
}'''},mutations=[['quantity>100','quantity>101']])

task('05-security','05 基础认证授权与CSRF边界','01-boot','C04-05',
'内部订单接口允许阅读者查订单，管理员才能修改。即使界面隐藏修改按钮，服务端仍必须拒绝越权与无CSRF的浏览器写请求。',
'1. 使用Usage查看本实验角色合同\n2. 实现SecurityFilterChain：公开健康入口、阅读权限、管理员写入、默认拒绝\n3. 保留CSRF保护并运行完整MockMvc安全过滤链测试\n4. 比较未登录401、权限不足403、缺CSRF403与合法写入201',
'GET /public/ping公开；GET /orders需READER或ADMIN；POST /orders需ADMIN和有效CSRF；其他路径默认拒绝。仅模拟用户，不接真实身份平台。不能为了测试通过全局permitAll或禁用CSRF。',
'[FilterChainProxy](https://github.com/spring-projects/spring-security/blob/6.5.11/web/src/main/java/org/springframework/security/web/FilterChainProxy.java)与[AuthorizationFilter](https://github.com/spring-projects/spring-security/blob/6.5.11/web/src/main/java/org/springframework/security/web/access/intercept/AuthorizationFilter.java)，固定Security6.5.11。先验证来源路径再记录关键分支。',
'认证先建立主体，授权再匹配HTTP动作与资源。CSRF防护与角色判断解决不同风险；会话/浏览器携带凭据的写请求不能仅靠角色检查。V1只做基础安全，企业OIDC/LDAP/Keycloak在V2。',
'- 401和403区别是什么？未认证与已知请求被拒绝不同\n- CORS是否能阻止所有恶意调用？它是浏览器跨域机制，不能代替后端授权\n- 隐藏按钮为什么不安全？客户端可以绕过页面直接发HTTP\n- 何时讨论CSRF与无状态token的不同？先明确凭据如何自动附带，不盲目关闭',
'''package labs.frameworks;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.*;
@SpringBootConfiguration @EnableAutoConfiguration(exclude=DataSourceAutoConfiguration.class) @Import(Lab.Api.class)
public class Lab {
 // 仅隔离教学账户；真实项目不能沿用固定实验口令。
 @Bean org.springframework.security.core.userdetails.UserDetailsService users(){
  var encoder=org.springframework.security.crypto.factory.PasswordEncoderFactories.createDelegatingPasswordEncoder();
  var reader=org.springframework.security.core.userdetails.User.withUsername("reader").password(encoder.encode("lab-only")).roles("READER").build();
  var admin=org.springframework.security.core.userdetails.User.withUsername("admin").password(encoder.encode("lab-only")).roles("ADMIN").build();
  return new org.springframework.security.provisioning.InMemoryUserDetailsManager(reader,admin);
 }
 @Bean org.springframework.web.cors.CorsConfigurationSource corsConfigurationSource(){var config=new org.springframework.web.cors.CorsConfiguration();config.setAllowedOrigins(java.util.List.of("http://127.0.0.1:18084"));config.setAllowedMethods(java.util.List.of("GET","POST"));config.setAllowedHeaders(java.util.List.of("Authorization","Content-Type","X-CSRF-TOKEN"));config.setAllowCredentials(true);var source=new org.springframework.web.cors.UrlBasedCorsConfigurationSource();source.registerCorsConfiguration("/**",config);return source;}
 @Bean SecurityFilterChain security(HttpSecurity http) throws Exception {
// 练习区开始
  return http.cors(Customizer.withDefaults()).authorizeHttpRequests(auth->auth
    .requestMatchers("/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET,"/orders").hasAnyRole("READER","ADMIN")
    .requestMatchers(HttpMethod.POST,"/orders").hasRole("ADMIN")
    .anyRequest().denyAll()).httpBasic(Customizer.withDefaults()).build();
// 练习区结束
 }
 @RestController public static class Api {
  @GetMapping("/public/ping") String ping(){return "可用";}
  @GetMapping("/orders") String list(){return "订单列表";}
  @PostMapping("/orders") @ResponseStatus(org.springframework.http.HttpStatus.CREATED) String create(){return "已创建";}
 }
 public static void main(String[] args){SpringApplication app=new SpringApplication(Lab.class);app.setDefaultProperties(java.util.Map.of("server.address","127.0.0.1"));app.run(args);}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
@SpringBootTest(classes=Lab.class) @AutoConfigureMockMvc
class LabTest {
 @Autowired MockMvc mvc;
 @Test void 实验口令也经真实认证过滤器() throws Exception {mvc.perform(get("/orders").with(httpBasic("reader","lab-only"))).andExpect(status().isOk());mvc.perform(get("/orders").with(httpBasic("reader","wrong"))).andExpect(status().isUnauthorized());}
 @Test void 公开接口与未登录() throws Exception {mvc.perform(get("/public/ping")).andExpect(status().isOk());mvc.perform(get("/orders")).andExpect(status().isUnauthorized());}
 @Test void 阅读者不能写() throws Exception {mvc.perform(get("/orders").with(user("reader").roles("READER"))).andExpect(status().isOk());mvc.perform(post("/orders").with(user("reader").roles("READER")).with(csrf())).andExpect(status().isForbidden());}
 @Test void 管理员仍需要CSRF() throws Exception {mvc.perform(post("/orders").with(user("admin").roles("ADMIN"))).andExpect(status().isForbidden());mvc.perform(post("/orders").with(user("admin").roles("ADMIN")).with(csrf())).andExpect(status().isCreated());}
 @Test void CORS不反射任意来源()throws Exception{mvc.perform(options("/orders").header("Origin","http://127.0.0.1:18084").header("Access-Control-Request-Method","GET")).andExpect(status().isOk()).andExpect(header().string("Access-Control-Allow-Origin","http://127.0.0.1:18084"));mvc.perform(options("/orders").header("Origin","https://untrusted.invalid").header("Access-Control-Request-Method","GET")).andExpect(status().isForbidden());}
 @Test void 其他资源默认拒绝() throws Exception {mvc.perform(get("/internal").with(user("admin").roles("ADMIN"))).andExpect(status().isForbidden());}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){System.out.println("本节真实调用方为MockMvc安全过滤链：运行:05-security:test，依次验证公开/匿名/阅读者/管理员/CSRF");}}''',mutations=[['.hasRole("ADMIN")','.hasAnyRole("READER","ADMIN")'],['.anyRequest().denyAll()','.anyRequest().permitAll()']])

task('06-runtime-lifecycle','06 生命周期健康与优雅关闭','01-boot','C04-06',
'服务停机时应停止接单，并在有限预算内处理已有任务。健康状态必须表达真实资源状态，而不是永远返回UP。',
'1. 运行Usage让真实Spring上下文启动并关闭任务池\n2. 实现Gate.stop停止接单、有限等待、必要中断和恢复中断标记\n3. 用latch控制在途任务，不用sleep猜顺序\n4. 检查HealthIndicator与关闭后拒绝提交',
'上下文启动后接单；stop后拒绝新任务；stop等待上限2秒，超时调用shutdownNow；线程中断标记不能被吞。关闭后不留下本实验线程。健康UP/DOWN来自实际running状态。',
'[DefaultLifecycleProcessor](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-context/src/main/java/org/springframework/context/support/DefaultLifecycleProcessor.java)：onRefresh/startBeans与onClose/stopBeans；SmartLifecycle的phase与关闭顺序。',
'SmartLifecycle将资源生命周期交给真实Spring容器。先改变接单状态再shutdown，避免关闭期间持续接收任务。优雅等待有预算，超时中断也是协作信号；不响应中断的业务仍需额外保护，不能声称任何任务都能安全强杀。',
'- readiness与liveness为什么不是同一件事？一个能否接流量，一个是否需重启\n- 为什么shutdown不等于任务立刻结束？已提交任务继续执行\n- 中断标记为何要恢复？让上层知道当前线程被要求停止\n- 关闭预算如何分配给多种资源？需要考虑依赖顺序和总预算',
'''package labs.frameworks;
import java.util.concurrent.*;
import org.springframework.context.*;
import org.springframework.context.annotation.*;
import org.springframework.boot.actuate.health.*;
@Configuration
public class Lab {
 public static class Gate implements SmartLifecycle {
  private volatile boolean running;
  private ExecutorService executor;
  public synchronized void start(){if(!running){executor=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(2),r->new Thread(r,"框架实验任务线程"),new ThreadPoolExecutor.AbortPolicy());running=true;}}
  public synchronized <T> Future<T> submit(Callable<T> work){if(!running)throw new RejectedExecutionException("服务已停止接单");return executor.submit(work);}
  public boolean isRunning(){return running;}
  public void stop(){
// 练习区开始
   ExecutorService current;
   synchronized(this){if(!running)return;running=false;current=executor;current.shutdown();}
   try{if(!current.awaitTermination(2,TimeUnit.SECONDS))current.shutdownNow();}
   catch(InterruptedException e){current.shutdownNow();Thread.currentThread().interrupt();}
// 练习区结束
  }
  public boolean terminated(){return executor!=null && executor.isTerminated();}
 }
 @Bean Gate gate(){return new Gate();}
 @Bean HealthIndicator workHealth(Gate gate){return ()->(gate.isRunning()?Health.up():Health.down()).withDetail("accepting",gate.isRunning()).build();}
 public static void main(String[] args) throws Exception {try(var c=new AnnotationConfigApplicationContext(Lab.class)){System.out.println("任务结果："+c.getBean(Gate.class).submit(()->42).get());}}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.boot.actuate.health.*;
import java.util.concurrent.*;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 @Test void Spring启动与关闭资源() throws Exception {var c=new AnnotationConfigApplicationContext(Lab.class);var gate=c.getBean(Lab.Gate.class);assertThat(gate.isRunning()).isTrue();assertThat(c.getBean(HealthIndicator.class).health().getStatus()).isEqualTo(Status.UP);assertThat(gate.submit(()->42).get(2,TimeUnit.SECONDS)).isEqualTo(42);c.close();assertThat(gate.isRunning()).isFalse();assertThat(gate.terminated()).isTrue();assertThatThrownBy(()->gate.submit(()->1)).isInstanceOf(RejectedExecutionException.class);}
 @Test void 已接收任务有机会完成() throws Exception {var gate=new Lab.Gate();gate.start();var started=new CountDownLatch(1);var release=new CountDownLatch(1);var result=gate.submit(()->{started.countDown();release.await();return 7;});assertThat(started.await(2,TimeUnit.SECONDS)).isTrue();try(var closer=Executors.newSingleThreadExecutor()){var stopped=closer.submit((Runnable)gate::stop);release.countDown();stopped.get(3,TimeUnit.SECONDS);}assertThat(result.get()).isEqualTo(7);assertThat(gate.terminated()).isTrue();}
 @Test void 队列饱和明确拒绝()throws Exception{var gate=new Lab.Gate();gate.start();var entered=new CountDownLatch(1);var release=new CountDownLatch(1);try{gate.submit(()->{entered.countDown();release.await();return 1;});assertThat(entered.await(2,TimeUnit.SECONDS)).isTrue();gate.submit(()->2);gate.submit(()->3);assertThatThrownBy(()->gate.submit(()->4)).isInstanceOf(RejectedExecutionException.class);}finally{release.countDown();gate.stop();}assertThat(gate.terminated()).isTrue();}
 @Test void 重复停止幂等(){var gate=new Lab.Gate();gate.start();gate.stop();gate.stop();assertThat(gate.isRunning()).isFalse();}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args) throws Exception {Lab.main(args);}}''',mutations=[['running=false;current=executor;','current=executor;']])

# 综合应用保留上一节HTTP合同，将存储替换成真实JDBC事务；前端无需学习者改写。
http_code=(ROOT/'framework-course/01-boot/02-http-contract/src/labs/frameworks/Lab.java').read_text()
start=http_code.index(' public static class Store {');end=http_code.index(' @RestController @RequestMapping',start)
store=''' public static class Store {
  private final org.springframework.jdbc.core.JdbcTemplate jdbc;
  private final org.springframework.transaction.support.TransactionTemplate tx;
  public Store(org.springframework.jdbc.core.JdbcTemplate jdbc,org.springframework.transaction.support.TransactionTemplate tx){this.jdbc=jdbc;this.tx=tx;}
  private Order row(java.sql.ResultSet rs,int n)throws java.sql.SQLException{return new Order(rs.getLong("id"),rs.getString("request_id"),rs.getString("sku"),rs.getInt("quantity"),rs.getLong("unit_price"),rs.getLong("total"));}
  public Creation create(Request r){
// 练习区开始
   if(r.quantity()<1 || r.quantity()>100 || r.unitPriceFen()<1)throw new IllegalArgumentException("数量或金额不合法");
   long total=Math.multiplyExact(r.quantity(),r.unitPriceFen());
   return tx.execute(status->{
    var old=jdbc.query("select * from orders where request_id=?",this::row,r.requestId());
    if(!old.isEmpty()){Order x=old.get(0);if(!x.sku().equals(r.sku()) || x.quantity()!=r.quantity() || x.unitPriceFen()!=r.unitPriceFen())throw new Conflict();return new Creation(x,false);}
    var key=new org.springframework.jdbc.support.GeneratedKeyHolder();
    jdbc.update(connection->{var statement=connection.prepareStatement("insert into orders(request_id,sku,quantity,unit_price,total) values(?,?,?,?,?)",java.sql.Statement.RETURN_GENERATED_KEYS);statement.setString(1,r.requestId());statement.setString(2,r.sku());statement.setInt(3,r.quantity());statement.setLong(4,r.unitPriceFen());statement.setLong(5,total);return statement;},key);
    return new Creation(new Order(java.util.Objects.requireNonNull(key.getKey()).longValue(),r.requestId(),r.sku(),r.quantity(),r.unitPriceFen(),total),true);
   });
// 练习区结束
  }
  public List<Order> list(){return jdbc.query("select * from orders order by id",this::row);}
  public Order get(long id){return jdbc.query("select * from orders where id=?",this::row,id).stream().findFirst().orElseThrow(Missing::new);}
 }
 @Bean Store store(org.springframework.jdbc.core.JdbcTemplate jdbc,org.springframework.transaction.PlatformTransactionManager tm){return new Store(jdbc,new org.springframework.transaction.support.TransactionTemplate(tm));}
'''
full=http_code[:start]+store+http_code[end:]
full=full.replace('@EnableAutoConfiguration(exclude=DataSourceAutoConfiguration.class)','@EnableAutoConfiguration')
full=full.replace('@ExceptionHandler(Missing.class)', '@ExceptionHandler(org.springframework.dao.DuplicateKeyException.class) ResponseEntity<ErrorBody> duplicate(){return ResponseEntity.status(409).body(new ErrorBody("CONCURRENT_RETRY","并发同键请求，请使用相同参数重试确认结果"));}\n  @ExceptionHandler(Missing.class)')
integration_test='''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.assertj.core.api.Assertions.*;
@SpringBootTest(classes=Lab.class,webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class LabTest {
 @Autowired TestRestTemplate http;@Autowired JdbcTemplate jdbc;
 @Test void 真实HTTP到数据库(){String id=java.util.UUID.randomUUID().toString();var request=new Lab.Request(id,"BOOK",2,150);var r=http.postForEntity("/api/orders",request,Lab.Order.class);assertThat(r.getStatusCode().value()).isEqualTo(201);assertThat(r.getBody().totalFen()).isEqualTo(300);assertThat(jdbc.queryForObject("select count(*) from orders where request_id=?",Integer.class,id)).isEqualTo(1);var repeat=http.postForEntity("/api/orders",request,Lab.Order.class);assertThat(repeat.getStatusCode().value()).isEqualTo(200);assertThat(repeat.getBody().id()).isEqualTo(r.getBody().id());assertThat(http.getForEntity("/api/orders/"+r.getBody().id(),Lab.Order.class).getBody().sku()).isEqualTo("BOOK");}
 @Test void 错误不会写入(){int count=jdbc.queryForObject("select count(*) from orders",Integer.class);var r=http.postForEntity("/api/orders",new Lab.Request("非法","BOOK",101,100),Lab.ErrorBody.class);assertThat(r.getStatusCode().value()).isEqualTo(400);assertThat(jdbc.queryForObject("select count(*) from orders",Integer.class)).isEqualTo(count);}
 @Test void 同键变更拒绝而非覆盖(){String id=java.util.UUID.randomUUID().toString();http.postForEntity("/api/orders",new Lab.Request(id,"BOOK",1,100),Lab.Order.class);var bad=http.postForEntity("/api/orders",new Lab.Request(id,"OTHER",1,100),Lab.ErrorBody.class);assertThat(bad.getStatusCode().value()).isEqualTo(409);assertThat(jdbc.queryForObject("select sku from orders where request_id=?",String.class,id)).isEqualTo("BOOK");}
 @Test void 中文页面可从真实端口使用(){assertThat(http.getForEntity("/",String.class).getBody()).contains("订单实验室");}
}'''
task('07-integrated-service','07 前端HTTP与数据库完整联调','01-boot','C04-07',
'把内存练习升级为真实SpringBoot/JDBC完整服务，预置界面不改，后端以唯一约束与事务保护请求。明确多实例竞态的结果未知与重试边界。',
'1. 运行预置页面与Usage，观察订单写入真实H2数据库\n2. 实现Store.create的事务、重复检查、GeneratedKeyHolder\n3. 用HTTP测试核对数据库真实状态\n4. 对比02节内存模型和本节持久层，不把H2内存数据库当生产持久部署\n5. 阅读依赖锁与迁移检查清单，解释升级Boot大版本的验证范围',
'保留02节HTTP合同；数据库request_id唯一。并发同键竞争可能返回明确409重试提示，不能假称跨进程锁。成功后事务内的数据一致；输入错误不产生记录。H2是可重建教学数据库，MySQL部署属于共享环境集成验收。',
'[Boot数据源自动配置](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.java)与[JdbcTemplate](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-jdbc/src/main/java/org/springframework/jdbc/core/JdbcTemplate.java)。从HTTP跟到连接获取、SQL执行和事务提交。',
'预置前端只调用相同API，存储实现变化不应破坏契约。数据库唯一约束是多实例的最终防线；先查询再写入仍可能竞态，因此冲突必须可解释并有重试合同。升级依赖必须检查BOM、starter、测试包、Servlet/Validation兼容、配置和完整回归，不能仅改版本号。',
'- 完整服务与CRUD样例差在哪？有失败、重试、生命周期和可验证合同\n- 并发先查后写为何不够？多个事务可同时看见不存在\n- 如何把H2换成MySQL？配置、驱动、迁移与真实集成测试一起更换\n- Boot3升级到4如何评估？先查官方迁移说明与依赖边界，本课不声称已完成Boot4运行验收',
full,integration_test,(ROOT/'framework-course/01-boot/02-http-contract/src/labs/frameworks/Usage.java').read_text(),extra={'resources/schema.sql':'''create table orders(id bigint generated by default as identity primary key,request_id varchar(128) not null unique,sku varchar(128) not null,quantity integer not null,unit_price bigint not null,total bigint not null);''','resources/static/index.html':(ROOT/'framework-course/01-boot/02-http-contract/resources/static/index.html').read_text(),'resources/application.properties':'''server.address=127.0.0.1
server.port=18084
spring.datasource.generate-unique-name=true
spring.sql.init.mode=always
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=5s
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.connection-timeout=1000
'''},mutations=[['r.quantity()>100','r.quantity()>101']])

task('08-container-di','08 最小容器与真实构造注入','02-source','C05-01',
'理解Spring之前先明确容器解决什么：依赖构造、共享实例与错误报告。教学容器只支持公开单构造器，不冒充Spring。',
'1. 运行Usage查看真实Spring注入\n2. 实现Tiny.get的构造递归、单例缓存和循环路径清理\n3. 对照真实AnnotationConfigApplicationContext的Bean创建\n4. 用缺失构造器/循环依赖反例解释模型省略了什么',
'Tiny只支持恰好一个公开构造器、无基本类型参数的类；每类型同一实例；循环依赖明确失败；失败不得污染正在构造集合。没有scope、代理、属性注入、生命周期、注解扫描。',
'[AbstractBeanFactory.doGetBean](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractBeanFactory.java) → [AbstractAutowireCapableBeanFactory.createBean](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java)。比较真实缓存、依赖解析和教学模型。',
'缓存命中和正在构造是不同状态。先标记构造中、递归解决依赖、成功后缓存，并在finally清理标记。真实Spring的BeanDefinition、scope、工厂Bean、后处理和早期引用远比模型复杂。',
'- IoC与DI是什么关系？控制创建和协作关系，注入是实现方式\n- 单例Bean是否自动线程安全？生命周期共享不等于状态同步\n- 为什么失败后要清理构造标记？否则后续合法请求会被误判\n- 为什么生产代码不直接用这个Tiny？功能与诊断边界故意缩小',
'''package labs.frameworks;
import java.util.*;
import org.springframework.context.annotation.*;
@Configuration
public class Lab {
 public static class Clock {public Clock(){} public String now(){return "示例时刻";}}
 public static class Orders {final Clock clock;public Orders(Clock c){clock=c;}public String describe(){return "订单创建于"+clock.now();}}
 @Bean Clock clock(){return new Clock();}
 @Bean Orders orders(Clock c){return new Orders(c);}
 public static class Tiny {
  final Map<Class<?>,Object> cache=new HashMap<>();final Set<Class<?>> constructing=new HashSet<>();
  public synchronized <T>T get(Class<T> type){
// 练习区开始
   if(cache.containsKey(type))return type.cast(cache.get(type));
   if(!constructing.add(type))throw new IllegalStateException("检测到构造循环："+type.getName());
   try{
    var constructors=type.getConstructors();if(constructors.length!=1)throw new IllegalArgumentException("教学容器只支持一个公开构造器");
    var constructor=constructors[0];Object[] args=Arrays.stream(constructor.getParameterTypes()).map(this::get).toArray();
    T result=type.cast(constructor.newInstance(args));cache.put(type,result);return result;
   }catch(ReflectiveOperationException e){throw new IllegalStateException("构造失败",e);}finally{constructing.remove(type);}
// 练习区结束
  }
 }
 public static void main(String[] args){try(var c=new AnnotationConfigApplicationContext(Lab.class)){System.out.println(c.getBean(Orders.class).describe());}}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 public static class A {public A(B b){}}public static class B {public B(A a){}}
 public static class Bad {public Bad(){throw new IllegalStateException("模拟构造失败");}}
 @Test void 教学单例与依赖共享(){var tiny=new Lab.Tiny();var orders=tiny.get(Lab.Orders.class);assertThat(orders).isSameAs(tiny.get(Lab.Orders.class));assertThat(orders.clock).isSameAs(tiny.get(Lab.Clock.class));}
 @Test void 循环明确失败而不是栈溢出(){assertThatThrownBy(()->new Lab.Tiny().get(A.class)).isInstanceOf(IllegalStateException.class).hasMessageContaining("循环");}
 @Test void 构造失败清理标记(){var t=new Lab.Tiny();assertThatThrownBy(()->t.get(Bad.class)).hasMessageContaining("构造失败");assertThatThrownBy(()->t.get(Bad.class)).hasMessageContaining("构造失败").hasMessageNotContaining("循环");}
 @org.springframework.context.annotation.Configuration static class Choices {
  @org.springframework.context.annotation.Bean Lab.Clock first(){return new Lab.Clock();}
  @org.springframework.context.annotation.Bean @org.springframework.context.annotation.Primary Lab.Clock preferred(){return new Lab.Clock();}
  @org.springframework.context.annotation.Bean Lab.Orders orders(Lab.Clock c){return new Lab.Orders(c);}
 }
 @Test void 多候选使用显式优先级(){try(var c=new AnnotationConfigApplicationContext(Choices.class)){assertThat(c.getBean(Lab.Orders.class).clock).isSameAs(c.getBean("preferred"));}}
 @Test void 真实Spring同样完成构造注入(){try(var c=new AnnotationConfigApplicationContext(Lab.class)){assertThat(c.getBean(Lab.Orders.class).clock).isSameAs(c.getBean(Lab.Clock.class));}}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(args);}}''',mutations=[['cache.put(type,result);return result;','return result;']])

task('09-bean-lifecycle','09 Bean定义与实例生命周期','02-source','C05-02',
'平台在Bean创建前调整配置，在初始化前后记录资源状态。把修改Bean定义和处理Bean实例混在一起会产生时序问题。',
'1. Usage打印真实Spring执行轨迹\n2. 实现BeanFactoryPostProcessor在实例化前设置label\n3. 实现BeanPostProcessor的初始化前后记录\n4. 关闭上下文，验证销毁调用一次',
'轨迹必须是构造→属性→初始化前→初始化→初始化后→销毁；label为企业订单。后处理器只处理Account，不能对所有对象强转。不要手动调用生命周期方法造假轨迹。',
'[AbstractApplicationContext.refresh](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java) → invokeBeanFactoryPostProcessors/registerBeanPostProcessors/finishBeanFactoryInitialization；[initializeBean](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java)。',
'BeanFactoryPostProcessor处理定义，此时目标Account还未创建。BeanPostProcessor围绕初始化处理实例。关闭由Spring触发DisposableBean，不靠测试直接调用destroy。静态@Bean声明后处理器避免过早实例化配置类。',
'- 两种PostProcessor有什么不同？对象和执行阶段不同\n- 为什么初始化前已经完成属性注入？要让初始化逻辑看到最终配置\n- 代理常在哪个阶段加入？初始化后常见，但应以实际框架机制为准\n- prototype关闭时是否和singleton一样自动销毁？不能一概而论',
'''package labs.frameworks;
import java.util.*;
import org.springframework.beans.factory.*;
import org.springframework.beans.factory.config.*;
import org.springframework.context.annotation.*;
@Configuration
public class Lab {
 public static class Account implements InitializingBean,DisposableBean {
  final List<String> events=new ArrayList<>();String label;
  public Account(){events.add("构造");}
  public void setLabel(String s){label=s;events.add("属性");}
  public void afterPropertiesSet(){events.add("初始化");}
  public void destroy(){events.add("销毁");}
  public List<String> events(){return List.copyOf(events);}
 }
 @Bean Account account(){return new Account();}
 @Bean static BeanFactoryPostProcessor definition(){
// 练习区开始
  return factory->factory.getBeanDefinition("account").getPropertyValues().add("label","企业订单");
// 练习区结束
 }
 @Bean static BeanPostProcessor instance(){
// 练习区开始
  return new BeanPostProcessor(){
   public Object postProcessBeforeInitialization(Object bean,String name){if(bean instanceof Account a)a.events.add("初始化前");return bean;}
   public Object postProcessAfterInitialization(Object bean,String name){if(bean instanceof Account a)a.events.add("初始化后");return bean;}
  };
// 练习区结束
 }
 public static void main(String[] args){Account a;try(var c=new AnnotationConfigApplicationContext(Lab.class)){a=c.getBean(Account.class);System.out.println("配置名称："+a.label);}System.out.println(a.events());}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 @Test void 真实容器驱动完整生命周期(){var c=new AnnotationConfigApplicationContext(Lab.class);var a=c.getBean(Lab.Account.class);assertThat(a.label).isEqualTo("企业订单");assertThat(a.events()).containsExactly("构造","属性","初始化前","初始化","初始化后");c.close();assertThat(a.events()).containsExactly("构造","属性","初始化前","初始化","初始化后","销毁");c.close();assertThat(a.events().stream().filter("销毁"::equals).count()).isEqualTo(1);}
 @Test void 每个上下文状态独立(){try(var a=new AnnotationConfigApplicationContext(Lab.class);var b=new AnnotationConfigApplicationContext(Lab.class)){assertThat(a.getBean(Lab.Account.class)).isNotSameAs(b.getBean(Lab.Account.class));}}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(args);}}''',mutations=[['a.events.add("初始化前");','a.events.add("错误时序");']])

task('10-circular-boundary','10 循环依赖的真实支持边界','02-source','C05-03',
'两个服务互相依赖导致启动失败。先用真实BeanFactory复现，再区分属性循环的早期引用与构造循环；不把放开配置当万能修复。',
'1. 构造两个RootBeanDefinition，以property reference连接\n2. 按参数显式设置allowCircularReferences\n3. 检查允许/拒绝两种模式\n4. 再运行构造注入循环，即使允许早期引用也失败\n5. 提出拆职责/第三方协调者的重构方案',
'属性循环允许模式可构造并共享同一实例；拒绝模式必须失败。构造循环没有已实例化的对象可暴露，仍失败。这里直接调用BeanFactory，不把其默认值等同Boot应用默认策略。',
'[AbstractAutowireCapableBeanFactory.doCreateBean](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java)：earlySingletonExposure、addSingletonFactory、getEarlyBeanReference；[DefaultSingletonBeanRegistry](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-beans/src/main/java/org/springframework/beans/factory/support/DefaultSingletonBeanRegistry.java)。',
'早期引用依赖对象已经实例化，构造阶段互相等待时没有这个条件。真实代理还可能改变早期引用的对象，因此不能背成“三级缓存解决所有循环”。本节不修改生产默认设置。',
'- 构造循环为何不同于setter循环？对象可暴露的时机不同\n- 代理介入为什么更复杂？早期和最终引用的一致性要维护\n- 为什么不建议靠开关修复架构？依赖方向与职责问题仍在\n- @Lazy是什么取舍？延迟某次解析，不是删除真实依赖',
'''package labs.frameworks;
import org.springframework.beans.factory.support.*;
public class Lab {
 public static class A {B b;public void setB(B b){this.b=b;}}
 public static class B {A a;public void setA(A a){this.a=a;}}
 public static class ConstructorA {public ConstructorA(ConstructorB b){}}
 public static class ConstructorB {public ConstructorB(ConstructorA a){}}
 public static DefaultListableBeanFactory factory(boolean allow){
// 练习区开始
  var f=new DefaultListableBeanFactory();f.setAllowCircularReferences(allow);
  var a=new RootBeanDefinition(A.class);a.getPropertyValues().add("b",new org.springframework.beans.factory.config.RuntimeBeanReference("b"));
  var b=new RootBeanDefinition(B.class);b.getPropertyValues().add("a",new org.springframework.beans.factory.config.RuntimeBeanReference("a"));
  f.registerBeanDefinition("a",a);f.registerBeanDefinition("b",b);return f;
// 练习区结束
 }
 public static void constructorCycle(){var f=new DefaultListableBeanFactory();f.setAllowCircularReferences(true);var a=new RootBeanDefinition(ConstructorA.class);a.setAutowireMode(AbstractBeanDefinition.AUTOWIRE_CONSTRUCTOR);var b=new RootBeanDefinition(ConstructorB.class);b.setAutowireMode(AbstractBeanDefinition.AUTOWIRE_CONSTRUCTOR);f.registerBeanDefinition("a",a);f.registerBeanDefinition("b",b);f.getBean("a");}
 public static void main(String[] args){var f=factory(true);var a=f.getBean(A.class);System.out.println("早期引用保持身份："+(a.b.a==a));f.destroySingletons();}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.BeanCreationException;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 @Test void 允许属性循环时身份一致(){var f=Lab.factory(true);var a=f.getBean(Lab.A.class);assertThat(a.b).isSameAs(f.getBean(Lab.B.class));assertThat(a.b.a).isSameAs(a);f.destroySingletons();}
 @Test void 拒绝循环时真实容器失败(){assertThatThrownBy(()->Lab.factory(false).getBean(Lab.A.class)).isInstanceOf(BeanCreationException.class);}
 @Test void 构造循环仍失败(){assertThatThrownBy(Lab::constructorCycle).isInstanceOf(BeanCreationException.class);}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(args);}}''',mutations=[['f.setAllowCircularReferences(allow);','f.setAllowCircularReferences(true);']])

task('11-aop-proxy','11 真实代理拦截链与自调用','02-source','C05-04',
'支付演示服务通过代理统一验证参数并记录调用。内部this调用绕过代理时，为什么看起来同一个方法行为不同？',
'1. 用ProxyFactory分别创建JDK代理和类代理\n2. 实现拦截器的前置校验、proceed、finally记录\n3. 对比外部charge与内部batch调用\n4. 异常传播不能吞掉，解释拆分服务注入代理的修复方法',
'外部charge金额必须正数；拦截轨迹包括进入/退出，异常也退出。方法返回值和原异常保持。batch内部直接调用charge用于展示自调用绕过，不得把该演示当生产支付代码。',
'[JdkDynamicAopProxy.invoke](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-aop/src/main/java/org/springframework/aop/framework/JdkDynamicAopProxy.java) → [ReflectiveMethodInvocation.proceed](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-aop/src/main/java/org/springframework/aop/framework/ReflectiveMethodInvocation.java)。类代理对照CglibAopProxy。',
'代理包装的是外部调用入口，target对象内部的this仍是target。拦截器必须调用proceed才能继续到目标，finally让失败也能记录退出。校验时机、异常与返回值都是合同，不只检查是否打印日志。',
'- JDK代理与类代理有什么边界？接口与可覆盖方法的限制不同\n- 为什么self-invocation不重新过代理？接收者是target本身\n- final方法可被类代理覆盖吗？不能按普通可覆盖方法处理\n- AOP为什么不能代替领域校验？调用入口可能绕过代理，关键规则要在合适层保护',
'''package labs.frameworks;
import java.util.*;
import org.springframework.aop.framework.ProxyFactory;
import org.aopalliance.intercept.MethodInterceptor;
public class Lab {
 public interface Payments {int charge(int amount);int batch(int amount);}
 public static class PaymentService implements Payments {public int charge(int amount){if(amount==13)throw new IllegalStateException("模拟支付失败");return amount;}public int batch(int amount){return charge(amount);}}
 public static Payments proxy(boolean classProxy,List<String> events){
// 练习区开始
  ProxyFactory factory=new ProxyFactory(new PaymentService());factory.setProxyTargetClass(classProxy);
  factory.addAdvice((MethodInterceptor)invocation->{
   if(invocation.getMethod().getName().equals("charge") && (int)invocation.getArguments()[0]<1)throw new IllegalArgumentException("金额必须为正");
   events.add("进入:"+invocation.getMethod().getName());
   try{return invocation.proceed();}finally{events.add("退出:"+invocation.getMethod().getName());}
  });return (Payments)factory.getProxy();
// 练习区结束
 }
 public static void main(String[] args){var events=new ArrayList<String>();System.out.println("代理结果："+proxy(false,events).charge(5));System.out.println(events);}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.aop.support.AopUtils;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 @Test void 两类真实代理都校验并透传(){for(boolean mode:List.of(false,true)){var events=new ArrayList<String>();var p=Lab.proxy(mode,events);assertThat(AopUtils.isAopProxy(p)).isTrue();assertThat(p.charge(5)).isEqualTo(5);assertThat(events).containsExactly("进入:charge","退出:charge");assertThatThrownBy(()->p.charge(0)).isInstanceOf(IllegalArgumentException.class);}}
 @Test void 原异常不吞且退出仍记录(){var events=new ArrayList<String>();var p=Lab.proxy(false,events);assertThatThrownBy(()->p.charge(13)).isInstanceOf(IllegalStateException.class).hasMessage("模拟支付失败");assertThat(events).containsExactly("进入:charge","退出:charge");}
 @Test void 自调用明确绕过内部方法拦截(){var events=new ArrayList<String>();assertThat(Lab.proxy(false,events).batch(-5)).isEqualTo(-5);assertThat(events).containsExactly("进入:batch","退出:batch");}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(args);}}''',mutations=[['(int)invocation.getArguments()[0]<1','(int)invocation.getArguments()[0]<0']])

task('12-transaction-source','12 事务代理传播与自调用失效','02-source','C05-05',
'订单服务调用审计服务；内部失败即使被catch，也可能把共享事务标记为rollback-only。另一个独立事务可能在外层回滚后保留。',
'1. 实现Inner.required/independent和Outer.catchInner/failAfterAudit上的传播注解\n2. 用真实DataSourceTransactionManager验证REQUIRED与REQUIRES_NEW\n3. 对比withoutProxy内部自调用，定位为何没有事务\n4. 在TransactionInterceptor和事务管理器打断点记录逻辑/物理事务',
'REQUIRED内部失败后外层catch仍在提交时UnexpectedRollback；REQUIRES_NEW审计在外层失败后保留；未过代理的自调用明确不启事务，本节用其作错误反例。所有SQL操作真实执行。',
'[TransactionInterceptor.invoke](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionInterceptor.java) → [TransactionAspectSupport.invokeWithinTransaction](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionAspectSupport.java) → AbstractPlatformTransactionManager提交/回滚。',
'逻辑事务边界可以共享一个物理事务。REQUIRED的失败把共享事务标为仅回滚，外层捕获异常不会自动清除。REQUIRES_NEW暂停外层并独立提交，需要额外连接容量。自调用绕过代理，注解本身不会执行代码。',
'- UnexpectedRollback为什么晚于原异常？真正提交发生在外层边界\n- REQUIRES_NEW为何可能耗尽连接池？外层连接可能仍占用，同时申请新连接\n- checked异常默认如何回滚？默认规则与显式rollbackFor要分开验证\n- 异步线程会继承当前线程事务吗？不能假定自动传播',
'''package labs.frameworks;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.*;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.*;
import org.springframework.transaction.annotation.*;
import javax.sql.DataSource;
@Configuration @EnableTransactionManagement
public class Lab {
 @Bean DataSource ds(){return new EmbeddedDatabaseBuilder().generateUniqueName(true).setType(EmbeddedDatabaseType.H2).addScript("schema.sql").build();}
 @Bean JdbcTemplate jdbc(DataSource ds){return new JdbcTemplate(ds);}
 @Bean PlatformTransactionManager transactionManager(DataSource ds){return new DataSourceTransactionManager(ds);}
 @Bean Inner inner(JdbcTemplate jdbc){return new Inner(jdbc);}
 @Bean Outer outer(JdbcTemplate jdbc,Inner inner){return new Outer(jdbc,inner);}
 public static class Inner {
  final JdbcTemplate jdbc;public Inner(JdbcTemplate j){jdbc=j;}
// 练习区开始
  @Transactional(propagation=Propagation.REQUIRED)
// 练习区结束
  public void required(){jdbc.update("insert into events(label) values('内部失败')");throw new IllegalStateException("内部失败");}
// 练习区开始
  @Transactional(propagation=Propagation.REQUIRES_NEW)
// 练习区结束
  public void independent(){jdbc.update("insert into events(label) values('独立审计')");}
 }
 public static class Outer {
  final JdbcTemplate jdbc;final Inner inner;public Outer(JdbcTemplate j,Inner i){jdbc=j;inner=i;}
// 练习区开始
  @Transactional
// 练习区结束
  public void catchInner(){jdbc.update("insert into events(label) values('外部')");try{inner.required();}catch(IllegalStateException ignored){/* 保留错误场景：捕获异常并不会清除共享事务的仅回滚标记。 */}}
// 练习区开始
  @Transactional
// 练习区结束
  public void failAfterAudit(){jdbc.update("insert into events(label) values('外部')");inner.independent();throw new IllegalStateException("外部失败");}
  public static class CheckedFailure extends Exception {}
  @Transactional public void checkedDefault()throws CheckedFailure{jdbc.update("insert into events(label) values('受检异常默认提交')");throw new CheckedFailure();}
  @Transactional(rollbackFor=CheckedFailure.class) public void checkedRollback()throws CheckedFailure{jdbc.update("insert into events(label) values('受检异常显式回滚')");throw new CheckedFailure();}
  @Transactional public boolean childThreadHasTransaction()throws Exception{try(var worker=java.util.concurrent.Executors.newSingleThreadExecutor()){return worker.submit((java.util.concurrent.Callable<Boolean>)org.springframework.transaction.support.TransactionSynchronizationManager::isActualTransactionActive).get();}}
  public void withoutProxy(){ownFailure();}
  @Transactional public void ownFailure(){jdbc.update("insert into events(label) values('自调用写入')");throw new IllegalStateException("自调用失败");}
 }
 public static void main(String[] args){try(var c=new AnnotationConfigApplicationContext(Lab.class)){try{c.getBean(Outer.class).failAfterAudit();}catch(IllegalStateException ignored){}System.out.println("外层回滚后保留："+c.getBean(JdbcTemplate.class).queryForList("select label from events",String.class));}}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 AnnotationConfigApplicationContext c;JdbcTemplate jdbc;Lab.Outer outer;
 @BeforeEach void 准备(){c=new AnnotationConfigApplicationContext(Lab.class);jdbc=c.getBean(JdbcTemplate.class);outer=c.getBean(Lab.Outer.class);}
 @AfterEach void 清理(){c.close();}
 @Test void 捕获内部异常仍不可提交共享事务(){assertThatThrownBy(outer::catchInner).isInstanceOf(UnexpectedRollbackException.class);assertThat(jdbc.queryForObject("select count(*) from events",Integer.class)).isZero();}
 @Test void 独立事务保留而外层回滚(){assertThatThrownBy(outer::failAfterAudit).isInstanceOf(IllegalStateException.class);assertThat(jdbc.queryForList("select label from events",String.class)).containsExactly("独立审计");}
 @Test void 直接过代理回滚(){assertThatThrownBy(outer::ownFailure).isInstanceOf(IllegalStateException.class);assertThat(jdbc.queryForObject("select count(*) from events",Integer.class)).isZero();}
 @Test void 受检异常规则必须明确(){assertThatThrownBy(outer::checkedDefault).isInstanceOf(Lab.Outer.CheckedFailure.class);assertThat(jdbc.queryForObject("select count(*) from events",Integer.class)).isEqualTo(1);assertThatThrownBy(outer::checkedRollback).isInstanceOf(Lab.Outer.CheckedFailure.class);assertThat(jdbc.queryForObject("select count(*) from events",Integer.class)).isEqualTo(1);}
 @Test void 新线程不自动继承事务()throws Exception{assertThat(outer.childThreadHasTransaction()).isFalse();}
 @Test void 自调用反例没有事务(){assertThatThrownBy(outer::withoutProxy).isInstanceOf(IllegalStateException.class);assertThat(jdbc.queryForList("select label from events",String.class)).containsExactly("自调用写入");}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(args);}}''',extra={'resources/schema.sql':'create table events(label varchar(128) not null);'},mutations=[['Propagation.REQUIRES_NEW','Propagation.REQUIRED']])

task('13-mvc-source','13 MVC参数解析拦截与异常处理','02-source','C05-06',
'订单接口从请求头解析教学租户上下文。明确参数解析、拦截器、控制器和异常处理的责任，同时强调真实租户身份必须来源于认证。',
'1. 为Tenant实现HandlerMethodArgumentResolver\n2. 通过WebMvcConfigurer注册解析器和响应轨迹拦截器\n3. 在真实HTTP请求中测试合法/缺失/非法头与路径\n4. 沿DispatcherServlet到参数处理器和异常解析器记录调用顺序',
'X-Lab-Tenant匹配[a-z]{2,12}，缺失/非法400；合法返回租户与订单号；id必须正数。这个头只用于教学解析，生产必须从已认证身份绑定租户，不能信任任意用户头。',
'[RequestMappingHandlerAdapter](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-webmvc/src/main/java/org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerAdapter.java) → [InvocableHandlerMethod.getMethodArgumentValues](https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-web/src/main/java/org/springframework/web/method/support/InvocableHandlerMethod.java)；异常链对照ExceptionHandlerExceptionResolver。',
'参数解析器先用supportsParameter判断是否负责，再解析并校验。拦截器与Servlet过滤器不同；解析失败不会执行控制器业务。异常响应应稳定，不泄漏内部栈。教学头不具有授权意义。',
'- Filter、Interceptor、AOP在哪里起作用？不同层与对象不能混为一谈\n- supportsParameter为何必须精准？抢占不属于自己的参数会破坏其他解析\n- 自定义参数是否自动带来安全身份？不会，信任来源要另验证\n- 参数错误为什么不返回500？它属于明确的客户端输入失败',
'''package labs.frameworks;
import java.util.*;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.core.MethodParameter;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.*;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.servlet.config.annotation.*;
import org.springframework.http.ResponseEntity;
@SpringBootConfiguration @EnableAutoConfiguration(exclude=DataSourceAutoConfiguration.class) @Import({Lab.Api.class,Lab.Errors.class,Lab.Mvc.class})
public class Lab {
 public record Tenant(String id){}
 public static class TenantResolver implements HandlerMethodArgumentResolver {
  public boolean supportsParameter(MethodParameter p){return p.getParameterType()==Tenant.class;}
  public Object resolveArgument(MethodParameter p,ModelAndViewContainer m,NativeWebRequest request,WebDataBinderFactory b){
// 练习区开始
   String tenant=request.getHeader("X-Lab-Tenant");
   if(tenant==null || !tenant.matches("[a-z]{2,12}"))throw new IllegalArgumentException("教学租户头不合法");
   return new Tenant(tenant);
// 练习区结束
  }
 }
 @Configuration public static class Mvc implements WebMvcConfigurer {
  public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers){resolvers.add(new TenantResolver());}
  public void addInterceptors(InterceptorRegistry registry){registry.addInterceptor(new org.springframework.web.servlet.HandlerInterceptor(){public boolean preHandle(jakarta.servlet.http.HttpServletRequest request,jakarta.servlet.http.HttpServletResponse response,Object handler){response.setHeader("X-Lab-Stage","mvc-interceptor");return true;}});}
 }
 @RestController public static class Api {@GetMapping("/orders/{id}") public Map<String,Object> get(@PathVariable long id,Tenant tenant){if(id<1)throw new IllegalArgumentException("订单号必须正数");return Map.of("tenant",tenant.id(),"orderId",id);}}
 @RestControllerAdvice public static class Errors {@ExceptionHandler(IllegalArgumentException.class) ResponseEntity<String> invalid(){return ResponseEntity.badRequest().body("请求参数不合法");}}
 public static void main(String[] args){var app=new SpringApplication(Lab.class);app.setDefaultProperties(java.util.Map.of("server.address","127.0.0.1","server.port","18084"));app.run(args);}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.*;
import static org.assertj.core.api.Assertions.*;
@SpringBootTest(classes=Lab.class,webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class LabTest {
 @Autowired TestRestTemplate http;
 ResponseEntity<String> get(String tenant,String path){var h=new HttpHeaders();if(tenant!=null)h.set("X-Lab-Tenant",tenant);return http.exchange(path,HttpMethod.GET,new HttpEntity<>(h),String.class);}
 @Test void 真实参数解析和拦截器(){var r=get("acme","/orders/7");assertThat(r.getStatusCode().value()).isEqualTo(200);assertThat(r.getBody()).contains("acme","7");assertThat(r.getHeaders().getFirst("X-Lab-Stage")).isEqualTo("mvc-interceptor");}
 @Test void 缺失和非法头返回400(){for(String tenant:new String[]{null,"A","acme/../../x","toolongtenantname"})assertThat(get(tenant,"/orders/7").getStatusCode().value()).isEqualTo(400);}
 @Test void 业务和转换错误同样拒绝(){assertThat(get("acme","/orders/0").getStatusCode().value()).isEqualTo(400);assertThat(get("acme","/orders/not-number").getStatusCode().value()).isEqualTo(400);}
}''',
'''package labs.frameworks;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.ServletWebRequest;
public class Usage {public static void main(String[] args){var request=new MockHttpServletRequest();request.addHeader("X-Lab-Tenant","acme");Object tenant=new Lab.TenantResolver().resolveArgument(null,null,new ServletWebRequest(request),null);System.out.println("解析结果："+tenant);}}''',mutations=[['"[a-z]{2,12}"','"[a-zA-Z]{1,30}"']])
# 调用方不依赖测试库：通过真实Spring上下文和标准HTTP执行。
write(TASKS[-1]['path']+'/src/labs/frameworks/Usage.java','''package labs.frameworks;
import java.net.*;import java.net.http.*;import java.util.Map;
import org.springframework.boot.SpringApplication;import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
public class Usage {public static void main(String[] args)throws Exception {var app=new SpringApplication(Lab.class);app.setDefaultProperties(Map.of("server.port","0","server.address","127.0.0.1"));try(var c=(ServletWebServerApplicationContext)app.run()){var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+c.getWebServer().getPort()+"/orders/7")).header("X-Lab-Tenant","acme").build();var r=HttpClient.newHttpClient().send(request,HttpResponse.BodyHandlers.ofString());if(r.statusCode()!=200)throw new AssertionError("调用失败");System.out.println(r.body());}}}
''')

task('14-autoconfiguration','14 自动配置条件退让与轻量Starter','02-source','C05-07',
'提供一个问候客户端的轻量starter：依赖存在且功能启用时自动装配；用户自己提供Bean时退让，不抢业务配置。',
'1. 阅读真实AutoConfiguration.imports文件\n2. 补上条件注解并实现从配置读取prefix\n3. 检查默认启用、关闭、用户覆盖和缺依赖四种上下文\n4. 读取ConditionEvaluationReport定位为什么某配置生效/未生效',
'默认prefix为你好，greeting.prefix可覆盖；greeting.enabled=false不装配；缺Transport类型不装配；用户自定义Greeting优先。条件不是运行时每次请求重新判断。',
'[AutoConfigurationImportSelector](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.java)读取候选；[OnBeanCondition](https://github.com/spring-projects/spring-boot/blob/v3.5.16/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/condition/OnBeanCondition.java)决定缺Bean条件。',
'候选导入、类路径条件、属性条件和缺Bean条件是不同阶段的筛选。@ConditionalOnMissingBean实现用户配置优先，不能靠Bean名字偶然覆盖。用ApplicationContextRunner隔离每种条件，用条件报告支持解释。',
'- 自动配置为何不是组件扫描同义词？候选元数据和条件机制不同\n- 为什么用户Bean应优先？starter提供默认能力而不是强制实现\n- 修改环境变量会立即重算条件吗？普通上下文不会自动刷新\n- 怎样写可维护starter？小接口、清晰条件、完整组合测试、版本兼容声明',
'''package labs.frameworks;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.*;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.*;
import org.springframework.context.annotation.*;
import org.springframework.core.env.Environment;
@SpringBootConfiguration @EnableAutoConfiguration(exclude=DataSourceAutoConfiguration.class)
public class Lab {
 public interface Greeting {String greet(String name);}
 @AutoConfiguration
// 练习区开始
 @ConditionalOnClass(name="labs.frameworks.Transport")
 @ConditionalOnProperty(prefix="greeting",name="enabled",havingValue="true",matchIfMissing=true)
// 练习区结束
 public static class GreetingAutoConfiguration {
  @Bean
// 练习区开始
  @ConditionalOnMissingBean(Greeting.class)
// 练习区结束
  Greeting greeting(Environment environment){
// 练习区开始
   String prefix=environment.getProperty("greeting.prefix","你好");return name->prefix+"，"+name;
// 练习区结束
  }
 }
 public static void main(String[] args){var app=new SpringApplication(Lab.class);app.setWebApplicationType(WebApplicationType.NONE);try(var c=app.run(args)){System.out.println(c.getBean(Greeting.class).greet("学习者"));}}
}''',
'''package labs.frameworks;
import org.junit.jupiter.api.*;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.context.annotation.*;
import static org.assertj.core.api.Assertions.*;
class LabTest {
 final ApplicationContextRunner runner=new ApplicationContextRunner().withConfiguration(AutoConfigurations.of(Lab.GreetingAutoConfiguration.class));
 @Configuration static class UserConfig {@Bean Lab.Greeting custom(){return name->"用户实现:"+name;}}
 @Test void 默认启用且配置可覆盖(){runner.run(c->{assertThat(c).hasSingleBean(Lab.Greeting.class);assertThat(c.getBean(Lab.Greeting.class).greet("甲")).isEqualTo("你好，甲");assertThat(ConditionEvaluationReport.get(c.getBeanFactory()).getConditionAndOutcomesBySource()).isNotEmpty();});runner.withPropertyValues("greeting.prefix=欢迎").run(c->assertThat(c.getBean(Lab.Greeting.class).greet("甲")).isEqualTo("欢迎，甲"));}
 @Test void 关闭时不装配(){runner.withPropertyValues("greeting.enabled=false").run(c->assertThat(c).doesNotHaveBean(Lab.Greeting.class));}
 @Test void 用户Bean优先(){runner.withUserConfiguration(UserConfig.class).run(c->{assertThat(c).hasSingleBean(Lab.Greeting.class);assertThat(c.getBean(Lab.Greeting.class).greet("甲")).isEqualTo("用户实现:甲");});}
 @Test void 缺依赖时退让(){runner.withClassLoader(new FilteredClassLoader(Transport.class)).run(c->assertThat(c).doesNotHaveBean(Lab.Greeting.class));}
}''',
'''package labs.frameworks;
public class Usage {public static void main(String[] args){Lab.main(new String[]{"--greeting.prefix=欢迎"});}}''',extra={'src/labs/frameworks/Transport.java':'''package labs.frameworks;
/** 教学依赖标记：用于验证类路径条件，不执行网络访问。 */
public interface Transport {}''','resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports':'labs.frameworks.Lab$GreetingAutoConfiguration'},mutations=[['@ConditionalOnMissingBean(Greeting.class)',''],['matchIfMissing=true','matchIfMissing=false']])
write('framework-course/01-boot/05-security/src/labs/frameworks/Usage.java','''package labs.frameworks;
import java.net.*;import java.net.http.*;import java.util.Map;
import org.springframework.boot.SpringApplication;import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
public class Usage {public static void main(String[] args)throws Exception {var app=new SpringApplication(Lab.class);app.setDefaultProperties(Map.of("server.port","0","server.address","127.0.0.1"));try(var c=(ServletWebServerApplicationContext)app.run()){var client=HttpClient.newHttpClient();String base="http://127.0.0.1:"+c.getWebServer().getPort();int publicCode=client.send(HttpRequest.newBuilder(URI.create(base+"/public/ping")).build(),HttpResponse.BodyHandlers.discarding()).statusCode();int protectedCode=client.send(HttpRequest.newBuilder(URI.create(base+"/orders")).build(),HttpResponse.BodyHandlers.discarding()).statusCode();if(publicCode!=200 || protectedCode!=401)throw new AssertionError("真实HTTP安全合同不满足");System.out.println("公开接口200，受保护接口匿名401；角色/CSRF完整测试见公开测试文件");}}}
''')
DIAGRAMS={'01-configuration': '[默认值] -> [配置文件/活动配置] -> [命令行覆盖]\n                                      |\n                                      v\n                              [绑定] -> [启动校验] -> [业务数量校验]', '02-http-contract': '[中文页面/调用方] -> [JSON解析与校验] -> [请求编号查重]\n                                              |\n                          +-------------------+------------------+\n                          |                   |                  |\n                       [新建201]          [同内容200]        [冲突409]', '03-transactions': '[事务开始] -> [查重] -> [条件扣库存] -> [插入订单] -> [提交]\n                             |              |\n                             +-- 任一步失败 -+\n                                      |\n                                      v\n                              [库存与订单同时回滚]', '04-test-layers': '[单元]     纯对象 + 价格替身     -> 业务边界/调用次数\n[切片]     MockMvc + MVC装配   -> 参数/状态码/异常映射\n[集成]     真端口 + 完整Boot    -> HTTP传输/真实应用装配', '05-security': '[请求] -> [CORS] -> [CSRF] -> [认证] -> [授权] -> [控制器]\n                                |         |\n                             [匿名401] [越权403]\n关键链路示意省略了其他过滤器；实际顺序以固定源码为准。', '06-runtime-lifecycle': '[接单中] -> [有界队列] -> [工作线程]\n    |\n    +-- 停止 --> [拒绝新任务] -> [shutdown] -> [限时等待]\n                                                   |\n                                            [超时则请求中断]', '07-integrated-service': '[预置前端] -> [Controller] -> [事务服务] -> [JdbcTemplate] -> [数据库]\n                                    |                            |\n                               [错误回滚]                    [唯一约束]\n                                    |                            |\n                                    +---------- [稳定HTTP合同] --+', '08-container-di': '[按类型获取] -> [缓存命中?] --是--> [同一实例]\n                    |否\n                    v\n              [构造路径检查] -> [递归解析依赖] -> [创建并缓存]\n                    |\n                 [循环报错]', '09-bean-lifecycle': '[修改Bean定义]\n       |\n       v\n[构造] -> [属性注入] -> [初始化前处理] -> [初始化] -> [初始化后处理]\n                                                              |\n                                                        [关闭时销毁]', '10-circular-boundary': '属性循环：  [已构造A] --设置B--> [已构造B]\n                ^                 |\n                +---- 设置A ------+\n\n构造循环：  [创建A需要B] -> [创建B需要A] -> [A尚未构造，失败]', '11-aop-proxy': '外部调用： [客户端] -> [代理] -> [拦截器] -> [目标charge]\n自调用：   [客户端] -> [代理] -> [目标batch] -> [this.charge]\n                                                 |\n                                          [不重新经过代理]', '12-transaction-source': '[外层REQUIRED] -> [内层REQUIRED] -> [共享物理事务]\n                         |失败\n                         v\n                   [rollback-only] -> [外层提交时报错]\n\n[外层事务] --暂停--> [REQUIRES_NEW独立事务] --完成--> [恢复外层]', '13-mvc-source': '[Servlet过滤器] -> [DispatcherServlet] -> [拦截器前置]\n                                              |\n                                              v\n[返回值处理] <- [控制器方法] <- [参数解析与校验]\n                                   |失败\n                                   v\n                           [异常解析器与错误响应]', '14-autoconfiguration': '[imports候选] -> [类路径条件] -> [属性条件] -> [缺Bean条件]\n                                                       |\n                                     +-----------------+-------------+\n                                     |                               |\n                                [创建默认Bean]               [保留用户自定义Bean]'}
finish()
