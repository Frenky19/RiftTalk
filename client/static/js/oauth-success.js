(function () {
  function $(id) { return document.getElementById(id); }

  const closeBtn = $('closeBtn');
  const copyBtn = $('copyBtn');
  const tEl = $('t');

  if (closeBtn) {
    closeBtn.addEventListener('click', () => window.close());
  }

  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText('OK'); } catch (e) {}
    });
  }

  // Auto-close after 3 seconds (best-effort)
  let t = 3;
  if (tEl) tEl.textContent = String(t);

  const timer = setInterval(() => {
    t -= 1;
    if (tEl) tEl.textContent = String(t);
    if (t <= 0) {
      clearInterval(timer);
      try { window.close(); } catch (e) {}
    }
  }, 1000);
})();
