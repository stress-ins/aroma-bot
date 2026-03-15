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
    copyText,
    openReels,
    openPlan,
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
    downloadCarouselPptx,
    importCarouselPptx,
    saveReelsScenario,
    regenerateReelsStoryboard,
    regenerateAllReelsFrames,
    saveReelsFrameFields,
    saveReelsFramePrompt,
    saveReelsFrameNote,
    regenerateReelsFrame,
    handleReelsFramePromptInput,
    handleReelsFrameNoteInput,
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
  window.copyText = copyText;
  window.openReels = openReels;
  window.openPlan = openPlan;
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
  window.downloadCarouselPptx = downloadCarouselPptx;
  window.importCarouselPptx = importCarouselPptx;

  window.saveReelsScenario = saveReelsScenario;
  window.regenerateReelsStoryboard = regenerateReelsStoryboard;
  window.regenerateAllReelsFrames = regenerateAllReelsFrames;
  window.saveReelsFrameFields = saveReelsFrameFields;
  window.saveReelsFramePrompt = saveReelsFramePrompt;
  window.saveReelsFrameNote = saveReelsFrameNote;
  window.regenerateReelsFrame = regenerateReelsFrame;
  window.handleReelsFramePromptInput = handleReelsFramePromptInput;
  window.handleReelsFrameNoteInput = handleReelsFrameNoteInput;

  window.publishDraft = publishDraft;
  window.cancelPublishSchedule = cancelPublishSchedule;
  window.saveContentReviewDraft = saveContentReviewDraft;
  window.polishContentDraft = polishContentDraft;
  window.openKeywordTopic = openKeywordTopic;
  window.addKeywordItem = addKeywordItem;
  window.removeKeywordItem = removeKeywordItem;
  window.addTodoItem = () => addTodoItem();
  window.removeTodoItem = (id) => removeTodoItem(id);
  window.renderCreateTool = renderCreateTool;

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
    state.settingsSection = section === "keywords" ? "keywords" : section === "brand" ? "brand" : "status";
    if (state.tab !== "settings") {
      setMode("content");
      setTab("settings");
    }
    await loadSettings();
  };
}
