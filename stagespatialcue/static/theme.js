/* Themes affect presentation only; no project or audio state is modified. */
'use strict';
(() => {
  const choices = new Set(['dark', 'graphite', 'warm', 'light']);
  const key = 'spatialstage.theme';
  let theme = 'dark';
  try { const saved = localStorage.getItem(key); if (choices.has(saved)) theme = saved; } catch (_) {}
  function apply(value) {
    document.documentElement.dataset.theme = choices.has(value) ? value : 'dark';
    const select = document.getElementById('themeSelect');
    if (select) select.value = document.documentElement.dataset.theme;
  }
  apply(theme);
  document.getElementById('themeSelect')?.addEventListener('change', event => {
    apply(event.target.value);
    try { localStorage.setItem(key, event.target.value); } catch (_) {}
  });
})();
