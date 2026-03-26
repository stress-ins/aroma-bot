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
    refreshReelsDetail,
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
    setSlidesViewMode,
    setDividerStyle,
    uploadSlideImage,
    downloadCarouselPptx,
    importCarouselPptx,
    exportToCanva,
    importFromCanva,
    selectCanvaDesign,
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
    recoverFrameImage,
    approveReels,
    forceEditReels,
    scheduleFrameOverlaySave,
    saveFrameImagePrompt,
    autoResize,
    copyReelsCaption,
    openReelsImageFullscreen,
    openReelsPreview,
    openBotUploadLink,
    // Video compose & upload
    composeReelVideo,
    uploadReelsVideo,
    cleanReelsVideo,
    checkAndPublish,
    // Phase 4
    publishReels,
    retryPlatform,
    jumpToReelsStep,
    runTechCheck,
    composeReelsVideo,
    reuploadVideo,
    proceedToPublish,
    splitReelsClips,
    notifyWhenReady,
    gradePreview,
    gradeShowProfiles,
    gradeSelectProfile,
    gradeApply,
    startMontage,
    refreshDraftMetrics,
    saveSeriesPost,
    selectCity,
    shareBlend,
    searchStockPhotos,
    selectStockPhoto,
    uploadDraftPhoto,
    adminResetStuck,
    adminRestartWorker,
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
    createContentFromOil,
    createContentFromOilTool,
    toggleDailyOilPicker,
    createContentFromDailyOil,
    toggleReferenceFilters,
    openBlendConstructor,
    addRecoOilToBlend,
    toggleEffect,
    selectSpeed,
    selectApp,
    updateConstructBtn,
    submitBlendConstructor,
    openSavedBlends,
    openSavedBlendDetail,
    savedBlendCreateContent,
    savedBlendLaunchContent,
    deleteSavedBlendFromDetail,
    blendSaveCurrentBlend,
    blendCreateContent,
    blendOfWeek,
    blendLaunchContent,
    blendRegenerate,
    blendAdjustWithOil,
    deleteSavedBlend,
    connectPlatform,
    createNewTeam,
    createTeamInvite,
    removeTeamMember,
    uploadTeamAvatar,
    activatePromo,
    generatePromos,
    goBackToSettings,
    setPlanStatusFilter,
    setPlanPlatformFilter,
    setPlanDateFilter,
    setPlansSubMode,
    setContentSubMode,
    switchContentSubTab,
    activatePlan,
    addForbiddenPhrase,
    removeForbiddenPhrase,
    addRewrite,
    removeRewrite,
    savePlatformTone,
    saveUploadPostPrefs,
    saveImageModels,
    setTheme,
    openMentionDetail,
    closeMentionDetail,
    generateReplies,
    publishReply,
    ignoreMentionAction,
    setMentionsFilter,
    upgradeToFull,
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
    createFromInsight,
    addMonitoredAccount,
    removeMonitoredAccount,
    addMonitoredAccountFromSettings,
    removeMonitoredAccountFromSettings,
    addTrackedHashtag,
    removeTrackedHashtag,
    // New features (roadmap sprint 1-6)
    recommendHashtags,
    applyRecommendedHashtags,
    adaptTone,
    startRepurpose,
    regenSeriesPost,
    regenSeriesAll,
    coherenceCheck,
    generateTrendCards,
    createFromTrendCard,
    openArchiveDetail,
    openArchiveForm,
    savePublication,
    deletePublication,
    importFromUrl,
    toggleArchiveStats,
    setArchivePlatformFilter,
    setArchiveScore,
    bulkImportFromAccount,
    toggleCoachingSummary,
    loadPostCoaching,
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
  window.refreshCurrentDetail = async () => {
    if (state.selectedReels?.draft_id) {
      await refreshReelsDetail(state.selectedReels.draft_id);
    } else if (state.selectedReference?.slug) {
      await openReference(state.selectedReference.slug, state.tab, { quiet: true });
    } else if (state.draftId) {
      await openDraft(state.draftId, { quiet: true });
    }
  };
  window.openPlan = openPlan;
  window.openPlanDetail = openPlanDetail;
  window.setPlanStatusFilter = setPlanStatusFilter;
  window.setPlanPlatformFilter = setPlanPlatformFilter;
  window.setPlanDateFilter = setPlanDateFilter;
  window.setPlansSubMode = setPlansSubMode;
  window.setContentSubMode = setContentSubMode;
  window.switchContentSubTab = switchContentSubTab;
  window.generateDraftFromPlan = generateDraftFromPlan;
  window.openPlanRelatedDraft = openPlanRelatedDraft;
  window.updateDraft = updateDraft;
  window.sendDraftToChat = sendDraftToChat;
  window.deleteDraft = deleteDraft;

  // ── YouTube actions ───────────────────────────────────────────────
  window.youtubeRegenScript = async function(draftId) {
    try {
      await fetchJson(`/api/youtube/${draftId}/regen-script`, { method: "POST", body: "{}" });
      showUiNotice("Перегенерация сценария запущена");
      setTimeout(() => openDraft(draftId), 2000);
    } catch (e) { showRequestError(e); }
  };
  window.youtubeRegenThumbnail = async function(draftId, mode) {
    const noteEl = document.getElementById("youtubeThumbNote");
    const revision_note = noteEl ? noteEl.value.trim() : "";
    try {
      await fetchJson(`/api/youtube/${draftId}/thumbnail`, {
        method: "POST",
        body: JSON.stringify({ mode: mode || "prompt", revision_note }),
      });
      showUiNotice("Генерация обложки запущена");
      setTimeout(() => openDraft(draftId), 3000);
    } catch (e) { showRequestError(e); }
  };
  window.youtubeGenMetadata = async function(draftId) {
    try {
      await fetchJson(`/api/youtube/${draftId}/metadata`, { method: "POST", body: "{}" });
      showUiNotice("Генерация метаданных запущена");
      setTimeout(() => openDraft(draftId), 3000);
    } catch (e) { showRequestError(e); }
  };
  window.youtubeCopySection = function(sectionIndex) {
    const d = state.selected;
    if (!d?.payload?.sections?.[sectionIndex]) return;
    const s = d.payload.sections[sectionIndex];
    const text = s.speaker_text || s.host_text || "";
    if (text) {
      navigator.clipboard.writeText(text).then(() => showUiNotice("Текст скопирован")).catch(() => {});
    }
  };
  window.youtubeCopyAllText = function() {
    const d = state.selected;
    const sections = d?.payload?.sections || [];
    const allText = sections
      .map(s => {
        const label = s.label || s.section_type || "";
        const text = s.speaker_text || s.host_text || "";
        return text ? `[${label}]\n${text}` : "";
      })
      .filter(Boolean)
      .join("\n\n---\n\n");
    if (allText) {
      navigator.clipboard.writeText(allText).then(() => showUiNotice("Весь текст скопирован")).catch(() => {});
    }
  };

  window.saveCarouselSlideText = saveCarouselSlideText;
  window.regenerateCarouselSlide = regenerateCarouselSlide;
  window.regenerateCarouselAll = regenerateCarouselAll;
  window.selectCarouselSlideVersion = selectCarouselSlideVersion;
  window.deleteCarouselSlideVersion = deleteCarouselSlideVersion;
  window.handleCarouselSlideNoteInput = handleCarouselSlideNoteInput;
  window.previewCarouselSlide = previewCarouselSlide;
  window.carouselSwiperGoTo = carouselSwiperGoTo;
  window.setSlidesViewMode = setSlidesViewMode;
  window.setDividerStyle = setDividerStyle;
  window.uploadSlideImage = uploadSlideImage;
  window.downloadCarouselPptx = downloadCarouselPptx;
  window.importCarouselPptx = importCarouselPptx;
  window.exportToCanva = exportToCanva;
  window.importFromCanva = importFromCanva;
  window.selectCanvaDesign = selectCanvaDesign;

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
  window.recoverFrameImage = recoverFrameImage;
  window.approveReels = approveReels;
  window.forceEditReels = forceEditReels;
  window.scheduleFrameOverlaySave = scheduleFrameOverlaySave;
  window.saveFrameImagePrompt = saveFrameImagePrompt;
  window.autoResize = autoResize;
  window.copyReelsCaption = copyReelsCaption;
  window.openReelsImageFullscreen = openReelsImageFullscreen;
  window.openReelsPreview = openReelsPreview;
  window.openBotUploadLink = openBotUploadLink;
  window.upgradeToFull = upgradeToFull;
  window.generateReelsImages = generateReelsImages;
  window.composeReelVideo = composeReelVideo;
  window.uploadReelsVideo = uploadReelsVideo;
  window.cleanReelsVideo = cleanReelsVideo;
  window.checkAndPublish = checkAndPublish;
  window.publishReels = publishReels;
  window.retryPlatform = retryPlatform;
  window.jumpToReelsStep = jumpToReelsStep;
  window.runTechCheck = runTechCheck;
  window.composeReelsVideo = composeReelsVideo;
  window.reuploadVideo = reuploadVideo;
  window.proceedToPublish = proceedToPublish;
  window.splitReelsClips = splitReelsClips;
  window.notifyWhenReady = notifyWhenReady;
  // Color grading
  window.gradePreview = gradePreview;
  window.gradeShowProfiles = gradeShowProfiles;
  window.gradeSelectProfile = gradeSelectProfile;
  window.gradeApply = gradeApply;
  // Auto-montage
  window.startMontage = startMontage;
  // Admin dashboard
  window.adminResetStuck = adminResetStuck;
  window.adminRestartWorker = adminRestartWorker;
  // Missing actions
  window.refreshDraftMetrics = refreshDraftMetrics;
  window.saveSeriesPost = saveSeriesPost;
  window.selectCity = selectCity;
  window.shareBlend = shareBlend;
  window.searchStockPhotos = searchStockPhotos;
  window.selectStockPhoto = selectStockPhoto;
  window.uploadDraftPhoto = uploadDraftPhoto;

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
  window.setTheme = setTheme;
  window.addTodoItem = () => addTodoItem();
  window.removeTodoItem = (id) => removeTodoItem(id);
  window.renderCreateTool = renderCreateTool;

  window.handleSmartSearch = handleSmartSearch;
  window.runSmartSearch = runSmartSearch;
  window.clearSmartSearch = clearSmartSearch;
  window.createContentFromOil = createContentFromOil;
  window.createContentFromOilTool = createContentFromOilTool;
  window.toggleDailyOilPicker = toggleDailyOilPicker;
  window.createContentFromDailyOil = createContentFromDailyOil;
  window.toggleReferenceFilters = toggleReferenceFilters;
  window.openBlendConstructor = openBlendConstructor;
  window.addRecoOilToBlend = addRecoOilToBlend;
  window.toggleEffect = toggleEffect;
  window.selectSpeed = selectSpeed;
  window.selectApp = selectApp;
  window.updateConstructBtn = updateConstructBtn;
  window.submitBlendConstructor = submitBlendConstructor;
  window.openSavedBlends = openSavedBlends;
  window.openSavedBlendDetail = openSavedBlendDetail;
  window.savedBlendCreateContent = savedBlendCreateContent;
  window.savedBlendLaunchContent = savedBlendLaunchContent;
  window.deleteSavedBlendFromDetail = deleteSavedBlendFromDetail;
  window.blendSaveCurrentBlend = blendSaveCurrentBlend;
  window.blendCreateContent = blendCreateContent;
  window.blendOfWeek = blendOfWeek;
  window.blendLaunchContent = blendLaunchContent;
  window.blendRegenerate = blendRegenerate;
  window.blendAdjustWithOil = blendAdjustWithOil;
  window.deleteSavedBlend = deleteSavedBlend;
  window.connectPlatform = connectPlatform;
  window.createNewTeam = createNewTeam;
  window.createTeamInvite = createTeamInvite;
  window.removeTeamMember = removeTeamMember;
  window.uploadTeamAvatar = uploadTeamAvatar;
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

  // New features (roadmap sprint 1-6)
  window.recommendHashtags = recommendHashtags;
  window.applyRecommendedHashtags = applyRecommendedHashtags;
  window.adaptTone = adaptTone;
  window.startRepurpose = startRepurpose;
  window.regenSeriesPost = regenSeriesPost;
  window.regenSeriesAll = regenSeriesAll;
  window.coherenceCheck = coherenceCheck;
  window.generateTrendCards = generateTrendCards;
  window.createFromTrendCard = createFromTrendCard;

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
    const valid = ["keywords", "brand", "accounts", "status", "team", "promo", "monitored", "hashtags", "theme", "city", "admin_dashboard"];
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
    if (!target) return;
    const len = el.value.length;
    target.textContent = `${len} / 500`;
    target.classList.toggle("is-over", len > 500);
    target.classList.toggle("is-warn", len > 480 && len <= 500);
  };

  window._syncSeriesCharCount = function(el) {
    const target = document.getElementById(el.dataset.countTarget);
    if (!target) return;
    const len = el.value.length;
    target.textContent = len;
    target.classList.toggle("is-over", len > 2200);
  };

  window._selectInput = function(el) {
    el.select();
  };

  window._scheduleThreadsSeriesFromBtn = function(el) {
    console.log("[schedule] el:", el, "draftId:", el?.dataset?.draftId, "date:", el?.dataset?.date);
    scheduleThreadsSeries(el.dataset.draftId, el.dataset.date, ["morning", "day", "evening"], el);
  };

  window._copyCodeBlock = function(el) {
    const pre = el.previousElementSibling;
    if (!pre) return;
    navigator.clipboard.writeText(pre.textContent).then(() => {
      el.innerHTML = '<i class="ph ph-check" style="font-size:13px"></i>';
      setTimeout(() => { el.textContent = "Копировать"; }, 1200);
    });
  };

  window._closeSlotHistory = function(el) {
    const overlay = el.closest(".slot-history-overlay");
    if (overlay) overlay.remove();
  };

  window._fillTopicFromSuggestion = function(el) {
    const textarea = el.closest(".create-form")?.querySelector("textarea[name=topic]");
    if (textarea) textarea.value = el.textContent;
  };

  window._dismissBlendContext = function() {
    sessionStorage.removeItem("blend_create_context");
    renderCreateTool(state.selectedCreateTool);
  };

  window._dismissDailyOilContext = function() {
    sessionStorage.removeItem("daily_oil_context");
    renderCreateTool(state.selectedCreateTool);
  };

  // Trends
  window.selectTrendsPlatform = selectTrendsPlatform;
  window.selectTrendsPeriod = selectTrendsPeriod;
  window.refreshTrends = refreshTrends;
  window.openTrendsPost = openTrendsPost;
  window.createFromInsight = createFromInsight;
  window.addMonitoredAccount = addMonitoredAccount;
  window.removeMonitoredAccount = removeMonitoredAccount;
  window.addMonitoredAccountFromSettings = addMonitoredAccountFromSettings;
  window.removeMonitoredAccountFromSettings = removeMonitoredAccountFromSettings;

  // Archive
  window.openArchiveDetail = openArchiveDetail;
  window.openArchiveForm = openArchiveForm;
  window.savePublication = savePublication;
  window.deletePublication = deletePublication;
  window.importFromUrl = importFromUrl;
  window.toggleArchiveStats = toggleArchiveStats;
  window.setArchivePlatformFilter = setArchivePlatformFilter;
  window.setArchiveScore = setArchiveScore;
  window.bulkImportFromAccount = bulkImportFromAccount;
  window.toggleCoachingSummary = toggleCoachingSummary;
  window.loadPostCoaching = loadPostCoaching;

  // ── Global event delegation ────────────────────────────────────────────────
  // Replaces inline onclick/onchange/oninput/onkeydown attributes.
  // Convention:
  //   data-action="fnName" data-args='["arg1","arg2",null]'
  //   null in data-args is replaced with the matched element (replaces `this`).
  //   data-on-change / data-on-input for change/input events.
  //   data-on-keydown="fnName" data-keydown-guard="Enter" data-args-keydown='[]'
  //     for keydown; guard = required key name (optional).

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

  document.addEventListener("submit", (e) => {
    const el = e.target.closest("[data-on-submit]");
    if (!el) return;
    e.preventDefault();
    const fn = window[el.dataset.onSubmit];
    if (typeof fn !== "function") return;
    const args = _resolveArgs(el, el.dataset.args);
    args.push(el, el.querySelector("button"));
    fn(...args);
  });

  document.addEventListener("blur", (e) => {
    const el = e.target.closest("[data-on-blur]");
    if (!el) return;
    const fn = window[el.dataset.onBlur];
    if (typeof fn !== "function") return;
    fn(..._resolveArgs(el, el.dataset.args));
  }, true);

  document.addEventListener("keydown", (e) => {
    const el = e.target.closest("[data-on-keydown]");
    if (!el) return;
    const guard = el.dataset.keydownGuard;
    if (guard && e.key !== guard) return;
    const fn = window[el.dataset.onKeydown];
    if (typeof fn !== "function") return;
    const raw = el.dataset.argsKeydown;
    if (raw) {
      const args = JSON.parse(raw).map((a) => (a === null ? el : a));
      args.push(el.value);
      fn(...args);
    } else {
      fn(el.value, el);
    }
  });
}
