/**
 * Installation PWA — Android (beforeinstallprompt) + aide iOS (Ajouter à l'écran d'accueil).
 */
(function () {
  "use strict";

  var deferredPrompt = null;
  var banner = document.getElementById("pwa-install-banner");
  if (!banner) return;

  var btnInstall = document.getElementById("pwa-install-btn");
  var btnClose = document.getElementById("pwa-install-close");
  var hint = document.getElementById("pwa-install-hint");
  var storageKey = "gab-event-pwa-dismissed";

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function isIos() {
    return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
  }

  function isAndroid() {
    return /android/i.test(window.navigator.userAgent);
  }

  function isInstallSurface() {
    return document.body.classList.contains("page-landing");
  }

  function showBanner() {
    if (!isInstallSurface()) return;
    if (isStandalone()) return;
    if (sessionStorage.getItem(storageKey) === "1") return;
    banner.hidden = false;
    banner.classList.add("is-visible");
  }

  function hideBanner(persist) {
    banner.hidden = true;
    banner.classList.remove("is-visible");
    if (persist) sessionStorage.setItem(storageKey, "1");
  }

  if (btnClose) {
    btnClose.addEventListener("click", function () {
      hideBanner(true);
    });
  }

  if (btnInstall) {
    btnInstall.addEventListener("click", async function () {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        try {
          await deferredPrompt.userChoice;
        } catch (_) {}
        deferredPrompt = null;
        hideBanner(true);
        return;
      }
      // iOS : pas d'API d'install — afficher les instructions
      if (hint) hint.hidden = false;
    });
  }

  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
    if (btnInstall) btnInstall.hidden = false;
    if (hint) hint.hidden = true;
    showBanner();
  });

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    hideBanner(true);
  });

  // iOS Safari : pas de beforeinstallprompt — bannière d'aide
  if (isIos() && !isStandalone()) {
    if (btnInstall) {
      btnInstall.textContent = "Comment installer";
      btnInstall.hidden = false;
    }
    if (hint) {
      hint.hidden = false;
      hint.textContent = "Partager, puis Sur l’écran d’accueil.";
    }
    showBanner();
  } else if (isAndroid() && !isStandalone()) {
    setTimeout(function () {
      if (!isStandalone()) {
        if (hint && hint.hidden) {
          hint.hidden = false;
          hint.textContent = "Menu du navigateur → Ajouter à l’écran d’accueil.";
        }
        showBanner();
      }
    }, 4000);
  }
})();
