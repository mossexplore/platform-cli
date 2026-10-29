import { text, businessName } from "./api.js";

export function selectionKey(b) {
  return JSON.stringify(
    ["type", "department_id", "tenant_id", "team_id", "businessId"].map(
      (k) => b?.[k] || "",
    ),
  );
}
export function filterBusinesses(list, query) {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return list.filter((b) => {
    const fields = [
      b.department_name,
      b.tenant_name,
      b.team_name,
      b.businessId,
      b.tenant_id,
      b.team_id,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return words.every((word) => fields.includes(word));
  });
}
export function bindBusinessPicker(list, current, elements) {
  const { search, select, count, empty, confirm } = elements;
  search.value = "";
  let chosen = current ? selectionKey(current) : "";
  function render() {
    const rows = filterBusinesses(list, search.value);
    select.replaceChildren();
    for (const b of rows) {
      const label = [b.department_name, businessName(b)]
        .filter(Boolean)
        .join(" / ");
      const option = text("option", label);
      option.title = label;
      option.value = b.selection_key || selectionKey(b);
      option.selected = option.value === chosen;
      select.append(option);
    }
    if (
      rows.length &&
      !rows.some((b) => (b.selection_key || selectionKey(b)) === chosen)
    ) {
      select.value = rows[0].selection_key || selectionKey(rows[0]);
    }
    count.textContent =
      "显示 " + rows.length + " / " + list.length + " 个租户或团队";
    empty.hidden = rows.length > 0;
    select.hidden = !rows.length;
    select.disabled = !rows.length;
    confirm.disabled = !rows.length;
  }
  select.onchange = () => {
    chosen = select.value;
  };
  search.oninput = render;
  render();
}
