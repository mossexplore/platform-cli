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
import {
  loadHistory,
  openConversation,
  newConversation,
  sendMessage,
  stopRun,
  disconnect,
  resumeRun,
} from "./chat.js";
import { bindBusinessPicker, selectionKey } from "./business-picker.js";
let availableBusinesses = [];
const environmentDescriptions = {
  dev: "用于日常开发与测试",
  mirror: "在镜像环境中查询平台资源",
  explore: "探索业务数据与模型",
  product: "查询正式业务环境数据",
};
let polling = false;

async function boot() {
  try {
    state.environments = await api("/environments");
    renderEnvironments();
    state.session = await api("/session");
    $("setup-error").hidden = true;
    await showSession();
  } catch (error) {
    if (error.code === "SETUP_REQUIRED") {
      $("setup-error").hidden = false;
      $("setup-message").textContent = error.message;
      $("login-button").disabled = true;
    } else notice(error.message);
  }
}
function renderEnvironments() {
  const list = $("environments");
  list.replaceChildren();
  state.environments.forEach((e, index) => {
    const label = text("label", "", "environment-option");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "environment";
    radio.value = e.id;
    radio.checked = index === 0;
    const copy = document.createElement("div");
    copy.append(
      text("strong", e.name),
      text(
        "small",
        environmentDescriptions[e.id] || "使用此环境的平台账号登录",
      ),
    );
    label.append(radio, copy, text("span", e.id.toUpperCase(), "env-code"));
    list.append(label);
  });
  if (!state.environments.length)
    list.append(text("p", "暂无已启用环境，请检查配置文件", "muted"));
  $("login-button").disabled = !state.environments.length;
}
export async function showSession() {
  const logged = !!state.session?.user;
  $("login-screen").hidden = logged;
  $("chat-screen").hidden = !logged;
  if (!logged) {
    disconnect();
    state.conversation = null;
    state.run = null;
    setBusy(false);
    return;
  }
  $("account-name").textContent =
    state.session.user.name || state.session.user.username;
  $("account-id").textContent = state.session.user.username;
  $("env-name").textContent =
    state.environments.find((e) => e.id === state.session.environment_id)
      ?.name || state.session.environment_id;
  $("business-name").textContent = businessName(state.session.business);
  setBusy(false);
  await loadHistory();
  if (state.session.status !== "ready") await chooseBusiness(true);
  else if (state.session.active_run) await resumeRun(state.session.active_run);
}
async function login(event) {
  event.preventDefault();
  if (polling) return;
  const env = document.querySelector("input[name=environment]:checked")?.value;
  if (!env) return;
  try {
    const result = await post("/login-attempts", { environment_id: env });
    state.attempt = result.attempt_id;
    polling = true;
    $("login-button").disabled = true;
    $("login-progress").hidden = false;
    $("login-status").textContent = "正在打开 Edge…";
    document
      .querySelectorAll("input[name=environment]")
      .forEach((e) => (e.disabled = true));
    while (polling) {
      const result = await api("/login-attempts/" + state.attempt);
      if (result.status === "succeeded") {
        polling = false;
        state.session = await api("/session");
        await showSession();
        if (result.message) notice(result.message);
        break;
      }
      if (["failed", "cancelled"].includes(result.status)) {
        polling = false;
        if (result.message) notice(result.message);
        break;
      }
      $("login-status").textContent =
        result.status === "verifying"
          ? "正在验证平台身份…"
          : result.status === "awaiting_login"
            ? "等待你完成平台登录…"
            : "正在打开 Edge…";
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
  } catch (error) {
    polling = false;
    notice(error.message);
  } finally {
    $("login-progress").hidden = true;
    $("login-button").disabled = !state.environments.length;
    document
      .querySelectorAll("input[name=environment]")
      .forEach((e) => (e.disabled = false));
  }
}
async function chooseBusiness(auto = false) {
  $("business-error").textContent = "";
  try {
    const list = await api("/businesses");
    availableBusinesses = list;
    bindBusinessPicker(list, state.session.business, {
      search: $("business-search"),
      select: $("business-select"),
      count: $("business-count"),
      empty: $("business-empty"),
      confirm: $("confirm-business"),
    });
    if (!list.length)
      $("business-error").textContent =
        "当前账号没有可选择业务，请联系平台管理员或退出重试。";
    if (auto && list.length === 1) {
      try {
        await confirmBusiness(list[0].selection_key || selectionKey(list[0]));
        return;
      } catch (error) {
        $("business-error").textContent = error.message;
      }
    }
    $("business-dialog").showModal();
    $("business-search").focus();
  } catch (error) {
    notice(error.message);
  }
}
async function confirmBusiness(key) {
  const business = availableBusinesses.find(
    (b) => (b.selection_key || selectionKey(b)) === key,
  );
  if (!business) throw new Error("请选择一个有效的租户或团队");
  state.session = await post("/business-selection", {
    business_id: business.businessId,
    selection_key: key,
  });
  $("business-name").textContent = businessName(state.session.business);
  $("business-dialog").close();
  setBusy(false);
  await newConversation();
}
async function logout() {
  try {
    const result = await post("/logout");
    disconnect();
    polling = false;
    state.conversation = null;
    state.run = null;
    $("logout-dialog").close();
    $("business-dialog").close();
    $("messages").replaceChildren();
    $("welcome").hidden = false;
    $("connection-status").textContent = "";
    await boot();
    if (result.warning) notice("服务端登录已退出；" + result.warning);
  } catch (error) {
    notice(error.message);
  }
}
$("login-form").addEventListener("submit", login);
$("cancel-login").onclick = async () => {
  try {
    await post("/login-attempts/" + state.attempt + "/cancel");
    polling = false;
  } catch (e) {
    notice(e.message);
  }
};
$("retry-setup").onclick = boot;
$("business-button").onclick = () => chooseBusiness();
$("close-business").onclick = () => $("business-dialog").close();
$("business-form").onsubmit = async (e) => {
  e.preventDefault();
  $("confirm-business").disabled = true;
  try {
    await confirmBusiness($("business-select").value);
  } catch (error) {
    $("business-error").textContent = error.message;
  } finally {
    $("confirm-business").disabled = false;
  }
};
$("logout").onclick = () => $("logout-dialog").showModal();
$("cancel-logout").onclick = () => $("logout-dialog").close();
$("confirm-logout").onclick = logout;
$("new-chat").onclick = () => newConversation().catch((e) => notice(e.message));
$("more-history").onclick = () => loadHistory(true).catch((e) => notice(e.message));
$("composer").onsubmit = (e) => {
  e.preventDefault();
  sendMessage().catch((e) => notice(e.message));
};
$("prompt").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (!state.busy) sendMessage().catch((e) => notice(e.message));
  }
});
$("stop-run").onclick = stopRun;
$("menu-button").onclick = () => $("sidebar").classList.toggle("open");
document.querySelectorAll("[data-prompt]").forEach(
  (b) =>
    (b.onclick = () => {
      $("prompt").value = b.dataset.prompt;
      sendMessage().catch((e) => notice(e.message));
    }),
);
window.addEventListener("agent-auth-expired", async () => {
  disconnect();
  notice("登录已失效，请重新登录");
  await boot();
});
boot();

// Renew the browser's Agent session cookie while the page is open.
// This does not extend platform credentials; only confirmed platform activity does.
setInterval(async () => {
  if (!state.session?.user) return;
  try {
    const session = await api("/session");
    if (!session.user) window.dispatchEvent(new Event("agent-auth-expired"));
  } catch (error) {
    if (error.status === 401)
      window.dispatchEvent(new Event("agent-auth-expired"));
  }
}, 60000);
