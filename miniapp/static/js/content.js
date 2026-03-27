export function createContentModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    stripMarkdown,
    renderBackButton,
    renderDetailLoader,
    renderGuidedState,
    renderDetailError,
    interactiveCardAttrs,
    contentKindIcon,
    kindLabel,
    sourceLabel,
    sourceTone,
    statusLabel,
    statusTone,
    tagMarkup,
    formatPlanDate,
    fetchJson,
    setEmptyState,
    syncMobileNavigation,
    enterDetailView,
    setTab,
    clearBackgroundRefreshes,
    mergeReelsIntoState,
    scheduleReelsRefresh,
    isCurrentReelsDetail,
    isEditingDetailForm,
    showUiNotice,
    callbacks,
  } = deps;

  async function loadInbox() {
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (state.inboxKind && state.inboxKind !== "all") params.set("kind", state.inboxKind);
    const data = await fetchJson(`/api/inbox?${params.toString()}`);
    state.inbox = data.items || [];
    state.inboxKind = data.kind || "all";
    renderInbox();
  }

  async function loadReels() {
    const data = await fetchJson("/api/reels?limit=30");
    state.reels = data.items || [];
    renderReels();
  }

  async function openReels(id) {
    elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю рилс")}`;
    setTab("reels");
    enterDetailView();
    clearBackgroundRefreshes();
    state.draftId = ""; // Clear stale draft ref so PTR refreshes the correct view
    const reel = await fetchJson(`/api/reels/${id}`);
    state.selectedReels = reel;
    renderReelsDetail(reel);
    enterDetailView();
  }

  function openPendingReelsCreation(topic) {
    const draftId = `pending-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    state.pendingCreateRecovery = {
      draft_id: draftId,
      kind: "reels",
      topic,
      started_at: Date.now(),
    };
    state.selectedReels = {
      draft_id: draftId,
      kind: "reels",
      topic,
      source: "/miniapp",
      created_at: new Date().toISOString(),
      status: "draft",
      feedback: "",
      preview: "Генерируем рилс...",
      storyboard_count: 4,
      images_ready: 0,
      generation_pending: true,
      generation_stage: "scenario",
      generation_message: "Собираю сценарий и раскадровку для рилса.",
      frame_count: 0,
      frames: [],
      payload: {
        concept: "",
        scenario: "",
        storyboard: [],
        generation_pending: true,
        generation_stage: "scenario",
        generation_message: "Собираю сценарий и раскадровку для рилса.",
      },
    };
    state.reels = [
      state.selectedReels,
      ...state.reels.filter((item) => item.draft_id !== draftId),
    ];
    renderReels();
    renderReelsDetail(state.selectedReels);
    enterDetailView();
    return state.selectedReels;
  }

  function finalizePendingReelsCreation(draft) {
    if (!draft?.draft_id) return;
    state.pendingCreateRecovery = null;
    mergeReelsIntoState(draft);
    renderReels();
    renderReelsDetail(draft);
    enterDetailView();
  }

  async function recoverPendingReelsCreation(topic, pendingDraftId, requestStartedAt) {
    const startedAt = requestStartedAt || Date.now();
    state.pendingCreateRecovery = {
      draft_id: pendingDraftId,
      kind: "reels",
      topic,
      started_at: startedAt,
    };
    for (let attempt = 0; attempt < 8; attempt += 1) {
      try {
        const data = await fetchJson("/api/drafts?kind=reels&limit=50", { timeout: 20000 });
        const items = data.items || [];
        const recovered = items.find((item) => {
          const createdAt = new Date(item.created_at || 0).getTime();
          return item.kind === "reels"
            && item.topic === topic
            && item.source === "/miniapp"
            && (Number.isNaN(createdAt) || createdAt >= startedAt - 10_000);
        });
        if (recovered?.draft_id) {
          state.pendingCreateRecovery = null;
          await loadReels();
          await openReels(recovered.draft_id);
          return true;
        }
      } catch (_error) {
        // ignore and retry
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    state.pendingCreateRecovery = null;
    await loadReels();
    renderReels();
    if (showUiNotice) showUiNotice("Генерация продолжается в фоне — рилс появится в списке", "info");
    syncMobileNavigation();
    return false;
  }

  function renderInbox() {
    elements.listTitle.textContent = "Согласование";
    elements.draftCount.textContent = `${state.inbox.length} на проверке`;
    setEmptyState(state.inbox.length > 0, {
      eyebrow: "Согласование",
      title: "Очередь пока пуста",
      body: "Здесь появятся материалы, ожидающие согласования.",
    });
    elements.draftList.innerHTML = state.inbox.map((item) => `
      <article ${interactiveCardAttrs(`Открыть материал на согласовании ${item.topic}`)} class="draft-card overview-card${item.draft_id === state.draftId ? " active" : ""} interactive-card" data-action="openDraft" data-args='${JSON.stringify([item.draft_id])}'>
        <div class="overview-card-top">
          <div class="draft-kind">${contentKindIcon(item.kind)}<span>${escapeHtml(kindLabel(item.kind))}</span></div>
          <span class="overview-card-date">${escapeHtml(formatPlanDate(item.created_at) || "На проверке")}</span>
        </div>
        <h4 class="draft-topic">${escapeHtml(item.topic)}</h4>
        <div class="draft-preview">${escapeHtml(stripMarkdown(item.preview || ""))}</div>
        <div class="draft-meta overview-card-footer">
          ${tagMarkup(statusLabel(item.status || "in_review"), statusTone(item.status || "in_review"))}
          ${tagMarkup(sourceLabel(item.source || "/content"), sourceTone(item.source || "/content"))}
        </div>
      </article>
    `).join("");
    syncMobileNavigation();
  }

  function renderReels() {
    // No-op: reels list screen removed — list panel stays on drafts.
    // Reels detail (renderReelsDetail) still works as before.
  }

  function renderReelsDetail(reel) {
    elements.draftDetail.innerHTML = callbacks.renderReelsDetailMarkup(reel);
    const hasGenerating = Array.isArray(reel.frames) && reel.frames.some((f) => f?.image_status === "generating");
    if (reel.generation_pending || hasGenerating || (reel.images_ready || 0) < (reel.frame_count || 0)) {
      scheduleReelsRefresh(reel.draft_id);
    }
    bindStoryboardDots(elements.draftDetail);
    syncMobileNavigation();
  }

  function bindStoryboardDots(container) {
    const storyboard = container.querySelector(".storyboard");
    const dots = container.querySelectorAll(".storyboard-dot");
    if (!storyboard || dots.length < 2) return;
    if (dots.length > 0) dots[0].classList.add("active");
    storyboard.addEventListener("scroll", () => {
      const cards = storyboard.querySelectorAll(".storyboard-card, .reels-frame-v2");
      if (!cards.length) return;
      const scrollLeft = storyboard.scrollLeft;
      const cardWidth = cards[0].offsetWidth + 12;
      const idx = Math.round(scrollLeft / cardWidth);
      dots.forEach((d, i) => d.classList.toggle("active", i === idx));
    }, { passive: true });
  }

  async function refreshReelsDetail(draftId) {
    const reel = await fetchJson(`/api/reels/${draftId}`);
    const readyFrames = Array.isArray(reel.frames)
      ? reel.frames.filter((f) => f?.current_asset?.url || f?.image_status === "ready").length
      : 0;
    const hasGeneratingFrames = Array.isArray(reel.frames) && reel.frames.some((f) => f?.image_status === "generating");
    state.reels = state.reels.map((item) => item.draft_id === reel.draft_id ? { ...item, ...reel } : item);
    state.drafts = state.drafts.map((item) => item.draft_id === reel.draft_id ? { ...item, ...reel } : item);
    if (isCurrentReelsDetail(reel.draft_id)) {
      state.selectedReels = reel;
      renderReels();
      if (!isEditingDetailForm()) renderReelsDetail(reel);
    }
    if (typeof callbacks.renderDraftList === "function") callbacks.renderDraftList();
    return {
      reel,
      shouldContinue: reel.generation_pending || hasGeneratingFrames || readyFrames < (reel.frame_count || 0),
    };
  }

  return {
    loadInbox,
    loadReels,
    openReels,
    openPendingReelsCreation,
    finalizePendingReelsCreation,
    recoverPendingReelsCreation,
    renderInbox,
    renderReels,
    renderReelsDetail,
    refreshReelsDetail,
  };
}
