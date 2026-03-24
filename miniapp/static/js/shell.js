export function createShellModule(deps) {
  const {
    state,
    elements,
    uiIcon,
    setMode,
    setTab,
    safeLoadCurrentTab,
    HANDBOOK_CATEGORY_META,
    initScrollFade,
  } = deps;

  let swipeStart = null;
  let detailEntryTimer = null;
  let keyboardViewportTimer = null;

  function syncBottomTabBar() {
    const tabBar = elements.bottomTabBar;
    if (!tabBar) return;

    const isMobile = window.matchMedia("(max-width: 760px)").matches;
    const isTablet = window.matchMedia("(min-width: 761px) and (max-width: 1024px)").matches;
    tabBar.hidden = !(isMobile || isTablet);
    if (!isMobile && !isTablet) return;

    // Map internal tab names to bottom-bar button tabs
    let activeTab = state.mode === "handbook" ? "aromas" : state.tab;
    if (activeTab === "drafts" || activeTab === "trends") activeTab = "inspiration";
    if (activeTab === "plans") activeTab = "content";
    tabBar.querySelectorAll(".bottom-tab-btn").forEach((button) => {
      const isActive = button.dataset.tab === activeTab;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function syncMobileNavigation() {
    const isMobile = window.matchMedia("(max-width: 760px)").matches;
    document.body.classList.toggle("is-mobile-layout", isMobile);
    document.body.classList.toggle("is-detail-view", isMobile && state.mobileView === "detail");

    if (!isMobile) {
      elements.listPanel.classList.remove("hidden-mobile");
      elements.detailPanel.classList.remove("hidden-mobile");
      syncBottomTabBar();
      return;
    }

    if (state.mobileView === "detail") {
      elements.listPanel.classList.add("hidden-mobile");
      elements.detailPanel.classList.remove("hidden-mobile");
      if (initScrollFade) initScrollFade(elements.detailPanel);
    } else {
      elements.listPanel.classList.remove("hidden-mobile");
      elements.detailPanel.classList.add("hidden-mobile");
    }

    syncBottomTabBar();
  }

  function animateBackToList() {
    elements.detailPanel.classList.remove("swipe-back-hint", "swipe-back-ready");
    elements.detailPanel.classList.add("swipe-back-exit");
    window.setTimeout(() => {
      state.mobileView = "list";
      elements.detailPanel.classList.remove("swipe-back-exit");
      elements.detailPanel.style.removeProperty("--swipe-offset");
      syncMobileNavigation();
      if (typeof window._currentTabRefresh === "function") window._currentTabRefresh();
    }, 260);
  }

  function goBackToList(animated = false) {
    if (state._recoWizardOpen) {
      window.Telegram?.WebApp?.BackButton?.hide();
      elements.detailPanel.classList.remove("swipe-back-exit", "swipe-back-hint", "swipe-back-ready");
      elements.detailPanel.style.removeProperty("--swipe-offset");
      if (state._recoWizardStep > 0) {
        window.recoWizardBack?.();
      } else {
        window.closeRecommendationsWizard?.();
      }
      return;
    }
    if (state._fromContext) {
      // Guard: stale context from a different tab should not redirect cross-tab
      if (state._fromContext.tab !== state.tab) {
        state._fromContext = null;
        // fall through to normal list navigation below
      } else {
        const ctx = state._fromContext;
        state._fromContext = null;
        void window.openReference(ctx.slug, ctx.tab);
        return;
      }
    }
    // Saved blend detail — back to saved list
    if (state.viewingSavedBlend && typeof window.openSavedBlends === "function") {
      window.Telegram?.WebApp?.BackButton?.hide();
      elements.detailPanel.classList.remove("swipe-back-exit", "swipe-back-hint", "swipe-back-ready");
      elements.detailPanel.style.removeProperty("--swipe-offset");
      state.viewingSavedBlend = null;
      window.openSavedBlends();
      return;
    }
    // Mentions detail — reset selectedMention and re-render
    if (state.selectedMention && typeof window.closeMentionDetail === "function") {
      window.Telegram?.WebApp?.BackButton?.hide();
      elements.detailPanel.classList.remove("swipe-back-exit", "swipe-back-hint", "swipe-back-ready");
      elements.detailPanel.style.removeProperty("--swipe-offset");
      window.closeMentionDetail();
      state.mobileView = "list";
      syncMobileNavigation();
      return;
    }
    // Settings sub-sections need a full reset, not just a view toggle
    if (state.tab === "settings" && state.settingsInDetail && typeof window.goBackToSettings === "function") {
      window.Telegram?.WebApp?.BackButton?.hide();
      // Clear swipe state before navigating
      elements.detailPanel.classList.remove("swipe-back-exit", "swipe-back-hint", "swipe-back-ready");
      elements.detailPanel.style.removeProperty("--swipe-offset");
      window.goBackToSettings();
      return;
    }
    window.Telegram?.WebApp?.BackButton?.hide();
    if (animated) {
      animateBackToList();
      return;
    }
    state.mobileView = "list";
    elements.detailPanel.classList.remove("swipe-back-exit", "swipe-back-hint", "swipe-back-ready");
    elements.detailPanel.style.removeProperty("--swipe-offset");
    syncMobileNavigation();
    // Re-render current list to ensure content is visible after back-navigation
    if (typeof window._currentTabRefresh === "function") window._currentTabRefresh();
  }

  function renderBackButton(customAction) {
    const isMobile = window.matchMedia("(max-width: 760px)").matches;
    syncBottomTabBar();
    if (customAction) {
      return `<button class="back-button visible" data-action="${customAction}">${uiIcon("back")}<span>Назад</span></button>`;
    }
    return `<button class="back-button visible" data-action="goBackToList" data-args='[${isMobile ? "true" : "false"}]'>${uiIcon("back")}<span>Назад к списку</span></button>`;
  }

  function enterDetailView() {
    const wasDetail = state.mobileView === "detail";
    state.mobileView = "detail";
    syncMobileNavigation();
    window.Telegram?.WebApp?.BackButton?.show();
    // Skip entry animation & scroll reset when already in detail view (e.g. pull-to-refresh)
    if (wasDetail) return;
    if (elements.detailPanel) {
      elements.detailPanel.scrollTop = 0;
      elements.detailPanel.classList.remove("is-entering");
      window.clearTimeout(detailEntryTimer);
      requestAnimationFrame(() => {
        elements.detailPanel.classList.add("is-entering");
        // Re-scroll after layout — prevents mid-page position after async render
        elements.detailPanel.scrollTop = 0;
        window.scrollTo(0, 0);
        detailEntryTimer = window.setTimeout(() => {
          elements.detailPanel?.classList.remove("is-entering");
        }, 280);
      });
    }
    window.scrollTo(0, 0);
  }

  function isInteractiveTarget(target) {
    if (!target || !(target instanceof Element)) return false;
    return Boolean(target.closest("textarea, input, select, button, a, [contenteditable='true']"));
  }

  function isSelectableTextTarget(target) {
    if (!target || !(target instanceof Element)) return false;
    return Boolean(target.closest(".detail-preview, .detail-markdown, .draft-preview, .draft-topic, .detail-title, .section"));
  }

  function hasActiveTextSelection() {
    const selection = window.getSelection?.();
    return Boolean(selection && String(selection).trim().length > 0);
  }

  function isEditingDetailForm() {
    const active = document.activeElement;
    if (!active || !(active instanceof HTMLElement)) return false;
    if (!elements.detailPanel.contains(active)) return false;
    return active.matches("textarea, input, select, [contenteditable='true']");
  }

  function bindTextareaAutoExpand() {
    const resizeTextarea = (field) => {
      if (!(field instanceof HTMLTextAreaElement)) return;
      field.style.height = "auto";
      const maxH = parseFloat(getComputedStyle(field).maxHeight) || Infinity;
      field.style.height = `${Math.min(field.scrollHeight, maxH)}px`;
    };

    const bindField = (field) => {
      if (!(field instanceof HTMLTextAreaElement)) return;
      if (field.dataset.autoExpandBound === "true") {
        resizeTextarea(field);
        return;
      }
      field.dataset.autoExpandBound = "true";
      resizeTextarea(field);
      field.addEventListener("input", () => resizeTextarea(field));
    };

    document.querySelectorAll("textarea").forEach(bindField);

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          if (node.matches("textarea")) {
            bindField(node);
            return;
          }
          node.querySelectorAll?.("textarea").forEach(bindField);
        });
      });
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  function bindKeyboardDismiss() {
    const dismiss = (event) => {
      const active = document.activeElement;
      if (!active || !(active instanceof HTMLElement)) return;
      if (!active.matches("textarea, input")) return;
      const target = event.target;
      if (target instanceof Element && target.closest("textarea, input, select")) return;
      active.blur();
    };
    document.addEventListener("touchstart", dismiss, { passive: true });
    document.addEventListener("mousedown", dismiss, { passive: true });
  }

  function bindTapAnimation() {
    const selector = ".tab-button, .mode-button, .back-button, .secondary-button, .status-button, .feedback-button, .primary-button, .bottom-tab-btn";
    const clearTap = (target) => {
      if (!(target instanceof HTMLElement)) return;
      if (target.dataset.tapTimerId) {
        window.clearTimeout(Number(target.dataset.tapTimerId));
        delete target.dataset.tapTimerId;
      }
      target.classList.remove("is-tapped");
    };

    document.addEventListener("pointerdown", (event) => {
      const target = event.target instanceof Element ? event.target.closest(selector) : null;
      if (!(target instanceof HTMLElement) || target.disabled) return;
      clearTap(target);
      target.classList.add("is-tapped");
      target.dataset.tapTimerId = String(window.setTimeout(() => clearTap(target), 80));
    }, { passive: true });

    document.addEventListener("pointerup", (event) => {
      const target = event.target instanceof Element ? event.target.closest(selector) : null;
      clearTap(target);
    }, { passive: true });

    document.addEventListener("pointercancel", (event) => {
      const target = event.target instanceof Element ? event.target.closest(selector) : null;
      clearTap(target);
    }, { passive: true });
  }

  function bindCardKeyboardActivation() {
    document.addEventListener("keydown", (event) => {
      if (event.defaultPrevented) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const card = target.closest(".interactive-card");
      if (!(card instanceof HTMLElement)) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      card.click();
    });
  }

  function ensureFieldAboveKeyboard(target, behavior = "smooth") {
    if (!(target instanceof HTMLElement)) return;
    const viewportHeight = window.visualViewport?.height || window.innerHeight || 0;
    if (!viewportHeight) return;
    const rect = target.getBoundingClientRect();
    const visibleTop = 84;
    const visibleBottom = viewportHeight - 20;
    if (rect.top >= visibleTop && rect.bottom <= visibleBottom) return;
    target.scrollIntoView({
      behavior,
      block: rect.top < visibleTop ? "start" : "center",
      inline: "nearest",
    });
  }

  function bindKeyboardViewportAssist() {
    const schedule = (target, delay = 0, behavior = "smooth") => {
      if (!(target instanceof HTMLElement)) return;
      window.clearTimeout(keyboardViewportTimer);
      keyboardViewportTimer = window.setTimeout(() => ensureFieldAboveKeyboard(target, behavior), delay);
    };

    document.addEventListener("focusin", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (!target.matches("textarea, input, select, [contenteditable='true']")) return;
      schedule(target, 0, "auto");
      schedule(target, 120, "smooth");
      schedule(target, 260, "smooth");
    });

    document.addEventListener("focusout", () => {
      // Small delay: focus may be moving between fields, not truly leaving
      window.setTimeout(() => {
        const active = document.activeElement;
        if (!(active instanceof HTMLElement) || !active.matches("textarea, input, select, [contenteditable='true']")) {
          document.body.classList.remove("is-keyboard-open");
        }
      }, 150);
    });

    const viewport = window.visualViewport;
    if (!viewport) return;
    let lastViewportH = viewport.height;
    const handleViewportChange = () => {
      // Keyboard is open when visual viewport is meaningfully smaller than layout viewport
      const keyboardVisible = window.innerHeight - viewport.height > 80;
      document.body.classList.toggle("is-keyboard-open", keyboardVisible);
      document.body.style.setProperty("--vv-height", viewport.height + "px");
      // Only scroll-assist when viewport height actually changed (keyboard open/close),
      // not on minor scroll reflows that cause oscillation
      const heightDelta = Math.abs(viewport.height - lastViewportH);
      lastViewportH = viewport.height;
      if (heightDelta < 20) return;
      const active = document.activeElement;
      if (!(active instanceof HTMLElement)) return;
      if (!active.matches("textarea, input, select, [contenteditable='true']")) return;
      schedule(active, 40, "smooth");
    };
    viewport.addEventListener("resize", handleViewportChange);
    viewport.addEventListener("scroll", handleViewportChange);
  }

  function bindPullToRefresh() {
    const THRESHOLD = 64;
    const MAX_PULL = 96;
    let pullStart = null;
    let pulling = false;
    let indicator = null;

    function getIndicator() {
      if (!indicator) {
        indicator = document.createElement("div");
        indicator.className = "pull-to-refresh-indicator";
        indicator.innerHTML = `<span class="ptr-spinner"></span>`;
        document.body.appendChild(indicator);
      }
      return indicator;
    }

    function getScrollParent() {
      const isMobile = window.matchMedia("(max-width: 760px)").matches;
      if (isMobile && state.mobileView === "detail") return elements.detailPanel;
      return null; // list view scrolls via document/body
    }

    function isAtTop() {
      const parent = getScrollParent();
      if (parent) return parent.scrollTop <= 0;
      return (window.scrollY || document.documentElement.scrollTop) <= 0;
    }

    document.addEventListener("touchstart", (e) => {
      if (!isAtTop()) return;
      const touch = e.touches[0];
      if (!touch) return;
      pullStart = { y: touch.clientY, locked: false };
      pulling = false;
    }, { passive: true });

    document.addEventListener("touchmove", (e) => {
      if (!pullStart) return;
      const touch = e.touches[0];
      if (!touch) return;
      const dy = touch.clientY - pullStart.y;

      if (!pullStart.locked) {
        if (dy < 0) { pullStart = null; return; }
        if (dy > 10 && isAtTop()) {
          pullStart.locked = true;
          pulling = true;
        } else {
          return;
        }
      }

      if (!pulling) return;
      const progress = Math.min(dy, MAX_PULL);
      const el = getIndicator();
      el.classList.add("visible");
      el.classList.toggle("ready", dy >= THRESHOLD);
      el.style.setProperty("--ptr-progress", `${progress}px`);
    }, { passive: true });

    document.addEventListener("touchend", async () => {
      if (!pulling || !pullStart) { pullStart = null; pulling = false; return; }
      const el = getIndicator();
      const isReady = el.classList.contains("ready");
      pullStart = null;
      pulling = false;

      if (!isReady) {
        el.classList.remove("visible", "ready");
        el.style.removeProperty("--ptr-progress");
        return;
      }

      el.classList.add("refreshing");
      el.style.setProperty("--ptr-progress", `${THRESHOLD}px`);
      try {
        // Skip PTR on Create tab — nothing to refresh, avoids form re-render
        if (state.tab === "create" && state.mobileView !== "detail") {
          /* no-op */
        } else if (state.mobileView === "detail") {
          if (typeof window.refreshCurrentDetail === "function") {
            await window.refreshCurrentDetail();
          }
        } else {
          // Save scroll position before re-render replaces innerHTML
          const scrollParent = getScrollParent();
          const scrollEl = scrollParent || document.scrollingElement || document.documentElement;
          const savedScroll = scrollEl.scrollTop;
          state.draftId = "";
          state.selectedReference = null;
          await safeLoadCurrentTab("Не удалось обновить");
          // Restore scroll after new content is rendered
          requestAnimationFrame(() => { scrollEl.scrollTop = savedScroll; });
        }
      } finally {
        el.classList.remove("visible", "ready", "refreshing");
        el.style.removeProperty("--ptr-progress");
      }
    }, { passive: true });
  }

  function bindSwipeBack() {
    const isMobile = window.matchMedia("(max-width: 760px)").matches;
    if (!isMobile) return;
    elements.detailPanel.addEventListener("touchstart", (event) => {
      const touch = event.touches[0];
      if (!touch || state.mobileView !== "detail" || hasActiveTextSelection()) {
        swipeStart = null;
        return;
      }
      const edgeSwipe = touch.clientX < 44;
      if (!edgeSwipe && (isInteractiveTarget(event.target) || isSelectableTextTarget(event.target))) {
        swipeStart = null;
        return;
      }
      swipeStart = { x: touch.clientX, y: touch.clientY, edgeSwipe };
    }, { passive: true });
    const panel = elements.detailPanel;
    const resetSwipe = (springBack = false) => {
      panel.classList.remove("swipe-back-hint", "swipe-back-ready");
      if (springBack) {
        panel.style.transition = "transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94), opacity 0.3s ease";
        panel.style.transform = "translateX(0)";
        panel.style.opacity = "1";
        window.setTimeout(() => {
          panel.style.removeProperty("transform");
          panel.style.removeProperty("opacity");
          panel.style.removeProperty("transition");
        }, 300);
      } else {
        panel.style.removeProperty("transform");
        panel.style.removeProperty("opacity");
        panel.style.removeProperty("transition");
      }
    };
    panel.addEventListener("touchmove", (event) => {
      if (!swipeStart || state.mobileView !== "detail" || hasActiveTextSelection()) return;
      if (!swipeStart.edgeSwipe && (isInteractiveTarget(event.target) || isSelectableTextTarget(event.target))) return;
      const touch = event.touches[0];
      const dx = Math.max(0, touch.clientX - swipeStart.x);
      const dy = Math.abs(touch.clientY - swipeStart.y);
      if (dx > 10 && dy < 72) {
        panel.style.removeProperty("transition");
        panel.style.transform = `translateX(${dx}px)`;
        panel.style.opacity = `${1 - (dx / window.innerWidth) * 0.4}`;
        panel.classList.toggle("swipe-back-ready", dx > 72);
      }
    }, { passive: true });
    panel.addEventListener("touchend", (event) => {
      if (!swipeStart || state.mobileView !== "detail" || hasActiveTextSelection()) {
        resetSwipe(true);
        return;
      }
      const touch = event.changedTouches[0];
      const dx = touch.clientX - swipeStart.x;
      const dy = Math.abs(touch.clientY - swipeStart.y);
      swipeStart = null;
      panel.classList.remove("swipe-back-hint", "swipe-back-ready");
      if (dx > 72 && dy < 56 && dx > dy * 1.4) {
        panel.style.transition = "transform 0.25s var(--ease-standard, ease), opacity 0.25s var(--ease-standard, ease)";
        panel.style.transform = "translateX(100%)";
        panel.style.opacity = "0.6";
        window.setTimeout(() => {
          panel.style.removeProperty("transform");
          panel.style.removeProperty("opacity");
          panel.style.removeProperty("transition");
          goBackToList(false);
        }, 260);
      } else {
        resetSwipe(true);
      }
    }, { passive: true });
    panel.addEventListener("touchcancel", () => {
      swipeStart = null;
      resetSwipe(true);
    }, { passive: true });
  }

  function bindBottomTabBar() {
    const tabBar = elements.bottomTabBar;
    if (!tabBar) return;

    tabBar.querySelectorAll(".bottom-tab-btn").forEach((button) => {
      button.addEventListener("click", () => {
        const targetTab = button.dataset.tab;
        if (!targetTab) return;

        if (targetTab === "aromas") {
          const rememberedHandbookTab = state.lastHandbookTab || "aromas";
          if (state.mode === "handbook" && state.mobileView === "detail") {
            goBackToList(false);
            return;
          }
          if (state.mode === "handbook" && state.mobileView === "list") {
            // Already on handbook list — scroll to top
            if (elements.listPanel) elements.listPanel.scrollTop = 0;
            return;
          }
          if (state.mode !== "handbook") {
            setMode("handbook");
          }
          setTab(rememberedHandbookTab);
          void safeLoadCurrentTab("Не удалось загрузить справочник");
          if (elements.listPanel) elements.listPanel.scrollTop = 0;
          return;
        }

        // Settings sub-screen: re-clicking the tab resets to main menu
        if (state.tab === targetTab && targetTab === "settings" && state.settingsInDetail) {
          state.settingsInDetail = false;
          state.settingsSection = null;
          state.mobileView = "list";
          void safeLoadCurrentTab("Не удалось загрузить настройки");
          return;
        }

        // "inspiration" button covers drafts + trends
        const isInspirationArea = targetTab === "inspiration" && ["drafts", "trends"].includes(state.tab);
        // "content" button covers plans (with sub-modes)
        const isContentArea = targetTab === "content" && state.tab === "plans";
        const effectiveMatch = state.tab === targetTab || isInspirationArea || isContentArea;

        if (state.mode === "content" && effectiveMatch && state.mobileView === "list") {
          if (elements.listPanel) elements.listPanel.scrollTop = 0;
          return;
        }

        if (state.mode === "content" && effectiveMatch && state.mobileView === "detail") {
          goBackToList(false);
          return;
        }

        if (state.mode !== "content") {
          setMode("content");
        }
        state.mobileView = "list";

        if (targetTab === "inspiration") {
          const sub = state.inspirationSubTab || "drafts";
          setTab(sub === "trends" ? "trends" : "drafts");
        } else if (targetTab === "content") {
          const sub = state.contentSubTab || "plans";
          if (sub === "plans" || sub === "publications") {
            state.plansSubMode = "publications";
            setTab("plans");
          } else if (sub === "mentions") {
            state.plansSubMode = "mentions";
            setTab("plans");
          } else if (sub === "archive") {
            state.plansSubMode = "archive";
            setTab("plans");
          } else {
            setTab("plans");
          }
        } else {
          setTab(targetTab);
        }
        void safeLoadCurrentTab("Не удалось загрузить вкладку");
        if (elements.listPanel) elements.listPanel.scrollTop = 0;
        if (elements.detailPanel) elements.detailPanel.scrollTop = 0;
      });
    });

    window.addEventListener("resize", syncBottomTabBar);
    syncBottomTabBar();
  }

  return {
    syncMobileNavigation,
    renderBackButton,
    goBackToList,
    enterDetailView,
    isEditingDetailForm,
    bindTextareaAutoExpand,
    bindKeyboardDismiss,
    bindTapAnimation,
    bindCardKeyboardActivation,
    bindKeyboardViewportAssist,
    bindPullToRefresh,
    bindSwipeBack,
    bindBottomTabBar,
  };
}
