"use strict";

document.querySelectorAll("[data-approval-environments]").forEach((group) => {
  const choices = [...group.querySelectorAll('input[name="environments"]')];
  group.querySelectorAll("[data-environment-selection]").forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.environmentSelection;
      choices.forEach((choice) => {
        choice.checked = mode === "all" || (mode === "default" && choice.dataset.defaultGrant === "true");
        choice.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  });
});
