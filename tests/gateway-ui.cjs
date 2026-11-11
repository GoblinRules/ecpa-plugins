// Isolated headless UI regression: no live ECPA server or user configuration.
// Install playwright in an external test directory and expose it via NODE_PATH.
const { chromium } = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    const calls=[];
    const state={services:[],version:'fixture',clients:[],backups:[],inventory:[],runtime:{mode:'fixture',host_id:'test-runtime',url:'http://127.0.0.1:8769/mcp',client_paths:{},bws_executable:'fixture',helper_executable:'fixture',workspaces:{}}};
    await page.route('**/*',async route=>{
      if(route.request().method()==='GET')return route.fulfill({contentType:'text/html',body:fs.readFileSync('plugins/connections-manager/web/gateway.html','utf8')});
      const body=route.request().postDataJSON();calls.push(body);
      let result={};
      if(body.action==='state')result=state;
      else if(body.action==='test')result={review:'fixture-review',tools:[],models:[{alias:'ecpa-work--primary'}],message:'Fixture model catalogue verified'};
      else if(body.action==='publish'){const tested=calls.findLast(x=>x.action==='test');state.services=[{...tested.service,enabled:true}];result={saved:tested.service.id};}
      else if(body.action==='requests')result={requests:[{id:'fixture-request',status:'pending',arguments:{prompt:'<script>throw Error("unsafe")</script>'}}]};
      await route.fulfill({contentType:'application/json',body:JSON.stringify(result)});
    });
    await page.goto('http://fixture.test/');
    await page.locator('#key').fill('fixture-only');await page.locator('#login button').click();
    await page.locator('#app').waitFor({state:'visible'});
    await page.locator('#preset').selectOption('cloudflare');await page.locator('#next').click();
    assert(await page.locator('#account-id').isVisible());assert(await page.locator('#wrangler-fields').isVisible());
    await page.locator('#wrangler-enabled').check();assert(await page.locator('#wrangler-node').isVisible());
    await page.locator('#back').click();await page.locator('#preset').selectOption('sample');await page.locator('#next').click();
    assert(!(await page.locator('#account-id').isVisible()));assert(!(await page.locator('#credential').isVisible()));
    await page.locator('#name').fill('Sample');await page.locator('#id').fill('sample');await page.locator('#next').click();
    const sample=JSON.parse(await page.locator('#definition').textContent());assert.equal(sample.service,'sample');assert.deepEqual(sample.credential_refs,[]);
    await page.locator('#new').click();await page.locator('#preset').selectOption('ssh');await page.locator('#next').click();
    assert(await page.locator('#machine-fields').isVisible());assert(!(await page.locator('#binding-fields').isVisible()));
    await page.locator('#new').click();await page.locator('#preset').selectOption('provider');await page.locator('#next').click();
    assert(await page.locator('#provider-fields').isVisible());assert(!(await page.locator('#project-ids').isVisible()));
    await page.locator('#name').fill('Work provider');await page.locator('#id').fill('work');
    await page.locator('#secret-id').fill('00000000-0000-0000-0000-000000000000');await page.locator('#provider-models').fill('primary=fixture-model');
    await page.locator('#next').click();await page.locator('#test').click();await page.locator('#tools').getByText('ecpa-work--primary',{exact:false}).waitFor();
    await page.locator('#read-only').check();await page.locator('#next').click();await page.locator('#publish').click();
    await page.locator('#notice').getByText('Provider published.',{exact:false}).waitFor();
    assert(calls.some(x=>x.action==='publish'&&x.confirm_core_access===true));
    await page.locator('#requests-tab').click();await page.locator('#load-requests').click();await page.locator('#request-list pre').waitFor();
    assert((await page.locator('#request-list pre').textContent()).includes('<script>'));
    await page.locator('#runtime-tab').click();assert(!(await page.locator('#requests').isVisible()));
    for(const width of [480,820,1200]){
      await page.setViewportSize({width,height:900});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`No horizontal overflow at ${width}`);
    }
    assert.deepEqual(errors,[]);
    console.log('PASS gateway preset switching, provider publish, approvals navigation, safe text and embedded widths');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
