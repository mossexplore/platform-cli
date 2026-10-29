import { text } from "./api.js";

export function formatMessageTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
}
export function attachMessageTime(row, value) {
  const time = text("time", "", "message-time");
  time.title = "北京时间（UTC+8）";
  row.append(time);
  function update(value) {
    time.textContent = formatMessageTime(value);
    time.hidden = !time.textContent;
    if (time.textContent) time.dateTime = value;
    else time.removeAttribute("datetime");
  }
  update(value);
  return update;
}
