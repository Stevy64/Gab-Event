/**
 * Admin UI — Zanalyze-style guest detail popup
 */
(function () {
  "use strict";

  function openModal(btn) {
    var modal = document.getElementById("zyz-detail-modal");
    if (!modal || !btn) return;
    var fields = [
      { ico: "👤", label: "Type", value: btn.dataset.type || "—" },
      { ico: "▢", label: "Catégorie", value: btn.dataset.category || "—" },
      { ico: "◆", label: "Code", value: btn.dataset.code || "—" },
      { ico: "★", label: "Places", value: btn.dataset.places || "—" },
      { ico: "✉", label: "Invitation", value: btn.dataset.invite || "—" },
      { ico: "◎", label: "Présence", value: btn.dataset.presence || "—" },
    ];
    document.getElementById("zyz-modal-title").textContent = btn.dataset.name || "Détail";
    document.getElementById("zyz-modal-avatar").textContent = btn.dataset.initials || "?";
    document.getElementById("zyz-modal-kicker").textContent =
      btn.dataset.vip === "1" ? "Invitation VIP" : "Invitation";
    var list = document.getElementById("zyz-modal-fields");
    list.innerHTML = "";
    fields.forEach(function (f) {
      var li = document.createElement("li");
      li.innerHTML =
        '<span class="zyz-modal-ico" aria-hidden="true">' +
        f.ico +
        "</span><div><em></em><strong></strong></div>";
      li.querySelector("em").textContent = f.label;
      li.querySelector("strong").textContent = f.value;
      list.appendChild(li);
    });
    var edit = document.getElementById("zyz-modal-edit");
    if (btn.dataset.href) {
      edit.href = btn.dataset.href;
      edit.hidden = false;
    } else {
      edit.hidden = true;
    }
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("zyz-modal-open");
  }

  function closeModal() {
    var modal = document.getElementById("zyz-detail-modal");
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("zyz-modal-open");
  }

  document.querySelectorAll(".js-guest-open").forEach(function (btn) {
    btn.addEventListener("click", function () {
      openModal(btn);
    });
  });

  var modal = document.getElementById("zyz-detail-modal");
  if (modal) {
    modal.querySelectorAll("[data-zyz-close]").forEach(function (el) {
      el.addEventListener("click", closeModal);
    });
  }
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeModal();
  });
})();
