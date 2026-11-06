"use strict";
// All displayed task text stays text, including in the confirmation dialog.
const dialog = document.getElementById("delete-dialog");
let pendingDelete = null;
document.querySelectorAll(".delete-form").forEach(form => {
  form.addEventListener("submit", event => {
    if (form.dataset.confirmed === "yes") return;
    event.preventDefault();
    pendingDelete = form;
    document.getElementById("delete-task-name").textContent = form.dataset.taskName;
    dialog.showModal();
    dialog.querySelector(".secondary-button").focus();
  });
});
dialog.addEventListener("close", () => {
  if (dialog.returnValue === "delete" && pendingDelete) {
    const form = pendingDelete;
    form.dataset.confirmed = "yes";
    const confirmation = document.createElement("input");
    confirmation.type = "hidden";
    confirmation.name = "confirm";
    confirmation.value = "yes";
    form.append(confirmation);
    form.requestSubmit();
  }
  pendingDelete = null;
  dialog.returnValue = "";
});
document.querySelectorAll("form:not([method='dialog'])").forEach(form => {
  form.addEventListener("submit", event => {
    // Wait for confirmation listeners before locking controls.
    if (!event.defaultPrevented) {
      form.setAttribute("aria-busy", "true");
      form.querySelectorAll("button[type='submit']").forEach(button => { button.disabled = true; });
    }
  });
});
document.querySelectorAll(".dismiss").forEach(button => button.addEventListener("click", () => button.closest(".notice").remove()));
window.addEventListener("pageshow", () => {
  document.querySelectorAll("[aria-busy]").forEach(form => {
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button").forEach(button => { button.disabled = false; });
  });
});
// A page restored from another tab can be stale. The server still validates
// each task version; leave in-progress input intact rather than auto-refreshing.
