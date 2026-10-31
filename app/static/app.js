// Small progressive enhancements for the server-rendered pages.

// ---- Confirm modal: <form data-confirm="Are you sure?">
(function () {
  const modal = document.getElementById("confirm-modal");
  if (!modal) return;
  const message = document.getElementById("confirm-message");
  let pending = null;
  const close = () => { modal.classList.add("hidden"); modal.classList.remove("flex"); pending = null; };

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form.dataset.confirm || form.dataset.confirmed) return;
    event.preventDefault();
    pending = form;
    message.textContent = form.dataset.confirm;
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  });
  document.getElementById("confirm-cancel").addEventListener("click", close);
  document.getElementById("confirm-ok").addEventListener("click", () => {
    const form = pending;
    close();
    if (form) { form.dataset.confirmed = "1"; form.requestSubmit(); }
  });
})();

// ---- Live password checklist: <input data-password-rules> + <ul data-password-checklist>
// Mirrors app/validators/password.py
const PASSWORD_RULES = {
  length: (p) => p.length > 8,
  upper: (p) => /[A-Z]/.test(p),
  lower: (p) => /[a-z]/.test(p),
  special: (p) => /[^A-Za-z0-9]/.test(p),
};
document.querySelectorAll("[data-password-rules]").forEach((input) => {
  const form = input.form;
  const list = form.querySelector("[data-password-checklist]");
  const button = form.querySelector("button[type=submit], button:not([type])");
  const update = () => {
    let ok = true;
    list.querySelectorAll("[data-rule]").forEach((item) => {
      const passed = PASSWORD_RULES[item.dataset.rule](input.value);
      ok = ok && passed;
      item.classList.toggle("text-emerald-600", passed);
      item.classList.toggle("text-slate-400", !passed);
      item.querySelector("span").textContent = passed ? "✓" : "○";
    });
    if (button) button.disabled = !ok;
    button && button.classList.toggle("opacity-50", !ok);
  };
  input.addEventListener("input", update);
  update();
});

// ---- Subscription line editor: add/remove rows, variants filtered by product
(function () {
  const container = document.querySelector("[data-lines]");
  if (!container) return;
  const template = document.getElementById("line-template");

  const syncVariants = (row) => {
    const product = row.querySelector("[name=product_id]");
    const variant = row.querySelector("[name=variant_id]");
    variant.querySelectorAll("option[data-product]").forEach((opt) => {
      const show = opt.dataset.product === product.value;
      opt.hidden = !show;
      if (!show && opt.selected) variant.value = "";
    });
  };
  const wire = (row) => {
    row.querySelector("[name=product_id]").addEventListener("change", () => syncVariants(row));
    row.querySelector("[data-remove]").addEventListener("click", () => {
      if (container.querySelectorAll("[data-line]").length > 1) row.remove();
    });
    syncVariants(row);
  };
  container.querySelectorAll("[data-line]").forEach(wire);
  document.querySelector("[data-add-line]").addEventListener("click", () => {
    const row = template.content.firstElementChild.cloneNode(true);
    container.appendChild(row);
    wire(row);
  });
})();
