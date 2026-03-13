export function createPlansModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    actionLabel,
    tagMarkup,
    interactiveCardAttrs,
    contentKindIcon,
    kindLabel,
    sourceLabel,
    sourceTone,
    formatPlanDate,
    renderBackButton,
    renderMarkdown,
    renderGuidedState,
    setEmptyState,
    fetchJson,
    withButtonFeedback,
    upsertDraftSummary,
    draftSummaryFromDraft,
    setTab,
    enterDetailView,
    syncMobileNavigation,
    loadPlans: reloadPlans,
    loadDrafts,
    loadReels,
    openDraft,
    openReels,
  } = deps;

  async function loadTodo() {
    try {
      const data = await fetchJson("/api/todo");
      state.todoItems = data.items || [];
    } catch (_e) {
      state.todoItems = state.todoItems || [];
    }
    renderTodoSection();
  }

  function renderTodoSection() {
    const el = document.getElementById("plansTodoSection");
    if (!el) return;
    const items = state.todoItems || [];
    el.innerHTML = `
      <section class="section todo-section">
        <h3>${uiIcon("text")}<span>Список дел</span></h3>
        <ul class="todo-list">
          ${items.map((item) => `
            <li class="todo-item">
              <span class="todo-text">${escapeHtml(item.text)}</span>
              <button class="ghost-button todo-remove-btn" type="button" onclick="removeTodoItem(${JSON.stringify(item.id)})" aria-label="Удалить">${uiIcon("trash")}</button>
            </li>
          `).join("")}
        </ul>
        <div class="todo-add-row">
          <input class="todo-input" id="todoNewItemInput" type="text" placeholder="Новое дело…" maxlength="200" />
          <button class="primary-button todo-add-btn" type="button" onclick="addTodoItem()">${uiIcon("plus")}<span>Добавить</span></button>
        </div>
      </section>
    `;
  }

  async function addTodoItemImpl() {
    const input = document.getElementById("todoNewItemInput");
    if (!(input instanceof HTMLInputElement)) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    try {
      const data = await fetchJson("/api/todo/add", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      state.todoItems = data.items || [];
    } catch (_e) {
      state.todoItems = [...(state.todoItems || []), { id: String(Date.now()), text }];
    }
    renderTodoSection();
  }

  async function removeTodoItemImpl(id) {
    try {
      const data = await fetchJson("/api/todo/remove", {
        method: "POST",
        body: JSON.stringify({ id }),
      });
      state.todoItems = data.items || [];
    } catch (_e) {
      state.todoItems = (state.todoItems || []).filter((item) => item.id !== id);
    }
    renderTodoSection();
  }

  async function loadPlans() {
    const data = await fetchJson("/api/plans?limit=20");
    state.plans = data.items || [];
    renderPlans();
  }

  function planEntryTargetKind(entry = {}) {
    const platform = String(entry.platform || "").trim().toLowerCase();
    const formatLabel = String(entry.format_label || "").trim().toLowerCase();
    if (platform.includes("reels") || formatLabel.includes("reels") || formatLabel.includes("рилс")) return "reels";
    if (formatLabel.includes("карус") || formatLabel.includes("carousel")) return "carousel";
    if (platform.includes("threads")) return "threads";
    if (platform.includes("instagram")) return "instagram";
    if (platform.includes("telegram")) return "telegram";
    return "instagram";
  }

  function planEntryFormatLabel(entry = {}) {
    const target = planEntryTargetKind(entry);
    return kindLabel(target) || "Контент";
  }

  function relatedDraftsForEntry(plan = {}, entry = {}) {
    const topic = String(entry.topic || "").trim();
    const related = Array.isArray(plan.related_drafts) ? plan.related_drafts : [];
    if (!topic) return [];
    return related.filter((draft) => String(draft.topic || "").trim() === topic);
  }

  async function openPlan(id) {
    elements.draftDetail.innerHTML = `${renderBackButton()}${deps.renderDetailLoader("Открываю план")}`;
    enterDetailView();
    const p = await fetchJson(`/api/plans/${id}`);
    state.selectedPlan = p;
    state.plans = state.plans.map((item) => item.plan_id === p.plan_id ? { ...item, ...p } : item);
    renderPlanDetail(p);
    enterDetailView();
    const params = new URLSearchParams(window.location.search);
    params.set("tab", state.tab);
    params.set("draft_id", id);
    history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
  }

  async function generateDraftFromPlan(planId, entryIndex, button) {
    const apply = async () => {
      const payload = await fetchJson(`/api/plans/${planId}/generate`, {
        method: "POST",
        body: JSON.stringify({ entry_index: entryIndex }),
      });
      const draft = payload?.draft || null;
      if (draft?.kind === "reels") {
        state.reels = [draft, ...state.reels.filter((item) => item.draft_id !== draft.draft_id)];
      } else if (draft?.draft_id) {
        upsertDraftSummary(draftSummaryFromDraft(draft));
      }
      await reloadPlans();
      await openPlan(planId);
      return draft;
    };
    const draft = button instanceof HTMLElement
      ? await withButtonFeedback(button, "Создаю...", apply, "Создано")
      : await apply();
    if (draft?.draft_id) {
      const tg = window.Telegram?.WebApp;
      if (tg?.showAlert) tg.showAlert("Черновик создан и привязан к плану");
    }
  }

  async function openPlanRelatedDraft(kind, draftId) {
    if (!draftId) return;
    if (kind === "reels") {
      setTab("reels");
      await loadReels();
      await openReels(draftId);
      return;
    }
    setTab("drafts");
    await loadDrafts();
    await openDraft(draftId);
  }

  function renderPlanDetail(p) {
    const entries = Array.isArray(p.entries) ? p.entries : [];
    const relatedDrafts = Array.isArray(p.related_drafts) ? p.related_drafts : [];
    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("calendar")}<span>План • ${escapeHtml(formatPlanDate(p.created_at) || p.plan_id)}</span></p>
          <h2 class="detail-title">Контент-план</h2>
          <div class="draft-meta">
            ${tagMarkup(`${entries.length} тем`, "progress")}
            ${relatedDrafts.length ? tagMarkup(`${relatedDrafts.length} связанных черновиков`, "status-positive") : tagMarkup("Без связанных черновиков", "status-neutral")}
          </div>
        </div>
        <section class="section">
          <h3>${uiIcon("text")}Исходный план</h3>
          <div class="detail-preview detail-markdown">${renderMarkdown(p.raw_text || "План без исходного текста")}</div>
        </section>
        <section class="section">
          <h3>${uiIcon("slides")}Темы и форматы</h3>
          <div class="plan-entry-list">
            ${entries.map((entry, index) => {
              const related = relatedDraftsForEntry(p, entry);
              return `
                <article class="plan-entry-card">
                  <div class="plan-entry-head">
                    <div>
                      <strong>${escapeHtml(entry.topic || `Тема ${index + 1}`)}</strong>
                      <div class="draft-meta">
                        ${entry.day_label ? tagMarkup(entry.day_label, "status-neutral") : ""}
                        ${entry.platform ? tagMarkup(entry.platform, "source-plan") : ""}
                        ${tagMarkup(planEntryFormatLabel(entry), "source-plan")}
                      </div>
                    </div>
                    <button class="primary-button" type="button" onclick="generateDraftFromPlan('${p.plan_id}', ${index}, this)">${actionLabel("sparkle", `Создать ${planEntryFormatLabel(entry)}`)}</button>
                  </div>
                  ${entry.angle ? `<div class="detail-preview">${escapeHtml(entry.angle)}</div>` : ""}
                  ${entry.goal ? `<div class="detail-preview"><strong>Цель:</strong> ${escapeHtml(entry.goal)}</div>` : ""}
                  ${related.length ? `
                    <div class="actions-row">
                      ${related.map((draft) => `
                        <button class="secondary-button" type="button" onclick="openPlanRelatedDraft('${escapeHtml(draft.kind)}', '${escapeHtml(draft.draft_id)}')">${actionLabel(draft.kind === "reels" ? "reel" : "eye", `Открыть ${kindLabel(draft.kind)}`)}</button>
                      `).join("")}
                    </div>
                  ` : ""}
                </article>
              `;
            }).join("")}
          </div>
        </section>
      </div>
    `;
    syncMobileNavigation();
  }

  function renderPlans() {
    elements.listTitle.textContent = "Планы";
    elements.draftCount.textContent = `${state.plans.length} шт`;
    setEmptyState(state.plans.length > 0, {
      eyebrow: "Планы",
      title: "Планов пока нет",
      body: "Соберите план на неделю, чтобы сразу разложить идеи по форматам и дням.",
      actionLabel: "Открыть создание",
      action: "setTab('create')",
    });
    elements.draftList.innerHTML = `<div id="plansTodoSection"></div>` + state.plans.map((plan) => `
      <article ${interactiveCardAttrs(`Открыть план ${plan.plan_id}`)} class="plan-card overview-card${plan.plan_id === state.selectedPlan?.plan_id ? " active" : ""} interactive-card" onclick="openPlan('${plan.plan_id}')">
        <div class="overview-card-top">
          <div class="draft-kind">${contentKindIcon("plan")}<span>План</span></div>
          <span class="overview-card-date">${escapeHtml(formatPlanDate(plan.created_at) || plan.plan_id)}</span>
        </div>
        <h3 class="draft-topic">${escapeHtml(formatPlanDate(plan.created_at) ? `План от ${formatPlanDate(plan.created_at)}` : plan.plan_id)}</h3>
        <div class="draft-preview">${escapeHtml(String(plan.raw_text || "").trim())}</div>
        <div class="draft-meta overview-card-footer">
          ${tagMarkup(`${(plan.entries || []).length} карточек`, "source-plan")}
          ${tagMarkup(`${(plan.related_drafts || []).length} черновиков`, "status-review")}
        </div>
      </article>
    `).join("");
    if (!state.selectedPlan) {
      elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({
        eyebrow: "План",
        title: "Откройте план недели",
        body: "Внутри плана можно создавать черновики по каждой карточке и сразу открывать связанный материал.",
      })}</div>`;
    }
    renderTodoSection();
    syncMobileNavigation();
  }

  return {
    loadPlans,
    loadTodo,
    addTodoItemImpl,
    removeTodoItemImpl,
    planEntryTargetKind,
    planEntryFormatLabel,
    relatedDraftsForEntry,
    openPlan,
    generateDraftFromPlan,
    openPlanRelatedDraft,
    renderPlans,
    renderPlanDetail,
  };
}
