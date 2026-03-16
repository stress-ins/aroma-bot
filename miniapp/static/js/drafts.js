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
    callbacks,
  } = deps;

  const cleanSlotText = (t) => t ? t.replace(/^[-*_]{3,}\s*$/gm, '').replace(/\n{3,}/g, '\n\n').trim() : '';

  function fullPreview(d) {
    const p = d.payload || {};
    if (d.kind === "carousel" && Array.isArray(p.slides) && p.slides.length) {
      return p.hook || p.angle || p.caption || p.slides[0] || "";
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

  function renderDraftList() {
    elements.listTitle.textContent = "Черновики";
    elements.draftCount.textContent = `${state.drafts.length} шт`;
    setEmptyState(state.drafts.length > 0, {
      eyebrow: "Черновики",
      title: "Ничего не найдено",
      body: "Создайте первый материал через вкладку «Создать». Выберите формат, укажите тему — AI сделает остальное.",
      actionLabel: "Открыть создание",
      action: "openCreateTool()",
    });
    elements.draftList.innerHTML = state.drafts.map((d, idx) => `
      <article ${interactiveCardAttrs(`Открыть черновик ${d.topic}`)} class="draft-card overview-card${d.draft_id === state.draftId ? " active" : ""}${d.generation_pending ? " is-pending" : ""} interactive-card" onclick="openDraft('${d.draft_id}')">
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
            <textarea
              id="slotText_${post.slot}_${d.draft_id}"
              class="threads-post-textarea"
              placeholder="Текст поста"
              ${isApproved ? "readonly" : ""}
              oninput="document.getElementById('charCount_${post.slot}_${d.draft_id}').textContent=this.value.length"
            >${escapeHtml(cleanSlotText(post.text || ""))}</textarea>
            <div class="threads-char-counter${isOver ? " is-over" : ""}" id="charCount_${post.slot}_${d.draft_id}">${charCount}</div>
          </div>
          ${!isApproved ? `
          <div class="threads-regen-note">
            <input class="threads-regen-input" id="regenNote_${post.slot}_${d.draft_id}" type="text" placeholder="Пожелание к перегенерации (необязательно)">
          </div>
          <div class="threads-regen-row">
            <button class="secondary-button" type="button" onclick="regenSlot('${d.draft_id}','${post.slot}',this)">${actionLabel("regenerate", "Переписать")}</button>
            <button class="secondary-button" type="button" onclick="showSlotHistory('${d.draft_id}','${post.slot}')">${actionLabel("history", "История")}</button>
          </div>
          <div class="actions-row" style="margin-top:4px">
            <button class="secondary-button" type="button" onclick="saveThreadsSlot('${d.draft_id}','${post.slot}',this)">${actionLabel("approve", "Сохранить слот")}</button>
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
          <button class="primary-button" id="schedulerSubmit_${d.draft_id}" type="button" data-date="" disabled
            onclick="scheduleThreadsSeries('${d.draft_id}',this.dataset.date,['morning','day','evening'],this)">
            ${actionLabel("approve", "Запланировать")}
          </button>
        </div>
      </div>
    ` : "";

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top detail-hero">
          <div class="detail-hero-copy">
            <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))} • ${escapeHtml(sourceLabel(d.source))}</span></p>
            <h2 class="detail-title">${escapeHtml(d.topic)}</h2>
            <div class="draft-meta">
              ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
              ${p.goal ? tagMarkup(GOAL_LABELS[p.goal] || p.goal, "status-neutral") : ""}
              ${p.emotion ? tagMarkup(EMOTION_LABELS[p.emotion] || p.emotion, "status-neutral") : ""}
            </div>
          </div>
          <div class="actions-row detail-actions">
            ${!isApproved ? `<button class="primary-button" type="button" onclick="approveThreadsSeries('${d.draft_id}',this)">${actionLabel("approve", "Согласовать")}</button>` : ""}
            ${isApproved && d.status !== "published" ? `<button class="primary-button" type="button" onclick="openThreadsScheduler('${d.draft_id}')">${actionLabel("approve", "Запланировать")}</button>` : ""}
            <div class="detail-icon-actions">
              <button class="secondary-button" title="Отправить в чат" onclick="sendDraftToChat('${d.draft_id}',this)">${uiIcon("chat")}</button>
            </div>
            <button class="danger-button" onclick="deleteDraft('${d.draft_id}','drafts',this)">${actionLabel("trash", "Удалить")}</button>
          </div>
        </div>
        ${p.series_summary ? payloadSection("Опорная мысль", p.series_summary) : ""}
        <section class="section section-primary">
          <div class="section-heading">
            <h3>${uiIcon("text")}Посты серии</h3>
            <p>${isApproved ? "Серия согласована. Запланируйте публикацию." : "Отредактируйте каждый пост, затем согласуйте серию."}</p>
          </div>
          ${slotsHtml}
        </section>
        ${schedulerHtml}
      </div>
    `;
    syncMobileNavigation();
  }

  function renderDraftDetail(d) {
    if (d?.kind === "threads_series") {
      return renderThreadsSeriesDetail(d);
    }

    if (isPendingDraftId(d?.draft_id)) {
      elements.draftDetail.innerHTML = `
        <div class="detail-grid detail-grid-pending">
          ${renderBackButton()}
          <div class="detail-top">
            <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))} • ${escapeHtml(sourceLabel(d.source || "/miniapp"))}</span></p>
            <h2 class="detail-title">${escapeHtml(d.topic || "Создаём черновик")}</h2>
            <div class="draft-meta">
              ${tagMarkup("Черновик", "status-neutral")}
              ${tagMarkup("Ещё генерируется", "pending")}
            </div>
          </div>
          ${renderDetailLoader("Генерирую карточку", "Сохраняю черновик и подгружаю содержимое.", "detail-loader-card-compact")}
        </div>
      `;
      syncMobileNavigation();
      return;
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
                <button class="primary-button" type="button" onclick="saveThreadsReviewDraft('${d.draft_id}', this)">${actionLabel("approve", "Сохранить 3 поста")}</button>
                <button class="secondary-button" type="button" onclick="polishContentDraft('${d.draft_id}', this)">${actionLabel("sparkle", "Уточнить через AI")}</button>
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
                <button class="primary-button" type="button" onclick="saveContentReviewDraft('${d.draft_id}', this)">${actionLabel("approve", "Сохранить версию")}</button>
                <button class="secondary-button" type="button" onclick="polishContentDraft('${d.draft_id}', this)">${actionLabel("sparkle", "Уточнить через AI")}</button>
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
            <button class="secondary-button" type="button" onclick="updateDraft('feedback', {feedback:'worked'}, this)">${actionLabel("approve", "Откликнулось")}</button>
            <button class="secondary-button" type="button" onclick="updateDraft('feedback', {feedback:'missed'}, this)">${actionLabel("reject", "Не дало результата")}</button>
            <button class="secondary-button" type="button" onclick="updateDraft('feedback', {feedback:''}, this)">${actionLabel("back", "Очистить отметку")}</button>
          </div>
        </section>
      `
      : "";

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top detail-hero">
          <div class="detail-hero-copy">
            <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))} • ${escapeHtml(sourceLabel(d.source))}</span></p>
            <h2 class="detail-title">${escapeHtml(d.topic)}</h2>
            <div class="draft-meta">
              ${d.seq_id ? `<span class="meta-chip meta-chip--muted">#${d.seq_id}</span>` : ""}
              ${formatPlanDate(d.created_at) ? `<span class="meta-chip meta-chip--muted">${escapeHtml(formatPlanDate(d.created_at))}</span>` : ""}
              ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
              ${d.generation_pending && draftGenerationLabel(d) ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
              ${isContentReviewKind(d.kind) ? tagMarkup(feedbackLabel(d.feedback), feedbackTone(d.feedback)) : ""}
              ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
            </div>
          </div>
          <div class="actions-row detail-actions">
            <button class="primary-button" onclick="updateDraft('status', {status:'approved'}, this)">${actionLabel("approve", "Согласовать")}</button>
            <div class="detail-icon-actions">
              <button class="secondary-button" title="Вернуть на доработку" onclick="updateDraft('status', {status:'rejected'}, this)">${uiIcon("reject")}</button>
              <button class="secondary-button" title="Отправить в чат" onclick="sendDraftToChat('${d.draft_id}', this)">${uiIcon("chat")}</button>
              ${d.kind === "carousel" ? `<button class="secondary-button" title="Скачать презентацию" onclick="downloadCarouselPptx('${d.draft_id}', this)">${uiIcon("download")}</button>` : ""}
              ${d.kind === "carousel" ? `<button class="secondary-button" title="Импорт из Canva" onclick="importCarouselPptx('${d.draft_id}', this)">${uiIcon("upload")}</button>` : ""}
              ${d.kind === "carousel" ? `<button class="secondary-button" title="Обновить все слайды" onclick="regenerateCarouselAll('${d.draft_id}', this)">${uiIcon("regenerate")}</button>` : ""}
            </div>
            <button class="danger-button" onclick="deleteDraft('${d.draft_id}', 'drafts', this)">${actionLabel("trash", "Удалить")}</button>
          </div>
        </div>
        ${payloadSection("Превью", fullPreview(d))}
        ${payloadSection("Угол", p.angle)}
        ${payloadSection("Текст", mainText)}
        ${payloadSection("CTA", p.cta)}
        ${generationStateMarkup(d, "draft")}
        ${reviewActions}
        ${renderPublishPanel(d.draft_id, d.status, { kind: d.kind, hasMedia: _hasMedia(d) })}
        ${renderSlides(d.draft_id, p.slides, p.img_prompts, p.slide_images, p.img_prompt_notes, p.slide_image_versions)}
        ${promptSection("Промпт для изображения", p.visual_prompt, "Скопировать промпт", `draft:${d.draft_id}:visual`)}
      </div>
    `;
    if (d.kind === "carousel") {
      const readyCount = (p.slide_images || []).filter(Boolean).length;
      const slideCount = (p.slides || []).length;
      if (d.generation_pending || readyCount < slideCount) scheduleCarouselRefresh(d.draft_id);
    }
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

  return {
    saveContentReviewDraft,
    saveThreadsReviewDraft,
    polishContentDraft,
    renderDraftList,
    openDraft,
    renderDraftDetail,
    renderThreadsSeriesDetail,
    renderEmptyDetail,
  };
}
