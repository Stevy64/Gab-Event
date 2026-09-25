/* Gab Event admin — navigation, animations, popups */
(function () {
  "use strict";

  var burger = document.querySelector("[data-cx-nav]");
  var nav = document.querySelector("[data-cx-side]");
  var scrim = document.querySelector("[data-cx-nav-close]");

  function setNav(open) {
    document.body.classList.toggle("cx-nav-open", open);
    if (scrim) scrim.hidden = !open;
  }
  if (burger && nav) {
    burger.addEventListener("click", function () {
      setNav(!document.body.classList.contains("cx-nav-open"));
    });
  }
  if (scrim) {
    scrim.addEventListener("click", function () { setNav(false); });
  }

  var collapseKey = "gabevent-cx-collapsed";
  var collapseBtn = document.querySelector("[data-cx-collapse]");
  function setCollapsed(on) {
    document.body.classList.toggle("cx-side-collapsed", on);
    try { localStorage.setItem(collapseKey, on ? "1" : "0"); } catch (err) {}
    if (collapseBtn) {
      collapseBtn.setAttribute("aria-label", on ? "Déplier le menu" : "Réduire le menu");
      collapseBtn.title = on ? "Déplier le menu" : "Réduire le menu";
    }
  }
  try {
    if (localStorage.getItem(collapseKey) === "1") setCollapsed(true);
  } catch (err) {}
  if (collapseBtn) {
    collapseBtn.addEventListener("click", function () {
      setCollapsed(!document.body.classList.contains("cx-side-collapsed"));
    });
  }

  document.querySelectorAll("[data-filebox]").forEach(function (box) {
    var input = box.querySelector("[data-filebox-input], input[type=file]");
    var pick = box.querySelector("[data-filebox-pick]");
    var img = box.querySelector("[data-filebox-img]");
    var ph = box.querySelector("[data-filebox-ph]");
    var name = box.querySelector("[data-filebox-name]");
    var clear = box.querySelector("[data-filebox-clear]");
    var clearWrap = box.querySelector("[data-filebox-clear-wrap]");
    if (!input) return;

    function hidePreview() {
      if (img) {
        img.hidden = true;
        img.removeAttribute("src");
        if (img._objectUrl) {
          URL.revokeObjectURL(img._objectUrl);
          img._objectUrl = "";
        }
      }
      if (ph) ph.hidden = false;
      box.classList.remove("has-file");
    }

    function showFile(file) {
      if (!file) return;
      box.classList.add("has-file");
      if (name) name.textContent = file.name;
      if (pick) pick.textContent = "Remplacer";
      if (clear) clear.checked = false;
      if (clearWrap) clearWrap.hidden = false;
      if (!img || (file.type && file.type.indexOf("image/") !== 0)) return;
      if (img._objectUrl) URL.revokeObjectURL(img._objectUrl);
      var url = URL.createObjectURL(file);
      img._objectUrl = url;
      img.onload = function () {
        img.hidden = false;
        if (ph) ph.hidden = true;
      };
      img.onerror = hidePreview;
      img.hidden = false;
      if (ph) ph.hidden = true;
      img.src = url;
    }

    if (img) {
      img.addEventListener("error", hidePreview);
    }
    if (pick) {
      pick.addEventListener("click", function (e) {
        if (e.target === input) return;
        if (typeof input.showPicker === "function") {
          try { input.showPicker(); return; } catch (err) {}
        }
        input.click();
      });
    }
    input.addEventListener("change", function () {
      showFile(input.files && input.files[0]);
    });
    ["dragenter", "dragover"].forEach(function (ev) {
      box.addEventListener(ev, function (e) {
        e.preventDefault();
        box.classList.add("is-drop");
      });
    });
    box.addEventListener("dragleave", function () { box.classList.remove("is-drop"); });
    box.addEventListener("drop", function (e) {
      e.preventDefault();
      box.classList.remove("is-drop");
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      try {
        var dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
      } catch (err) {}
      showFile(file);
    });
  });

  function prefersReduced() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function animateCount(el) {
    var raw = (el.getAttribute("data-count") || el.textContent || "0").replace(/\s/g, "").replace(",", ".");
    var target = parseFloat(raw);
    if (!isFinite(target)) return;
    var decimals = raw.indexOf(".") !== -1 ? 0 : 0;
    if (prefersReduced() || target > 99999) {
      el.textContent = String(Math.round(target));
      return;
    }
    var start = 0;
    var duration = 700;
    var t0 = null;
    function frame(ts) {
      if (!t0) t0 = ts;
      var p = Math.min(1, (ts - t0) / duration);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = String(Math.round(start + (target - start) * eased));
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    void decimals;
  }
  document.querySelectorAll("[data-count]").forEach(animateCount);

  function textOf(el) {
    return moneyText(((el && el.textContent) || "").replace(/\s+/g, " ").trim());
  }

  function moneyText(value) {
    return String(value || "")
      .replace(/\bXOF\b/gi, "F CFA")
      .replace(/\bXAF\b/gi, "F CFA")
      .replace(/\bFCFA\b/gi, "F CFA")
      .replace(/€/g, "F CFA");
  }

  function iconFor(label) {
    var l = (label || "").toLowerCase();
    if (l.indexOf("mail") !== -1 || l.indexOf("e-mail") !== -1) return "✉";
    if (l.indexOf("statut") !== -1 || l.indexOf("actif") !== -1) return "●";
    if (l.indexOf("date") !== -1 || l.indexOf("quand") !== -1) return "◷";
    if (l.indexOf("montant") !== -1 || l.indexOf("prix") !== -1) return "F";
    if (l.indexOf("user") !== -1 || l.indexOf("organ") !== -1 || l.indexOf("nom") !== -1) return "●";
    if (l.indexOf("invit") !== -1) return "✦";
    if (l.indexOf("formule") !== -1 || l.indexOf("type") !== -1) return "★";
    return "•";
  }

  function openModal(title, initiale, kicker, cells, href) {
    var modal = document.getElementById("zyz-detail-modal");
    if (!modal) return;
    document.getElementById("zyz-modal-title").textContent = title || "Détail";
    document.getElementById("zyz-modal-avatar").textContent = initiale || "?";
    document.getElementById("zyz-modal-kicker").textContent = kicker || "Fiche";
    var fields = document.getElementById("zyz-modal-fields");
    fields.innerHTML = "";
    cells.forEach(function (c) {
      var li = document.createElement("li");
      li.innerHTML =
        '<span class="zyz-modal-ico" aria-hidden="true">' +
        iconFor(c.label) +
        "</span><div><em></em><strong></strong></div>";
      li.querySelector("em").textContent = c.label || "Info";
      li.querySelector("strong").textContent = c.value;
      fields.appendChild(li);
    });
    var edit = document.getElementById("zyz-modal-edit");
    if (href) {
      edit.href = href;
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

  document.querySelectorAll("[data-zyz-close]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      closeModal();
      closeConfirm();
      setNav(false);
    }
  });

  var confirmModal = document.getElementById("cx-confirm-modal");
  var confirmTitle = document.getElementById("cx-confirm-title");
  var confirmText = document.getElementById("cx-confirm-text");
  var confirmOk = document.getElementById("cx-confirm-ok");
  var confirmKicker = document.getElementById("cx-confirm-kicker");
  var pendingConfirm = null;

  function closeConfirm() {
    if (!confirmModal) return;
    confirmModal.hidden = true;
    confirmModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("zyz-modal-open");
    pendingConfirm = null;
  }

  function openConfirm(opts) {
    if (!confirmModal) return false;
    pendingConfirm = opts || {};
    if (confirmKicker) confirmKicker.textContent = pendingConfirm.kicker || "Confirmation";
    if (confirmTitle) confirmTitle.textContent = pendingConfirm.title || "Confirmer";
    if (confirmText) confirmText.textContent = pendingConfirm.text || "Continuer ?";
    if (confirmOk) {
      confirmOk.textContent = pendingConfirm.ok || "Confirmer";
      confirmOk.classList.toggle("is-danger", !!pendingConfirm.danger);
    }
    confirmModal.querySelector(".cx-confirm-card")?.classList.toggle("is-danger", !!pendingConfirm.danger);
    confirmModal.hidden = false;
    confirmModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("zyz-modal-open");
    return true;
  }

  if (confirmModal) {
    confirmModal.querySelectorAll("[data-cx-confirm-cancel]").forEach(function (el) {
      el.addEventListener("click", closeConfirm);
    });
    if (confirmOk) {
      confirmOk.addEventListener("click", function () {
        var form = pendingConfirm && pendingConfirm.form;
        closeConfirm();
        if (!form) return;
        form.setAttribute("data-cx-confirmed", "1");
        if (typeof form.requestSubmit === "function") form.requestSubmit();
        else form.submit();
      });
    }
  }

  document.querySelectorAll("form[data-cx-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (ev) {
      if (form.getAttribute("data-cx-confirmed") === "1") return;
      if (!confirmModal) return;
      ev.preventDefault();
      openConfirm({
        form: form,
        title: form.getAttribute("data-cx-confirm-title") || "Confirmer",
        text: form.getAttribute("data-cx-confirm") || "Continuer ?",
        ok: form.getAttribute("data-cx-confirm-ok") || "Confirmer",
        danger: /supprim|retir/i.test(form.getAttribute("data-cx-confirm") || ""),
      });
    });
  });

  document.querySelectorAll("table.cx-table").forEach(function (table) {
    var kicker =
      table.getAttribute("data-zyz-kicker") ||
      textOf(document.querySelector(".cx-top h1, .zyz-top h1, .zyz-page-title")) ||
      "Fiche";
    var headers = Array.prototype.map.call(table.querySelectorAll("thead th"), textOf);
    table.querySelectorAll("tbody tr").forEach(function (tr) {
      Array.prototype.forEach.call(tr.children, function (td, i) {
        if (headers[i] && !td.getAttribute("data-label")) {
          td.setAttribute("data-label", headers[i]);
        }
      });
      if (tr.querySelectorAll("td").length < 2) return;
      tr.classList.add("is-zyz-row");
      tr.addEventListener("click", function (ev) {
        if (ev.target.closest("a, button, input, select, textarea, form, label, .cx-row-actions")) return;
        var cells = [];
        var href = "";
        Array.prototype.forEach.call(tr.children, function (td, i) {
          var idcell = td.querySelector(".cx-idcell");
          var value = idcell
            ? textOf(idcell.querySelector("span:last-child") || idcell)
            : textOf(td);
          if (!value) return;
          cells.push({ label: headers[i] || "Info", value: value });
          var link = td.querySelector("a");
          if (link && !href) href = link.href;
        });
        if (!cells.length) return;
        ev.preventDefault();
        var title = cells[0].value;
        var initiale = title.replace(/[^0-9a-zA-ZÀ-ÿ]/g, "").charAt(0).toUpperCase() || "?";
        openModal(title, initiale, kicker, cells, href);
      });
    });
  });
})();
