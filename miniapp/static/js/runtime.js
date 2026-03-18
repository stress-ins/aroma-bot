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
    renderCreate,
    showBootFallback,
    hideBootFallback,
    showRuntimeWarning,
    renderPanelLoader,
  } = deps;

  async function loadCurrentTab() {
    if (state.tab === "create") return renderCreate();
    if (state.tab === "inbox") return loadInbox();
    if (state.tab === "plans") return loadPlans();
    if (state.tab === "reels") return loadReels();
    if (state.tab === "schedule") return loadSchedule();
    if (deps.HANDBOOK_CATEGORY_META[state.tab]) return loadReferences(state.tab);
    if (state.tab === "settings") return loadSettings();
    if (state.tab === "status") return loadStatus();
    if (state.tab === "keywords") return loadKeywords();
    return loadDrafts();
  }

  async function safeLoadCurrentTab(prefix = "Не удалось загрузить раздел") {
    try {
      await loadCurrentTab();
      hideBootFallback();
      return true;
    } catch (error) {
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

    [elements.kindFilter, elements.statusFilter, elements.feedbackFilter].forEach((field) => field.addEventListener("change", loadDrafts));

    elements.queryFilter.addEventListener("input", () => {
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
