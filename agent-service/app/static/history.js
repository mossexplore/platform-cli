import { $, state, api, text, icon, notice } from "./api.js";

let rows = [], scope = "", prefs = {}, open, archived = false, generation = 0;
let editing = null;
const day = (value) => new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date(value));
export function historyGroup(row, preference = {}, now = Date.now()) {
  if (preference.pinned) return "置顶";
  if (!row.updated_at || !Number.isFinite(Date.parse(row.updated_at))) return "更早";
  if (day(row.updated_at) === day(now)) return "今天";
  if (day(row.updated_at) === day(now - 86400000)) return "昨天";
  return "更早";
}
export function filterHistory(items, query, preferences, showArchived) {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(c => Boolean(preferences[c.id]?.archived) === showArchived &&
    terms.every(term => c.title.toLocaleLowerCase().includes(term)));
}
function save() {
  try { localStorage.setItem(scope, JSON.stringify(prefs)); }
  catch { notice("浏览器无法保存整理偏好，本次操作仅在当前页面有效"); }
}
function closeMenus() {
  document.querySelectorAll(".history-menu").forEach(m => m.hidden = true);
  document.querySelectorAll(".history-actions").forEach(b => b.setAttribute("aria-expanded", "false"));
}
function action(label, handler) {
  const button = text("button", label);
  button.type = "button";
  button.onclick = handler;
  return button;
}
function entry(c) {
  const row = text("div", "", "history-row");
  const button = text("button", "", "history-entry");
  button.type = "button";
  button.dataset.id = c.id;
  button.title = c.title;
  if (c.id === state.conversation?.id) {
    row.classList.add("active");
    button.setAttribute("aria-current", "page");
  }
  button.append(text("span", c.title));
  const date = text("time", "", "history-date");
  if (c.updated_at && Number.isFinite(Date.parse(c.updated_at))) {
    date.dateTime = c.updated_at;
    date.textContent = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit",
    }).format(new Date(c.updated_at)).replaceAll("/", "-");
    date.title = new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "medium",
    }).format(new Date(c.updated_at)) + " 北京时间";
  }
  button.append(date);
  button.onclick = () => open(c).catch(e => notice(e.message));
  const toggle = text("button", "", "history-actions");
  toggle.append(icon("three-dots"));
  toggle.setAttribute("aria-label", "整理对话：" + c.title);
  toggle.setAttribute("aria-expanded", "false");
  const menu = text("div", "", "history-menu");
  menu.hidden = true;
  toggle.onclick = () => {
    const show = menu.hidden;
    closeMenus();
    menu.hidden = !show;
    toggle.setAttribute("aria-expanded", String(show));
    if (show) menu.querySelector("button").focus();
  };
  menu.append(action("重命名", () => {
    closeMenus(); editing = c;
    $("rename-title").value = c.title;
    $("rename-dialog").showModal(); $("rename-title").select();
  }), action(prefs[c.id]?.pinned ? "取消置顶" : "置顶", () => {
    prefs[c.id] = { ...prefs[c.id], pinned: !prefs[c.id]?.pinned };
    save(); render();
  }), action(archived ? "恢复对话" : "归档", () => {
    prefs[c.id] = { ...prefs[c.id], archived: !archived };
    save(); render();
  }));
  row.append(button, toggle, menu);
  return row;
}
function render() {
  const visible = filterHistory(rows, $("history-search").value, prefs, archived);
  const nav = $("history"); nav.replaceChildren();
  $("history-caption").textContent = archived ? "已归档 · 仅此浏览器" : "对话历史";
  $("history-archived").textContent = archived ? "返回历史" : "已归档";
  $("history-archived").setAttribute("aria-pressed", String(archived));
  for (const group of ["置顶", "今天", "昨天", "更早"]) {
    const members = visible.filter(c => historyGroup(c, prefs[c.id]) === group);
    if (!members.length) continue;
    const section = text("section", "", "history-group");
    section.setAttribute("aria-label", group);
    section.append(text("h2", group, "history-heading"), ...members.map(entry));
    nav.append(section);
  }
  if (!visible.length) nav.append(text("p", rows.length ? "没有匹配的对话" : "你的对话将在这里保留", "history-empty"));
}
export async function refreshHistory(onOpen) {
  open = onOpen;
  const ticket = ++generation;
  const key = "wiserec-history:" + JSON.stringify([state.session?.environment_id, state.session?.user?.username]);
  if (scope !== key) {
    scope = key; archived = false; rows = []; prefs = {};
    $("history-search").value = "";
    render();
    try { const value = JSON.parse(localStorage.getItem(scope) || "{}");
      if (value && typeof value === "object" && !Array.isArray(value)) prefs = value;
    } catch { /* A corrupt or unavailable store must not prevent history loading. */ }
  }
  const result = [];
  // Read all pages so search and browser-local pins include older conversations.
  for (let offset = 0; ; offset += 50) {
    const page = await api("/conversations?offset=" + offset);
    if (ticket !== generation) return;
    result.push(...page);
    if (page.length < 50) break;
  }
  rows = result;
  $("more-history").hidden = true;
  render();
}
$("history-search").oninput = render;
$("history-archived").onclick = () => { archived = !archived; render(); };
$("rename-cancel").onclick = () => $("rename-dialog").close();
$("rename-form").onsubmit = async e => {
  e.preventDefault();
  const title = $("rename-title").value.trim();
  if (!title) { $("rename-title").focus(); return; }
  const c = editing, submit = e.submitter;
  if (submit) submit.disabled = true;
  try {
    const updated = await api("/conversations/" + c.id, { method: "PATCH", body: JSON.stringify({ title }) });
    c.title = updated.title;
    if (state.conversation?.id === c.id) state.conversation.title = updated.title;
    $("rename-dialog").close(); render();
  } catch (error) { notice(error.message); }
  finally { if (submit) submit.disabled = false; }
};
document.addEventListener("click", e => { if (!e.target.closest(".history-row")) closeMenus(); });
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    const toggle = document.querySelector('.history-actions[aria-expanded="true"]');
    closeMenus(); toggle?.focus();
  }
});
