export function registerWindowBridge(deps) {
  const {
    state,
    setMode,
    setTab,
    loadSettings,
    renderCreate,
    renderCreateTool,
    retryCurrentTab,
    openDraft,
    openAroma,
    openReference,
    openDailyOilReference,
    copyText,
    openReels,
    openPlan,
    openPlanDetail,
    generateDraftFromPlan,
    openPlanRelatedDraft,
    updateDraft,
    sendDraftToChat,
    deleteDraft,
    saveCarouselSlideText,
    regenerateCarouselSlide,
    regenerateCarouselAll,
    selectCarouselSlideVersion,
    deleteCarouselSlideVersion,
    handleCarouselSlideNoteInput,
    previewCarouselSlide,
    carouselSwiperGoTo,
    downloadCarouselPptx,
    importCarouselPptx,
    exportToCanva,
    importFromCanva,
    saveReelsScenario,
    regenerateReelsStoryboard,
    regenerateAllReelsFrames,
    saveReelsFrameFields,
    saveReelsFramePrompt,
    saveReelsFrameNote,
    regenerateReelsFrame,
    handleReelsFramePromptInput,
    handleReelsFrameNoteInput,
    // V2 reels functions
    regenConcept,
    regenScenario,
    regenCaption,
    regenFrameImage,
    regenFrameImageWithPrompt,
    approveReels,
    scheduleFrameOverlaySave,
    saveFrameImagePrompt,
    autoResize,
    copyReelsCaption,
    openReelsImageFullscreen,
    openReelsPreview,
    // Phase 4
    publishReels,
    retryPlatform,
    saveContentReviewDraft,
    polishContentDraft,
    openKeywordTopic,
    addKeywordItem,
    removeKeywordItem,
    publishDraft,
    cancelPublishSchedule,
    addTodoItem,
    removeTodoItem,
    goBackToList,
    renderReferences,
    // Threads-series slot actions
    regenSlot,
    regenerateSeriesPosts,
    saveThreadsSlot,
    showSlotHistory,
    approveThreadsSeries,
    scheduleThreadsSeries,
    openThreadsScheduler,
    publishThreadsSeriesNow,
    publishScheduledNow,
    retryPublication,
    saveThreadsReviewDraft,
    handleSmartSearch,
    runSmartSearch,
    clearSmartSearch,
    openBlendConstructor,
    toggleEffect,
    selectSpeed,
    selectApp,
    updateConstructBtn,
    submitBlendConstructor,
    openSavedBlends,
    blendSaveCurrentBlend,
    blendCreateContent,
    blendLaunchContent,
    blendRegenerate,
    blendAdjustWithOil,
    deleteSavedBlend,
    connectPlatform,
    createNewTeam,
    createTeamInvite,
    removeTeamMember,
    activatePromo,
    generatePromos,
    goBackToSettings,
    setPlanStatusFilter,
    setPlanPlatformFilter,
    setPlanDateFilter,
    setPlansSubMode,
    setContentSubMode,
    activatePlan,
    addForbiddenPhrase,
    removeForbiddenPhrase,
    addRewrite,
    removeRewrite,
    savePlatformTone,
    saveUploadPostPrefs,
    saveImageModels,
    openMentionDetail,
    closeMentionDetail,
    generateReplies,
    publishReply,
    ignoreMentionAction,
    setMentionsFilter,
    generateReelsImages,
    moveDraftToTeam,
    switchAccountsTeam,
    openRecommendationsWizard,
    closeRecommendationsWizard,
    recoWizardNext,
    recoWizardBack,
    recoSelectMood,
    recoSelectGoal,
    recoUpdateSymptoms,
    recoToggleAroma,
    recoUpdateContra,
    submitRecommendations,
    _selectSchedulerDate,
    _renderThreadsSchedulerDates,
    selectTrendsPlatform,
    selectTrendsPeriod,
    refreshTrends,
    openTrendsPost,
    addMonitoredAccount,
    removeMonitoredAccount,
    addTrackedHashtag,
    removeTrackedHashtag,
  } = deps;

  window.retryCurrentTab = retryCurrentTab;
  window.goBackToList = goBackToList;
  window.setReferenceFilter = (value) => {
    state.referenceFilter = String(value || "");
    renderReferences();
  };
  window.setSymptomParentFilter = (value) => {
    state.referenceFilterParent = String(value || "");
    state.referenceFilter = "";
    renderReferences();
  };

  window.openDraft = openDraft;
  window.openAroma = openAroma;
  window.openReference = openReference;
  window.openDailyOilReference = openDailyOilReference;
  window.copyText = copyText;
  window.openReels = openReels;
  window.openPlan = openPlan;
  window.openPlanDetail = openPlanDetail;
  window.setPlanStatusFilter = setPlanStatusFilter;
  window.setPlanPlatformFilter = setPlanPlatformFilter;
  window.setPlanDateFilter = setPlanDateFilter;
  window.setPlansSubMode = setPlansSubMode;
  window.setContentSubMode = setContentSubMode;
  window.generateDraftFromPlan = generateDraftFromPlan;
  window.openPlanRelatedDraft = openPlanRelatedDraft;
  window.updateDraft = updateDraft;
  window.sendDraftToChat = sendDraftToChat;
  window.deleteDraft = deleteDraft;

  window.saveCarouselSlideText = saveCarouselSlideText;
  window.regenerateCarouselSlide = regenerateCarouselSlide;
  window.regenerateCarouselAll = regenerateCarouselAll;
  window.selectCarouselSlideVersion = selectCarouselSlideVersion;
  window.deleteCarouselSlideVersion = deleteCarouselSlideVersion;
  window.handleCarouselSlideNoteInput = handleCarouselSlideNoteInput;
  window.previewCarouselSlide = previewCarouselSlide;
  window.carouselSwiperGoTo = carouselSwiperGoTo;
  window.downloadCarouselPptx = downloadCarouselPptx;
  window.importCarouselPptx = importCarouselPptx;
  window.exportToCanva = exportToCanva;
  window.importFromCanva = importFromCanva;

  window.saveReelsScenario = saveReelsScenario;
  window.regenerateReelsStoryboard = regenerateReelsStoryboard;
  window.regenerateAllReelsFrames = regenerateAllReelsFrames;
  window.saveReelsFrameFields = saveReelsFrameFields;
  window.saveReelsFramePrompt = saveReelsFramePrompt;
  window.saveReelsFrameNote = saveReelsFrameNote;
  window.regenerateReelsFrame = regenerateReelsFrame;
  window.handleReelsFramePromptInput = handleReelsFramePromptInput;
  window.handleReelsFrameNoteInput = handleReelsFrameNoteInput;

  // V2 reels window bridge
  window.regenConcept = regenConcept;
  window.regenScenario = regenScenario;
  window.regenCaption = regenCaption;
  window.regenFrameImage = regenFrameImage;
  window.regenFrameImageWithPrompt = regenFrameImageWithPrompt;
  window.approveReels = approveReels;
  window.scheduleFrameOverlaySave = scheduleFrameOverlaySave;
  window.saveFrameImagePrompt = saveFrameImagePrompt;
  window.autoResize = autoResize;
  window.copyReelsCaption = copyReelsCaption;
  window.openReelsImageFullscreen = openReelsImageFullscreen;
  window.openReelsPreview = openReelsPreview;
  window.generateReelsImages = generateReelsImages;
  window.publishReels = publishReels;
  window.retryPlatform = retryPlatform;

  // Threads-series slot actions
  window.regenSlot = regenSlot;
  window.regenerateSeriesPosts = regenerateSeriesPosts;
  window.saveThreadsSlot = saveThreadsSlot;
  window.showSlotHistory = showSlotHistory;
  window.approveThreadsSeries = approveThreadsSeries;
  window.scheduleThreadsSeries = scheduleThreadsSeries;
  window.openThreadsScheduler = openThreadsScheduler;
  window.publishThreadsSeriesNow = publishThreadsSeriesNow;
  window.publishScheduledNow = publishScheduledNow;
  window.retryPublication = retryPublication;
  window.saveThreadsReviewDraft = saveThreadsReviewDraft;

  window.publishDraft = publishDraft;
  window.cancelPublishSchedule = cancelPublishSchedule;
  window.saveContentReviewDraft = saveContentReviewDraft;
  window.polishContentDraft = polishContentDraft;
  window.openKeywordTopic = openKeywordTopic;
  window.activatePlan = activatePlan;
  window.addKeywordItem = addKeywordItem;
  window.removeKeywordItem = removeKeywordItem;
  window.addForbiddenPhrase = addForbiddenPhrase;
  window.removeForbiddenPhrase = removeForbiddenPhrase;
  window.addRewrite = addRewrite;
  window.removeRewrite = removeRewrite;
  window.savePlatformTone = savePlatformTone;
  window.saveUploadPostPrefs = saveUploadPostPrefs;
  window.saveImageModels = saveImageModels;
  window.addTodoItem = () => addTodoItem();
  window.removeTodoItem = (id) => removeTodoItem(id);
  window.renderCreateTool = renderCreateTool;

  window.handleSmartSearch = handleSmartSearch;
  window.runSmartSearch = runSmartSearch;
  window.clearSmartSearch = clearSmartSearch;
  window.openBlendConstructor = openBlendConstructor;
  window.toggleEffect = toggleEffect;
  window.selectSpeed = selectSpeed;
  window.selectApp = selectApp;
  window.updateConstructBtn = updateConstructBtn;
  window.submitBlendConstructor = submitBlendConstructor;
  window.openSavedBlends = openSavedBlends;
  window.blendSaveCurrentBlend = blendSaveCurrentBlend;
  window.blendCreateContent = blendCreateContent;
  window.blendLaunchContent = blendLaunchContent;
  window.blendRegenerate = blendRegenerate;
  window.blendAdjustWithOil = blendAdjustWithOil;
  window.deleteSavedBlend = deleteSavedBlend;
  window.connectPlatform = connectPlatform;
  window.createNewTeam = createNewTeam;
  window.createTeamInvite = createTeamInvite;
  window.removeTeamMember = removeTeamMember;
  window.activatePromo = activatePromo;
  window.generatePromos = generatePromos;
  window.goBackToSettings = goBackToSettings;
  window.openMentionDetail = openMentionDetail;
  window.closeMentionDetail = closeMentionDetail;
  window.generateReplies = generateReplies;
  window.publishReply = publishReply;
  window.ignoreMentionAction = ignoreMentionAction;
  window.setMentionsFilter = setMentionsFilter;
  window.moveDraftToTeam = moveDraftToTeam;
  window.switchAccountsTeam = switchAccountsTeam;
  window.addTrackedHashtag = addTrackedHashtag;
  window.removeTrackedHashtag = removeTrackedHashtag;
  window._selectSchedulerDate = _selectSchedulerDate;
  window._renderThreadsSchedulerDates = _renderThreadsSchedulerDates;

  // Recommendations wizard
  window.openRecommendationsWizard = openRecommendationsWizard;
  window.closeRecommendationsWizard = closeRecommendationsWizard;
  window.recoWizardNext = recoWizardNext;
  window.recoWizardBack = recoWizardBack;
  window.recoSelectMood = recoSelectMood;
  window.recoSelectGoal = recoSelectGoal;
  window.recoUpdateSymptoms = recoUpdateSymptoms;
  window.recoToggleAroma = recoToggleAroma;
  window.recoUpdateContra = recoUpdateContra;
  window.submitRecommendations = submitRecommendations;

  window.openImageFullscreen = function(src, title) {
    const existing = document.getElementById("img-fullscreen-modal");
    if (existing) existing.remove();
    const modal = document.createElement("div");
    modal.id = "img-fullscreen-modal";
    modal.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.92);display:flex;align-items:center;justify-content:center;cursor:zoom-out;-webkit-tap-highlight-color:transparent";
    modal.innerHTML = `<img src="${src}" style="max-width:100vw;max-height:100vh;object-fit:contain" alt="${title || ""}">`;
    modal.addEventListener("click", () => modal.remove());
    document.body.appendChild(modal);
  };

  window.expandSection = function(btn) {
    const wrap = btn.closest(".exp-section-wrap");
    if (!wrap) return;
    wrap.querySelector(".exp-collapsed").hidden = true;
    wrap.querySelector(".exp-expanded").hidden = false;
  };

  window.openCreateTool = (toolId = "content") => {
    setMode("content");
    setTab("create");
    renderCreate();
    renderCreateTool(toolId);
  };

  const CHAR_LIMITS = { threads: 500, instagram: 2200, telegram: 1200 };
  window.updateCharCounter = (textarea, kind) => {
    const limit = CHAR_LIMITS[kind] || 2200;
    const len = textarea.value.length;
    const counter = textarea.parentElement?.querySelector(".char-counter");
    if (!counter) return;
    counter.textContent = `${len}/${limit}`;
    counter.classList.toggle("warn", len > limit * 0.8 && len <= limit);
    counter.classList.toggle("over", len > limit);
  };

  window.openSettingsSection = async (section) => {
    const valid = ["keywords", "brand", "accounts", "status", "team", "promo"];
    state.settingsSection = valid.includes(section) ? section : "status";
    state.settingsInDetail = true;
    if (state.tab !== "settings") {
      setMode("content");
      setTab("settings");
    }
    await loadSettings();
  };

  // Compound input handlers (replace multi-call inline oninput)
  window._overlayTextareaInput = function(el) {
    autoResize(el);
    scheduleFrameOverlaySave(el.dataset.draftId, el.dataset.frameId, el.value);
  };

  window._syncCharCount = function(el) {
    const target = document.getElementById(el.dataset.countTarget);
    if (target) target.textContent = el.value.length;
  };

  window._selectInput = function(el) {
    el.select();
  };

  window._scheduleThreadsSeriesFromBtn = function(el) {
    scheduleThreadsSeries(el.dataset.draftId, el.dataset.date, ["morning", "day", "evening"], el);
  };

  // Trends
  window.selectTrendsPlatform = selectTrendsPlatform;
  window.selectTrendsPeriod = selectTrendsPeriod;
  window.refreshTrends = refreshTrends;
  window.openTrendsPost = openTrendsPost;
  window.addMonitoredAccount = addMonitoredAccount;
  window.removeMonitoredAccount = removeMonitoredAccount;

  // ── Global event delegation ────────────────────────────────────────────────
  // Replaces inline onclick/onchange/oninput attributes.
  // Convention:
  //   data-action="fnName" data-args='["arg1","arg2",null]'
  //   null in data-args is replaced with the matched element (replaces `this`).
  //   data-on-change / data-on-input for change/input events.

  function _resolveArgs(el, raw) {
    if (!raw) return [];
    return JSON.parse(raw).map((a) => (a === null ? el : a));
  }

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const fn = window[el.dataset.action];
    if (typeof fn === "function") fn(..._resolveArgs(el, el.dataset.args));
  });

  document.addEventListener("change", (e) => {
    const el = e.target.closest("[data-on-change]");
    if (!el) return;
    const fn = window[el.dataset.onChange];
    if (typeof fn !== "function") return;
    if (el.dataset.guard === "truthy" && !el.value) return;
    const args = _resolveArgs(el, el.dataset.args);
    args.push(el.value, el);
    fn(...args);
  });

  document.addEventListener("input", (e) => {
    const el = e.target.closest("[data-on-input]");
    if (!el) return;
    const fn = window[el.dataset.onInput];
    if (typeof fn !== "function") return;
    const raw = el.dataset.args;
    if (raw) {
      const args = JSON.parse(raw).map((a) => (a === null ? el : a));
      args.push(el.value);
      fn(...args);
    } else {
      fn(el);
    }
  });
}
