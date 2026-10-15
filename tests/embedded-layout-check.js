// Evaluate in a same-origin preview host with one unlocked editor iframe.
// Read-only: changes iframe size, checks layout/images, then restores its width.
(async () => {
  const frame = document.querySelector('iframe');
  if (!frame?.contentDocument) throw Error('Use a same-origin embedded test host');
  const page = frame.contentWindow, doc = frame.contentDocument;
  if (doc.getElementById('app')?.hidden) throw Error('Unlock the isolated editor first');
  const previous = frame.style.width;
  try {
    for (const width of [1000, 820, 375]) {
      frame.style.width = width + 'px';
      await new Promise(resolve => setTimeout(resolve, 150));
      if (doc.documentElement.scrollWidth > page.innerWidth) throw Error(`Horizontal overflow at ${width}px`);
      for (const image of doc.querySelectorAll('.agent-logo')) {
        if (!image.complete || !image.naturalWidth) throw Error(`Missing agent icon at ${width}px`);
      }
      for (const control of doc.querySelectorAll('input,select,textarea')) {
        if (!control.getClientRects().length || control.closest('dialog:not([open])')) continue;
        const bounds = control.getBoundingClientRect();
        if (bounds.left < -1 || bounds.right > page.innerWidth + 1) throw Error(`Control ${control.id} exceeds viewport`);
      }
    }
    return 'PASS: embedded layout and agent icons at 1000, 820 and 375px';
  } finally { frame.style.width = previous; }
})()
