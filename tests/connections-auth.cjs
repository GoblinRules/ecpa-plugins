// Isolated browser profiles and fake management responses; no user storage/core.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const KEY='ecpa-suite.management-key.v1';
const SESSION='ecpa-connections.management-key.session.v1';
const editorState={connections:[],projects:[],platformSupported:true,helper:{available:false}};
const gatewayState={services:[],clients:[],backups:[],inventory:[],runtime:{host_id:'fixture',client_paths:{},bws_executable:'fixture',helper_executable:'fixture'}};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const entry of ['editor','gateway']){
   const context=await browser.newContext(),page=await context.newPage();const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   let deny=false,networkFailure=false,requests=0;
   await page.route('**/*',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('.html'))return route.fulfill({contentType:'text/html',body:fs.readFileSync('plugins/connections-manager/web/'+path.split('/').pop(),'utf8')});
    requests++;
    if(networkFailure)return route.abort();
    const auth=route.request().headers().authorization;
    if(deny||auth!=='Bearer fixture-key')return route.fulfill({status:401,contentType:'application/json',body:'{"error":"Unauthorized"}'});
    return route.fulfill({contentType:'application/json',body:JSON.stringify(path.endsWith('/gateway')?gatewayState:editorState)});
   });
   const url='http://fixture.test/'+entry+'.html';
   await page.goto(url);assert.equal(requests,0);
   await page.locator('#key').fill('fixture-key');await page.locator('#remember').check();await page.locator('#login button').click();
   await page.locator('#app').waitFor({state:'visible'});
   assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),'fixture-key');
   await page.reload();await page.locator('#app').waitFor({state:'visible'});
   // The other page reuses the opt-in shared key, even after an iframe remount.
   await page.goto('http://fixture.test/'+(entry==='editor'?'gateway':'editor')+'.html');
   await page.locator('#app').waitFor({state:'visible'});
   await page.locator('#lock').click();
   assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),null);
   assert.equal(await page.evaluate(key=>sessionStorage.getItem(key),SESSION),null);
   await page.goto(url);await page.locator('#login').waitFor({state:'visible'});
   // Unchecked login persists only for the tab, not a later browser profile.
   await page.locator('#key').fill('fixture-key');await page.locator('#login button').click();
   await page.locator('#app').waitFor({state:'visible'});
   assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),null);
   await page.reload();await page.locator('#app').waitFor({state:'visible'});
   // Network failures preserve remembered credentials; rejected credentials do not.
   await page.evaluate(key=>localStorage.setItem(key,'fixture-key'),KEY);
   networkFailure=true;await page.reload();await page.locator('#notice.error').waitFor();
   assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),'fixture-key');
   networkFailure=false;deny=true;await page.reload();await page.locator('#notice.error').waitFor();
   assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),null);
   assert.equal(await page.evaluate(key=>sessionStorage.getItem(key),SESSION),null);
   assert(await page.locator('#login').isVisible());
   assert.deepEqual(errors,[]);
   // Storage-disabled browser remains usable with a manually entered key.
   deny=false;await context.addInitScript(()=>{Storage.prototype.getItem=()=>{throw Error('blocked')};Storage.prototype.setItem=()=>{throw Error('blocked')};Storage.prototype.removeItem=()=>{throw Error('blocked')};});
   await page.reload();await page.locator('#key').fill('fixture-key');await page.locator('#remember').check();await page.locator('#login button').click();
   await page.locator('#app').waitFor({state:'visible'});
   assert((await page.locator('#notice').textContent()).includes('storage'));
   await page.locator('#lock').click();assert(await page.locator('#login').isVisible());
   assert.deepEqual(errors,[]);await context.close();
  }
  console.log('PASS both Connections pages: opt-in memory, cross-page reuse, tab sessions, lock/forget, rejected keys, network failures and blocked storage');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
