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
    enterDetailView();
    clearBackgroundRefreshes();
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
    setTab("reels");
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

  async function recoverPendingReelsCreation(topic, pendingDraftId) {
    const startedAt = Date.now();
    state.pendingCreateRecovery = {
      draft_id: pendingDraftId,
      kind: "reels",
      topic,
      started_at: startedAt,
    };
    for (let attempt = 0; attempt < 8; attempt += 1) {
      try {
        const data = await fetchJson("/api/drafts?kind=reels&limit=20", { timeout: 20000 });
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
    elements.draftDetail.innerHTML = renderDetailError(
      "Рилс создаётся дольше обычного",
      "Мы продолжаем ждать сценарий и кадры. Откройте Рилсы ещё раз или повторите позже.",
      "retryCurrentTab()",
    );
    syncMobileNavigation();
    return false;
  }

  function renderInbox() {
    elements.listTitle.textContent = "Согласование";
    elements.draftCount.textContent = `${state.inbox.length} на проверке`;
    setEmptyState(state.inbox.length > 0, {
      eyebrow: "Согласование",
      title: "Очередь пока пуста",
      body: "Когда появятся материалы на ревью, они сразу окажутся здесь.",
    });
    elements.draftList.innerHTML = state.inbox.map((item) => `
      <article ${interactiveCardAttrs(`Открыть материал на согласовании ${item.topic}`)} class="draft-card overview-card${item.draft_id === state.draftId ? " active" : ""} interactive-card" onclick="openDraft('${item.draft_id}')">
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
    elements.listTitle.textContent = "Рилсы";
    elements.draftCount.textContent = `${state.reels.length} шт`;
    setEmptyState(state.reels.length > 0, {
      eyebrow: "Рилсы",
      title: "Рилсов пока нет",
      body: "Создайте сценарий и раскадровку, чтобы здесь появился готовый рабочий список.",
      actionLabel: "Открыть создание",
      action: "setTab('create')",
    });
    elements.draftList.innerHTML = state.reels.map((reel) => `
      <article ${interactiveCardAttrs(`Открыть рилс ${reel.topic}`)} class="reels-card overview-card${reel.draft_id === state.selectedReels?.draft_id ? " active" : ""} interactive-card" onclick="openReels('${reel.draft_id}')">
        <div class="overview-card-top">
          <div class="draft-kind">${contentKindIcon("reels")}<span>Рилс</span></div>
          <span class="overview-card-date">${escapeHtml(formatPlanDate(reel.created_at) || "Видео")}</span>
        </div>
        <h3 class="draft-topic">${escapeHtml(reel.topic)}</h3>
        <div class="draft-preview">${escapeHtml(stripMarkdown(reel.preview || ""))}</div>
        <div class="draft-meta overview-card-footer">
          ${tagMarkup(statusLabel(reel.status || "draft"), statusTone(reel.status || "draft"))}
          ${tagMarkup(`${reel.images_ready || 0}/${reel.frame_count || 0} кадров`, "progress")}
          ${tagMarkup(sourceLabel(reel.source || "/miniapp"), sourceTone(reel.source || "/miniapp"))}
        </div>
      </article>
    `).join("");
    syncMobileNavigation();
  }

  function renderReelsDetail(reel) {
    elements.draftDetail.innerHTML = callbacks.renderReelsDetailMarkup(reel);
    if (reel.generation_pending || (reel.images_ready || 0) < (reel.frame_count || 0)) {
      scheduleReelsRefresh(reel.draft_id);
    }
    syncMobileNavigation();
  }

  async function refreshReelsDetail(draftId) {
    const reel = await fetchJson(`/api/reels/${draftId}`);
    const readyFrames = Array.isArray(reel.frames) ? reel.frames.filter((item) => item.current_asset?.url).length : 0;
    state.reels = state.reels.map((item) => item.draft_id === reel.draft_id ? { ...item, ...reel } : item);
    if (isCurrentReelsDetail(reel.draft_id)) {
      state.selectedReels = reel;
      renderReels();
      if (!isEditingDetailForm()) renderReelsDetail(reel);
    }
    return {
      reel,
      shouldContinue: reel.generation_pending || readyFrames < (reel.frame_count || 0),
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
