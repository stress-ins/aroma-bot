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
    fetchJson,
    withButtonFeedback,
    mergeDraftIntoState,
    scheduleCarouselRefresh,
    setEmptyState,
    enterDetailView,
    syncMobileNavigation,
    callbacks,
  } = deps;

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
      body: "Попробуйте сбросить фильтры или собрать новый материал через вкладку «Создать».",
      actionLabel: "Открыть создание",
      action: "setTab('create')",
    });
    elements.draftList.innerHTML = state.drafts.map((d) => `
      <article ${interactiveCardAttrs(`Открыть черновик ${d.topic}`)} class="draft-card overview-card${d.draft_id === state.draftId ? " active" : ""}${d.generation_pending ? " is-pending" : ""} interactive-card" onclick="openDraft('${d.draft_id}')">
        <div class="overview-card-top">
          <div class="draft-kind">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}</span></div>
          <span class="overview-card-date">${escapeHtml(formatPlanDate(d.created_at) || "Новый черновик")}</span>
        </div>
        <h3 class="draft-topic">${escapeHtml(d.topic)}</h3>
        <div class="draft-preview">${escapeHtml(stripMarkdown(d.preview || "Без превью"))}</div>
        <div class="draft-meta overview-card-footer">
          ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
          ${d.generation_pending ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
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
    state.selected = d;
    state.draftId = id;
    renderDraftList();
    renderDraftDetail(d);
    enterDetailView();
  }

  function renderDraftDetail(d) {
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
    const heroFacts = [
      detailFactMarkup("Тип", kindLabel(d.kind)),
      detailFactMarkup("Источник", sourceLabel(d.source)),
      detailFactMarkup("Статус", statusLabel(d.status)),
      isContentReviewKind(d.kind) ? detailFactMarkup("Реакция", feedbackLabel(d.feedback)) : "",
      detailFactMarkup("Создан", formatPlanDate(d.created_at)),
    ].join("");

    const reviewActions = isContentReviewKind(d.kind)
      ? `
        <section class="section section-primary">
          <div class="section-heading">
            <h3>${uiIcon("text")}Редакторский review</h3>
            <p>Сначала соберите сильную мысль и основной текст, затем уточните подачу, визуал и комментарии для следующего прохода.</p>
          </div>
          <div class="content-review-form">
            <div class="content-review-highlight">
              <label><span>Тема материала</span><textarea id="contentTopicField" placeholder="О чем этот материал и зачем он читателю">${escapeHtml(d.topic || "")}</textarea></label>
              <label><span>Опорная мысль</span><textarea id="contentAngleField" placeholder="Какой угол подачи или тезис держит весь текст">${escapeHtml(p.angle || "")}</textarea></label>
              <label><span>Первая фраза</span><textarea id="contentHookField" placeholder="С чего лучше начать, чтобы зацепить внимание">${escapeHtml(p.hook || "")}</textarea></label>
            </div>
            <label class="content-review-lead"><span>Основной текст</span><textarea id="contentCaptionField" placeholder="Соберите здесь основную версию текста, которую будете отправлять на согласование">${escapeHtml(p.caption || "")}</textarea></label>
            <p class="field-help">Сохраняйте версию после смыслового прохода. Если нужен быстрый черновой рефайн, используйте AI как промежуточный шаг.</p>
            <div class="content-review-support-grid">
              <label><span>Призыв к действию</span><textarea id="contentCtaField" placeholder="Что читателю стоит сделать после текста">${escapeHtml(p.cta || "")}</textarea></label>
              <label><span>Теги</span><textarea id="contentHashtagsField" placeholder="#ритуал #аромапрактика">${escapeHtml(p.hashtags || "")}</textarea></label>
              <label><span>Промпт для визуала</span><textarea id="contentVisualPromptField" placeholder="Какой образ или сцену должен поддержать визуал">${escapeHtml(p.visual_prompt || "")}</textarea></label>
              <label><span>Комментарий редактора</span><textarea id="contentEditorNotesField" placeholder="Что стоит усилить, сократить или перепроверить в следующем проходе">${escapeHtml(p.editor_notes || "")}</textarea></label>
            </div>
            <div class="actions-row review-actions">
              <button class="primary-button" type="button" onclick="saveContentReviewDraft('${d.draft_id}', this)">${actionLabel("approve", "Сохранить версию")}</button>
              <button class="secondary-button" type="button" onclick="polishContentDraft('${d.draft_id}', this)">${actionLabel("sparkle", "Уточнить через AI")}</button>
            </div>
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
            <p class="detail-summary">${escapeHtml(draftHeroSummary(d, p, mainText))}</p>
            <div class="draft-meta">
              ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
              ${d.generation_pending ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
              ${isContentReviewKind(d.kind) ? tagMarkup(feedbackLabel(d.feedback), feedbackTone(d.feedback)) : ""}
              ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
            </div>
          </div>
          <div class="detail-hero-side">
            <div class="detail-facts">${heroFacts}</div>
          </div>
          <div class="actions-row detail-actions">
            <button class="secondary-button" onclick="updateDraft('status', {status:'approved'}, this)">${actionLabel("approve", "Отметить как согласовано")}</button>
            <button class="secondary-button" onclick="updateDraft('status', {status:'rejected'}, this)">${actionLabel("reject", "Вернуть на доработку")}</button>
            <button class="secondary-button" onclick="sendDraftToChat('${d.draft_id}', this)">${actionLabel("chat", "Отправить в чат")}</button>
            ${d.kind === "carousel" ? `<button class="secondary-button" onclick="downloadCarouselPptx('${d.draft_id}', this)">${actionLabel("pptx", "Скачать презентацию")}</button>` : ""}
            ${d.kind === "carousel" ? `<button class="secondary-button" onclick="regenerateCarouselAll('${d.draft_id}', this)">${actionLabel("regenerate", "Обновить все слайды")}</button>` : ""}
            <button class="secondary-button" onclick="deleteDraft('${d.draft_id}', 'drafts', this)">${actionLabel("trash", "Удалить черновик")}</button>
          </div>
        </div>
        ${payloadSection("Превью", d.preview)}
        ${payloadSection("Угол", p.angle)}
        ${payloadSection("Текст", mainText)}
        ${payloadSection("CTA", p.cta)}
        ${generationStateMarkup(d, "draft")}
        ${reviewActions}
        ${renderSlides(d.draft_id, p.slides, p.img_prompts, p.slide_images, p.img_prompt_notes, p.slide_image_versions)}
        ${promptSection("Промпт для изображения", p.visual_prompt)}
      </div>
    `;
    if (d.kind === "carousel") {
      const readyCount = (p.slide_images || []).filter(Boolean).length;
      const slideCount = (p.slides || []).length;
      if (d.generation_pending || readyCount < slideCount) scheduleCarouselRefresh(d.draft_id);
    }
  }

  function renderEmptyDetail() {
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

  return {
    saveContentReviewDraft,
    polishContentDraft,
    renderDraftList,
    openDraft,
    renderDraftDetail,
    renderEmptyDetail,
  };
}
