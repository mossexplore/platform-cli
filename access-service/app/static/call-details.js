'use strict';
document.querySelectorAll('[data-copy-call]').forEach((button) => {
  button.addEventListener('click', async () => {
    const text = document.getElementById(button.dataset.copyCall);
    const status = button.closest('dialog').querySelector('[data-copy-status]');
    try {
      await navigator.clipboard.writeText(text.textContent);
      status.textContent = '完整命令已复制。';
    } catch (_) {
      const range = document.createRange();
      range.selectNodeContents(text);
      const selection = window.getSelection();
      selection.removeAllRanges(); selection.addRange(range);
      text.focus();
      status.textContent = '已选中完整命令，请按 Ctrl+C（Mac：⌘C）复制。';
    }
  });
});
