// Evaluate on an isolated integration fixture, with the editor locked.
// Reload/auto-unlock is additionally checked by navigating the browser between calls.
(async () => {
  const slot='agent-instructions.management-key.v1', testKey='isolated-plugin-test-key';
  const info=await (await fetch('/v0/management/agent-instructions/files',{headers:{Authorization:'Bearer '+testKey}})).json();
  if(!info.files.every(f=>f.path.includes('agent-instructions-test-')))throw Error('Fixture only');
  const el=id=>document.getElementById(id), assert=(v,m)=>{if(!v)throw Error(m)};
  const wait=async f=>{for(let i=0;i<100;i++){if(f())return;await new Promise(r=>setTimeout(r,50))}throw Error('Timed out')};
  const login=async remember=>{el('key').value=testKey;el('remember').checked=remember;el('login-form').requestSubmit();await wait(()=>!el('app').hidden&&!el('reload').disabled)};
  const lock=async()=>{el('lock').click();await wait(()=>!el('login').hidden)};
  assert(!el('login').hidden,'Start locked');
  localStorage.removeItem(slot);
  await login(false);assert(localStorage.getItem(slot)===null,'Default login persists nothing');await lock();
  await login(true);assert(localStorage.getItem(slot)===testKey,'Opt-in saves validated key');await lock();
  assert(localStorage.getItem(slot)===null,'Lock forgets key');
  el('key').value='invalid-fixture-key';el('remember').checked=true;el('login-form').requestSubmit();
  await wait(()=>!el('status').hidden&&!el('connect').disabled);
  assert(!el('login').hidden&&localStorage.getItem(slot)===null,'Invalid key not saved');
  const old=Storage.prototype.setItem;
  try {
    Storage.prototype.setItem=function(){throw Error('Storage blocked')};
    await login(true);assert(el('status').textContent.includes('could not be remembered'),'Storage failure explained');
    assert(localStorage.getItem(slot)===null,'Storage failure is session-only');
  } finally {Storage.prototype.setItem=old;await lock()}
  return 'PASS: session-only default, opt-in, forget, invalid key, storage failure';
})()
