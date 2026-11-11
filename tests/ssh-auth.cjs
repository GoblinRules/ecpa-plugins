// Synthetic management server and isolated browser storage; no live SSH or user data.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const KEY='ecpa-suite.management-key.v1';
const SESSION='ecpa-ssh-machines.management-key.session.v1';
const state={machines:[],executionHost:'fixture-host',sshAvailable:true,version:'fixture-version'};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext(),page=await context.newPage(),errors=[],requests=[];
  let deny=0,networkFailure=false;
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async route=>{
   const req=route.request(),path=new URL(req.url()).pathname;
   if(path==='/editor')return route.fulfill({contentType:'text/html',body:fs.readFileSync('plugins/ssh-machines/web/editor.html','utf8')});
   requests.push({method:req.method(),path});
   if(networkFailure)return route.abort();
   if(deny)return route.fulfill({status:deny,contentType:'text/plain',body:'Denied'});
   assert.equal(req.headers().authorization,'Bearer fixture-key');
   return route.fulfill({contentType:'application/json',body:JSON.stringify(state)});
  });
  await page.goto('http://fixture.test/editor');
  assert.equal(requests.length,0);
  assert.equal(await page.locator('h1').textContent(),'SSH and Machines');
  // A key remembered by another suite page unlocks without any SSH action.
  await page.evaluate(key=>localStorage.setItem(key,'fixture-key'),KEY);
  await page.reload();await page.locator('#app').waitFor({state:'visible'});
  assert(await page.locator('#remember').isChecked());
  await page.locator('#lock').click();
  assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),null);
  // Explicit opt-in survives opening a fresh tab.
  await page.locator('#key').fill('fixture-key');await page.locator('#remember').check();await page.locator('#login button').click();
  await page.locator('#app').waitFor({state:'visible'});
  assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),'fixture-key');
  assert.equal(await page.evaluate(key=>sessionStorage.getItem(key),SESSION),'fixture-key');
  const other=await context.newPage();
  await other.goto('http://fixture.test/editor');await other.locator('#app').waitFor({state:'visible'});
  await other.close();
  await page.reload();await page.locator('#app').waitFor({state:'visible'});
  await page.locator('#recovery').click();
  await page.locator('#manifest').fill('{"name":"private fixture draft"}');
  await page.locator('#lock').click();
  assert.equal(await page.locator('#manifest').inputValue(),'');
  assert.equal(await page.evaluate(key=>sessionStorage.getItem(key),SESSION),null);
  await page.reload();assert(await page.locator('#login').isVisible());
  // Unchecked login is tab-scoped and still survives iframe reloads.
  await page.locator('#key').fill('fixture-key');await page.locator('#login button').click();
  await page.locator('#app').waitFor({state:'visible'});
  assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),null);
  const fresh=await context.newPage();
  const before=requests.length;
  await fresh.goto('http://fixture.test/editor');assert(await fresh.locator('#login').isVisible());
  assert.equal(requests.length,before);await fresh.close();
  await page.reload();await page.locator('#app').waitFor({state:'visible'});
  await page.evaluate(key=>localStorage.setItem(key,'fixture-key'),KEY);
  networkFailure=true;await page.reload();await page.locator('#status.error').waitFor();
  assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),'fixture-key');
  networkFailure=false;
  for(const code of [401,403]){
   await page.evaluate(key=>localStorage.setItem(key,'fixture-key'),KEY);
   deny=code;await page.reload();await page.locator('#status.error').waitFor();
   assert(await page.locator('#login').isVisible());
   assert.equal(await page.evaluate(key=>localStorage.getItem(key),KEY),null);
   assert.equal(await page.evaluate(key=>sessionStorage.getItem(key),SESSION),null);
  }
  deny=0;
  await context.addInitScript(()=>{for(const method of ['getItem','setItem','removeItem'])Storage.prototype[method]=()=>{throw Error('blocked')};});
  await page.reload();await page.locator('#key').fill('fixture-key');await page.locator('#remember').check();await page.locator('#login button').click();
  await page.locator('#app').waitFor({state:'visible'});
  assert((await page.locator('#status').textContent()).includes('storage'));
  await page.locator('#lock').click();assert(await page.locator('#login').isVisible());
  assert((await page.locator('#status').textContent()).includes('clear site data'));
  assert(requests.length>0);
  assert(requests.every(r=>r.method==='GET'&&r.path==='/v0/management/ssh-machines/state'),'Unlock must never scan, connect or mutate machines');
  assert.deepEqual(errors,[]);
  console.log('PASS SSH login: shared remembered key, opt-in, tab session, lock cleanup, 401/403, network errors, blocked storage; no SSH actions');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
