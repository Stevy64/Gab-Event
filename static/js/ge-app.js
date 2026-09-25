/**
 * Gab Event — dock bas + bottom sheets (mobile)
 */
(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function setOpen(el, open) {
    if (!el) return;
    if (open) {
      el.hidden = false;
      requestAnimationFrame(function () { el.classList.add('is-open'); });
    } else {
      el.classList.remove('is-open');
      setTimeout(function () {
        if (!el.classList.contains('is-open')) el.hidden = true;
      }, 380);
    }
  }

  function setBackdrop(open) {
    qsa('.ge-sheet-backdrop').forEach(function (bd) { setOpen(bd, open); });
  }

  function restoreDockActive() {
    qsa('.ge-dock').forEach(function (dock) {
      var key = dock.getAttribute('data-active') || '';
      qsa('.ge-dock-item', dock).forEach(function (item) {
        item.classList.toggle('is-active', item.getAttribute('data-dock') === key);
        item.classList.remove('is-pressed');
      });
    });
  }

  function resetSheetChrome(sheet) {
    if (!sheet) return;
    sheet.style.transform = '';
    sheet.style.height = '';
    sheet.style.maxHeight = '';
    sheet.classList.remove('is-dragging', 'is-expanded');
  }

  function closeAll() {
    qsa('.ge-bottom-sheet').forEach(function (s) {
      resetSheetChrome(s);
      if (s.classList.contains('is-open') || !s.hidden) setOpen(s, false);
    });
    setBackdrop(false);
    document.body.classList.remove('ge-sheet-open');
    qsa('[data-sheet][aria-expanded="true"]').forEach(function (b) {
      b.setAttribute('aria-expanded', 'false');
    });
    restoreDockActive();
  }

  function openSheet(sheet, trigger) {
    if (!sheet) return;
    if (trigger && sheet.id === 'ge-sheet-event-life-confirm') fillLifeConfirm(trigger);
    if (trigger && sheet.id === 'ge-sheet-event-life') fillLifeMenu(trigger);
    qsa('.ge-bottom-sheet.is-open').forEach(function (s) {
      if (s !== sheet) {
        resetSheetChrome(s);
        setOpen(s, false);
      }
    });
    resetSheetChrome(sheet);
    setBackdrop(true);
    setOpen(sheet, true);
    document.body.classList.add('ge-sheet-open');
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
  }

  function dismissDraggedSheet(sheet) {
    resetSheetChrome(sheet);
    sheet._geDragMoved = false;
    if (sheet.classList.contains('ok-event-sheet')) {
      sheet.classList.remove('is-open');
      setTimeout(function () {
        if (!sheet.classList.contains('is-open')) sheet.hidden = true;
      }, 400);
      var overlay = document.getElementById('ok-overlay');
      if (overlay) {
        overlay.classList.remove('is-open');
        overlay.style.opacity = '';
        overlay.hidden = true;
      }
      document.body.classList.remove('ok-sheet-open');
      return;
    }
    closeAll();
  }

  function bindSheetDrag(sheet) {
    if (!sheet || sheet.getAttribute('data-ge-drag') === '1') return;
    sheet.setAttribute('data-ge-drag', '1');

    var startY = null;
    var dy = 0;
    var dragging = false;
    var pointerId = null;
    var baseHeight = 0;
    var THRESHOLD = 120;
    var EXPAND_THRESHOLD = 72;
    var expandable = sheet.hasAttribute('data-ge-expand');

    function isOpen() {
      return sheet.classList.contains('is-open') && !sheet.hidden;
    }

    function fromHandle(target) {
      return !!(target && target.closest && target.closest(
        '.ge-sheet-handle, .ok-event-sheet-handle, .ge-sheet-head, .ok-event-hero'
      ));
    }

    function scroller() {
      return sheet.querySelector('.ge-sheet-scroll') || sheet;
    }

    function applyOffset(offset) {
      var expanded = sheet.classList.contains('is-expanded');
      var bd = document.querySelector('.ge-sheet-backdrop.is-open, #ok-overlay.is-open');
      if (offset < 0 && expandable && !expanded) {
        var lift = Math.min(-offset, window.innerHeight - baseHeight);
        sheet.style.height = (baseHeight + lift) + 'px';
        sheet.style.maxHeight = '100dvh';
        sheet.style.transform = 'translateX(-50%) translateY(0)';
        if (bd) bd.style.opacity = '1';
        return;
      }
      var down = Math.max(0, offset);
      sheet.style.height = '';
      sheet.style.maxHeight = '';
      sheet.style.transform = 'translateX(-50%) translateY(' + down + 'px)';
      if (bd) bd.style.opacity = String(Math.max(0.15, 1 - down / 400));
    }

    function clearBackdropFade() {
      qsa('.ge-sheet-backdrop, #ok-overlay').forEach(function (bd) {
        bd.style.opacity = '';
      });
    }

    sheet.addEventListener('pointerdown', function (e) {
      if (!isOpen() || e.button) return;
      if (e.target.closest('a, button, input, textarea, select, label, summary') && !fromHandle(e.target)) return;
      var box = scroller();
      if (box.scrollTop > 2 && !fromHandle(e.target)) return;
      startY = e.clientY;
      dy = 0;
      dragging = false;
      pointerId = e.pointerId;
      baseHeight = sheet.getBoundingClientRect().height;
    });

    sheet.addEventListener('pointermove', function (e) {
      if (startY === null || e.pointerId !== pointerId) return;
      var next = e.clientY - startY;
      if (!dragging) {
        if (Math.abs(next) < 10) return;
        if (!fromHandle(e.target)) {
          if (next < 0) {
            startY = null;
            return;
          }
          if (scroller().scrollTop > 2) {
            startY = null;
            return;
          }
        }
        dragging = true;
        sheet._geDragMoved = true;
        sheet.classList.add('is-dragging');
        try { sheet.setPointerCapture(e.pointerId); } catch (err) {}
      }
      if (e.cancelable) e.preventDefault();
      dy = next;
      applyOffset(dy);
    }, { passive: false });

    function endDrag(e) {
      if (startY === null) return;
      if (e && pointerId != null && e.pointerId !== pointerId) return;
      var expanded = sheet.classList.contains('is-expanded');
      sheet.classList.remove('is-dragging');
      startY = null;
      pointerId = null;
      dragging = false;
      clearBackdropFade();
      if (expandable && !expanded && dy < -EXPAND_THRESHOLD) {
        sheet.style.transform = '';
        sheet.style.height = '';
        sheet.style.maxHeight = '';
        sheet.classList.add('is-expanded');
      } else if (expandable && expanded && dy > EXPAND_THRESHOLD && dy <= THRESHOLD + 40) {
        sheet.classList.remove('is-expanded');
        sheet.style.transform = '';
        sheet.style.height = '';
        sheet.style.maxHeight = '';
      } else if (dy > THRESHOLD) {
        dismissDraggedSheet(sheet);
      } else {
        sheet.style.transform = '';
        sheet.style.height = '';
        sheet.style.maxHeight = '';
      }
      dy = 0;
    }

    sheet.addEventListener('pointerup', endDrag);
    sheet.addEventListener('pointercancel', endDrag);
    sheet.addEventListener('click', function (e) {
      if (!sheet._geDragMoved) return;
      e.preventDefault();
      e.stopPropagation();
      sheet._geDragMoved = false;
    }, true);
  }

  window.GeSheets = { open: openSheet, close: closeAll, bindDrag: bindSheetDrag };

  function initDock(dock) {
    qsa('.ge-dock-item', dock).forEach(function (item) {
      item.addEventListener('click', function (e) {
        var sheetId = item.getAttribute('data-sheet');
        if (sheetId) {
          e.preventDefault();
          qsa('.ge-dock-item', dock).forEach(function (i) {
            i.classList.remove('is-active', 'is-pressed');
          });
          item.classList.add('is-pressed');
          openSheet(document.getElementById(sheetId), item);
          return;
        }
        qsa('.ge-dock-item', dock).forEach(function (i) {
          i.classList.remove('is-active', 'is-pressed');
        });
        item.classList.add('is-active');
      });
    });
  }

  function dismissToast(host) {
    if (!host || host.classList.contains('is-done')) return;
    host.classList.add('is-done');
    setTimeout(function () {
      if (host.parentNode) host.parentNode.removeChild(host);
    }, 300);
  }

  function initToasts() {
    var host = qs('#ge-toast-host');
    if (!host) return;
    qsa('[data-ge-toast-close]', host).forEach(function (btn) {
      btn.addEventListener('click', function () { dismissToast(host); });
    });
    host.addEventListener('click', function (e) {
      if (e.target === host) dismissToast(host);
    });
    setTimeout(function () { dismissToast(host); }, 2800);
  }

  function initHideHeader() {
    var header = qs('#ge-app-top') || qs('.ge-app-top');
    if (!header) return;
    if (document.body.classList.contains('page-sheet-ui')) return;
    var lastY = window.scrollY;
    var ticking = false;

    function update() {
      var y = window.scrollY;
      var delta = y - lastY;
      if (y < 16) {
        header.classList.remove('is-away');
      } else if (delta > 6) {
        header.classList.add('is-away');
      } else if (delta < -6) {
        header.classList.remove('is-away');
      }
      lastY = y;
      ticking = false;
    }

    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(update);
    }, { passive: true });
  }

  function easeOut(p) { return 1 - Math.pow(1 - p, 3); }

  function parsePct(value) {
    var n = parseFloat(String(value == null ? '' : value).replace(',', '.'));
    return isFinite(n) ? n : 0;
  }

  function animateCount(el) {
    var target = parsePct(el.getAttribute('data-ge-count'));
    if (isNaN(target)) return;
    var suffix = el.getAttribute('data-ge-suffix') || '';
    var decimals = parseInt(el.getAttribute('data-ge-decimals') || '0', 10);
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      el.textContent = target.toFixed(decimals) + suffix;
      return;
    }
    var duration = 1100;
    var t0 = null;
    function tick(now) {
      if (!t0) t0 = now;
      var p = Math.min(1, (now - t0) / duration);
      var value = target * easeOut(p);
      el.textContent = (decimals ? value.toFixed(decimals) : String(Math.round(value))) + suffix;
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function presenceTone(pct) {
    var n = parsePct(pct);
    if (n < 20) return 'red';
    if (n <= 50) return 'orange';
    if (n <= 90) return 'blue';
    return 'green';
  }

  function applyPresenceTone(host, pct) {
    if (!host) return;
    host.setAttribute('data-presence-tone', presenceTone(pct));
  }

  function animateRing(el) {
    var pct = Math.max(0, Math.min(100, parsePct(el.getAttribute('data-ge-ring'))));
    var radius = parseFloat(el.getAttribute('r')) || 56;
    var circ = 2 * Math.PI * radius;
    var host = el.closest('[data-ge-presence], .ge-dash-orb');
    el.style.strokeDasharray = String(circ);
    applyPresenceTone(host, pct);
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      el.style.strokeDashoffset = String(circ * (1 - pct / 100));
      return;
    }
    el.style.strokeDashoffset = String(circ);
    var duration = 1200;
    var t0 = null;
    function tick(now) {
      if (!t0) t0 = now;
      var p = Math.min(1, (now - t0) / duration);
      var current = pct * easeOut(p);
      el.style.strokeDashoffset = String(circ * (1 - current / 100));
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function initDashboardMotion() {
    qsa('[data-ge-count]').forEach(animateCount);
    qsa('[data-ge-ring]').forEach(animateRing);
    qsa('[data-ge-presence]').forEach(function (el) {
      if (el.querySelector('[data-ge-ring]')) return;
      applyPresenceTone(el, el.getAttribute('data-ge-presence'));
    });
  }

  function previewFile(input, targets, opts) {
    var file = input.files && input.files[0];
    if (!file || !file.type || file.type.indexOf('image/') !== 0) return;
    var url = URL.createObjectURL(file);
    targets.forEach(function (el) {
      if (!el) return;
      var img = el.tagName === 'IMG' ? el : qs('img', el);
      if (!img) {
        img = document.createElement('img');
        el.innerHTML = '';
        el.appendChild(img);
      }
      img.src = url;
      img.classList.remove('is-empty');
    });
    if (opts && opts.hero) opts.hero.style.setProperty('--event-color', getComputedStyle(document.documentElement).getPropertyValue('--event-color'));
  }

  function initPhotoPicker() {
    qsa('[data-photo-picker]').forEach(function (box) {
      var input = qs('input[type="file"]', box);
      var img = qs('[data-photo-img]', box);
      var ph = qs('[data-photo-ph]', box);
      var nameEl = qs('[data-photo-name]', box);
      var cta = qs('[data-photo-cta]', box);
      var clearBtn = qs('[data-photo-clear]', box);
      var clearCb = qs('input[name="avatar-clear"]', box);

      function showPhoto(src, label) {
        if (img) {
          img.src = src;
          img.hidden = false;
        }
        if (ph) ph.hidden = true;
        box.classList.add('has-photo');
        box.classList.remove('is-cleared');
        if (nameEl) nameEl.textContent = label || 'Photo actuelle';
        if (cta) cta.textContent = 'Remplacer';
        if (clearBtn) clearBtn.hidden = false;
      }

      function showEmpty() {
        if (img) {
          img.removeAttribute('src');
          img.hidden = true;
        }
        if (ph) ph.hidden = false;
        box.classList.remove('has-photo');
        box.classList.add('is-cleared');
        if (nameEl) nameEl.textContent = 'Aucune photo';
        if (cta) cta.textContent = 'Ajouter une photo';
        if (clearBtn) clearBtn.hidden = true;
      }

      if (input) {
        input.addEventListener('change', function () {
          var file = input.files && input.files[0];
          if (!file || !file.type || file.type.indexOf('image/') !== 0) return;
          if (clearCb) clearCb.checked = false;
          showPhoto(URL.createObjectURL(file), file.name);
        });
      }
      if (clearBtn) {
        clearBtn.addEventListener('click', function () {
          if (clearCb) clearCb.checked = true;
          if (input) input.value = '';
          showEmpty();
        });
      }
    });
  }

  function initStyleStudio() {
    var form = qs('[data-style-form]');
    if (!form) return;
    var hero = qs('[data-style-hero]');
    var flyerBox = qs('[data-style-flyer]');
    var flyerThumb = qs('[data-style-flyer-thumb]');
    var logoEl = qs('[data-style-logo]');
    var logoThumb = qs('[data-style-logo-thumb]');
    var hex = qs('[data-style-hex]');
    var color = qs('.ge-color-input', form);
    var flyerInput = qs('input[name="flyer"]', form);
    var logoInput = qs('input[name="logo"]', form);

    if (flyerInput) {
      flyerInput.addEventListener('change', function () {
        previewFile(flyerInput, [flyerBox, flyerThumb]);
      });
    }
    if (logoInput) {
      logoInput.addEventListener('change', function () {
        previewFile(logoInput, [logoEl, logoThumb]);
        if (logoEl) logoEl.classList.remove('is-empty');
      });
    }
    if (color) {
      color.addEventListener('input', function () {
        var value = color.value || '#16130F';
        if (hero) hero.style.setProperty('--event-color', value);
        if (hex) hex.textContent = value;
      });
    }
  }

  function pageLoaderEl() {
    return document.getElementById('ge-page-loader');
  }

  function isEventPath(pathname) {
    return /^\/evenements\/\d+(\/|$)/.test(pathname || '');
  }

  function showPageLoader(opts) {
    window.__gePageLeaving = true;
    document.documentElement.classList.add('ge-loading');
    document.documentElement.classList.toggle('ge-loading-event', !!(opts && opts.toEvent));
    var el = pageLoaderEl();
    if (el) el.classList.add('is-on');
  }

  function hidePageLoader(force) {
    if (window.__gePageLeaving && !force) return;
    window.__gePageLeaving = false;
    document.documentElement.classList.remove('ge-loading', 'ge-loading-event');
    var el = pageLoaderEl();
    if (el) el.classList.remove('is-on');
  }

  function filenameFromDisposition(header, fallback) {
    if (!header) return fallback;
    var star = /filename\*=(?:UTF-8''|utf-8'')([^;]+)/i.exec(header);
    if (star) {
      try { return decodeURIComponent(star[1].replace(/["']/g, '').trim()); } catch (err) {}
    }
    var plain = /filename=(?:"([^"]+)"|([^;]+))/i.exec(header);
    if (plain) return (plain[1] || plain[2] || '').trim();
    return fallback;
  }

  function initDownloads() {
    document.addEventListener('click', function (e) {
      var a = e.target.closest('a[data-ge-download]');
      if (!a || !a.href || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      hidePageLoader(true);
      a.classList.add('is-busy');
      var fallbackName = a.getAttribute('download') || 'invitation';
      fetch(a.href, { credentials: 'same-origin' })
        .then(function (res) {
          if (!res.ok) throw new Error('download');
          var name = filenameFromDisposition(res.headers.get('Content-Disposition'), fallbackName);
          return res.blob().then(function (blob) { return { blob: blob, name: name }; });
        })
        .then(function (out) {
          var url = URL.createObjectURL(out.blob);
          var link = document.createElement('a');
          link.href = url;
          link.download = out.name || fallbackName;
          document.body.appendChild(link);
          link.click();
          link.remove();
          setTimeout(function () { URL.revokeObjectURL(url); }, 2500);
          var eventId = window.GERoster && window.GERoster.eventId();
          if (eventId && /export|xlsx|excel/i.test(a.href + fallbackName)) {
            window.GERoster.sync(eventId);
          }
        })
        .catch(function () {
          var link = document.createElement('a');
          link.href = a.href;
          link.setAttribute('download', fallbackName);
          link.setAttribute('data-no-loader', '');
          document.body.appendChild(link);
          link.click();
          link.remove();
        })
        .then(function () {
          a.classList.remove('is-busy');
          hidePageLoader(true);
        });
    });
  }

  function shouldLoadForLink(a) {
    if (!a || a.hasAttribute('download') || a.getAttribute('data-no-loader') != null) return false;
    if (a.hasAttribute('data-ge-download') || a.hasAttribute('data-sheet')) return false;
    if (a.target === '_blank' || a.getAttribute('rel') === 'external') return false;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0) return false;
    if (/^(mailto|tel|sms):/i.test(href)) return false;
    try {
      var url = new URL(a.href, location.href);
      if (url.origin !== location.origin) return false;
      if (url.pathname === location.pathname && url.search === location.search && url.hash) return false;
      if (/\/carte\/?$/.test(url.pathname)) return false;
      if (/(?:^|[?&])fmt=(png|pdf)\b/i.test(url.search)) return false;
    } catch (err) {
      return false;
    }
    return true;
  }

  function initPageLoader() {
    hidePageLoader(true);
    document.addEventListener('click', function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (e.target.closest('[data-sheet], [data-sheet-close], [data-no-loader]')) return;
      var a = e.target.closest('a[href]');
      if (!shouldLoadForLink(a)) return;
      var toEvent = false;
      try { toEvent = isEventPath(new URL(a.href, location.href).pathname); } catch (err) {}
      showPageLoader({ toEvent: toEvent });
    });
    document.addEventListener('submit', function (e) {
      if (e.defaultPrevented) return;
      var form = e.target;
      if (!form || form.getAttribute('data-no-loader') != null || form.target === '_blank') return;
      showPageLoader({ toEvent: document.body.classList.contains('page-event') });
    });
    window.addEventListener('pageshow', function () { hidePageLoader(true); });
    window.addEventListener('pagehide', function (e) {
      if (e.persisted) hidePageLoader(true);
    });
  }

  function initPasswordToggles() {
    qsa('input[type="password"]').forEach(function (input) {
      var wrap = input.closest('.ge-field-wrap');
      if (!wrap || wrap.querySelector('[data-pw-toggle]')) return;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ge-pw-toggle';
      btn.setAttribute('data-pw-toggle', '');
      btn.setAttribute('aria-label', 'Voir le mot de passe');
      btn.setAttribute('aria-pressed', 'false');
      btn.innerHTML =
        '<svg class="ge-pw-show" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>' +
        '<svg class="ge-pw-hide" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 10.6A3 3 0 0012 15a3 3 0 002.4-4.4"/><path d="M9.9 5.2A11 11 0 0112 5c6.5 0 10 7 10 7a16.7 16.7 0 01-3.2 3.9"/><path d="M6.1 6.1C3.7 7.8 2 12 2 12s3.5 7 10 7a10.6 10.6 0 003.8-.7"/></svg>';
      wrap.appendChild(btn);
    });
    qsa('[data-pw-toggle]').forEach(function (btn) {
      if (btn._gePwBound) return;
      btn._gePwBound = true;
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var wrap = btn.closest('.ge-field-wrap') || btn.parentElement;
        var input = wrap && wrap.querySelector('input');
        if (!input) return;
        var show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        btn.classList.toggle('is-on', show);
        btn.setAttribute('aria-pressed', show ? 'true' : 'false');
        btn.setAttribute('aria-label', show ? 'Masquer le mot de passe' : 'Voir le mot de passe');
      });
    });
  }

  function initCopyButtons() {
    qsa('[data-copy], [data-copy-input]').forEach(function (btn) {
      if (btn._geCopyBound) return;
      btn._geCopyBound = true;
      btn.addEventListener('click', function () {
        var text = btn.getAttribute('data-copy') || '';
        var sel = btn.getAttribute('data-copy-input');
        if (sel) {
          var el = document.querySelector(sel);
          if (el) text = el.value || el.textContent || text;
        }
        if (!text) return;
        var done = function () {
          btn.classList.add('is-copied');
          var idle = btn.querySelector('[data-copy-idle]');
          var ok = btn.querySelector('[data-copy-done]');
          if (idle && ok) { idle.hidden = true; ok.hidden = false; }
          setTimeout(function () {
            btn.classList.remove('is-copied');
            if (idle && ok) { idle.hidden = false; ok.hidden = true; }
          }, 1800);
        };
        var fallback = function () {
          var field = sel ? document.querySelector(sel) : null;
          if (field && field.select) {
            field.focus();
            field.select();
            try {
              if (document.execCommand('copy')) { done(); return; }
            } catch (err) {}
          }
          window.prompt('Copiez ce lien', text);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(fallback);
        } else {
          fallback();
        }
      });
    });
  }

  function initInviteFields() {
    qsa('.ge-invite-fields input[type="checkbox"]').forEach(function (box) {
      box.addEventListener('change', function () {
        var li = box.closest('li');
        if (li) li.classList.toggle('is-on', box.checked);
      });
    });
  }

  window.GERoster = {
    queueKey: 'ge-admit-queue',
    key: function (eventId) {
      return 'ge-roster-' + String(eventId || '');
    },
    compact: function (code) {
      return String(code || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
    },
    load: function (eventId) {
      try {
        return JSON.parse(localStorage.getItem(this.key(eventId)) || 'null');
      } catch (err) {
        return null;
      }
    },
    save: function (eventId, data) {
      try {
        localStorage.setItem(this.key(eventId), JSON.stringify(data));
      } catch (err) {}
    },
    findGuest: function (eventId, code) {
      var pack = this.load(eventId);
      if (!pack || !pack.guests) return null;
      var needle = this.compact(code);
      if (!needle) return null;
      for (var i = 0; i < pack.guests.length; i += 1) {
        if (this.compact(pack.guests[i].code) === needle) return pack.guests[i];
      }
      return null;
    },
    lookup: function (eventId, code) {
      var guest = this.findGuest(eventId, code);
      if (!guest) {
        return { status: 'invalid', message: 'Ce code n’est pas dans la liste locale (Excel / base synchronisée).' };
      }
      if (guest.is_active === false) {
        return { status: 'invalid', message: 'Invitation désactivée.', guest: guest };
      }
      if ((guest.places_remaining || 0) <= 0 || (guest.places_used || 0) >= (guest.places || 1)) {
        return { status: 'already_used', guest: guest };
      }
      return { status: 'recognized', guest: guest, offline: true };
    },
    markLocalAdmit: function (eventId, code) {
      var pack = this.load(eventId);
      if (!pack || !pack.guests) return null;
      var needle = this.compact(code);
      for (var i = 0; i < pack.guests.length; i += 1) {
        var guest = pack.guests[i];
        if (this.compact(guest.code) !== needle) continue;
        guest.places_used = (guest.places_used || 0) + 1;
        guest.places_remaining = Math.max(0, (guest.places || 1) - guest.places_used);
        this.save(eventId, pack);
        return guest;
      }
      return null;
    },
    queueAdmit: function (eventId, code) {
      var queue = [];
      try { queue = JSON.parse(localStorage.getItem(this.queueKey) || '[]'); } catch (err) {}
      queue.push({ event_id: eventId, code: code, at: Date.now() });
      try { localStorage.setItem(this.queueKey, JSON.stringify(queue)); } catch (err) {}
    },
    pendingCount: function (eventId) {
      var queue = [];
      try { queue = JSON.parse(localStorage.getItem(this.queueKey) || '[]'); } catch (err) {}
      if (!eventId) return queue.length;
      return queue.filter(function (row) { return String(row.event_id) === String(eventId); }).length;
    },
    sync: function (eventId) {
      var self = this;
      if (!eventId || !navigator.onLine) return Promise.resolve(null);
      return fetch('/api/scan-roster/?event_id=' + encodeURIComponent(eventId), {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
          if (!data || !data.guests) return null;
          data.synced_at = Date.now();
          self.save(eventId, data);
          return data;
        })
        .catch(function () { return null; });
    },
    flush: function () {
      var self = this;
      if (!navigator.onLine) return Promise.resolve();
      var queue = [];
      try { queue = JSON.parse(localStorage.getItem(this.queueKey) || '[]'); } catch (err) {}
      if (!queue.length) return Promise.resolve();
      var token = '';
      var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
      if (csrf) token = csrf.value;
      else {
        var match = document.cookie.match(/csrftoken=([^;]+)/);
        token = match ? match[1] : '';
      }
      var left = queue.slice();
      function next() {
        if (!left.length) {
          try { localStorage.setItem(self.queueKey, '[]'); } catch (err) {}
          return Promise.resolve();
        }
        var row = left.shift();
        return fetch('/api/admit/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': token,
          },
          body: JSON.stringify({ code: row.code, persons: 1, event_id: row.event_id }),
        })
          .then(function () { return next(); })
          .catch(function () {
            left.unshift(row);
            try { localStorage.setItem(self.queueKey, JSON.stringify(left)); } catch (err) {}
          });
      }
      return next();
    },
    eventId: function () {
      if (window.__SCAN_EVENT_ID__) return window.__SCAN_EVENT_ID__;
      var host = document.querySelector('[data-event-id]');
      if (host) return parseInt(host.getAttribute('data-event-id'), 10) || null;
      var q = new URLSearchParams(location.search).get('event');
      return q ? parseInt(q, 10) || null : null;
    },
    boot: function () {
      var self = this;
      var eventId = this.eventId();
      if (eventId) this.sync(eventId);
      this.flush();
      window.addEventListener('online', function () {
        self.flush();
        var id = self.eventId();
        if (id) self.sync(id);
      });
    },
  };

  function persistRecentPage() {
    try {
      var path = location.pathname + location.search;
      if (!path || path === '/offline/') return;
      if (/^\/(accounts|payments|console|admin)\b/.test(path)) return;
      var item = { path: path, title: (document.title || '').split('—')[0].trim(), at: Date.now() };
      var list = [];
      try { list = JSON.parse(localStorage.getItem('ge-recent') || '[]'); } catch (err) {}
      list = [item].concat(list.filter(function (x) { return x && x.path !== path; })).slice(0, 12);
      localStorage.setItem('ge-recent', JSON.stringify(list));
    } catch (err) {}
  }

  function prefetchWarm() {
    if (!navigator.onLine || !document.body.classList.contains('page-app')) return;
    var run = window.requestIdleCallback || function (fn) { setTimeout(fn, 700); };
    run(function () {
      ['/mes-evenements/', '/profil/'].forEach(function (url) {
        if (location.pathname === url) return;
        fetch(url, { credentials: 'same-origin', headers: { 'Purpose': 'prefetch' } }).catch(function () {});
      });
    });
  }

  var LIFE_COPY = {
    disable: {
      title: 'Désactiver cet événement ?',
      lead: 'Le scan et le lien d’invitation seront suspendus. Vous pourrez le réactiver tant que la période de validité n’est pas écoulée.',
      submit: 'Désactiver',
      irreversible: false
    },
    enable: {
      title: 'Réactiver cet événement ?',
      lead: 'L’événement redevient actif. Le lien d’invitation reste à republier si besoin.',
      submit: 'Activer',
      irreversible: false
    },
    archive: {
      title: 'Archiver définitivement ?',
      lead: 'Cette manœuvre est irréversible : une fois archivé, l’événement ne pourra plus être réactivé.',
      submit: 'Archiver',
      irreversible: true
    },
    delete: {
      title: 'Supprimer définitivement ?',
      lead: 'Cette manœuvre est irréversible : l’événement, ses invitations et ses présences seront effacés.',
      submit: 'Supprimer',
      irreversible: true
    }
  };

  function fillLifeMenu(trigger) {
    var sheet = qs('#ge-sheet-event-life');
    if (!sheet || !trigger) return;
    var name = trigger.getAttribute('data-life-name') || 'cet événement';
    var actions = (trigger.getAttribute('data-life-actions') || '').split(',').filter(Boolean);
    var note = trigger.getAttribute('data-life-note') || '';
    sheet.setAttribute('data-life-id', trigger.getAttribute('data-life-id') || '');
    sheet.setAttribute('data-life-name', name);
    var title = qs('[data-life-title]', sheet);
    if (title) title.textContent = '« ' + name + ' »';
    var noteEl = qs('[data-life-note]', sheet);
    if (noteEl) {
      noteEl.textContent = note;
      noteEl.hidden = !note;
    }
    qsa('[data-life-act]', sheet).forEach(function (btn) {
      btn.hidden = actions.indexOf(btn.getAttribute('data-life-act')) === -1;
    });
  }

  function fillLifeConfirm(trigger) {
    if (!trigger) return;
    var action = trigger.getAttribute('data-life-act');
    var eventId = trigger.getAttribute('data-life-id');
    var name = trigger.getAttribute('data-life-name') || 'cet événement';
    var copy = LIFE_COPY[action];
    var sheet = qs('#ge-sheet-event-life-confirm');
    var form = sheet && qs('[data-life-form]', sheet);
    if (!copy || !sheet || !form || !eventId) return;
    var title = qs('[data-life-confirm-title]', sheet);
    var lead = qs('[data-life-confirm-lead]', sheet);
    var submit = qs('[data-life-confirm-submit]', sheet);
    var actionInput = qs('[data-life-action-input]', sheet);
    if (title) title.textContent = copy.title;
    if (lead) lead.textContent = '« ' + name + ' » — ' + copy.lead;
    if (submit) {
      submit.textContent = copy.submit;
      submit.classList.toggle('is-danger', !!copy.irreversible);
    }
    if (actionInput) actionInput.value = action;
    var nextInput = form.querySelector('input[name="next"]');
    if (nextInput) nextInput.value = location.pathname || '/mes-evenements/';
    form.action = '/evenements/' + eventId + '/statut/';
    var wrap = trigger.closest('details');
    if (wrap) wrap.open = false;
  }

  function initEventLifeMenu() {
    document.addEventListener('click', function (e) {
      var wrap = e.target.closest('.ge-hub-more-wrap');
      qsa('.ge-hub-more-wrap[open]').forEach(function (el) {
        if (el !== wrap) el.removeAttribute('open');
      });
    });
  }

  function boot() {
    qsa('.ge-dock').forEach(initDock);
    qsa('.ge-sheet-backdrop').forEach(function (el) {
      el.addEventListener('click', closeAll);
    });
    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-sheet-close]')) {
        e.preventDefault();
        closeAll();
        return;
      }
      var trigger = e.target.closest('[data-sheet]');
      if (!trigger || trigger.classList.contains('ge-dock-item')) return;
      var sheet = document.getElementById(trigger.getAttribute('data-sheet'));
      if (!sheet) return;
      e.preventDefault();
      if (sheet.id === 'ge-sheet-event-life') fillLifeMenu(trigger);
      openSheet(sheet, trigger);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeAll();
    });
    initToasts();
    initHideHeader();
    initDashboardMotion();
    initStyleStudio();
    initPhotoPicker();
    initPageLoader();
    initDownloads();
    initPasswordToggles();
    initCopyButtons();
    initInviteFields();
    initEventLifeMenu();
    persistRecentPage();
    prefetchWarm();
    window.GERoster.boot();
    qsa('.ge-bottom-sheet, .ok-event-sheet').forEach(bindSheetDrag);
    var autoSheet = qs('.ge-bottom-sheet[data-open]');
    if (autoSheet) openSheet(autoSheet);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
