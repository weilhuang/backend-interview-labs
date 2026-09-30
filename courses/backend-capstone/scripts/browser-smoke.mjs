// 这是作者的浏览器验收工具，学习者不需要修改前端或安装Node。
import { chromium } from '../build/browser/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
const layouts=[];
async function checkViewport(page,width,height,label){
 await page.setViewportSize({width,height});
 const layout=await page.evaluate(()=>({
  viewport:window.innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth,
  containers:[...document.querySelectorAll('main,aside,.stack,section,.table,.metric,#notice,#audit,#history')].map(element=>{
   const box=element.getBoundingClientRect();
   return {element:element.id||element.className||element.tagName,left:box.left,right:box.right,width:box.width};
  }),
  tables:[...document.querySelectorAll('.table')].map(element=>({id:element.id,width:element.clientWidth,scrollWidth:element.scrollWidth,overflow:getComputedStyle(element).overflowX}))
 }));
 layouts.push({label,...layout});
 await writeFile('build/browser-layout.json',JSON.stringify(layouts,null,2)+'\n');
 assert.ok(layout.document<=layout.viewport&&layout.body<=layout.viewport,`${label}：页面横向溢出 ${JSON.stringify(layout)}`);
 assert.ok(layout.containers.every(box=>box.left>=0&&box.right<=layout.viewport),`${label}：外层容器超出视口 ${JSON.stringify(layout)}`);
 for(const table of layout.tables){
  assert.ok(['auto','scroll'].includes(table.overflow),`${label}：${table.id} 必须保留局部横向滚动`);
  if(width<=390){
   assert.ok(table.scrollWidth>table.width,`${label}：长请求号表格应在容器内横向滚动`);
   const scrolled=await page.locator('#'+table.id).evaluate(element=>{
    element.scrollLeft=element.scrollWidth;
    const last=element.querySelector('tr').lastElementChild.getBoundingClientRect();
    const edge=element.getBoundingClientRect();
    const result={offset:element.scrollLeft,lastColumnVisible:last.left>=edge.left&&last.right<=edge.right+1};
    element.scrollLeft=0;
    return result;
   });
   assert.ok(scrolled.offset>0&&scrolled.lastColumnVisible,`${label}：${table.id} 最后一列必须能滚动看到`);
  }
 }
 await page.screenshot({path:`build/browser-${label}.png`,fullPage:true});
}
console.log('阶段：启动有沙箱的Chrome');
const watchdog=setTimeout(()=>{console.error('浏览器验收超过180秒总预算');process.exit(2);},180000);
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',chromiumSandbox:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1080}});
 page.setDefaultTimeout(10000);page.setDefaultNavigationTimeout(15000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 console.log('阶段：打开真实中文页面');
 await page.goto('http://127.0.0.1:'+(process.env.CAPSTONE_HTTP_PORT||'8088'));
 await page.getByText('MySQL：可用',{exact:true}).waitFor();
 // 合同允许64字符身份；同时验证长身份在真实记录、操作提示与历史中的布局。
 const requestId=('browser-'+Date.now()+'-').padEnd(64,'x');
 await page.locator('#request').fill(requestId);
 console.log('阶段：真实API空查询与404');
 await page.getByRole('button',{name:'强一致查询原请求'}).click();
 await page.getByText('依赖或请求错误：订单不存在',{exact:true}).waitFor();
 console.log('阶段：提交或同号重试');
 await page.getByRole('button',{name:'提交 / 原号重试'}).click();
 await page.getByText('提交订单完成',{exact:true}).waitFor();
 console.log('阶段：提交或同号重试');
 await page.getByRole('button',{name:'提交 / 原号重试'}).click();
 await page.getByText('提交订单完成',{exact:true}).waitFor();
 await page.locator('#quantity').fill('3');
 console.log('阶段：提交或同号重试');
 await page.getByRole('button',{name:'提交 / 原号重试'}).click();
 await page.getByText('业务冲突：同一请求号不能换商品或数量',{exact:true}).waitFor();
 const id=await page.locator('#request').inputValue();
 await page.locator('tr').filter({hasText:id}).getByRole('button',{name:'取消',exact:true}).click();
 await page.getByText('取消 '+id+'完成',{exact:true}).waitFor();
 console.log('阶段：等待真实Kafka与RPC重放，最多40秒');
 await page.getByRole('button',{name:'发布待发事件并消费重放'}).click();
 await page.getByText('事件重放完成',{exact:true}).waitFor({timeout:40000});
 // 完成提示先于dashboard刷新；等真实投影渲染，避免把旧DOM当成本次重放结果。
 await page.locator('#deliveries tr').filter({hasText:id}).filter({hasText:'CANCELLED / 2'}).waitFor();
 assert.equal(await page.locator('#deliveries tr').filter({hasText:id}).count(),1);
 assert.equal(await page.locator('#orders tr').filter({hasText:id}).getByRole('button',{name:'已取消',exact:true}).isDisabled(),true);
 assert.match(await page.locator('#deliveries tr').filter({hasText:id}).innerText(),/CANCELLED \/ 2/);
 await page.screenshot({path:'build/browser-smoke.png',fullPage:true});
 console.log('阶段：真实长请求号记录的多视口布局与表格局部滚动');
 for(const width of [320,390,800,801,1440])await checkViewport(page,width,844,'layout-'+width);
 assert.equal(errors.length,0,errors.join('\n'));
 console.log('中文前端：提交、原号重试、冲突、取消、真实事件重放、读模型与多视口布局均通过');
} catch(error) {
 console.error('浏览器失败：',error);
 for(const context of browser.contexts())for(const page of context.pages())await page.screenshot({path:'build/browser-failure.png',fullPage:true,timeout:5000}).catch(()=>{});
 throw error;
} finally {clearTimeout(watchdog);await Promise.race([browser.close(),new Promise(resolve=>setTimeout(resolve,5000))]);}
