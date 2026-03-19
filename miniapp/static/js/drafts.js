export function createDraftsModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    renderBackButton,
    renderDetailLoader,
    renderGuidedState,
    renderDetailError,
    payloadSection,
    promptSection,
    detailFactMarkup,
    actionLabel,
    tagMarkup,
    contentKindIcon,
    kindLabel,
    sourceLabel,
    sourceTone,
    statusLabel,
    statusTone,
    feedbackLabel,
    feedbackTone,
    draftGenerationLabel,
    draftHeroSummary,
    generationStateMarkup,
    formatPlanDate,
    stripMarkdown,
    uiIcon,
    interactiveCardAttrs,
    isPendingDraftId,
    isContentReviewKind,
    renderSlides,
    renderPublishPanel,
    fetchJson,
    withButtonFeedback,
    mergeDraftIntoState,
    scheduleCarouselRefresh,
    setEmptyState,
    enterDetailView,
    syncMobileNavigation,
    renderMarkdown,
    callbacks,
  } = deps;

  const cleanSlotText = (t) => t ? t.replace(/^[-*_]{3,}\s*$/gm, '').replace(/\n{3,}/g, '\n\n').trim() : '';

  function _metricsBadge(ms) {
    const parts = [];
    if (ms.likes) parts.push(`<i data-lucide="heart" style="width:12px;height:12px"></i> ${ms.likes}`);
    if (ms.comments) parts.push(`<i data-lucide="message-circle" style="width:12px;height:12px"></i> ${ms.comments}`);
    if (ms.views) parts.push(`<i data-lucide="eye" style="width:12px;height:12px"></i> ${ms.views}`);
    if (!parts.length) return "";
    return `<span class="tag metrics-badge">${parts.join(" ")}</span>`;
  }

  function fullPreview(d) {
    const p = d.payload || {};
    if (d.kind === "carousel" && Array.isArray(p.slides) && p.slides.length) {
      return p.hook || p.angle || p.caption || p.slides[0] || "";
    }
    if (d.kind === "threads_series") {
      return p.series_summary || p.angle || d.preview || "";
    }
    return p.caption || p.hook || p.angle || d.preview || "";
  }

  async function saveContentReviewDraft(draftId, button) {
    const payload = {
      topic: String(document.getElementById("contentTopicField")?.value || "").trim(),
      angle: String(document.getElementById("contentAngleField")?.value || "").trim(),
      hook: String(document.getElementById("contentHookField")?.value || "").trim(),
      caption: String(document.getElementById("contentCaptionField")?.value || "").trim(),
      cta: String(document.getElementById("contentCtaField")?.value || "").trim(),
      hashtags: String(document.getElementById("contentHashtagsField")?.value || "").trim(),
      visual_prompt: String(document.getElementById("contentVisualPromptField")?.value || "").trim(),
      editor_notes: String(document.getElementById("contentEditorNotesField")?.value || "").trim(),
    };
    await withButtonFeedback(button, "Сохраняю...", async () => {
      const draft = await fetchJson(`/api/drafts/${draftId}/content`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      mergeDraftIntoState(draft);
      callbacks.renderDraftList?.();
      callbacks.renderDraftDetail?.(draft);
    }, "Сохранено");
  }

  async function saveThreadsReviewDraft(draftId, button) {
    const posts = [];
    for (let i = 0; i < 3; i++) {
      posts.push({
        slot: ["morning", "day", "evening"][i],
        label: ["УТРО", "ДЕНЬ", "ВЕЧЕР"][i],
        text: String(document.getElementById(`threadsPostText${i}`)?.value || "").trim(),
        scheduled_time: String(document.getElementById(`threadsPostTime${i}`)?.value || "").trim(),
      });
    }
    const payload = {
      threads_posts: posts,
      angle: String(document.getElementById("contentAngleField")?.value || "").trim(),
      visual_prompt: String(document.getElementById("contentVisualPromptField")?.value || "").trim(),
    };
    await withButtonFeedback(button, "Сохраняю...", async () => {
      const draft = await fetchJson(`/api/drafts/${draftId}/content`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      mergeDraftIntoState(draft);
      callbacks.renderDraftList?.();
      callbacks.renderDraftDetail?.(draft);
    }, "Сохранено");
  }

  async function polishContentDraft(draftId, button) {
    await withButtonFeedback(button, "Полирую...", async () => {
      const draft = await fetchJson(`/api/drafts/${draftId}/content/polish`, {
        method: "POST",
        body: "{}",
      });
      mergeDraftIntoState(draft);
      callbacks.renderDraftList?.();
      callbacks.renderDraftDetail?.(draft);
    }, "Готово");
  }

  function renderContentSwitcher(active) {
    return `<div class="content-sub-switcher">
      <button class="tab-button${active === "drafts" ? " active" : ""}" data-action="setContentSubMode" data-args='["drafts"]'>Черновики</button>
      <button class="tab-button${active === "trends" ? " active" : ""}" data-action="setContentSubMode" data-args='["trends"]'>Тренды</button>
    </div>`;
  }

  function renderDraftList() {
    elements.listTitle.textContent = "Контент";
    elements.draftCount.textContent = `${state.drafts.length} шт`;
    setEmptyState(state.drafts.length > 0, {
      eyebrow: "Черновики",
      title: "Ничего не найдено",
      body: "Создайте первый материал через вкладку «Создать». Выберите формат, укажите тему — AI сделает остальное.",
      actionLabel: "Открыть создание",
      action: "openCreateTool()",
    });
    elements.draftList.innerHTML = renderContentSwitcher("drafts") + state.drafts.map((d, idx) => `
      <article ${interactiveCardAttrs(`Открыть черновик ${d.topic}`)} class="draft-card overview-card${d.draft_id === state.draftId ? " active" : ""}${d.generation_pending ? " is-pending" : ""} interactive-card" data-action="openDraft" data-args='${JSON.stringify([d.draft_id])}'>
        <div class="overview-card-top">
          <div class="draft-kind">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}</span></div>
          <span class="overview-card-date">#${d.seq_id || idx + 1} · ${escapeHtml(formatPlanDate(d.created_at) || "Новый черновик")}</span>
        </div>
        <h3 class="draft-topic">${escapeHtml(d.topic)}</h3>
        <div class="draft-preview">${escapeHtml(stripMarkdown(d.preview || "Без превью"))}</div>
        <div class="draft-meta overview-card-footer">
          ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
          ${d.generation_pending && draftGenerationLabel(d) ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
          ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
          ${d.metrics_summary ? _metricsBadge(d.metrics_summary) : ""}
        </div>
      </article>
    `).join("");
    syncMobileNavigation();
  }

  async function openDraft(id) {
    if (isPendingDraftId(id) && state.selected?.draft_id === id) {
      renderDraftList();
      renderDraftDetail(state.selected);
      enterDetailView();
      return;
    }
    elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю черновик")}`;
    enterDetailView();
    const d = await fetchJson(`/api/drafts/${id}`, { timeout: 20000 });
    if (d?.kind === "reels" && callbacks.openReels) {
      await callbacks.openReels(d.draft_id);
      return;
    }
    state.selected = d;
    state.draftId = id;
    renderDraftList();
    renderDraftDetail(d);
    enterDetailView();
  }

  function renderThreadsSeriesDetail(d) {
    const p = d.payload || {};
    const posts = Array.isArray(p.threads_posts) ? p.threads_posts : [];
    const isApproved = d.status === "approved" || d.status === "scheduled" || d.status === "published";
    const SLOT_ICONS = { morning: uiIcon("sunrise"), day: uiIcon("sun"), evening: uiIcon("moon") };
    const SLOT_NAMES = { morning: "Утро", day: "День", evening: "Вечер" };
    const GOAL_LABELS = { trust: "Доверие", authority: "Экспертность", engagement: "Вовлечённость", sales: "Продажи" };
    const EMOTION_LABELS = { calm: "Спокойная", inspiration: "Вдохновляющая", curiosity: "Любопытство", trust: "Доверие", joy: "Радость" };

    const slotsHtml = posts.map((post) => {
      const icon = SLOT_ICONS[post.slot] || "";
      const name = SLOT_NAMES[post.slot] || post.slot;
      const charCount = (post.text || "").length;
      const isOver = charCount > 500;
      return `
        <div class="threads-slot">
          <div class="threads-slot-header">
            <span class="threads-slot-icon">${icon}</span>
            <span class="threads-slot-label">${escapeHtml(name)}</span>
            <input class="threads-slot-time" id="slotTime_${post.slot}_${d.draft_id}" type="time" value="${escapeHtml(post.scheduled_time || "")}" ${isApproved ? "readonly" : ""}>
          </div>
          <div class="threads-slot-body">
            ${!isApproved ? `<textarea
              id="slotText_${post.slot}_${d.draft_id}"
              class="threads-post-textarea"
              placeholder="Текст поста"
              data-on-input="_syncCharCount" data-count-target="charCount_${post.slot}_${d.draft_id}"
            >${escapeHtml(cleanSlotText(post.text || ""))}</textarea>
            <div class="threads-char-counter${isOver ? " is-over" : ""}" id="charCount_${post.slot}_${d.draft_id}">${charCount}</div>
            ${post.why_it_works ? `<div class="threads-slot-annotation"><span class="annotation-label">Почему это сработает:</span> ${escapeHtml(post.why_it_works)}</div>` : ""}` : `<div class="threads-post-rendered detail-markdown">${renderMarkdown(cleanSlotText(post.text || ""))}</div>
            ${post.why_it_works ? `<div class="threads-slot-annotation"><span class="annotation-label">Почему это сработает:</span> ${escapeHtml(post.why_it_works)}</div>` : ""}`}
          </div>
          ${!isApproved ? `
          <div class="threads-regen-note">
            <input class="threads-regen-input" id="regenNote_${post.slot}_${d.draft_id}" type="text" placeholder="Пожелание к перегенерации (необязательно)">
          </div>
          <div class="threads-regen-row">
            <button class="secondary-button" type="button" data-action="regenSlot" data-args='${JSON.stringify([d.draft_id, post.slot, null])}'>${actionLabel("regenerate", "Переписать")}</button>
            <button class="secondary-button" type="button" data-action="showSlotHistory" data-args='${JSON.stringify([d.draft_id, post.slot])}'>${actionLabel("history", "История")}</button>
          </div>
          <div class="actions-row" style="margin-top:4px">
            <button class="secondary-button" type="button" data-action="saveThreadsSlot" data-args='${JSON.stringify([d.draft_id, post.slot, null])}'>${actionLabel("approve", "Сохранить слот")}</button>
          </div>
          ` : `
          <div class="slot-status-row">
            ${tagMarkup(post.status === "scheduled" ? "Запланировано" : post.status === "published" ? "Опубликовано" : "Согласовано", post.status === "published" ? "status-success" : "status-neutral")}
          </div>
          `}
        </div>
      `;
    }).join("");

    const schedulerHtml = isApproved && d.status !== "published" ? `
      <div id="scheduler_${d.draft_id}" hidden>
        <div class="date-picker-row" id="schedulerDates_${d.draft_id}"></div>
        <div class="actions-row" style="margin-top:8px">
          <button class="primary-button" id="schedulerSubmit_${d.draft_id}" type="button" data-date="" data-draft-id="${d.draft_id}" disabled
            data-action="_scheduleThreadsSeriesFromBtn">
            ${actionLabel("approve", "Запланировать публикацию")}
          </button>
        </div>
      </div>
    ` : "";

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top detail-hero">
          <div class="detail-hero-copy">
            <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}${sourceLabel(d.source) ? " • " + escapeHtml(sourceLabel(d.source)) : ""}</span></p>
            <h2 class="detail-title">${escapeHtml(d.topic)}</h2>
            <div class="draft-meta">
              ${d.seq_id ? `<span class="meta-chip meta-chip--muted">#${d.seq_id}</span>` : ""}
              ${formatPlanDate(d.created_at) ? `<span class="meta-chip meta-chip--muted">${escapeHtml(formatPlanDate(d.created_at))}</span>` : ""}
              ${d.updated_at && d.updated_at !== d.created_at ? `<span class="meta-chip meta-chip--muted">изм. ${escapeHtml(formatPlanDate(d.updated_at))}</span>` : ""}
              ${d.created_by_username ? `<span class="meta-chip meta-chip--muted">@${escapeHtml(d.created_by_username)}</span>` : ""}
              ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
              ${p.goal ? tagMarkup(GOAL_LABELS[p.goal] || p.goal, "status-neutral") : ""}
              ${p.emotion ? tagMarkup(EMOTION_LABELS[p.emotion] || p.emotion, "status-neutral") : ""}
            </div>
          </div>
          <div class="actions-row detail-actions">
            ${!isApproved && posts.length ? `<button class="primary-button" type="button" data-action="approveThreadsSeries" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("approve", "Согласовать")}</button>` : ""}
            ${isApproved && d.status !== "published" ? `<button class="secondary-button" type="button" data-action="openThreadsScheduler" data-args='${JSON.stringify([d.draft_id])}'>${actionLabel("calendar", "Выбрать дату публикации")}</button>` : ""}
            ${isApproved && d.status !== "published" ? `<button class="primary-button" type="button" data-action="publishThreadsSeriesNow" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("send", "Опубликовать все сейчас")}</button>` : ""}
            <button class="secondary-button" data-action="sendDraftToChat" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("chat", "В чат")}</button>
            ${renderMoveButton(d.draft_id)}
          </div>
          ${schedulerHtml}
        </div>
        ${p.series_summary ? payloadSection("Опорная мысль", p.series_summary) : ""}
        <section class="section section-primary">
          <div class="section-heading">
            <h3>${uiIcon("text")}Посты серии</h3>
            <p>${isApproved ? "Серия согласована. Запланируйте публикацию." : posts.length ? "Отредактируйте каждый пост, затем согласуйте серию." : "Посты не были сгенерированы. Попробуйте заново."}</p>
          </div>
          ${slotsHtml}
          ${!posts.length && !isApproved ? `
          <div class="actions-row" style="margin-top: var(--space-3)">
            <button class="primary-button" type="button" data-action="regenerateSeriesPosts" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("regenerate", "Сгенерировать посты")}</button>
          </div>
          ` : ""}
        </section>
        <div class="actions-row detail-actions-danger">
          <button class="danger-button" data-action="deleteDraft" data-args='${JSON.stringify([d.draft_id, "drafts", null])}'>${actionLabel("trash", "Удалить")}</button>
        </div>
      </div>
    `;
    syncMobileNavigation();
  }

  function renderDraftDetail(d) {
    if (isPendingDraftId(d?.draft_id)) {
      const isSeries = d?.kind === "threads_series";
      elements.draftDetail.innerHTML = `
        <div class="detail-grid detail-grid-pending">
          ${renderBackButton()}
          <div class="detail-top">
            <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}${sourceLabel(d.source || "/miniapp") ? " • " + escapeHtml(sourceLabel(d.source || "/miniapp")) : ""}</span></p>
            <h2 class="detail-title">${escapeHtml(d.topic || "Создаём черновик")}</h2>
            <div class="draft-meta">
              ${tagMarkup("Черновик", "status-neutral")}
              ${tagMarkup("Ещё генерируется", "pending")}
            </div>
          </div>
          ${renderDetailLoader(isSeries ? "Генерирую серию" : "Генерирую карточку", isSeries ? "Создаю три поста: утро, день, вечер.<br>Займёт 15–30 секунд." : "Сохраняю черновик и подгружаю содержимое.", "detail-loader-card-compact")}
        </div>
      `;
      syncMobileNavigation();
      return;
    }

    if (d?.kind === "threads_series") {
      return renderThreadsSeriesDetail(d);
    }

    const p = d.payload || {};
    const mainText = p.caption || p.scenario || "";

    const threadsPosts = Array.isArray(p.threads_posts) && p.threads_posts.length ? p.threads_posts : null;
    const SLOT_ICONS = { morning: uiIcon("sunrise"), day: uiIcon("sun"), evening: uiIcon("moon") };

    const reviewActions = isContentReviewKind(d.kind)
      ? `
        <section class="section section-primary">
          <div class="section-heading">
            <h3>${uiIcon("text")}Редактор</h3>
            <p>${threadsPosts ? "Три поста на день: утро, день, вечер. Редактируйте каждый отдельно." : "Соберите сильную мысль и основной текст, затем уточните подачу и визуал."}</p>
          </div>
          <div class="content-review-form">
            ${threadsPosts ? `
              ${threadsPosts.map((post, idx) => `
                <div class="threads-post-section" data-slot="${post.slot}">
                  <span class="threads-post-label">${SLOT_ICONS[post.slot] || ""} ${escapeHtml(post.label)}</span>
                  <textarea id="threadsPostText${idx}" class="threads-post-textarea" placeholder="Текст поста">${escapeHtml(cleanSlotText(post.text || ""))}</textarea>
                  ${post.why_it_works ? `<div class="threads-slot-annotation"><span class="annotation-label">Почему это сработает:</span> ${escapeHtml(post.why_it_works)}</div>` : ""}
                  <div class="threads-post-schedule">
                    <label><span>Время</span><input type="time" id="threadsPostTime${idx}" value="${escapeHtml(post.scheduled_time || post.default_time || "")}"></label>
                  </div>
                </div>
              `).join("")}
              <div class="content-review-support-grid">
                <label><span>Опорная мысль</span><textarea id="contentAngleField" placeholder="Угол подачи">${escapeHtml(p.angle || "")}</textarea></label>
                <label><span>Промпт для визуала</span><textarea id="contentVisualPromptField" placeholder="Образ или сцена для визуала">${escapeHtml(p.visual_prompt || "")}</textarea></label>
              </div>
              <div class="actions-row review-actions">
                <button class="primary-button" type="button" data-action="saveThreadsReviewDraft" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("approve", "Сохранить 3 поста")}</button>
                <button class="secondary-button" type="button" data-action="polishContentDraft" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("sparkle", "Уточнить через AI")}</button>
              </div>
            ` : `
              <div class="content-review-highlight">
                <label><span>Тема материала</span><textarea id="contentTopicField" placeholder="О чем этот материал и зачем он читателю">${escapeHtml(d.topic || "")}</textarea></label>
                <label><span>Опорная мысль</span><textarea id="contentAngleField" placeholder="Какой угол подачи или тезис держит весь текст">${escapeHtml(p.angle || "")}</textarea></label>
                <label><span>Первая фраза</span><textarea id="contentHookField" placeholder="С чего лучше начать, чтобы зацепить внимание">${escapeHtml(p.hook || "")}</textarea></label>
              </div>
              <label class="content-review-lead"><span>Основной текст</span><textarea id="contentCaptionField" placeholder="Соберите здесь основную версию текста">${escapeHtml(p.caption || "")}</textarea></label>
              <p class="field-help">Сохраняйте версию после смыслового прохода.</p>
              <div class="content-review-support-grid">
                <label><span>Призыв к действию</span><textarea id="contentCtaField" placeholder="Что читателю стоит сделать после текста">${escapeHtml(p.cta || "")}</textarea></label>
                <label><span>Теги</span><textarea id="contentHashtagsField" placeholder="#ритуал #аромапрактика">${escapeHtml(p.hashtags || "")}</textarea></label>
                <label><span>Промпт для визуала</span><textarea id="contentVisualPromptField" placeholder="Какой образ или сцену должен поддержать визуал">${escapeHtml(p.visual_prompt || "")}</textarea></label>
                <label><span>Комментарий редактора</span><textarea id="contentEditorNotesField" placeholder="Что усилить или перепроверить">${escapeHtml(p.editor_notes || "")}</textarea></label>
              </div>
              <div class="actions-row review-actions">
                <button class="primary-button" type="button" data-action="saveContentReviewDraft" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("approve", "Сохранить версию")}</button>
                <button class="secondary-button" type="button" data-action="polishContentDraft" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("sparkle", "Уточнить через AI")}</button>
              </div>
            `}
          </div>
        </section>
        <section class="section section-accent">
          <div class="section-heading">
            <h3>${uiIcon("chat")}Результат публикации</h3>
            <p>После публикации отметьте фактический результат, чтобы видеть, какие материалы реально срабатывают у аудитории.</p>
          </div>
          <div class="draft-meta">
            ${tagMarkup(feedbackLabel(d.feedback), feedbackTone(d.feedback))}
          </div>
          <div class="actions-row">
            <button class="secondary-button" type="button" data-action="updateDraft" data-args='["feedback",{"feedback":"worked"},null]'>${actionLabel("approve", "Откликнулось")}</button>
            <button class="secondary-button" type="button" data-action="updateDraft" data-args='["feedback",{"feedback":"missed"},null]'>${actionLabel("reject", "Не дало результата")}</button>
            <button class="secondary-button" type="button" data-action="updateDraft" data-args='["feedback",{"feedback":""},null]'>${actionLabel("back", "Очистить отметку")}</button>
          </div>
        </section>
      `
      : "";

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top detail-hero">
          <div class="detail-hero-copy">
            <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}${sourceLabel(d.source) ? " • " + escapeHtml(sourceLabel(d.source)) : ""}</span></p>
            <h2 class="detail-title">${escapeHtml(d.topic)}</h2>
            <div class="draft-meta">
              ${d.seq_id ? `<span class="meta-chip meta-chip--muted">#${d.seq_id}</span>` : ""}
              ${formatPlanDate(d.created_at) ? `<span class="meta-chip meta-chip--muted">${escapeHtml(formatPlanDate(d.created_at))}</span>` : ""}
              ${d.updated_at && d.updated_at !== d.created_at ? `<span class="meta-chip meta-chip--muted">изм. ${escapeHtml(formatPlanDate(d.updated_at))}</span>` : ""}
              ${d.created_by_username ? `<span class="meta-chip meta-chip--muted">@${escapeHtml(d.created_by_username)}</span>` : ""}
              ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
              ${d.generation_pending && draftGenerationLabel(d) ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
              ${isContentReviewKind(d.kind) ? tagMarkup(feedbackLabel(d.feedback), feedbackTone(d.feedback)) : ""}
              ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
            </div>
          </div>
          <div class="actions-row detail-actions">
            <button class="primary-button" data-action="updateDraft" data-args='["status",{"status":"approved"},null]'>${actionLabel("approve", "Согласовать")}</button>
            <div class="detail-icon-actions">
              <button class="secondary-button" title="Вернуть на доработку" data-action="updateDraft" data-args='["status",{"status":"rejected"},null]'>${uiIcon("reject")}</button>
              ${d.kind === "carousel" ? `<button class="secondary-button" title="Обновить все слайды" data-action="regenerateCarouselAll" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("regenerate")}</button>` : ""}
            </div>
            ${d.kind === "carousel" ? `
              <div class="carousel-export-row">
                <button class="secondary-button" data-action="downloadCarouselPptx" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("download")}<span>PPTX</span></button>
                <button class="secondary-button" data-action="importCarouselPptx" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("upload")}<span>PPTX</span></button>
                <button class="secondary-button" data-action="exportToCanva" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("arrow-up-right")}<span>Canva</span></button>
                <button class="secondary-button" data-action="importFromCanva" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("arrow-down-left")}<span>Canva</span></button>
              </div>
            ` : ""}
            ${renderMoveButton(d.draft_id)}
          </div>
        </div>
        ${payloadSection("Превью", fullPreview(d))}
        ${payloadSection("Угол", p.angle)}
        ${payloadSection("Текст", mainText)}
        ${payloadSection("CTA", p.cta)}
        ${generationStateMarkup(d, "draft")}
        ${reviewActions}
        ${renderPublishPanel(d.draft_id, d.status, { kind: d.kind, hasMedia: _hasMedia(d) })}
        ${d.status === "published" ? `<section class="section metrics-section" id="metricsSection_${d.draft_id}"><div class="metrics-empty"><i data-lucide="bar-chart-3"></i><span>Загружаю метрики...</span></div></section>` : ""}
        ${renderSlides(d.draft_id, p.slides, p.img_prompts, p.slide_images, p.img_prompt_notes, p.slide_image_versions)}
        ${promptSection("Промпт для изображения", p.visual_prompt, "Скопировать промпт", `draft:${d.draft_id}:visual`)}
        <div class="actions-row detail-actions-danger">
          <button class="danger-button" data-action="deleteDraft" data-args='${JSON.stringify([d.draft_id, "drafts", null])}'>${actionLabel("trash", "Удалить")}</button>
        </div>
      </div>
    `;
    if (d.status === "published") _loadMetricsSection(d.draft_id);
    if (d.kind === "carousel") {
      const readyCount = (p.slide_images || []).filter(Boolean).length;
      const slideCount = (p.slides || []).length;
      if (d.generation_pending || readyCount < slideCount) scheduleCarouselRefresh(d.draft_id);
    }
  }


  // -- Metrics helpers --

  const PLATFORM_METRICS = {
    threads: [
      { key: "views", icon: "eye", label: "Просмотры" },
      { key: "likes", icon: "heart", label: "Лайки" },
      { key: "replies", icon: "message-circle", label: "Ответы" },
      { key: "reposts", icon: "repeat", label: "Репосты" },
      { key: "quotes", icon: "quote", label: "Цитаты" },
    ],
    instagram: [
      { key: "impressions", icon: "eye", label: "Показы" },
      { key: "reach", icon: "users", label: "Охват" },
      { key: "likes", icon: "heart", label: "Лайки" },
      { key: "comments", icon: "message-circle", label: "Комментарии" },
    ],
  };

  function _renderMetricsHTML(draftId, data) {
    const items = data.metrics || [];
    if (!items.length) {
      return `<div class="metrics-empty"><i data-lucide="bar-chart-3"></i><span>Метрики ещё не собраны</span></div>
        <div class="actions-row"><button class="secondary-button" type="button" data-action="refreshDraftMetrics" data-args='${JSON.stringify([draftId, null])}'><i data-lucide="refresh-cw"></i> Обновить</button></div>`;
    }
    let html = `<div class="section-heading"><h3><i data-lucide="bar-chart-3"></i> Эффективность</h3></div>`;
    for (const entry of items) {
      const defs = PLATFORM_METRICS[entry.platform] || [];
      if (!defs.length) continue;
      const m = entry.metrics || {};
      html += `<p class="metrics-platform-label">${escapeHtml(entry.platform)}</p><div class="metrics-grid">`;
      for (const def of defs) {
        const val = m[def.key];
        if (val === undefined || val === null) continue;
        html += `<div class="metric-card"><i data-lucide="${def.icon}"></i><span class="metric-value">${Number(val).toLocaleString("ru-RU")}</span><span class="metric-label">${escapeHtml(def.label)}</span></div>`;
      }
      html += `</div>`;
    }
    const latestFetch = items.reduce((acc, i) => (!acc || i.fetched_at > acc) ? i.fetched_at : acc, null);
    if (latestFetch) {
      const dt = new Date(latestFetch);
      const ts = dt.toLocaleDateString("ru-RU") + " " + dt.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
      html += `<p class="metrics-updated">Последнее обновление: ${ts}</p>`;
    }
    html += `<div class="actions-row"><button class="secondary-button" type="button" data-action="refreshDraftMetrics" data-args='${JSON.stringify([draftId, null])}'><i data-lucide="refresh-cw"></i> Обновить</button></div>`;
    return html;
  }

  async function _loadMetricsSection(draftId) {
    const container = document.getElementById(`metricsSection_${draftId}`);
    if (!container) return;
    try {
      const data = await fetchJson(`/api/drafts/${draftId}/metrics`);
      container.innerHTML = _renderMetricsHTML(draftId, data);
    } catch (_e) {
      container.innerHTML = `<div class="metrics-empty"><i data-lucide="bar-chart-3"></i><span>Метрики ещё не собраны</span></div>
        <div class="actions-row"><button class="secondary-button" type="button" data-action="refreshDraftMetrics" data-args='${JSON.stringify([draftId, null])}'><i data-lucide="refresh-cw"></i> Обновить</button></div>`;
    }
    if (window.lucide) lucide.createIcons();
  }

  async function refreshDraftMetrics(draftId, button) {
    await withButtonFeedback(button, "Обновляю...", async () => {
      await fetchJson(`/api/drafts/${draftId}/metrics/refresh`, { method: "POST", body: "{}" });
      await _loadMetricsSection(draftId);
    }, "Готово");
  }

  function renderEmptyDetail() {
    // On mobile, go back to list view instead of showing empty detail
    if (state.mobileView === "detail") {
      state.mobileView = "list";
    }
    elements.draftDetail.innerHTML = `
      ${renderBackButton()}
      <div class="detail-empty">
        ${renderGuidedState({
          eyebrow: "Детали",
          title: "Выберите элемент из списка",
          body: "Откройте карточку слева, чтобы увидеть детали, правки и быстрые действия.",
        })}
      </div>
    `;
    syncMobileNavigation();
  }

  function _hasMedia(d) {
    const p = d.payload || {};
    if (d.kind === "carousel") return !!(p.slide_images?.length);
    if (d.kind === "reels") return true;
    return !!(p.image?.filename);
  }

  async function moveDraftToTeam(draftId, targetTeamId, button) {
    await withButtonFeedback(button, "Переношу...", async () => {
      await fetchJson(`/api/drafts/${draftId}/move`, {
        method: "POST",
        body: JSON.stringify({ target_team_id: targetTeamId }),
      });
      state.drafts = state.drafts.filter((d) => d.draft_id !== draftId);
      if (state.selected?.draft_id === draftId) state.selected = null;
      renderDraftList();
      renderEmptyDetail();
    }, "Перенесён");
  }

  function renderMoveButton(draftId) {
    const teams = state.teams || [];
    if (teams.length <= 1) return "";
    const currentTeamId = state.activeTeamId;
    const otherTeams = teams.filter((t) => t.team_id !== currentTeamId);
    if (!otherTeams.length) return "";
    const options = otherTeams.map((t) =>
      `<option value="${escapeHtml(t.team_id)}">${escapeHtml(t.name)}</option>`
    ).join("");
    return `<select class="move-to-team-select" data-on-change="moveDraftToTeam" data-args='${JSON.stringify([draftId])}' data-guard="truthy"><option value="">Перенести в...</option>${options}</select>`;
  }

  return {
    saveContentReviewDraft,
    saveThreadsReviewDraft,
    polishContentDraft,
    renderDraftList,
    openDraft,
    renderDraftDetail,
    renderThreadsSeriesDetail,
    renderEmptyDetail,
    refreshDraftMetrics,
    moveDraftToTeam,
    renderMoveButton,
  };
}
