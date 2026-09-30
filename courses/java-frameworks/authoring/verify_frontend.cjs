/* 使用云端已安装的Chromium验证预置界面，不下载或安装浏览器。 */
const {chromium}=require('playwright');
const fs=require('fs');
const assert=require('assert/strict');
let activeBrowser, activePage, phase='启动浏览器';
function mark(name){phase=name;console.log('[界面验收] '+name);}
function bounded(promise,label,ms=12000){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(label+' 等待超时')),ms);})]).finally(()=>clearTimeout(timer));}
const watchdog=setTimeout(()=>{console.error('界面验收总预算耗尽，阶段='+phase);process.exit(1);},120000);
fs.mkdirSync('build/ui',{recursive:true});
(async()=>{
 mark("启动runner现有浏览器");
 const browser=activeBrowser=await chromium.launch({executablePath:process.env.LAB_CHROMIUM || '/usr/bin/chromium',headless:true,chromiumSandbox:true});
 const page=activePage=await browser.newPage({viewport:{width:1100,height:850}});
 page.setDefaultTimeout(10000);page.setDefaultNavigationTimeout(15000);
 mark('加载中文首页与空态');
 const results=[]; const errors=[];page.on('pageerror',e=>errors.push(e.message));
 async function status(text){await page.getByRole('status').filter({hasText:text}).waitFor({timeout:10000});}
 async function submit(){await page.locator('#submit').click();}
 await page.goto('http://127.0.0.1:18084');
 await page.getByRole('heading',{name:'订单实验室',exact:true}).waitFor();
 await page.locator('#orders').filter({hasText:'暂无订单'}).waitFor();results.push('中文页面和空态');
 mark('创建、幂等重试、冲突与输入边界');
 await page.locator('#requestId').fill('ui-normal');await page.locator('#sku').fill('UI-BOOK');
 await submit();await status('HTTP 201');const created=JSON.parse(await page.locator('#response').innerText());assert.equal(created.totalFen,300);results.push('真实后端创建');
 await submit();await status('HTTP 200');assert.equal(JSON.parse(await page.locator('#response').innerText()).id,created.id);results.push('同键重试同一订单');
 await page.locator('#sku').fill('UI-CONFLICT');await submit();await status('HTTP 409');results.push('冲突有明确提示');
 await page.locator('#newKey').click();assert.notEqual(await page.locator('#requestId').inputValue(),'ui-normal');
 await page.locator('#quantity').fill('0');assert.equal(await page.locator('#quantity').evaluate(e=>e.checkValidity()),false);await page.locator('#quantity').fill('2');results.push('表单边界阻止非法输入');
 mark('拦截在途提交并检查按钮');
 let release,routeReady;const gate=new Promise(r=>release=r),intercepted=new Promise(r=>routeReady=r);
 await page.route('**/api/orders',async route=>{if(route.request().method()==='POST'){routeReady();await gate;}await route.continue();});
 await submit();await page.waitForFunction(()=>document.getElementById('submit').disabled);await bounded(intercepted,'POST被路由捕获');release();await status('HTTP 201');await page.unrouteAll({behavior:'wait'});results.push('在途禁用与完成恢复');
 mark('网络失败后恢复操作');
 await page.locator('#newKey').click();await page.route('**/api/orders',async route=>{if(route.request().method()==='POST')await route.abort('failed');else await route.continue();});
 await submit();await status('网络请求失败');assert.equal(await page.locator('#submit').isEnabled(),true);await page.unrouteAll({behavior:'wait'});results.push('网络失败恢复操作');
 mark('有界请求超时');
 await page.route('**/api/orders',async route=>{if(route.request().method()==='POST'){await new Promise(r=>setTimeout(r,5500));try{await route.abort();}catch{}}else await route.continue();});
 await submit();await status('请求超时');assert.equal(await page.locator('#submit').isEnabled(),true);await page.unrouteAll({behavior:'wait'});results.push('五秒超时与结果未知提示');
 mark('旧刷新响应不能覆盖新结果');
 let oldRelease,oldReady,oldRequest;const oldGate=new Promise(r=>oldRelease=r),ready=new Promise(r=>oldReady=r);let first=true;
 await page.route('**/api/orders',async route=>{if(route.request().method()==='GET'&&first){first=false;oldRequest=route.request();const response=await route.fetch();oldReady();await oldGate;await route.fulfill({response});}else await route.continue();});
 await page.locator('#refresh').click();await bounded(ready,'旧GET响应被路由捕获');
 const response=await page.request.post('http://127.0.0.1:18084/api/orders',{data:{requestId:'ui-latest',sku:'LATEST',quantity:1,unitPriceFen:'99'}});assert.equal(response.status(),201);
 await page.locator('#refresh').click();await page.locator('#orders').filter({hasText:'ui-latest'}).waitFor();oldRelease();const delivered=await oldRequest.response();await bounded(delivered.finished(),'旧GET完成');await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));await page.unrouteAll({behavior:'wait'});assert.match(await page.locator('#orders').innerText(),/ui-latest/);results.push('旧刷新响应不覆盖新结果');
 mark('移动与桌面排版截图');
 await page.setViewportSize({width:375,height:812});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:'build/ui/mobile.png',fullPage:true});
 await page.setViewportSize({width:1100,height:850});await page.screenshot({path:'build/ui/desktop.png',fullPage:true});results.push('窄屏无横向溢出');
 assert.deepEqual(errors,[]);results.push('浏览器无脚本异常');
 fs.writeFileSync('authoring/ui-verification.json',JSON.stringify({browser:'云端已安装Chromium，Playwright驱动',status:'passed',checks:results,screenshots:['build/ui/mobile.png','build/ui/desktop.png'],backend:'02真实Spring Boot内存订单服务',note:'07同一前端资源；07 HTTP/JDBC另由真实集成测试验证。本记录不等于Academy导入。'},null,2));
 console.log(results);clearTimeout(watchdog);await browser.close();
})().catch(async error=>{clearTimeout(watchdog);console.error('失败阶段='+phase,error);try{if(activePage)await activePage.screenshot({path:'build/ui/failure.png',fullPage:true,timeout:5000});}catch{}try{if(activeBrowser)await bounded(activeBrowser.close(),'关闭测试浏览器',3000);}catch{}process.exit(1)});
