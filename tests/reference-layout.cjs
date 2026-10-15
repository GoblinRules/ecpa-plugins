// Run only against the isolated embedded-preview.py host backed by test fixtures.
// PLAYWRIGHT_MODULE points to the locally installed Playwright module.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.goto(process.env.PLUGIN_PREVIEW_URL || 'http://127.0.0.1:58610');
    const screenshots = process.env.PLUGIN_SCREENSHOT_DIR || 'dist/screenshots';
    fs.mkdirSync(screenshots, { recursive: true });
    for (const id of (process.env.PLUGIN_IDS || 'agent-instructions,agent-profiles,mcp-manager,agent-diagnostics,prompt-library,config-snapshots,agent-skills').split(',')) {
      await page.evaluate(id => { document.querySelector('iframe').src = `/v0/resource/plugins/${id}/editor`; }, id);
      const frame = page.frames().find(f => f !== page.mainFrame());
      await frame.waitForURL(`**/${id}/editor`);
      await frame.locator('#key').fill('isolated-plugin-test-key');
      await frame.locator(id === 'agent-instructions' ? '#login-form' : '#login').evaluate(form => form.requestSubmit());
      await frame.locator('#app').waitFor({ state: 'visible' });
      if (id === 'mcp-manager') {
        await frame.locator('#new').click();
        await frame.locator('#name').fill('Example server · fixture');
        await frame.locator('#command').fill('node');
        await frame.locator('#args').fill('["example-server.js"]');
        await frame.evaluate(() => { dirty = false; });
      }
      for (const height of [560, 800]) {
        await page.locator('iframe').evaluate((f, h) => f.style.height = h + 'px', height);
        console.log(id, height, await page.evaluate(fs.readFileSync('tests/embedded-layout-check.js', 'utf8')));
      }
      await page.locator('iframe').evaluate(f => { f.style.width = '1380px'; f.style.height = '900px'; });
      await frame.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0,0); });
      await page.screenshot({ path: path.join(screenshots, `${id}-desktop.png`), fullPage: true });
      await page.locator('iframe').evaluate(f => { f.style.width = '820px'; f.style.height = '560px'; });
      await frame.evaluate(() => window.scrollTo(0,0));
      await page.screenshot({ path: path.join(screenshots, `${id}-embedded.png`), fullPage: true });
      const script = fs.readFileSync(id === 'agent-instructions' ? 'plugins/agent-instructions/tests/browser-check.js' : id === 'mcp-manager' ? 'tests/mcp-browser-check.js' : 'tests/suite-browser-check.js', 'utf8');
      // Inline execution respects the plugin CSP (which intentionally forbids eval).
      await frame.addScriptTag({ content: 'window.__workflow = ' + script });
      console.log(id, await frame.evaluate(() => window.__workflow));
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
