/**
 * Scanner terrain (accueil).
 *
 * Flux :
 *  1. Bottom sheet → caméra (html5-qrcode) ou saisie manuelle
 *  2. POST /api/validate/  → recognized | already_used | invalid
 *  3. Si recognized → choix du nb de personnes → POST /api/admit/
 *
 * Notes prod :
 *  - HTTPS requis pour la caméra (PythonAnywhere OK)
 *  - Classe CSS .camera-live retire le transform du sheet (sinon getUserMedia échoue)
 */
(function () {
  "use strict";

  const LOOKUP_URL = "/api/validate/";
  const ADMIT_URL = "/api/admit/";
  const DISMISS_THRESHOLD = 120;

  const sheet = document.getElementById("scanner-sheet");
  const backdrop = document.getElementById("sheet-backdrop");
  const sheetGrab = document.getElementById("sheet-grab");
  const idlePanel = document.getElementById("idle-panel");
  const cameraPanel = document.getElementById("camera-panel");
  const manualPanel = document.getElementById("manual-panel");
  const resultModal = document.getElementById("result-modal");
  const resultBackdrop = document.getElementById("result-backdrop");
  const resultCard = document.getElementById("result-card");
  const resultIcon = document.getElementById("result-icon");
  const resultIconWrap = document.getElementById("result-icon-wrap");
  const resultTitle = document.getElementById("result-title");
  const resultBody = document.getElementById("result-body");
  const errorMsg = document.getElementById("error-msg");
  const netDot = document.getElementById("net-dot");
  const btnNext = document.getElementById("btn-next");
  const loader = document.getElementById("app-loader");
  const homeScreen = document.getElementById("home-screen");

  const ICONS = {
    valid:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#1F9D57"/><path d="M14 24.5l6.5 6.5L34 17" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    already_used:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#D97706"/><path d="M24 14v14" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/><circle cx="24" cy="34" r="2.2" fill="#fff"/></svg>',
    invalid:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#DC3B3B"/><path d="M17 17l14 14M31 17L17 31" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/></svg>',
    vip:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#D4AF37"/><path d="M14 30l4-12 6 8 6-8 4 12H14z" fill="#0F1A2A"/></svg>',
  };

  let html5QrCode = null;
  let scanning = false;
  let locked = false;
  let sheetOpen = false;
  let dragStartY = null;
  let dragCurrentY = 0;
  let pendingGuest = null;

  function csrfToken() {
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    if (el) return el.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  function setHidden(el, hidden) {
    if (!el) return;
    el.hidden = hidden;
    el.classList.toggle("is-hidden", hidden);
  }

  function showError(message) {
    if (!errorMsg) return;
    errorMsg.textContent = message;
    setHidden(errorMsg, false);
  }

  function clearError() {
    if (!errorMsg) return;
    errorMsg.textContent = "";
    setHidden(errorMsg, true);
  }

  function setOnlineUI() {
    if (!netDot) return;
    netDot.classList.toggle("offline", !navigator.onLine);
  }

  function showLoader(text) {
    if (!loader) return;
    const label = loader.querySelector(".loader-text");
    if (label && text) label.textContent = text;
    setHidden(loader, false);
    loader.classList.add("is-visible");
  }

  function hideLoader() {
    if (!loader) return;
    loader.classList.remove("is-visible");
    setHidden(loader, true);
  }

  function showPanel(panel) {
    [idlePanel, cameraPanel, manualPanel].forEach((p) => {
      if (!p) return;
      const active = p === panel;
      setHidden(p, !active);
      if (active) {
        p.classList.remove("panel-enter");
        void p.offsetWidth;
        p.classList.add("panel-enter");
      }
    });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function openSheet() {
    if (!sheet || !backdrop) return;
    sheetOpen = true;
    setHidden(backdrop, false);
    setHidden(sheet, false);
    sheet.setAttribute("aria-hidden", "false");
    document.body.classList.add("no-scroll");
    void sheet.offsetWidth;
    backdrop.classList.add("is-open");
    sheet.classList.add("is-open");
    sheet.style.transform = "";
    if (homeScreen) homeScreen.classList.add("sheet-active");
    showPanel(idlePanel);
    clearError();
    if (window.history && window.location.search.indexOf("scan=1") === -1) {
      window.history.replaceState({}, "", "/?scan=1");
    }
  }

  async function closeSheet() {
    if (!sheet || !backdrop) return;
    await stopCamera();
    closeResultModal(false);
    sheetOpen = false;
    sheet.classList.remove("is-open");
    backdrop.classList.remove("is-open");
    sheet.style.transform = "";
    sheet.setAttribute("aria-hidden", "true");
    if (homeScreen) homeScreen.classList.remove("sheet-active");
    document.body.classList.remove("no-scroll");
    setTimeout(() => {
      if (!sheetOpen) {
        setHidden(sheet, true);
        setHidden(backdrop, true);
        showPanel(idlePanel);
      }
    }, 320);
    if (window.history) window.history.replaceState({}, "", "/");
  }

  function personsButtons(remaining) {
    let html = '<div class="persons-picker"><p class="persons-label">Combien de personnes entrent ?</p><div class="persons-btns">';
    for (let i = 1; i <= remaining; i++) {
      html +=
        '<button type="button" class="btn-person" data-persons="' +
        i +
        '">' +
        i +
        "</button>";
    }
    html += "</div></div>";
    return html;
  }

  function openResultModal(data) {
    if (!resultModal || !resultCard) return;
    pendingGuest = data.guest || null;
    const g = pendingGuest || {};
    const isVip = !!g.is_vip || g.participant_type === "VIP";
    resultCard.className = "result-popup " + data.status + (isVip ? " vip" : "");
    if (resultIconWrap) {
      resultIconWrap.className =
        "result-icon-wrap " + data.status + (isVip ? " vip" : "");
    }

    if (data.status === "recognized") {
      resultIcon.innerHTML = isVip ? ICONS.vip : ICONS.valid;
      resultTitle.textContent = isVip ? "Invitation VIP" : "Invitation reconnue";
      const remaining = g.places_remaining || 0;
      resultBody.innerHTML =
        '<div class="guest-hero">' +
        '<strong class="guest-name">' +
        escapeHtml((g.first_name || "") + " " + (g.last_name || "")) +
        "</strong>" +
        (isVip ? '<span class="vip-badge">VIP</span>' : "") +
        '<span class="guest-cat">' +
        escapeHtml((g.category || "").toUpperCase()) +
        "</span>" +
        "<code>" +
        escapeHtml(g.code || "") +
        "</code></div>" +
        '<div class="places-grid">' +
        "<div><span>Autorisées</span><strong>" +
        (g.places_allowed || g.places || 1) +
        "</strong></div>" +
        "<div><span>Utilisées</span><strong>" +
        (g.places_used || 0) +
        "</strong></div>" +
        "<div><span>Restantes</span><strong>" +
        remaining +
        "</strong></div></div>" +
        personsButtons(remaining) +
        '<button type="button" id="btn-admit" class="btn btn-primary btn-xl btn-block" disabled>Valider l\'entrée</button>';
      btnNext.classList.add("is-hidden");
      btnNext.hidden = true;
      bindAdmitUI(g.code, remaining);
    } else if (data.status === "already_used") {
      resultIcon.innerHTML = ICONS.already_used;
      resultTitle.textContent = "Places épuisées";
      resultBody.innerHTML =
        '<div class="guest-hero"><strong class="guest-name">' +
        escapeHtml((g.first_name || "") + " " + (g.last_name || "")) +
        '</strong><span class="guest-cat">' +
        escapeHtml(g.category || "") +
        "</span><code>" +
        escapeHtml(g.code || "") +
        '</code></div><p class="result-msg">Toutes les places de cette invitation ont déjà été utilisées.</p>';
      btnNext.hidden = false;
      btnNext.classList.remove("is-hidden");
      btnNext.textContent = "Scanner le suivant";
    } else if (data.status === "admitted") {
      resultIcon.innerHTML = ICONS.valid;
      resultTitle.textContent = "Entrée validée";
      resultBody.innerHTML =
        '<div class="guest-hero"><strong class="guest-name">' +
        escapeHtml((g.first_name || "") + " " + (g.last_name || "")) +
        '</strong></div><p class="result-msg"><strong>' +
        (data.persons || 0) +
        "</strong> personne(s) enregistrée(s).<br>Places restantes : <strong>" +
        (g.places_remaining || 0) +
        "</strong></p>";
      btnNext.hidden = false;
      btnNext.classList.remove("is-hidden");
      btnNext.textContent = "Scanner le suivant";
    } else {
      resultIcon.innerHTML = ICONS.invalid;
      resultTitle.textContent = "Invitation non reconnue";
      resultBody.innerHTML =
        '<p class="result-msg">Ce QR Code ne correspond à aucune invitation valide.</p>';
      btnNext.hidden = false;
      btnNext.classList.remove("is-hidden");
      btnNext.textContent = "Scanner à nouveau";
    }

    setHidden(resultBackdrop, false);
    setHidden(resultModal, false);
    requestAnimationFrame(() => {
      resultBackdrop.classList.add("is-open");
      resultModal.classList.add("is-open");
      resultCard.classList.add("pop-in");
    });
  }

  function bindAdmitUI(code, remaining) {
    let selected = remaining === 1 ? 1 : 0;
    const admitBtn = document.getElementById("btn-admit");
    const picker = resultBody.querySelector(".persons-picker");
    if (remaining === 1 && admitBtn) {
      admitBtn.disabled = false;
      selected = 1;
      picker?.querySelector('[data-persons="1"]')?.classList.add("is-selected");
    }
    resultBody.querySelectorAll(".btn-person").forEach((btn) => {
      btn.addEventListener("click", () => {
        resultBody.querySelectorAll(".btn-person").forEach((b) => b.classList.remove("is-selected"));
        btn.classList.add("is-selected");
        selected = parseInt(btn.getAttribute("data-persons"), 10);
        if (admitBtn) admitBtn.disabled = false;
      });
    });
    admitBtn?.addEventListener("click", async () => {
      if (!selected) return;
      await confirmAdmit(code, selected);
    });
  }

  async function confirmAdmit(code, persons) {
    showLoader("Enregistrement de l'entrée…");
    try {
      const response = await fetch(ADMIT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ code, persons }),
        credentials: "same-origin",
      });
      const data = await response.json();
      hideLoader();
      if (data.status === "admitted") {
        openResultModal(data);
      } else if (data.status === "already_used") {
        openResultModal(data);
      } else {
        showError(data.message || "Impossible d'enregistrer l'entrée.");
        closeResultModal(true);
        showPanel(idlePanel);
        locked = false;
      }
    } catch (_) {
      hideLoader();
      showError("Connexion indisponible. Réessayez.");
      locked = false;
    }
  }

  function closeResultModal(animate) {
    if (!resultModal) return;
    resultBackdrop?.classList.remove("is-open");
    resultModal.classList.remove("is-open");
    resultCard?.classList.remove("pop-in");
    const hide = () => {
      setHidden(resultModal, true);
      setHidden(resultBackdrop, true);
    };
    if (animate === false) hide();
    else setTimeout(hide, 280);
  }

  async function stopCamera() {
    if (sheet) sheet.classList.remove("camera-live");
    if (!html5QrCode) {
      scanning = false;
      return;
    }
    if (scanning) {
      try { await html5QrCode.stop(); } catch (_) {}
    }
    try { await html5QrCode.clear(); } catch (_) {}
    scanning = false;
  }

  function extractScannedCode(raw) {
    const text = String(raw || "").trim();
    if (!text) return "";
    const compact = text.replace(/\s+/g, "").toUpperCase();
    const match = compact.match(/(ATC24|VIP)[-_]?([A-Z0-9]{6})/);
    if (match) return match[1] + "-" + match[2];
    return compact;
  }

  function scanConfig() {
    const el = document.getElementById("qr-reader");
    const width = (el && el.clientWidth) || 260;
    const box = Math.max(160, Math.min(240, Math.floor(width * 0.78)));
    return { fps: 10, qrbox: { width: box, height: box }, aspectRatio: 1.0 };
  }

  async function waitFrames(n) {
    for (let i = 0; i < n; i++) {
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
  }

  async function createScanner() {
    const el = document.getElementById("qr-reader");
    if (!el) throw new Error("Élément scanner manquant");
    if (html5QrCode) {
      try {
        if (html5QrCode.isScanning) await html5QrCode.stop();
      } catch (_) {}
      try { await html5QrCode.clear(); } catch (_) {}
      html5QrCode = null;
    }
    el.innerHTML = "";
    html5QrCode = new Html5Qrcode("qr-reader", { verbose: false });
    return html5QrCode;
  }

  async function startOnCamera(cameraConfig, config) {
    await createScanner();
    await html5QrCode.start(cameraConfig, config, onScanSuccess, () => {});
  }

  async function startCamera() {
    clearError();
    if (!navigator.onLine) {
      showError("Connexion indisponible.");
      return;
    }
    if (typeof Html5Qrcode === "undefined") {
      showError("Bibliothèque de scan indisponible. Utilisez la saisie manuelle.");
      return;
    }
    if (!window.isSecureContext && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
      showError("La caméra nécessite HTTPS. Utilisez la saisie manuelle.");
      return;
    }
    locked = false;
    showPanel(cameraPanel);
    if (sheet) sheet.classList.add("camera-live");
    await waitFrames(2);
    showLoader("Ouverture de la caméra…");
    const config = scanConfig();
    let lastError = null;
    try {
      try {
        await startOnCamera({ facingMode: "environment" }, config);
      } catch (errEnv) {
        lastError = errEnv;
        try {
          await startOnCamera({ facingMode: "user" }, config);
        } catch (errUser) {
          lastError = errUser;
          const cameras = await Html5Qrcode.getCameras().catch(() => []);
          if (!cameras || !cameras.length) throw lastError;
          let started = false;
          for (let i = cameras.length - 1; i >= 0; i--) {
            try {
              await startOnCamera(cameras[i].id, config);
              started = true;
              break;
            } catch (errCam) {
              lastError = errCam;
            }
          }
          if (!started) throw lastError;
        }
      }
      scanning = true;
      hideLoader();
    } catch (err) {
      hideLoader();
      if (sheet) sheet.classList.remove("camera-live");
      showPanel(idlePanel);
      const msg = String((err && (err.message || err.name)) || err || "");
      console.warn("[scanner] camera start failed:", err);
      if (/NotAllowedError|Permission|denied|NotAllowed/i.test(msg)) {
        showError("Permission caméra refusée. Autorisez-la dans le navigateur ou saisissez le code.");
      } else if (/NotFoundError|Requested device not found|DevicesNotFound/i.test(msg)) {
        showError("Aucune caméra détectée. Utilisez la saisie manuelle.");
      } else if (/NotReadableError|TrackStartError|Could not start/i.test(msg)) {
        showError("Caméra déjà utilisée par une autre application. Fermez-la puis réessayez.");
      } else {
        showError("Impossible d'ouvrir la caméra. Essayez la saisie manuelle.");
      }
    }
  }

  async function onScanSuccess(decodedText) {
    if (locked) return;
    locked = true;
    const code = extractScannedCode(decodedText);
    await stopCamera();
    if (!code) {
      locked = false;
      showError("QR Code illisible. Réessayez ou saisissez le code.");
      showPanel(idlePanel);
      return;
    }
    await lookupCode(code);
  }

  async function lookupCode(code) {
    clearError();
    const normalized = extractScannedCode(code);
    if (!navigator.onLine) {
      showError("Connexion indisponible. Vérifiez votre connexion puis réessayez.");
      locked = false;
      showPanel(idlePanel);
      return;
    }
    showLoader("Vérification de l'invitation…");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(LOOKUP_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ code: normalized }),
        credentials: "same-origin",
        signal: controller.signal,
      });
      let data = null;
      try {
        data = await response.json();
      } catch (_) {
        data = null;
      }
      hideLoader();
      showPanel(idlePanel);
      if (!data || !data.status) {
        showError(
          response.status === 403
            ? "Session expirée. Rechargez la page puis réessayez."
            : "Impossible de vérifier cette invitation."
        );
        locked = false;
        return;
      }
      if (
        data.status === "recognized" ||
        data.status === "already_used" ||
        data.status === "invalid"
      ) {
        openResultModal(data);
        if (data.status !== "recognized") locked = false;
      } else {
        showError(data.message || "Réponse inattendue du serveur.");
        locked = false;
      }
    } catch (err) {
      hideLoader();
      locked = false;
      showPanel(idlePanel);
      showError(
        err && err.name === "AbortError"
          ? "Délai dépassé. Réessayez."
          : "Impossible de vérifier cette invitation."
      );
    } finally {
      clearTimeout(timeout);
    }
  }

  async function resetAfterResult(restartCamera) {
    locked = false;
    clearError();
    closeResultModal(true);
    await stopCamera();
    if (!sheetOpen) return;
    if (restartCamera) setTimeout(() => startCamera(), 320);
    else showPanel(idlePanel);
  }

  function onDragStart(clientY) {
    if (!sheetOpen || resultModal?.classList.contains("is-open")) return;
    dragStartY = clientY;
    dragCurrentY = 0;
    sheet.classList.add("is-dragging");
  }

  function onDragMove(clientY) {
    if (dragStartY === null || !sheet) return;
    dragCurrentY = Math.max(0, clientY - dragStartY);
    const desk = window.matchMedia("(min-width: 768px)").matches;
    sheet.style.transform = desk
      ? "translate(-50%, " + dragCurrentY + "px)"
      : "translateY(" + dragCurrentY + "px)";
    if (backdrop) backdrop.style.opacity = String(Math.max(0.15, 1 - dragCurrentY / 400));
  }

  async function onDragEnd() {
    if (dragStartY === null || !sheet) return;
    sheet.classList.remove("is-dragging");
    const shouldClose = dragCurrentY > DISMISS_THRESHOLD;
    dragStartY = null;
    if (backdrop) backdrop.style.opacity = "";
    if (shouldClose) await closeSheet();
    else sheet.style.transform = "";
    dragCurrentY = 0;
  }

  function bindDrag(el) {
    if (!el) return;
    el.addEventListener("touchstart", (e) => onDragStart(e.touches[0].clientY), {
      passive: true,
    });
    el.addEventListener("touchmove", (e) => onDragMove(e.touches[0].clientY), {
      passive: true,
    });
    el.addEventListener("touchend", onDragEnd);
    el.addEventListener("mousedown", (e) => {
      onDragStart(e.clientY);
      const move = (ev) => onDragMove(ev.clientY);
      const up = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        onDragEnd();
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    });
  }

  document.getElementById("btn-open-scanner")?.addEventListener("click", openSheet);
  document.getElementById("btn-close-sheet")?.addEventListener("click", closeSheet);
  backdrop?.addEventListener("click", closeSheet);
  resultBackdrop?.addEventListener("click", () => {
    if (pendingGuest && resultCard?.classList.contains("recognized")) return;
    resetAfterResult(false);
  });

  document.getElementById("btn-start-scan")?.addEventListener("click", startCamera);
  document.getElementById("btn-stop-scan")?.addEventListener("click", async () => {
    await stopCamera();
    showPanel(idlePanel);
  });
  document.getElementById("btn-toggle-manual")?.addEventListener("click", async () => {
    await stopCamera();
    clearError();
    showPanel(manualPanel);
    document.getElementById("id_code")?.focus();
  });
  document.getElementById("btn-close-manual")?.addEventListener("click", () => {
    showPanel(idlePanel);
  });
  btnNext?.addEventListener("click", () => resetAfterResult(true));

  document.getElementById("manual-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("id_code");
    const code = input ? input.value.trim() : "";
    if (!code) return;
    locked = true;
    await lookupCode(code);
  });

  bindDrag(sheetGrab);
  bindDrag(document.querySelector(".scanner-head"));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (resultModal && !resultModal.hidden) resetAfterResult(false);
      else if (sheetOpen) closeSheet();
    }
  });

  window.addEventListener("online", setOnlineUI);
  window.addEventListener("offline", setOnlineUI);
  setOnlineUI();

  if (
    window.__OPEN_SCANNER__ ||
    new URLSearchParams(window.location.search).get("scan") === "1"
  ) {
    openSheet();
  }
})();
