export const state = {
  session: null,
  environments: [],
  conversation: null,
  run: null,
  stream: null,
  attempt: null,
  busy: false,
  historyOffset: 0,
};
export const $ = (id) => document.getElementById(id);
let noticeTimer;
export function notice(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => ($("notice").hidden = true), 8000);
}
export async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (options.method && options.method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-Agent-CSRF"] = state.session?.csrf_token || "";
  }
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error?.message || "请求未完成");
    error.code = body.error?.code;
    error.status = response.status;
    throw error;
  }
  return body;
}
export const post = (path, body = {}) =>
  api(path, { method: "POST", body: JSON.stringify(body) });
export function text(tag, content, cls) {
  const element = document.createElement(tag);
  element.textContent = content;
  if (cls) element.className = cls;
  return element;
}
export function icon(name) {
  const i = document.createElement("i");
  i.className = "bi bi-" + name;
  i.setAttribute("aria-hidden", "true");
  return i;
}
export function businessName(b) {
  return b?.team_name
    ? b.tenant_name + " / " + b.team_name
    : b?.tenant_name || "选择业务";
}
export function markdown(node, content) {
  if (window.marked && window.DOMPurify) {
    node.innerHTML = DOMPurify.sanitize(marked.parse(content), {
      FORBID_TAGS: ["img", "style", "form", "input", "button", "iframe"],
      FORBID_ATTR: ["style"],
    });
    node.querySelectorAll("table").forEach((table) => {
      const wrapper = document.createElement("div");
      wrapper.className = "table-scroll";
      table.replaceWith(wrapper);
      wrapper.append(table);
      const headers = [...table.querySelectorAll("thead th")];
      const statusIndex = headers.findIndex(
        (cell) => cell.textContent.trim() === "状态",
      );
      if (statusIndex >= 0)
        table.querySelectorAll("tbody tr").forEach((row) => {
          const cell = row.cells[statusIndex];
          const status = cell?.textContent.trim();
          const tones = {
            已部署: "success",
            运行中: "success",
            训练完成: "info",
            成功: "success",
            失败: "danger",
            异常: "danger",
            等待中: "info",
          };
          if (tones[status]) {
            const badge = text("span", status, "status-badge " + tones[status]);
            cell.replaceChildren(badge);
          }
        });
    });
    node.querySelectorAll("a").forEach((a) => {
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    });
  } else node.textContent = content;
}
export function setBusy(busy) {
  state.busy = busy;
  $("send-button").hidden = busy;
  $("stop-run").hidden = !busy;
  $("prompt").disabled = busy || state.session?.status !== "ready";
  $("new-chat").disabled = busy;
  $("business-button").disabled = busy;
  document
    .querySelectorAll("[data-prompt]")
    .forEach((b) => (b.disabled = busy));
}
