// Evaluate only on MCP Manager in tests/suite_integration.py's isolated fixture.
(async () => {
  const check = (ok, text) => { if (!ok) throw Error(text); };
  const wait = async fn => { for (let i=0;i<100;i++) { if(fn())return;await new Promise(r=>setTimeout(r,50)); } throw Error('Timed out: '+$('status').textContent); };
  const input = (id, value) => { $(id).value=value;$(id).dispatchEvent(new Event('input',{bubbles:true})); };
  const click = async id => { $(id).click();await wait(()=>!busy); };
  if ($('app').hidden) { input('key','isolated-plugin-test-key');$('login').requestSubmit();await wait(()=>!busy&&state); }
  check(file().path.includes('ecpa-suite-test-'), 'Use isolated files only');
  await click('new');input('name','browser-managed');input('command','node');input('args','["server with spaces.js"]');
  await click('add-env');const pair=$('env').firstElementChild;pair.children[0].value='TEST_TOKEN';pair.children[1].value='fixture-only';
  check(pair.children[1].type==='password','Environment values masked');
  $('targets').querySelector('input[value="codex-config"]').checked=true;
  await click('preview');check($('preview-dialog').open,'Assignment preview opens');check($('changes').children.length===2,'Both targets previewed');
  check($('changes').textContent.includes('server with spaces.js'),'Arguments preserved');await click('apply');
  check(servers('claude-config')['browser-managed'].env.TEST_TOKEN==='fixture-only','Claude saved');
  check(servers('codex-config')['browser-managed'].type===undefined,'Codex translated without Claude type');
  edit('browser-managed',servers()['browser-managed']);await click('duplicate');input('name','browser-duplicate');await click('preview');await click('apply');
  check(!!servers()['browser-duplicate'],'Duplicate creates a separate server');
  edit('browser-duplicate',servers()['browser-duplicate']);input('name','browser-renamed');await click('json-tab');
  const extra=JSON.parse($('definition').value);extra.customField={nested:'keep'};input('definition',JSON.stringify(extra));
  await click('form-tab');input('command','updated-node');await click('preview');await click('apply');
  check(!servers()['browser-duplicate'],'Rename removes old source name');check(servers()['browser-renamed'].customField.nested==='keep','Unknown fields preserved through form');
  edit('browser-renamed',servers()['browser-renamed']);$('targets').querySelector('input[value="codex-config"]').checked=true;
  await click('preview');check(!$('preview-dialog').open&&$('status').textContent.includes('customField'),'Lossy cross-client copy blocked');
  // Rename collision requires explicit replacement.
  edit('browser-renamed',servers()['browser-renamed']);input('name','browser-managed');await click('preview');
  check(!$('preview-dialog').open&&$('status').textContent.includes('already exists'),'Collision blocked');
  $('replace').checked=true;await click('preview');check($('preview-dialog').open,'Replacement can be reviewed');await click('cancel-preview');
  // Delete only the selected source server; keep its cross-agent copy.
  edit('browser-managed',servers()['browser-managed']);await click('delete');check($('changes').children.length===1,'Deletion targets source only');await click('apply');
  check(!servers()['browser-managed']&&!!servers('codex-config')['browser-managed'],'Deletion preserves other agents');
  // HTTP field translation in the other direction.
  await chooseAgent('codex-config');edit('',{url:'https://example.com/mcp',http_headers:{'X-Fixture':'test'}});input('name','browser-http');
  $('targets').querySelector('input[value="claude-config"]').checked=true;await click('preview');await click('apply');
  check(servers('claude-config')['browser-http'].type==='http','Remote Claude type generated');
  check(servers('claude-config')['browser-http'].headers['X-Fixture']==='test','Remote headers translated');
  const backup=$('backups').value;check(!!backup,'Backups are available');await click('restore');check($('preview-dialog').open,'Restore preview opens');await click('cancel-preview');
  dirty=false;await click('lock');check(!state&&!key&&$('definition').value===''&&!$('env').children.length,'Lock clears sensitive form state');
  return 'PASS MCP: add, masked variables, assign, translate, duplicate, rename, preserve advanced fields, collision, delete, restore preview, lock';
})()
