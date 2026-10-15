// Evaluate on each suite editor served by tests/suite_integration.py --serve.
// Only use the isolated fixture: these tests intentionally create/modify fixture files.
(async () => {
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  const wait = async (condition) => {
    for (let i = 0; i < 100; i++) { if (condition()) return; await new Promise(r => setTimeout(r, 50)); }
    throw Error('Timed out: ' + document.getElementById('status').textContent);
  };
  const input = (id, value) => { $(id).value = value; $(id).dispatchEvent(new Event('input', { bubbles: true })); };
  const click = async id => { $(id).click(); await wait(() => !busy); };
  input('key', 'isolated-plugin-test-key');
  $('login').requestSubmit();
  await wait(() => !busy && state);
  const mode = state.mode;
  assert(!$('app').hidden, 'Workspace opens');
  assert(document.documentElement.scrollWidth <= innerWidth, 'No horizontal page overflow');
  if (mode === 'diagnostics') {
    assert($('diagnostics').querySelectorAll('tr').length === 11, 'Ten diagnostic file slots');
    assert($('workspace').hidden, 'Diagnostics has no editing controls');
    return 'PASS diagnostics read-only dashboard';
  }
  if (mode === 'prompts') {
    await click('new');
    input('record-id', 'browser-prompt'); input('name', 'Browser prompt'); input('tags', 'test, review');
    input('content', '<script>never execute</script> & exact text');
    await click('save');
    assert(state.library.records.some(r => r.id === 'browser-prompt'), 'Prompt saved through UI');
    input('search', 'review');
    assert($('list').textContent.includes('Browser prompt'), 'Tags are searchable');
    assert($('content').value === '<script>never execute</script> & exact text', 'Literal Markdown round trip');
  } else {
    if (mode === 'profiles' || mode === 'snapshots') {
      input('name', 'Browser ' + mode); await click('save');
      assert(!dirty && selected, 'Record saved before apply');
    } else if (mode === 'mcp') {
      input('content', JSON.stringify({ browser: { command: 'fixture-only', args: ['--test'] } }, null, 2));
    } else if (mode === 'skills') {
      await click('new'); input('folder', 'browser-skill');
      input('content', '---\nname: browser-skill\ndescription: Browser test workflow\n---\n\nFixture only.\n');
    }
    await click('preview');
    assert($('preview-dialog').open, 'Review dialog opens');
    assert($('changes').querySelectorAll('.before').length > 0, 'Current contents shown');
    assert($('changes').querySelectorAll('.after').length > 0, 'Proposed contents shown');
    await click('apply');
    assert(!$('preview-dialog').open, 'Preview closes after apply');
    assert($('status').textContent.startsWith('Changes applied.'), 'Application succeeds');
    if (mode === 'skills') assert(state.files.some(f => f.id.endsWith('/browser-skill')), 'Created skill is listed');
  }
  await click('lock');
  assert(!$('login').hidden && $('app').hidden && !key, 'Lock clears the session');
  return 'PASS ' + mode + ' UI workflow';
})();
