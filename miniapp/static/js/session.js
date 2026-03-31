import { sseQueryString } from "./sse-auth.js";

export function createSessionModule(deps) {
  const {
    state,
    elements,
    timers,
    fetchJson,
    renderDraftList,
    renderDraftDetail,
    renderReels,
    renderReelsDetail,
    renderEmptyDetail,
    renderDetailError,
    hasPendingCarouselOperations,
    setCarouselSlideOperation,
    clearAllCarouselOperations,
    isEditingDetailForm,
    syncMobileNavigation,
    enterDetailView,
    openDraft,
    scheduleReelsDetailRefresh,
  } = deps;

  let _reelsEventSource = null;
  let _carouselEventSource = null;
  let _draftEventSource = null;

  function clearBackgroundRefreshes() {
    window.clearTimeout(timers.getReelRefresh());
    window.clearTimeout(timers.getCarouselRefresh());
    window.clearTimeout(timers.getDraftRefresh());
    timers.setReelRefresh(null);
    timers.setCarouselRefresh(null);
    timers.setDraftRefresh(null);
    if (_reelsEventSource) { _reelsEventSource.close(); _reelsEventSource = null; }
    if (_carouselEventSource) { _carouselEventSource.close(); _carouselEventSource = null; }
    if (_draftEventSource) { _draftEventSource.close(); _draftEventSource = null; }
  }

  function isCurrentDraftDetail(draftId) {
    return state.mode === "content" && state.tab === "drafts" && state.mobileView === "detail" && state.draftId === draftId;
  }

  function isCurrentReelsDetail(draftId) {
    return state.mode === "content" && state.tab === "reels" && state.mobileView === "detail" && state.selectedReels?.draft_id === draftId;
  }

  function authQueryString() {
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) return "";
    return `?init_data=${encodeURIComponent(initData)}`;
  }

  function applyTelegramTheme() {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    tg.ready();
    tg.expand();
    // Request fullscreen (Bot API 8.0+); expand() is the fallback
    try { if (tg.requestFullscreen) tg.requestFullscreen(); } catch (_e) {}
    // Match Telegram's native background to our --surface so no dark strips
    // show through safe-area insets (top notch / bottom home indicator).
    const activeTheme = document.body.dataset.theme;
    const themedSurface = {
      "terracotta":"#1a0f09","racing-green":"#0b1c10","champagne":"#352b1e",
      "violet":"#261e38","teal":"#0c1e22","raspberry":"#201020"
    }[activeTheme];
    const surfaceColor = themedSurface || (tg.colorScheme === "dark" ? "#251e18" : "#f5f0e8");
    try { tg.setBackgroundColor(surfaceColor); } catch (_e) {}
    try { tg.setBottomBarColor(surfaceColor); } catch (_e) {}
    const bgColor = tg.themeParams.secondary_bg_color;
    const textColor = tg.themeParams.text_color;
    if (bgColor) document.documentElement.style.setProperty("--panel", bgColor);
    if (textColor) document.documentElement.style.setProperty("--text", textColor);
    document.body.classList.toggle("tg-theme-dark", tg.colorScheme === "dark");
    // contentSafeAreaInset.top covers Telegram chrome bar + iPhone notch (Bot API 8.0+).
    // safeAreaInset.top covers only the iPhone notch (Bot API 7.7+).
    // For older Telegram (no contentSafeAreaInset), add ~44px for the Telegram header bar
    // so content is never hidden under the back button / close bar UI chrome.
    const TG_HEADER_FALLBACK = 44;
    function applyInset() {
      const contentTop = tg.contentSafeAreaInset?.top ?? 0;
      const safeTop = tg.safeAreaInset?.top ?? 0;
      // contentTop = full chrome (preferred). If unavailable, add TG header on top of notch.
      const top = contentTop > 0 ? contentTop : safeTop + TG_HEADER_FALLBACK;
      document.documentElement.style.setProperty("--tg-content-inset-top", `${top}px`);
    }
    applyInset();
    tg.onEvent("safeAreaChanged", applyInset);
    tg.onEvent("contentSafeAreaChanged", applyInset);
    function syncViewportVars() {
      const h = tg.viewportHeight;
      const sh = tg.viewportStableHeight;
      if (h) document.documentElement.style.setProperty("--tg-viewport-height", h + "px");
      if (sh) document.documentElement.style.setProperty("--tg-viewport-stable-height", sh + "px");
      if (syncMobileNavigation) syncMobileNavigation();
    }
    syncViewportVars();
    tg.onEvent("viewportChanged", syncViewportVars);
    if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
    if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    if (tg.BackButton && tg.isVersionAtLeast?.("6.9")) {
      document.body.classList.add("tg-webapp");
      tg.BackButton.onClick(() => window.goBackToList?.(true));
    }
  }

  function applyTheme(theme) {
    const valid = ["terracotta","racing-green","champagne","violet","teal","raspberry"];
    const t = valid.includes(theme) ? theme : "terracotta";
    document.body.dataset.theme = t;
    localStorage.setItem("aromara_theme", t);
    const tg = window.Telegram?.WebApp;
    if (tg) {
      const surfaceMap = {
        "terracotta":   "#1a0f09",
        "racing-green": "#0b1c10",
        "champagne":    "#352b1e",
        "violet":       "#261e38",
        "teal":         "#0c1e22",
        "raspberry":    "#201020",
      };
      const color = surfaceMap[t] || "#1a0f09";
      try { tg.setBackgroundColor(color); } catch (_e) {}
      try { tg.setBottomBarColor(color); } catch (_e) {}
    }
  }

  function filtersToQueryString() {
    const params = new URLSearchParams();
    if (elements.kindFilter.value) params.set("kind", elements.kindFilter.value);
    if (elements.statusFilter.value) params.set("status", elements.statusFilter.value);
    if (elements.feedbackFilter.value) params.set("feedback", elements.feedbackFilter.value);
    if (elements.queryFilter.value.trim()) params.set("query", elements.queryFilter.value.trim());
    params.set("limit", "100");
    return params.toString();
  }

  function initDataHeaders() {
    const initData = window.Telegram?.WebApp?.initData;
    return initData ? { "X-Telegram-Init-Data": initData } : {};
  }

  async function scheduleReelsRefresh(draftId, attempts = 90) {
    if (!draftId) return;
    // Close any existing SSE connection for a different draft
    if (_reelsEventSource) {
      _reelsEventSource.close();
      _reelsEventSource = null;
    }
    // Try SSE first, fallback to polling
    if (typeof EventSource !== "undefined") {
      const qs = await sseQueryString();
      const url = `/api/reels/${draftId}/stream${qs}`;
      const es = new EventSource(url);
      _reelsEventSource = es;
      es.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.error === "not_found") {
            es.close();
            _reelsEventSource = null;
            return;
          }
          // Refresh full detail from API to keep state consistent
          await scheduleReelsDetailRefresh(draftId);
          if (!data.generation_pending) {
            es.close();
            _reelsEventSource = null;
          }
        } catch (_e) { /* ignore parse errors */ }
      };
      es.onerror = () => {
        es.close();
        _reelsEventSource = null;
        if (attempts > 0) {
          // Retry SSE after a short delay; fall back to polling after 3 SSE retries
          window.setTimeout(() => scheduleReelsRefresh(draftId, attempts - 1), 3000);
        } else {
          _pollReelsRefresh(draftId, 90);
        }
      };
    } else {
      _pollReelsRefresh(draftId, attempts);
    }
  }

  function _pollReelsRefresh(draftId, attempts = 90) {
    if (!draftId || attempts <= 0) return;
    window.clearTimeout(timers.getReelRefresh());
    timers.setReelRefresh(window.setTimeout(async () => {
      try {
        const { shouldContinue } = await scheduleReelsDetailRefresh(draftId);
        if (shouldContinue) _pollReelsRefresh(draftId, attempts - 1);
      } catch (_error) {
        _pollReelsRefresh(draftId, attempts - 1);
      }
    }, 4000));
  }

  // ── Draft generation SSE ──────────────────────────────────────────────
  async function _refreshDraftState(draftId) {
    const draft = await fetchJson(`/api/drafts/${draftId}`, { timeout: 10000 });
    const posts = Array.isArray(draft.payload?.threads_posts) ? draft.payload.threads_posts : [];
    state.drafts = state.drafts.map(item =>
      item.draft_id === draft.draft_id ? { ...item, ...draft } : item
    );
    if (isCurrentDraftDetail(draft.draft_id)) {
      state.selected = draft;
      renderDraftList();
      if (!isEditingDetailForm()) renderDraftDetail(draft);
    }
    return { shouldContinue: draft.generation_pending || (draft.kind === "threads_series" && !posts.length) };
  }

  async function scheduleDraftRefresh(draftId, attempts = 90) {
    if (!draftId) return;
    if (_draftEventSource) { _draftEventSource.close(); _draftEventSource = null; }
    if (typeof EventSource !== "undefined") {
      const qs = await sseQueryString();
      const es = new EventSource(`/api/drafts/${draftId}/stream${qs}`);
      _draftEventSource = es;
      es.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.error === "not_found") { es.close(); _draftEventSource = null; return; }
          const { shouldContinue } = await _refreshDraftState(draftId);
          if (!shouldContinue) { es.close(); _draftEventSource = null; }
        } catch (_e) { /* ignore */ }
      };
      es.onerror = () => { es.close(); _draftEventSource = null; _pollDraftRefresh(draftId, attempts); };
    } else {
      _pollDraftRefresh(draftId, attempts);
    }
  }

  function _pollDraftRefresh(draftId, attempts = 90) {
    if (!draftId || attempts <= 0) return;
    window.clearTimeout(timers.getDraftRefresh());
    timers.setDraftRefresh(window.setTimeout(async () => {
      try {
        const { shouldContinue } = await _refreshDraftState(draftId);
        if (shouldContinue) _pollDraftRefresh(draftId, attempts - 1);
      } catch (error) {
        const msg = String(error?.message || "");
        if (msg.includes("401") || msg.includes("403")) return;
        _pollDraftRefresh(draftId, attempts - 1);
      }
    }, 4000));
  }

  // ── Carousel generation SSE ─────────────────────────────────────────
  async function _refreshCarouselState(draftId) {
    const draft = await fetchJson(`/api/carousel/${draftId}`);
    const payload = draft.payload || {};
    const slideImages = Array.isArray(payload.slide_images) ? payload.slide_images : [];
    const slideCount = Array.isArray(payload.slides) ? payload.slides.length : 0;
    const readyCount = slideImages.filter(Boolean).length;
    const prevPayload = state.selected?.draft_id === draftId ? (state.selected.payload || {}) : {};
    const prevImages = Array.isArray(prevPayload.slide_images) ? prevPayload.slide_images : [];
    slideImages.forEach((img, idx) => {
      if (img?.url && !prevImages[idx]?.url) {
        state.openPromptPanels[`carousel:${draftId}:${idx}`] = false;
        // Clear pending operation when image becomes ready
        if (typeof setCarouselSlideOperation === "function") {
          setCarouselSlideOperation(draftId, idx, "");
        }
      }
    });
    // Clear all pending operations when generation is fully done
    if (!draft.generation_pending && typeof clearAllCarouselOperations === "function") {
      clearAllCarouselOperations(draftId);
    }
    state.drafts = state.drafts.map((item) => item.draft_id === draft.draft_id ? { ...item, ...draft } : item);
    if (isCurrentDraftDetail(draft.draft_id)) {
      const prev = state.selected;
      state.selected = draft;
      renderDraftList();
      const detailHasFocus = elements.draftDetail?.contains(document.activeElement);
      // Skip heavy re-render when still generating and nothing meaningful changed
      const stateUnchanged = draft.generation_pending && prev?.generation_pending
        && prev.generation_stage === draft.generation_stage
        && prev.generation_message === draft.generation_message
        && readyCount === (Array.isArray(prevPayload.slide_images) ? prevPayload.slide_images.filter(Boolean).length : 0);
      if (!stateUnchanged && !isEditingDetailForm() && !detailHasFocus && !hasPendingCarouselOperations(draft.draft_id)) {
        renderDraftDetail(draft);
      }
    }
    return { shouldContinue: draft.generation_pending || readyCount < slideCount };
  }

  async function scheduleCarouselRefresh(draftId, attempts = 90) {
    if (!draftId) return;
    if (_carouselEventSource) { _carouselEventSource.close(); _carouselEventSource = null; }
    if (typeof EventSource !== "undefined") {
      const qs = await sseQueryString();
      const es = new EventSource(`/api/carousel/${draftId}/stream${qs}`);
      _carouselEventSource = es;
      es.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.error === "not_found") { es.close(); _carouselEventSource = null; return; }
          if (!data.generation_pending) {
            es.close(); _carouselEventSource = null;
            // Re-render to show completed state (text ready, export buttons, etc.)
            await _refreshCarouselState(draftId);
            // Images may still be loading — use polling fallback
            if (data.images_ready < data.slide_count) _pollCarouselRefresh(draftId, 30);
            return;
          }
          const { shouldContinue } = await _refreshCarouselState(draftId);
          if (!shouldContinue) { es.close(); _carouselEventSource = null; }
        } catch (_e) { /* ignore */ }
      };
      es.onerror = () => { es.close(); _carouselEventSource = null; _pollCarouselRefresh(draftId, attempts); };
    } else {
      _pollCarouselRefresh(draftId, attempts);
    }
  }

  function _pollCarouselRefresh(draftId, attempts = 90) {
    if (!draftId || attempts <= 0) return;
    window.clearTimeout(timers.getCarouselRefresh());
    timers.setCarouselRefresh(window.setTimeout(async () => {
      try {
        const { shouldContinue } = await _refreshCarouselState(draftId);
        if (shouldContinue) _pollCarouselRefresh(draftId, attempts - 1);
      } catch (error) {
        const msg = String(error?.message || "");
        if (msg.includes("401") || msg.includes("403")) return;
        _pollCarouselRefresh(draftId, attempts - 1);
      }
    }, 4000));
  }

  async function loadUserPlan() {
    try {
      const res = await fetch("/api/user/plan", {
        headers: { "Content-Type": "application/json", ...initDataHeaders() },
      });
      if (res.ok) {
        state.userPlan = await res.json();
      }
    } catch (_err) {
      // Non-critical — paywall will fall back gracefully
    }
  }

  async function loadDrafts() {
    const gen = state._loadGen;
    const data = await fetchJson(`/api/drafts?${filtersToQueryString()}&include_metrics=true`, { timeout: 20000 });
    if (gen !== state._loadGen) return;
    state.drafts = data.items || [];
    renderDraftList();
    const preferredId = state.draftId || "";
    if (!preferredId) {
      renderEmptyDetail();
      return;
    }
    if (String(preferredId).startsWith("pending-")) {
      if (state.selected?.draft_id === preferredId) {
        renderDraftDetail(state.selected);
        enterDetailView();
        return;
      }
      state.draftId = "";
      renderEmptyDetail();
      return;
    }
    try {
      await openDraft(preferredId);
    } catch (error) {
      console.error("miniapp failed to open preferred draft", error);
      const message = error?.message === "request_timeout"
        ? "Карточка открывается слишком долго. Список уже загружен, можно повторить открытие."
        : (error?.message || "Не удалось открыть карточку.");
      elements.draftDetail.innerHTML = renderDetailError("Не удалось открыть карточку", message, "openDraft", [preferredId]);
      syncMobileNavigation();
    }
  }

  return {
    clearBackgroundRefreshes,
    isCurrentDraftDetail,
    isCurrentReelsDetail,
    authQueryString,
    applyTelegramTheme,
    applyTheme,
    filtersToQueryString,
    initDataHeaders,
    scheduleReelsRefresh,
    scheduleCarouselRefresh,
    scheduleDraftRefresh,
    loadDrafts,
    loadUserPlan,
  };
}
