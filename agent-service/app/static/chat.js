import {
  state,
  $,
  api,
  post,
  notice,
  text,
  icon,
  businessName,
  markdown,
  setBusy,
} from "./api.js";
let earliest = null;
const toolNames = {
  list_models: "查询模型列表",
  get_model: "读取模型详情",
  get_model_source: "追溯模型来源",
  get_model_training: "查询模型训练任务",
  list_train_tasks: "查询训练任务",
  get_train_task: "查找训练任务",
  list_train_instances: "查询执行实例",
  list_train_history: "查询执行历史",
  list_services: "查询服务列表",
  list_service_hosts: "查询服务主机",
  get_service_deployments: "查询部署状态",
  list_service_log_files: "读取日志文件列表",
  search_service_logs: "检索服务日志",
};
export function disconnect() {
  if (state.stream) {
    state.stream.close();
    state.stream = null;
  }
}
export async function loadHistory(more = false) {
  if (!more) {
    state.historyOffset = 0;
    $("history").replaceChildren();
  }
  const rows = await api("/conversations?offset=" + state.historyOffset);
  state.historyOffset += rows.length;
  rows.forEach((c) => {
    const button = text("button", "", "history-entry");
    button.dataset.id = c.id;
    button.title = c.title;
    if (c.id === state.conversation?.id) button.classList.add("active");
    button.append(icon("chat-left"), text("span", c.title));
    button.onclick = () => openConversation(c).catch((e) => notice(e.message));
    $("history").append(button);
  });
  if (!state.historyOffset)
    $("history").append(text("p", "你的对话将在这里保留", "history-empty"));
  $("more-history").hidden = rows.length < 50;
}
export async function newConversation() {
  if (state.busy) return;
  disconnect();
  state.conversation = null;
  state.run = null;
  $("messages").replaceChildren();
  $("welcome").hidden = false;
  $("older-messages").hidden = true;
  $("connection-status").textContent = "";
  await loadHistory();
  $("prompt").focus();
}
function appendMessage(role, content, status = "completed", prepend = false) {
  const row = text("article", "", "message " + role),
    body = text("div", "", "message-body");
  if (role === "assistant") {
    const avatar = text("div", "", "avatar");
    avatar.append(icon("stars"));
    row.append(avatar);
    body.append(text("div", "WiseRec Agent", "message-label"));
    const result = text("div", "", "markdown");
    markdown(result, content);
    body.append(result);
    if (status !== "completed")
      body.append(
        text(
          "div",
          status === "cancelled"
            ? "本次查询已停止"
            : "此回答未完成，请重新查询",
          "message-error",
        ),
      );
  } else body.textContent = content;
  row.append(body);
  if (prepend) $("messages").prepend(row);
  else $("messages").append(row);
  return body;
}
export async function openConversation(c) {
  if (state.busy) {
    notice("请等待当前查询结束或先停止");
    return;
  }
  if (c.business.businessId !== state.session.business?.businessId) {
    notice(
      "请先通过顶部业务选择切换到「" +
        businessName(c.business) +
        "」，再打开此对话",
    );
    return;
  }
  disconnect();
  state.conversation = c;
  state.run = null;
  $("messages").replaceChildren();
  $("welcome").hidden = true;
  const messages = await api("/conversations/" + c.id + "/messages");
  earliest = messages[0]?.id;
  messages.forEach((m) => appendMessage(m.role, m.content, m.status));
  $("older-messages").hidden = messages.length < 50;
  $("sidebar").classList.remove("open");
  await loadHistory();
  scrollDown();
}
$("older-messages").onclick = async () => {
  if (!state.conversation || !earliest) return;
  try {
    const rows = await api(
      "/conversations/" +
        state.conversation.id +
        "/messages?before=" +
        earliest,
    );
    earliest = rows[0]?.id;
    [...rows]
      .reverse()
      .forEach((m) => appendMessage(m.role, m.content, m.status, true));
    $("older-messages").hidden = rows.length < 50;
  } catch (e) {
    notice(e.message);
  }
};
function scrollDown() {
  const node = $("message-scroll");
  node.scrollTop = node.scrollHeight;
}
export async function sendMessage() {
  const value = $("prompt").value.trim();
  if (!value || state.busy) return;
  if (state.session?.status !== "ready") {
    notice("请先完成登录并选择业务");
    return;
  }
  setBusy(true);
  try {
    if (!state.conversation) state.conversation = await post("/conversations");
    const clientId = crypto.randomUUID();
    const result = await post(
      "/conversations/" + state.conversation.id + "/runs",
      { message: value, client_message_id: clientId },
    );
    $("welcome").hidden = true;
    appendMessage("user", value);
    $("prompt").value = "";
    state.run = result.run_id;
    const body = appendMessage("assistant", "");
    connectEvents(result.run_id, body);
    await loadHistory();
    scrollDown();
  } catch (error) {
    setBusy(false);
    if (error.status === 401)
      window.dispatchEvent(new Event("agent-auth-expired"));
    throw error;
  }
}
function connectEvents(runId, body) {
  disconnect();
  let answer = "",
    lastId = 0,
    retries = 0,
    finished = false;
  const output = body.querySelector(".markdown"),
    steps = new Map();
  $("connection-status").textContent = "正在理解问题…";
  const source = new EventSource("/api/runs/" + runId + "/events");
  state.stream = source;
  const on = (kind, handler) =>
    source.addEventListener(kind, (event) => {
      const id = Number(event.lastEventId || 0);
      if (id && id <= lastId) return;
      if (id) lastId = id;
      handler(JSON.parse(event.data));
    });
  function finish(data) {
    if (finished) return;
    finished = true;
    disconnect();
    setBusy(false);
    state.run = null;
    if (data.answer !== undefined) {
      answer = data.answer;
      markdown(output, answer);
    }
    $("connection-status").textContent = data.message || "查询完成";
    if (data.message) body.append(text("div", data.message, "message-error"));
    scrollDown();
  }
  on("run.started", () => {
    $("connection-status").textContent = "正在查询平台数据…";
  });
  on("tool.started", (data) => {
    const step = text("div", "", "tool-step");
    step.append(
      icon("arrow-repeat spin"),
      text("span", toolNames[data.name] || data.name),
      text("small", "执行中"),
    );
    body.insertBefore(step, output);
    steps.set(data.tool_call_id, step);
    scrollDown();
  });
  on("tool.completed", (data) => {
    const step = steps.get(data.tool_call_id);
    if (step) {
      step.firstChild.className =
        "bi bi-" +
        (data.status === "completed"
          ? "check-circle-fill"
          : "exclamation-circle");
      step.lastChild.textContent =
        data.status === "completed" ? "已完成" : "未完成";
      if (data.status !== "completed") step.classList.add("failed");
    }
  });
  on("answer.delta", (data) => {
    answer += data.text;
    markdown(output, answer);
    $("connection-status").textContent = "正在整理回答…";
    scrollDown();
  });
  on("run.completed", finish);
  on("run.failed", finish);
  on("run.cancelled", finish);
  on("stream.closed", finish);
  on("auth.expired", () => {
    disconnect();
    window.dispatchEvent(new Event("agent-auth-expired"));
  });
  source.onopen = () => {
    retries = 0;
  };
  source.onerror = async () => {
    if (finished) return;
    $("connection-status").textContent = "连接暂时中断，正在恢复…";
    retries++;
    try {
      const run = await api("/runs/" + runId);
      if (
        ["completed", "failed", "cancelled", "interrupted"].includes(run.status)
      ) {
        finish({ answer: run.answer, message: run.error });
        return;
      }
    } catch (e) {
      if (e.status === 401) {
        disconnect();
        window.dispatchEvent(new Event("agent-auth-expired"));
        return;
      }
    }
    if (retries >= 5) {
      disconnect();
      setBusy(false);
      notice("连接未恢复，任务可能仍在运行。请刷新页面检查状态，勿重复提交。");
    }
  };
}
export async function stopRun() {
  if (!state.run) return;
  try {
    await post("/runs/" + state.run + "/cancel");
    $("connection-status").textContent = "正在停止后续执行…";
  } catch (e) {
    notice(e.message);
  }
}

export async function resumeRun(active) {
  const c = await api("/conversations/" + active.conversation_id);
  await openConversation(c);
  state.run = active.id;
  setBusy(true);
  connectEvents(active.id, appendMessage("assistant", ""));
}
