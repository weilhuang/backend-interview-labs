// 这是作者的浏览器验收工具，学习者不需要修改前端或安装Node。
import { chromium } from '../build/browser/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
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
 await page.locator('#request').fill('browser-'+Date.now());
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
 assert.equal(await page.locator('#deliveries tr').filter({hasText:id}).count(),1);
 assert.equal(errors.length,0,errors.join('\n'));
 await page.screenshot({path:'build/browser-smoke.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'手机布局出现横向溢出');
 await page.screenshot({path:'build/browser-mobile.png',fullPage:true});
 console.log('中文前端：提交、原号重试、冲突、取消、真实事件重放与读模型均通过');
} catch(error) {
 console.error('浏览器失败：',error);
 for(const context of browser.contexts())for(const page of context.pages())await page.screenshot({path:'build/browser-failure.png',fullPage:true,timeout:5000}).catch(()=>{});
 throw error;
} finally {clearTimeout(watchdog);await Promise.race([browser.close(),new Promise(resolve=>setTimeout(resolve,5000))]);}
