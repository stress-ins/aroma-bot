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
    downloadSlideImage,
    uploadSlideImage,
    uploadSlideImageFromInput,
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
    openIntelligenceOpp,
    createFromIntelligence,
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

  // ALL window exports use deps.X (aliased as d) to avoid Vite minifier
  // variable reuse bug — destructured locals get short names that collide.
  // Destructured local vars (short names like j, J, he) collide across scopes.
  const d = deps;
  // Carousel
  window.saveCarouselSlideText = d.saveCarouselSlideText;
  window.regenerateCarouselSlide = d.regenerateCarouselSlide;
  window.regenerateCarouselAll = d.regenerateCarouselAll;
  window.selectCarouselSlideVersion = d.selectCarouselSlideVersion;
  window.deleteCarouselSlideVersion = d.deleteCarouselSlideVersion;
  window.handleCarouselSlideNoteInput = d.handleCarouselSlideNoteInput;
  window.previewCarouselSlide = d.previewCarouselSlide;
  window.carouselSwiperGoTo = d.carouselSwiperGoTo;
  window.setSlidesViewMode = d.setSlidesViewMode;
  window.setDividerStyle = d.setDividerStyle;
  window.downloadSlideImage = d.downloadSlideImage;
  window.uploadSlideImage = d.uploadSlideImage;
  window.uploadSlideImageFromInput = d.uploadSlideImageFromInput;
  window.downloadCarouselPptx = d.downloadCarouselPptx;
  window.importCarouselPptx = d.importCarouselPptx;
  window.exportToCanva = d.exportToCanva;
  window.importFromCanva = d.importFromCanva;
  window.selectCanvaDesign = d.selectCanvaDesign;
  // Reels
  window.saveReelsScenario = d.saveReelsScenario;
  window.regenerateReelsStoryboard = d.regenerateReelsStoryboard;
  window.regenerateAllReelsFrames = d.regenerateAllReelsFrames;
  window.saveReelsFrameFields = d.saveReelsFrameFields;
  window.saveReelsFramePrompt = d.saveReelsFramePrompt;
  window.saveReelsFrameNote = d.saveReelsFrameNote;
  window.regenerateReelsFrame = d.regenerateReelsFrame;
  window.handleReelsFramePromptInput = d.handleReelsFramePromptInput;
  window.handleReelsFrameNoteInput = d.handleReelsFrameNoteInput;
  window.regenConcept = d.regenConcept;
  window.regenScenario = d.regenScenario;
  window.regenCaption = d.regenCaption;
  window.regenFrameImage = d.regenFrameImage;
  window.regenFrameImageWithPrompt = d.regenFrameImageWithPrompt;
  window.recoverFrameImage = d.recoverFrameImage;
  window.approveReels = d.approveReels;
  window.forceEditReels = d.forceEditReels;
  window.scheduleFrameOverlaySave = d.scheduleFrameOverlaySave;
  window.saveFrameImagePrompt = d.saveFrameImagePrompt;
  window.autoResize = d.autoResize;
  window.copyReelsCaption = d.copyReelsCaption;
  window.openReelsImageFullscreen = d.openReelsImageFullscreen;
  window.openReelsPreview = d.openReelsPreview;
  window.openBotUploadLink = d.openBotUploadLink;
  window.upgradeToFull = d.upgradeToFull;
  window.generateReelsImages = d.generateReelsImages;
  window.composeReelVideo = d.composeReelVideo;
  window.uploadReelsVideo = d.uploadReelsVideo;
  window.cleanReelsVideo = d.cleanReelsVideo;
  window.checkAndPublish = d.checkAndPublish;
  window.publishReels = d.publishReels;
  window.retryPlatform = d.retryPlatform;
  window.jumpToReelsStep = d.jumpToReelsStep;
  window.runTechCheck = d.runTechCheck;
  window.composeReelsVideo = d.composeReelsVideo;
  window.reuploadVideo = d.reuploadVideo;
  window.proceedToPublish = d.proceedToPublish;
  window.splitReelsClips = d.splitReelsClips;
  window.notifyWhenReady = d.notifyWhenReady;
  window.gradePreview = d.gradePreview;
  window.gradeShowProfiles = d.gradeShowProfiles;
  window.gradeSelectProfile = d.gradeSelectProfile;
  window.gradeApply = d.gradeApply;
  window.startMontage = d.startMontage;
  window.adminResetStuck = d.adminResetStuck;
  window.adminRestartWorker = d.adminRestartWorker;
  window.refreshDraftMetrics = d.refreshDraftMetrics;
  window.saveSeriesPost = d.saveSeriesPost;
  window.selectCity = d.selectCity;
  window.shareBlend = d.shareBlend;
  window.searchStockPhotos = d.searchStockPhotos;
  window.selectStockPhoto = d.selectStockPhoto;
  window.uploadDraftPhoto = d.uploadDraftPhoto;
  window.regenSlot = d.regenSlot;
  window.regenerateSeriesPosts = d.regenerateSeriesPosts;
  window.saveThreadsSlot = d.saveThreadsSlot;
  window.showSlotHistory = d.showSlotHistory;
  window.approveThreadsSeries = d.approveThreadsSeries;
  window.scheduleThreadsSeries = d.scheduleThreadsSeries;
  window.openThreadsScheduler = d.openThreadsScheduler;
  window.publishThreadsSeriesNow = d.publishThreadsSeriesNow;
  window.publishScheduledNow = d.publishScheduledNow;
  window.retryPublication = d.retryPublication;
  window.saveThreadsReviewDraft = d.saveThreadsReviewDraft;
  window.publishDraft = d.publishDraft;
  window.cancelPublishSchedule = d.cancelPublishSchedule;
  window.saveContentReviewDraft = d.saveContentReviewDraft;
  window.polishContentDraft = d.polishContentDraft;
  window.openKeywordTopic = d.openKeywordTopic;
  window.activatePlan = d.activatePlan;
  window.addKeywordItem = d.addKeywordItem;
  window.removeKeywordItem = d.removeKeywordItem;
  window.addForbiddenPhrase = d.addForbiddenPhrase;
  window.removeForbiddenPhrase = d.removeForbiddenPhrase;
  window.addRewrite = d.addRewrite;
  window.removeRewrite = d.removeRewrite;
  window.savePlatformTone = d.savePlatformTone;
  window.saveUploadPostPrefs = d.saveUploadPostPrefs;
  window.saveImageModels = d.saveImageModels;
  window.setTheme = d.setTheme;
  window.addTodoItem = () => d.addTodoItem();
  window.removeTodoItem = (id) => d.removeTodoItem(id);
  window.renderCreateTool = d.renderCreateTool;
  window.handleSmartSearch = d.handleSmartSearch;
  window.runSmartSearch = d.runSmartSearch;
  window.clearSmartSearch = d.clearSmartSearch;
  window.createContentFromOil = d.createContentFromOil;
  window.createContentFromOilTool = d.createContentFromOilTool;
  window.toggleDailyOilPicker = d.toggleDailyOilPicker;
  window.createContentFromDailyOil = d.createContentFromDailyOil;
  window.toggleReferenceFilters = d.toggleReferenceFilters;
  window.openBlendConstructor = d.openBlendConstructor;
  window.addRecoOilToBlend = d.addRecoOilToBlend;
  window.toggleEffect = d.toggleEffect;
  window.selectSpeed = d.selectSpeed;
  window.selectApp = d.selectApp;
  window.updateConstructBtn = d.updateConstructBtn;
  window.submitBlendConstructor = d.submitBlendConstructor;
  window.openSavedBlends = d.openSavedBlends;
  window.openSavedBlendDetail = d.openSavedBlendDetail;
  window.savedBlendCreateContent = d.savedBlendCreateContent;
  window.savedBlendLaunchContent = d.savedBlendLaunchContent;
  window.deleteSavedBlendFromDetail = d.deleteSavedBlendFromDetail;
  window.blendSaveCurrentBlend = d.blendSaveCurrentBlend;
  window.blendCreateContent = d.blendCreateContent;
  window.blendOfWeek = d.blendOfWeek;
  window.blendLaunchContent = d.blendLaunchContent;
  window.blendRegenerate = d.blendRegenerate;
  window.blendAdjustWithOil = d.blendAdjustWithOil;
  window.deleteSavedBlend = d.deleteSavedBlend;
  window.connectPlatform = d.connectPlatform;
  window.createNewTeam = d.createNewTeam;
  window.createTeamInvite = d.createTeamInvite;
  window.removeTeamMember = d.removeTeamMember;
  window.uploadTeamAvatar = d.uploadTeamAvatar;
  window.activatePromo = d.activatePromo;
  window.generatePromos = d.generatePromos;
  window.goBackToSettings = d.goBackToSettings;
  window.openMentionDetail = d.openMentionDetail;
  window.closeMentionDetail = d.closeMentionDetail;
  window.generateReplies = d.generateReplies;
  window.publishReply = d.publishReply;
  window.ignoreMentionAction = d.ignoreMentionAction;
  window.setMentionsFilter = d.setMentionsFilter;
  window.moveDraftToTeam = d.moveDraftToTeam;
  window.switchAccountsTeam = d.switchAccountsTeam;
  window.addTrackedHashtag = d.addTrackedHashtag;
  window.removeTrackedHashtag = d.removeTrackedHashtag;
  window._selectSchedulerDate = d._selectSchedulerDate;
  window._renderThreadsSchedulerDates = d._renderThreadsSchedulerDates;
  window.recommendHashtags = d.recommendHashtags;
  window.applyRecommendedHashtags = d.applyRecommendedHashtags;
  window.adaptTone = d.adaptTone;
  window.startRepurpose = d.startRepurpose;
  window.regenSeriesPost = d.regenSeriesPost;
  window.regenSeriesAll = d.regenSeriesAll;
  window.coherenceCheck = d.coherenceCheck;
  window.generateTrendCards = d.generateTrendCards;
  window.createFromTrendCard = d.createFromTrendCard;
  window.openIntelligenceOpp = d.openIntelligenceOpp;
  window.createFromIntelligence = d.createFromIntelligence;
  window.openRecommendationsWizard = d.openRecommendationsWizard;
  window.closeRecommendationsWizard = d.closeRecommendationsWizard;
  window.recoWizardNext = d.recoWizardNext;
  window.recoWizardBack = d.recoWizardBack;
  window.recoSelectMood = d.recoSelectMood;
  window.recoSelectGoal = d.recoSelectGoal;
  window.recoUpdateSymptoms = d.recoUpdateSymptoms;
  window.recoToggleAroma = d.recoToggleAroma;
  window.recoUpdateContra = d.recoUpdateContra;
  window.submitRecommendations = d.submitRecommendations;

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

  // ── Progressive image loading (blur-up) ─────────────────────────────────
  // When a .progressive-img__full image loads, check if it was showing a thumb.
  // If so, load the full-quality image in the background and swap when ready.
  document.addEventListener("load", (e) => {
    const img = e.target;
    if (!img.matches) return;
    // Simple progressive: img with data-full loads thumb first, then upgrades
    if (img.matches(".progressive-carousel-img[data-full]")) {
      const fullSrc = img.dataset.full;
      if (fullSrc && !img.src.includes(fullSrc.split("/").pop())) {
        const loader = new Image();
        loader.onload = () => { img.src = fullSrc; };
        loader.src = fullSrc;
      }
      return;
    }
    if (!img.matches(".progressive-img__full")) return;
    const fullSrc = img.dataset.full;
    if (!fullSrc || img.src.includes(fullSrc.split("/").pop())) {
      // Already showing full — just reveal
      img.classList.add("is-loaded");
      return;
    }
    // Currently showing thumb — load full in background
    const loader = new Image();
    loader.onload = () => {
      img.src = fullSrc;
      img.classList.add("is-loaded");
    };
    loader.onerror = () => {
      // Thumb is fine as fallback
      img.classList.add("is-loaded");
    };
    loader.src = fullSrc;
  }, true); // capture phase to catch img load events

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
    const actionName = el.dataset.action;
    const fn = window[actionName];
    if (typeof fn === "function") {
      fn(..._resolveArgs(el, el.dataset.args));
    } else {
      console.error(`[data-action] "${actionName}" is not a function:`, typeof fn, fn);
      // Show debug toast so user can report
      if (window.showUiNotice) window.showUiNotice(`Кнопка "${actionName}" не найдена (${typeof fn})`, "error");
    }
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
