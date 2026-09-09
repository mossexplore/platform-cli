'use strict';
// Bound list cell height while keeping the original text available via a keyboard-accessible dialog.
const detail = document.createElement('dialog');
detail.className = 'drawer list-cell-dialog';
detail.setAttribute('aria-labelledby', 'list-cell-title');
const heading = document.createElement('div');
heading.className = 'drawer-heading';
const title = document.createElement('h2');
title.id = 'list-cell-title';
const close = document.createElement('button');
close.type = 'button';
close.className = 'text-button';
close.textContent = '关闭';
close.setAttribute('data-close', '');
heading.append(title, close);
const body = document.createElement('div');
body.className = 'drawer-body';
const content = document.createElement('pre');
content.className = 'list-cell-content';
body.append(content);
detail.append(heading, body);
document.body.append(detail);

const observer = new ResizeObserver((entries) => {
  for (const {target} of entries) {
    const preview = target.querySelector('.cell-preview');
    const button = target.querySelector('.cell-expand');
    const overflow = preview.scrollHeight > preview.clientHeight + 1 || preview.scrollWidth > preview.clientWidth + 1;
    button.hidden = !overflow;
  }
});
document.querySelectorAll('.main-content > .panel .table-scroll > table > tbody > tr > td').forEach((cell) => {
  if (cell.colSpan > 1 || cell.querySelector('button,a,input') || cell.closest('.grant-accounts')) return;
  const preview = document.createElement('div');
  preview.className = 'cell-preview';
  const text = cell.innerText;
  while (cell.firstChild) preview.append(cell.firstChild);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'cell-expand';
  button.textContent = '查看';
  button.hidden = true;
  const label = cell.closest('table').querySelectorAll('thead th')[cell.cellIndex]?.textContent || '内容';
  const fullLabel = label.startsWith('完整') ? label : `完整${label}`;
  button.setAttribute('aria-label', `查看${fullLabel}`);
  button.addEventListener('click', () => {
    title.textContent = fullLabel;
    content.textContent = text;
    detail.showModal();
  });
  cell.classList.add('has-cell-preview');
  cell.append(preview, button);
  observer.observe(cell);
});
