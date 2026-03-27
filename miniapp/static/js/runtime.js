export function createRuntimeModule(deps) {
  const {
    state,
    elements,
    MODE_TABS,
    appState,
    timers,
    applyTelegramTheme,
    bindTextareaAutoExpand,
    bindTapAnimation,
    bindPullToRefresh,
    bindSwipeBack,
    bindKeyboardDismiss,
    bindCardKeyboardActivation,
    bindKeyboardViewportAssist,
    bindBottomTabBar,
    setMode,
    setTab,
    loadReferenceAccess,
    loadDrafts,
    loadInbox,
    loadPlans,
    loadReels,
    loadSchedule,
    loadReferences,
    loadSettings,
    loadStatus,
    loadKeywords,
    loadTrends,
    renderCreate,
    showBootFallback,
    hideBootFallback,
    showRuntimeWarning,
    renderPanelLoader,
  } = deps;

  async function loadCurrentTab() {
    // Static action-group + search: show only on handbook tabs
    const isHandbook = !!deps.HANDBOOK_CATEGORY_META[state.tab];
    const refActions = document.getElementById("referenceActions");
    if (refActions) refActions.style.display = isHandbook ? "" : "none";
    // Filters bar (filtersContainer): only show on drafts tab
    const isDrafts = state.tab === "drafts" || (!["create", "inbox", "plans", "schedule", "settings", "status", "keywords", "trends"].includes(state.tab) && !isHandbook);
    const filtersEl = document.getElementById("filtersContainer");
    if (filtersEl) filtersEl.style.display = isDrafts ? "" : "none";

    if (state.tab === "create") return renderCreate();
    if (state.tab === "inbox") return loadInbox();
    if (state.tab === "plans") return loadPlans();
    if (state.tab === "schedule") return loadSchedule();
    if (deps.HANDBOOK_CATEGORY_META[state.tab]) return loadReferences(state.tab);
    if (state.tab === "settings") return loadSettings();
    if (state.tab === "status") return loadStatus();
    if (state.tab === "keywords") return loadKeywords();
    if (state.tab === "trends") return loadTrends();
    return loadDrafts();
  }

  async function safeLoadCurrentTab(prefix = "Не удалось загрузить раздел") {
    const gen = (state._loadGen = (state._loadGen || 0) + 1);
    try {
      await loadCurrentTab();
      if (gen !== state._loadGen) return false;
      hideBootFallback();
      return true;
    } catch (error) {
      if (gen !== state._loadGen) return false;
      console.error("miniapp runtime tab load failed", error);
      showRuntimeWarning(prefix, error);
      hideBootFallback();
      return false;
    }
  }

  async function loadInitialScreen() {
    if (appState.startupLoadInFlight()) return false;
    appState.setStartupLoadInFlight(true);
    showBootFallback(
      "Загружаю интерфейс",
      "Если экран остаётся пустым дольше пары секунд, попробуйте открыть mini app ещё раз.",
      false,
    );
    timers.setBootstrapWatchdog(window.setTimeout(() => {
      if (!appState.isBootstrapped()) {
        showBootFallback(
          "Интерфейс загружается слишком долго",
          "Похоже, стартовый экран отвечает медленнее обычного. Можно повторить загрузку.",
          true,
        );
      }
    }, 1800));

    const result = await Promise.race([
      safeLoadCurrentTab("Не удалось загрузить вкладку"),
      new Promise((resolve) => {
        window.clearTimeout(timers.getBootstrapWatchdog());
        timers.setBootstrapWatchdog(window.setTimeout(() => resolve("timeout"), 8000));
      }),
    ]);

    appState.setStartupLoadInFlight(false);
    window.clearTimeout(timers.getBootstrapWatchdog());

    if (result === true) {
      appState.setBootstrapped(true);
      hideBootFallback();
      return true;
    }
    if (result === "timeout") {
      showBootFallback(
        "Интерфейс загружается слишком долго",
        "Мы не дождались первого ответа. Попробуйте повторить загрузку.",
        true,
      );
    }
    // Mark app-ready even on error/timeout so UI tests don't hang
    document.body.classList.add("app-ready");
    return false;
  }

  async function bootstrap() {
    applyTelegramTheme();
    bindTextareaAutoExpand();
    bindTapAnimation();
    bindPullToRefresh();
    bindSwipeBack();
    bindKeyboardDismiss();
    bindCardKeyboardActivation();
    bindKeyboardViewportAssist();
    elements.modeContent.addEventListener("click", () => {
      setMode("content");
      void safeLoadCurrentTab("Не удалось загрузить раздел контента");
    });
    elements.modeHandbook.addEventListener("click", () => {
      setMode("handbook");
      void safeLoadCurrentTab("Не удалось загрузить справочник");
    });
    elements.settingsButton?.addEventListener("click", () => {
      state.settingsSection = state.settingsSection || "status";
      setMode("content");
      setTab("settings");
      void safeLoadCurrentTab("Не удалось загрузить настройки");
    });

    [elements.kindFilter, elements.statusFilter, elements.feedbackFilter].forEach((field) => field.addEventListener("change", () => {
      loadDrafts();
      _updateFiltersToggleLabel();
    }));

    // Chip filter bridge: click chip → update hidden select → trigger change
    const _filterSelectMap = { kind: elements.kindFilter, status: elements.statusFilter, feedback: elements.feedbackFilter };
    document.querySelectorAll(".filter-chips-row [data-filter]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const filterName = chip.dataset.filter;
        const filterValue = chip.dataset.value;
        const select = _filterSelectMap[filterName];
        if (!select) return;
        select.value = filterValue;
        select.dispatchEvent(new Event("change"));
        // Update active state on chips in same row
        chip.parentElement.querySelectorAll("[data-filter]").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
      });
    });

    // Filters collapse toggle
    const filtersToggleBtn = document.getElementById("filtersToggleBtn");
    const filtersBody = document.getElementById("filtersBody");
    const _updateFiltersToggleLabel = () => {
      const label = document.getElementById("filtersToggleLabel");
      if (!label) return;
      const active = [elements.kindFilter, elements.statusFilter, elements.feedbackFilter]
        .filter((f) => f && f.value).length + (elements.queryFilter?.value ? 1 : 0);
      label.textContent = active > 0 ? `Фильтры (${active})` : "Фильтры";
    };
    if (filtersToggleBtn && filtersBody) {
      filtersToggleBtn.addEventListener("click", () => {
        const isHidden = filtersBody.hidden;
        filtersBody.hidden = !isHidden;
        filtersToggleBtn.classList.toggle("is-open", isHidden);
      });
    }

    elements.queryFilter.addEventListener("input", () => {
      _updateFiltersToggleLabel();
      window.clearTimeout(timers.getReelRefresh());
      timers.setReelRefresh(window.setTimeout(() => {
        if (state.tab === "drafts") {
          void safeLoadCurrentTab("Не удалось обновить черновики");
        }
      }, 300));
    });

    bindBottomTabBar();
    if (MODE_TABS.handbook.find((tab) => tab.id === state.tab)) state.mode = "handbook";
    setMode(state.mode);

    // Show UI immediately — data loads into visible panels with inline loaders
    document.body.classList.add("app-ready");
    appState.setBootstrapped(true);

    if (state.mode === "content") {
      void loadReferenceAccess();
    }
    void safeLoadCurrentTab("Не удалось загрузить вкладку");
  }

  function retryCurrentTab() {
    elements.draftList.innerHTML = renderPanelLoader("Повторяю загрузку");
    void safeLoadCurrentTab("Не удалось загрузить вкладку");
  }

  function bindBootFallbackReload() {
    if (!elements.bootFallbackReload) return;
    elements.bootFallbackReload.addEventListener("click", () => {
      if (appState.isBootstrapped()) {
        retryCurrentTab();
        return;
      }
      window.location.reload();
    });
  }

  function bindStartupErrorFallbacks() {
    window.addEventListener("error", () => {
      if (appState.isBootstrapped()) return;
      showBootFallback(
        "Интерфейс временно недоступен",
        "Во время загрузки произошла ошибка. Попробуйте обновить экран.",
        true,
      );
    });

    window.addEventListener("unhandledrejection", () => {
      if (appState.isBootstrapped()) return;
      showBootFallback(
        "Интерфейс временно недоступен",
        "Во время загрузки произошла ошибка. Попробуйте обновить экран.",
        true,
      );
    });
  }

  return {
    loadCurrentTab,
    safeLoadCurrentTab,
    loadInitialScreen,
    bootstrap,
    retryCurrentTab,
    bindBootFallbackReload,
    bindStartupErrorFallbacks,
  };
}
