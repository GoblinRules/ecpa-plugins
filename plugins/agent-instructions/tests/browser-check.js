// Run in the browser on tests/integration.py --serve, after unlocking its editor.
(async () => {
  const el = id => document.getElementById(id);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const until = async fn => { for (let i=0;i<80;i++) { if(fn()) return; await new Promise(r=>setTimeout(r,100)); } throw Error('UI timeout'); };
  check(el('path').textContent.includes('agent-instructions-test-'), 'Only run against the isolated fixture');
  await until(()=>!el('reload').disabled);
  const original = el('content').value;
  const edit = value => { el('content').value=value; el('content').dispatchEvent(new Event('input',{bubbles:true})); };
  edit(original+'\n- Browser save test.');
  check(!el('save').disabled,'Editing enables save');
  document.querySelector('[data-id="codex"]').click();
  await until(()=>el('confirm').open);el('cancel').click();
  check(el('content').value.includes('Browser save test'),'Cancel preserves draft');
  el('save').click();
  await until(()=>el('status').textContent.startsWith('Saved.')&&!el('reload').disabled);
  check(el('save').disabled,'Successful save clears dirty state');
  const headers={Authorization:'Bearer isolated-plugin-test-key','Content-Type':'application/json'};
  const api='/v0/management/agent-instructions';
  let data=await (await fetch(api+'/files',{headers})).json();
  let f=data.files.find(x=>x.id==='claude');
  check(f.content.includes('Browser save test'),'UI save reached the real file');
  await fetch(api+'/file',{method:'PUT',headers,body:JSON.stringify({id:'claude',version:f.version,content:'Changed externally'})});
  edit('Unsaved conflict draft');el('save').click();
  await until(()=>el('status').classList.contains('error')&&!el('reload').disabled);
  check(el('content').value==='Unsaved conflict draft','Conflict retains the draft');
  check(el('status').textContent.includes('changed. Copy your draft, then reload'),'Conflict is explained');
  el('reload').click();await until(()=>el('confirm').open);el('accept').click();
  await until(()=>el('content').value==='Changed externally'&&!el('reload').disabled);
  check(el('backup').options.length>0,'Backups available');
  el('restore').click();await until(()=>el('confirm').open);el('accept').click();
  await until(()=>el('status').textContent.startsWith('Version restored')&&!el('reload').disabled);
  check(el('content').value!=='Changed externally','Restore replaces disk content');
  document.querySelector('[data-id="codex-override"]').click();
  await until(()=>el('file-title').textContent==='Codex override'&&!el('reload').disabled);
  check(el('notice').textContent.includes('instead of'),'Override precedence is explained');
  document.querySelector('[data-id="claude"]').click();
  await until(()=>el('file-title').textContent==='Claude Code'&&!el('reload').disabled);
  edit(original);if(!el('save').disabled){el('save').click();await until(()=>!el('reload').disabled)}
  el('lock').click();await until(()=>!el('login').hidden);
  check(el('content').value===''&&el('key').value==='','Lock clears editor and key input');
  check(localStorage.length===0&&sessionStorage.length===0,'No credentials persisted');
  return 'PASS: edit, save, discard cancellation, conflict draft retention, reload, restore, override, lock';
})()
