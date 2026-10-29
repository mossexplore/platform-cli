import { text, icon, markdown } from "./api.js";

// The same renderer handles live events, persisted history and completion recovery.
export function createTimeline(body, toolNames) {
  const container = text("div", "", "message-timeline");
  body.append(container);
  let blocks = [],
    active = null;
  const tools = new Map();

  function textBlock(content = "") {
    const node = text("div", "", "markdown");
    container.append(node);
    const block = { type: "text", content, node };
    blocks.push(block);
    active = block;
    markdown(node, content);
    return block;
  }
  function delta(value) {
    if (!active) textBlock();
    active.content += value;
    markdown(active.node, active.content);
  }
  function completeTool(data) {
    const step = tools.get(data.tool_call_id || data.id);
    if (!step) return;
    step.status = data.status;
    step.node.firstChild.className =
      "bi bi-" +
      (data.status === "running"
        ? "arrow-repeat spin"
        : data.status === "completed"
          ? "check-circle-fill"
          : "exclamation-circle");
    step.node.lastChild.textContent =
      data.status === "running"
        ? "执行中"
        : data.status === "completed"
          ? "已完成"
          : data.status === "cancelled"
            ? "已停止"
            : "未完成";
    if (!["running", "completed"].includes(data.status))
      step.node.classList.add("failed");
  }
  function startTool(data) {
    active = null;
    const id = data.tool_call_id || data.id;
    if (tools.has(id)) return;
    const node = text("div", "", "tool-step");
    node.append(
      icon("arrow-repeat spin"),
      text("span", toolNames[data.name] || data.name),
      text("small", "执行中"),
    );
    container.append(node);
    const block = {
      type: "tool",
      id,
      name: data.name,
      status: data.status || "running",
      node,
    };
    blocks.push(block);
    tools.set(id, block);
    completeTool(block);
  }
  function restore(parts) {
    container.replaceChildren();
    blocks = [];
    active = null;
    tools.clear();
    for (const block of parts) {
      if (block.type === "text") textBlock(block.content);
      if (block.type === "tool") startTool(block);
    }
  }
  function finish(answer, parts) {
    if (parts?.length) {
      restore(parts);
      return;
    }
    if (answer === undefined) return;
    const combined = blocks
      .filter((b) => b.type === "text")
      .map((b) => b.content)
      .join("");
    if (answer === combined) return;
    if (!active) textBlock();
    if (answer.startsWith(combined))
      active.content += answer.slice(combined.length);
    else active.content = answer;
    markdown(active.node, active.content);
  }
  return { delta, startTool, completeTool, restore, finish };
}
