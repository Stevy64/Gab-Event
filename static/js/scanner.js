/**
 * Scanner terrain (accueil) — réservé aux agents connectés.
 *
 * Flux :
 *  1. Bottom sheet → caméra ou saisie manuelle
 *  2. POST /api/validate/  → recognized | already_used | invalid
 *  3. Si recognized → Valider l'entrée (1 personne) → POST /api/admit/
 *  4. Message de bienvenue + Scanner le suivant / Fermer
 */
(function () {
  "use strict";

  const LOOKUP_URL = "/api/validate/";
  const ADMIT_URL = "/api/admit/";
  const DISMISS_THRESHOLD = 120;

  function resolveEventId() {
    if (window.__SCAN_EVENT_ID__) return window.__SCAN_EVENT_ID__;
    const fromDom = document.getElementById("home-screen")?.getAttribute("data-event-id");
    if (fromDom) return parseInt(fromDom, 10) || null;
    const fromQuery = new URLSearchParams(window.location.search).get("event");
    return fromQuery ? parseInt(fromQuery, 10) || null : null;
  }

  function scanPayload(extra) {
    const body = Object.assign({}, extra || {});
    const eid = resolveEventId();
    if (eid) body.event_id = eid;
    return body;
  }

  function scanQueryString() {
    const eid = resolveEventId();
    return eid ? "/?scan=1&event=" + eid : "/?scan=1";
  }

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
  const btnDismiss = document.getElementById("btn-dismiss-result");
  const btnCloseResult = document.getElementById("btn-close-result");
  const loader = document.getElementById("app-loader");
  const homeScreen = document.getElementById("home-screen");

  if (!sheet) return;

  const ICONS = {
    valid:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#1F9D57"/><path d="M14 24.5l6.5 6.5L34 17" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    already_used:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#D97706"/><path d="M24 14v14" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/><circle cx="24" cy="34" r="2.2" fill="#fff"/></svg>',
    invalid:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#DC3B3B"/><path d="M17 17l14 14M31 17L17 31" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/></svg>',
    vip:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#D4AF37"/><path d="M14 30l4-12 6 8 6-8 4 12H14z" fill="#0F1A2A"/></svg>',
    welcome:
      '<svg viewBox="0 0 48 48" width="40" height="40"><circle cx="24" cy="24" r="22" fill="#1F9D57"/><path d="M16 24c2 4 6 8 8 8s6-4 8-8" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/><circle cx="18" cy="20" r="2" fill="#fff"/><circle cx="30" cy="20" r="2" fill="#fff"/></svg>',
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
    if (window.history) {
      window.history.replaceState({}, "", scanQueryString());
    }
  }

  async function closeSheet() {
    if (!sheet || !backdrop) return;
    await stopCamera();
    closeResultModal(false);
    locked = false;
    pendingGuest = null;
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
    if (window.history) {
      const eid = resolveEventId();
      window.history.replaceState({}, "", eid ? "/?event=" + eid : "/");
    }
  }

  function setResultActions(showNext, nextLabel, dismissLabel) {
    if (btnNext) {
      btnNext.hidden = !showNext;
      btnNext.classList.toggle("is-hidden", !showNext);
      if (nextLabel) btnNext.textContent = nextLabel;
    }
    if (btnDismiss) {
      btnDismiss.hidden = false;
      btnDismiss.classList.remove("is-hidden");
      btnDismiss.textContent = dismissLabel || "Fermer";
    }
  }

  function openResultModal(data) {
    if (!resultModal || !resultCard) return;
    pendingGuest = data.guest || null;
    const g = pendingGuest || {};
    const isVip = !!g.is_vip || g.participant_type === "VIP";
    const fullName = ((g.first_name || "") + " " + (g.last_name || "")).trim();
    resultCard.className = "result-popup " + data.status + (isVip ? " vip" : "");
    if (resultIconWrap) {
      resultIconWrap.className =
        "result-icon-wrap " + data.status + (isVip ? " vip" : "");
    }

    if (data.status === "recognized") {
      resultIcon.innerHTML = isVip ? ICONS.vip : ICONS.valid;
      resultTitle.textContent = isVip ? "Invitation VIP" : "Invitation reconnue";
      resultBody.innerHTML =
        '<div class="guest-hero">' +
        '<strong class="guest-name">' +
        escapeHtml(fullName) +
        "</strong>" +
        (isVip ? '<span class="vip-badge">VIP</span>' : "") +
        '<span class="guest-cat">' +
        escapeHtml((g.category || "").toUpperCase()) +
        "</span>" +
        "<code>" +
        escapeHtml(g.code || "") +
        "</code></div>" +
        '<p class="result-msg">Billet individuel — 1 personne.</p>' +
        '<button type="button" id="btn-admit" class="btn btn-primary btn-xl btn-block">Valider l\'entrée</button>';
      setResultActions(false, "", "Annuler");
      document.getElementById("btn-admit")?.addEventListener("click", () => {
        confirmAdmit(g.code);
      });
    } else if (data.status === "already_used") {
      resultIcon.innerHTML = ICONS.already_used;
      resultTitle.textContent = "Déjà utilisée";
      resultBody.innerHTML =
        '<div class="guest-hero"><strong class="guest-name">' +
        escapeHtml(fullName) +
        '</strong><span class="guest-cat">' +
        escapeHtml(g.category || "") +
        "</span><code>" +
        escapeHtml(g.code || "") +
        '</code></div><p class="result-msg">Cette invitation a déjà été scannée et validée.</p>';
      setResultActions(true, "Scanner le suivant", "Fermer");
      locked = false;
    } else if (data.status === "admitted") {
      resultIcon.innerHTML = ICONS.welcome;
      resultTitle.textContent = "Entrée validée";
      const welcome =
        data.welcome ||
        data.message ||
        (fullName ? "Bienvenue, " + fullName + " !" : "Bienvenue !");
      resultBody.innerHTML =
        '<p class="welcome-message">' +
        escapeHtml(welcome) +
        "</p>" +
        '<div class="guest-hero"><strong class="guest-name">' +
        escapeHtml(fullName) +
        "</strong>" +
        (isVip ? '<span class="vip-badge">VIP</span>' : "") +
        "<code>" +
        escapeHtml(g.code || "") +
        "</code></div>" +
        '<p class="result-msg">Invitation enregistrée. Bonne cérémonie.</p>';
      setResultActions(true, "Scanner le suivant", "Fermer");
      locked = false;
    } else if (data.status === "wrong_event") {
      resultIcon.innerHTML = ICONS.invalid;
      resultTitle.textContent = "Mauvais événement";
      resultBody.innerHTML =
        '<p class="result-msg">' +
        escapeHtml(
          data.message ||
            "Cette invitation n'appartient pas à l'événement ouvert pour le scan."
        ) +
        "</p>";
      setResultActions(true, "Scanner à nouveau", "Fermer");
      locked = false;
    } else {
      resultIcon.innerHTML = ICONS.invalid;
      resultTitle.textContent = "Invitation non reconnue";
      resultBody.innerHTML =
        '<p class="result-msg">' +
        escapeHtml(
          data.message ||
            "Ce QR Code ne correspond à aucune invitation valide pour cet événement."
        ) +
        "</p>";
      setResultActions(true, "Scanner à nouveau", "Fermer");
      locked = false;
    }

    setHidden(resultBackdrop, false);
    setHidden(resultModal, false);
    requestAnimationFrame(() => {
      resultBackdrop.classList.add("is-open");
      resultModal.classList.add("is-open");
      resultCard.classList.add("pop-in");
    });
  }

  async function confirmAdmit(code) {
    showLoader("Enregistrement de l'entrée…");
    try {
      const response = await fetch(ADMIT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify(scanPayload({ code, persons: 1 })),
        credentials: "same-origin",
      });
      const data = await response.json();
      hideLoader();
      if (response.status === 401) {
        showError(data.message || "Session expirée. Reconnectez-vous.");
        closeResultModal(true);
        locked = false;
        return;
      }
      if (data.status === "admitted" || data.status === "already_used") {
        openResultModal(data);
      } else if (data.status === "wrong_event" || data.status === "invalid") {
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
      try {
        await html5QrCode.stop();
      } catch (_) {}
    }
    try {
      await html5QrCode.clear();
    } catch (_) {}
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
      try {
        await html5QrCode.clear();
      } catch (_) {}
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
    if (
      !window.isSecureContext &&
      location.hostname !== "localhost" &&
      location.hostname !== "127.0.0.1"
    ) {
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
        showError(
          "Permission caméra refusée. Autorisez-la dans le navigateur ou saisissez le code."
        );
      } else if (/NotFoundError|Requested device not found|DevicesNotFound/i.test(msg)) {
        showError("Aucune caméra détectée. Utilisez la saisie manuelle.");
      } else if (/NotReadableError|TrackStartError|Could not start/i.test(msg)) {
        showError(
          "Caméra déjà utilisée par une autre application. Fermez-la puis réessayez."
        );
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
        body: JSON.stringify(scanPayload({ code: normalized })),
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
      if (response.status === 401) {
        showError(
          (data && data.message) || "Connectez-vous pour scanner les invitations."
        );
        locked = false;
        return;
      }
      if (response.status === 400) {
        showError(
          (data && data.message) ||
            "Ouvrez le scan depuis un événement pour valider ses invitations."
        );
        locked = false;
        return;
      }
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
        data.status === "invalid" ||
        data.status === "wrong_event"
      ) {
        openResultModal(data);
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
    pendingGuest = null;
    clearError();
    closeResultModal(true);
    await stopCamera();
    if (!sheetOpen) return;
    if (restartCamera) setTimeout(() => startCamera(), 320);
    else showPanel(idlePanel);
  }

  async function dismissAndClose() {
    locked = false;
    pendingGuest = null;
    closeResultModal(true);
    await closeSheet();
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
    if (backdrop)
      backdrop.style.opacity = String(Math.max(0.15, 1 - dragCurrentY / 400));
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

  // Toujours pouvoir fermer le popup (plus de blocage)
  resultBackdrop?.addEventListener("click", () => resetAfterResult(false));
  btnCloseResult?.addEventListener("click", () => resetAfterResult(false));
  btnDismiss?.addEventListener("click", () => {
    if (btnDismiss.textContent === "Annuler") resetAfterResult(false);
    else dismissAndClose();
  });
  btnNext?.addEventListener("click", () => resetAfterResult(true));

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

  (function syncEventLabel() {
    const help = document.getElementById("scan-event-help");
    const title = document.getElementById("sheet-title");
    const name = window.__SCAN_EVENT_NAME__;
    if (name && help) {
      help.textContent =
        "Scan limité à « " + name + " ». Un QR d’un autre événement sera refusé.";
    }
    if (name && title) title.textContent = "Scan · " + name;
  })();

  if (
    window.__OPEN_SCANNER__ ||
    new URLSearchParams(window.location.search).get("scan") === "1"
  ) {
    openSheet();
  }
})();
