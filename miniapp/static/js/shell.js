export function createShellModule(deps) {
  const {
    state,
    elements,
    uiIcon,
    setMode,
    setTab,
    safeLoadCurrentTab,
    HANDBOOK_CATEGORY_META,
  } = deps;

  let swipeStart = null;
  let detailEntryTimer = null;
  let keyboardViewportTimer = null;

  function syncBottomTabBar() {
    const tabBar = elements.bottomTabBar;
    if (!tabBar) return;

    const isMobile = window.matchMedia("(max-width: 760px)").matches;
    tabBar.hidden = !isMobile;
    if (!isMobile) return;

    const activeTab = state.mode === "handbook" ? "aromas" : state.tab;
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
    } else {
      elements.listPanel.classList.remove("hidden-mobile");
      elements.detailPanel.classList.add("hidden-mobile");
    }

    syncBottomTabBar();
  }

  function animateBackToList() {
    elements.detailPanel.classList.remove("swipe-back-armed");
    elements.detailPanel.classList.add("swipe-back-exit");
    window.setTimeout(() => {
      state.mobileView = "list";
      elements.detailPanel.classList.remove("swipe-back-exit");
      elements.detailPanel.style.removeProperty("--swipe-offset");
      syncMobileNavigation();
    }, 180);
  }

  function goBackToList(animated = false) {
    if (animated) {
      animateBackToList();
      return;
    }
    state.mobileView = "list";
    elements.detailPanel.classList.remove("swipe-back-exit", "swipe-back-armed");
    elements.detailPanel.style.removeProperty("--swipe-offset");
    syncMobileNavigation();
  }

  function renderBackButton() {
    const isMobile = window.matchMedia("(max-width: 760px)").matches;
    syncBottomTabBar();
    if (!isMobile) return "";
    return `<button class="back-button visible" onclick="goBackToList(true)">${uiIcon("back")}<span>Назад к списку</span></button>`;
  }

  function enterDetailView() {
    state.mobileView = "detail";
    syncMobileNavigation();
    if (elements.detailPanel) {
      elements.detailPanel.classList.remove("is-entering");
      window.clearTimeout(detailEntryTimer);
      requestAnimationFrame(() => {
        elements.detailPanel.classList.add("is-entering");
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
      field.style.height = `${field.scrollHeight}px`;
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
    const selector = ".tab-button, .mode-button, .back-button, .secondary-button, .status-button, .feedback-button, .primary-button, .icon-corner-button, .bottom-tab-btn";
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

    const viewport = window.visualViewport;
    if (!viewport) return;
    const handleViewportChange = () => {
      const active = document.activeElement;
      if (!(active instanceof HTMLElement)) return;
      if (!active.matches("textarea, input, select, [contenteditable='true']")) return;
      schedule(active, 40, "smooth");
    };
    viewport.addEventListener("resize", handleViewportChange);
    viewport.addEventListener("scroll", handleViewportChange);
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
      // Allow swipe from left edge (first 44px) even over buttons
      const edgeSwipe = touch.clientX < 44;
      if (!edgeSwipe && (isInteractiveTarget(event.target) || isSelectableTextTarget(event.target))) {
        swipeStart = null;
        return;
      }
      swipeStart = { x: touch.clientX, y: touch.clientY, edgeSwipe };
    }, { passive: true });
    elements.detailPanel.addEventListener("touchmove", (event) => {
      if (!swipeStart || state.mobileView !== "detail" || hasActiveTextSelection()) return;
      if (!swipeStart.edgeSwipe && (isInteractiveTarget(event.target) || isSelectableTextTarget(event.target))) return;
      const touch = event.touches[0];
      const dx = Math.max(0, touch.clientX - swipeStart.x);
      const dy = Math.abs(touch.clientY - swipeStart.y);
      if (dx > 10 && dy < 72) {
        elements.detailPanel.classList.add("swipe-back-armed");
        elements.detailPanel.style.setProperty("--swipe-offset", `${Math.min(dx, 96)}px`);
      }
    }, { passive: true });
    elements.detailPanel.addEventListener("touchend", (event) => {
      if (!swipeStart || state.mobileView !== "detail" || hasActiveTextSelection()) return;
      const touch = event.changedTouches[0];
      const dx = touch.clientX - swipeStart.x;
      const dy = Math.abs(touch.clientY - swipeStart.y);
      swipeStart = null;
      if (dx > 72 && dy < 56 && dx > dy * 1.4) {
        goBackToList(true);
        return;
      }
      elements.detailPanel.classList.remove("swipe-back-armed");
      elements.detailPanel.style.removeProperty("--swipe-offset");
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
            return; // already on handbook list — no-op
          }
          if (state.mode !== "handbook") {
            setMode("handbook");
          }
          setTab(rememberedHandbookTab);
          void safeLoadCurrentTab("Не удалось загрузить справочник");
          return;
        }

        if (state.mode === "content" && state.tab === targetTab && state.mobileView === "detail") {
          goBackToList(false);
          return;
        }

        if (state.mode !== "content") {
          setMode("content");
        }
        setTab(targetTab);
        void safeLoadCurrentTab("Не удалось загрузить вкладку");
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
    bindSwipeBack,
    bindBottomTabBar,
  };
}
