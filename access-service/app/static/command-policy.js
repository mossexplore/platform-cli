// Count normalized, unique lines; editing the draft never changes saved rules.
document.querySelectorAll('[data-command-policy]').forEach(panel => {
  const input = panel.querySelector('[data-command-input]');
  const commands = () => new Set(input.value.split(/\r?\n/)
    .map(line => line.trim().replace(/\s+/g, ' ')).filter(Boolean));
  const initial = commands();
  input.addEventListener('input', () => {
    const selected = commands();
    const added = [...selected].filter(value => !initial.has(value)).length;
    const removed = [...initial].filter(value => !selected.has(value)).length;
    panel.querySelector('[data-command-count]').textContent =
      `已禁止 ${selected.size} 个命令 · 新增禁止 ${added} 个 · 解除禁止 ${removed} 个`;
  });
});
