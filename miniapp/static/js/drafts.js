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
    scheduleDraftRefresh,
    setEmptyState,
    enterDetailView,
    syncMobileNavigation,
    renderMarkdown,
    callbacks,
  } = deps;
  const showRequestError = deps.showRequestError || ((e) => console.error(e));
  const showUiNotice = deps.showUiNotice || ((msg) => console.log(msg));
  const renderPhotoPickerSection = deps.stockPhotoActions?.renderPhotoPickerSection || (() => "");

  const cleanSlotText = (t) => t ? t.replace(/\((?:Hot Take|Thread|Байт на обсуждение|Список|Туториал|Рефлексия|Шутка|Факап|Личная история)\)\s*/gi, '').replace(/^[-*_]{3,}\s*$/gm, '').replace(/\n{3,}/g, '\n\n').trim() : '';

  function _pluralizeDrafts(n) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return `${n} черновик`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${n} черновика`;
    return `${n} черновиков`;
  }

  function _metricsBadge(ms) {
    const parts = [];
    if (ms.likes) parts.push(`<i class="ph ph-heart" style="font-size:12px"></i> ${ms.likes}`);
    if (ms.comments) parts.push(`<i class="ph ph-chat-circle" style="font-size:12px"></i> ${ms.comments}`);
    if (ms.views) parts.push(`<i class="ph ph-eye" style="font-size:12px"></i> ${ms.views}`);
    if (!parts.length) return "";
    return `<span class="tag metrics-badge">${parts.join(" ")}</span>`;
  }

  function _canvaHeroPreview(p) {
    if (!p.canva_design_id) return "";
    const imgs = (p.slide_images || []).filter(Boolean);
    if (!imgs.length) return "";
    const thumbs = imgs.slice(0, 5).map((img, i) =>
      `<img src="${escapeHtml(img.url)}" alt="Слайд ${i + 1}" class="canva-hero-thumb" data-action="openImageFullscreen" data-args='${JSON.stringify([img.url, `Слайд ${i + 1}`])}' />`
    ).join("");
    const extra = imgs.length > 5 ? `<span class="canva-hero-extra">+${imgs.length - 5}</span>` : "";
    return `<div class="canva-hero-strip">${thumbs}${extra}</div>`;
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
        timeout: 30000,
      });
      mergeDraftIntoState(draft);
      callbacks.renderDraftList?.();
      callbacks.renderDraftDetail?.(draft);
    }, "Готово");
  }

  function renderDraftList() {
    elements.listTitle.textContent = "Вдохновение";
    elements.draftCount.textContent = _pluralizeDrafts(state.drafts.length);
    setEmptyState(state.drafts.length > 0, {
      eyebrow: "Публикации",
      title: "Ничего не найдено",
      body: "Создайте первый материал через вкладку «Создать». Выберите формат, укажите тему — AI сделает остальное.",
      actionLabel: "Открыть создание",
      action: "openCreateTool()",
    });
    elements.draftList.innerHTML = state.drafts.map((d, idx) => `
      <article ${interactiveCardAttrs(`Открыть черновик ${d.topic}`)} class="draft-card overview-card${d.draft_id === state.draftId ? " active" : ""}${d.generation_pending ? " is-pending" : ""} interactive-card" data-action="openDraft" data-args='${JSON.stringify([d.draft_id])}'>
        <div class="overview-card-top">
          <div class="draft-kind">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}</span></div>
          <span class="overview-card-date">#${d.seq_id || idx + 1} · ${escapeHtml(formatPlanDate(d.created_at) || "Новый черновик")}</span>
        </div>
        <h3 class="draft-topic">${escapeHtml(d.topic)}</h3>
        <div class="draft-preview">${escapeHtml(stripMarkdown(d.preview || "Без превью"))}</div>
        <div class="draft-meta overview-card-footer">
          ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
          ${d.payload?.canva_design_id ? tagMarkup("Canva", "status-positive") : ""}
          ${d.generation_pending && draftGenerationLabel(d) ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
          ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
          ${d.metrics_summary ? _metricsBadge(d.metrics_summary) : ""}
        </div>
      </article>
    `).join("");
    syncMobileNavigation();
  }

  async function openDraft(id, { quiet = false } = {}) {
    if (isPendingDraftId(id) && state.selected?.draft_id === id) {
      renderDraftList();
      renderDraftDetail(state.selected);
      enterDetailView();
      return;
    }
    if (!quiet) {
      elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю черновик")}`;
      enterDetailView();
    }
    const d = await fetchJson(`/api/drafts/${id}`, { timeout: 20000 });
    if ((d?.kind === "reels" || d?.kind === "reels_v2") && callbacks.openReels) {
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

    const sourceBadges = [
      p.trend_source ? tagMarkup("На основе тренда", "status-neutral") : "",
      p.handbook_source ? tagMarkup("Из справочника", "status-neutral") : "",
    ].filter(Boolean).join(" ");

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
            <div class="threads-char-counter${isOver ? " is-over" : charCount > 480 ? " is-warn" : ""}" id="charCount_${post.slot}_${d.draft_id}">${charCount} / 500</div>
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
              ${sourceBadges}
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
            <p>${isApproved ? "Серия согласована. Запланируйте публикацию." : d.generation_pending && !posts.length ? "Генерируем посты..." : posts.length ? "Отредактируйте каждый пост, затем согласуйте серию." : "Посты не были сгенерированы. Попробуйте заново."}</p>
          </div>
          ${d.generation_pending && !posts.length ? renderDetailLoader("Генерирую серию", "Создаю три поста: утро, день, вечер.<br>Займёт 15–30 секунд.", "detail-loader-card-compact") : ""}
          ${slotsHtml}
          ${!posts.length && !isApproved && !d.generation_pending ? `
          <div class="actions-row" style="margin-top: var(--space-3)">
            <button class="primary-button" type="button" data-action="regenerateSeriesPosts" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("regenerate", "Сгенерировать посты")}</button>
          </div>
          <p class="field-help">AI подбирает лучший контент — генерация может занять 15–30 секунд.</p>
          ` : ""}
        </section>
        <div class="actions-row detail-actions-danger">
          <button class="danger-button" data-action="deleteDraft" data-args='${JSON.stringify([d.draft_id, "drafts", null])}'>${actionLabel("trash", "Удалить")}</button>
        </div>
      </div>
    `;
    syncMobileNavigation();
    if (d.generation_pending || (!posts.length && !isApproved)) {
      scheduleDraftRefresh(d.draft_id);
    }
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

    if (d?.kind === "content_series") {
      return renderContentSeriesDetail(d);
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
                <div id="hashtagRecommendations" hidden class="hashtag-recommendations"></div>
                <button class="secondary-button" type="button" data-action="recommendHashtags" data-args='${JSON.stringify([d.draft_id])}'>${uiIcon("hash", 14)}<span>Подобрать хэштеги</span></button>
                <label><span>Промпт для визуала</span><textarea id="contentVisualPromptField" placeholder="Какой образ или сцену должен поддержать визуал">${escapeHtml(p.visual_prompt || "")}</textarea></label>
                <label><span>Комментарий редактора</span><textarea id="contentEditorNotesField" placeholder="Что усилить или перепроверить">${escapeHtml(p.editor_notes || "")}</textarea></label>
              </div>
              <div class="tone-adapter-row">
                <span class="tone-label">${uiIcon("palette", 14)} Тональность:</span>
                <button class="keyword-chip" type="button" data-action="adaptTone" data-args='${JSON.stringify([d.draft_id, "educational"])}'>Образовательный</button>
                <button class="keyword-chip" type="button" data-action="adaptTone" data-args='${JSON.stringify([d.draft_id, "inspirational"])}'>Вдохновляющий</button>
                <button class="keyword-chip" type="button" data-action="adaptTone" data-args='${JSON.stringify([d.draft_id, "selling"])}'>Продающий</button>
                <button class="keyword-chip" type="button" data-action="adaptTone" data-args='${JSON.stringify([d.draft_id, "storytelling"])}'>Сторителлинг</button>
              </div>
              <div class="actions-row review-actions">
                <button class="primary-button" type="button" data-action="saveContentReviewDraft" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("approve", "Сохранить версию")}</button>
                <button class="secondary-button" type="button" data-action="polishContentDraft" data-args='${JSON.stringify([d.draft_id, null])}'>${actionLabel("sparkle", "Уточнить через AI")}</button>
                ${d.status === "approved" ? `<button class="secondary-button" type="button" data-action="startRepurpose" data-args='${JSON.stringify([d.draft_id])}'>${uiIcon("copy-plus", 14)}<span>Адаптировать в другие форматы</span></button>` : ""}
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
              ${p.canva_design_id ? tagMarkup("Canva", "status-positive") : ""}
              ${d.kind === "carousel" && p.layout_style === "editorial" ? tagMarkup("Редакционная", "status-neutral") : ""}
              ${d.generation_pending && draftGenerationLabel(d) ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
              ${isContentReviewKind(d.kind) ? tagMarkup(feedbackLabel(d.feedback), feedbackTone(d.feedback)) : ""}
              ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
            </div>
          </div>
          ${_canvaHeroPreview(p)}
          <div class="actions-row detail-actions">
            ${(() => {
              if (d.kind === "carousel") {
                const readyCount = (p.slide_images || []).filter(Boolean).length;
                const slideCount = (p.slides || []).length;
                const allSlidesReady = slideCount > 0 && readyCount >= slideCount && !d.generation_pending;
                return `<button class="primary-button${allSlidesReady ? "" : " is-disabled"}" ${allSlidesReady ? "" : "disabled"} data-action="updateDraft" data-args='["status",{"status":"approved"},null]'>${actionLabel("approve", "Согласовать")}</button>${!allSlidesReady && slideCount > 0 ? `<span class="field-help">Готово ${readyCount} из ${slideCount} слайдов</span>` : ""}`;
              }
              return `<button class="primary-button" data-action="updateDraft" data-args='["status",{"status":"approved"},null]'>${actionLabel("approve", "Согласовать")}</button>`;
            })()}
            <div class="detail-icon-actions">
              <button class="secondary-button" title="Вернуть на доработку" data-action="updateDraft" data-args='["status",{"status":"rejected"},null]'>${uiIcon("reject")}</button>
              ${d.kind === "carousel" ? `<button class="secondary-button" title="Обновить все слайды" data-action="regenerateCarouselAll" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("regenerate")}</button>` : ""}
            </div>
            ${d.kind === "carousel" && !d.generation_pending ? `
              <div class="carousel-export-row">
                <button class="secondary-button" data-action="downloadCarouselPptx" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("download")}<span>Скачать PPTX</span></button>
                <button class="secondary-button" data-action="importCarouselPptx" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("upload")}<span>Загрузить PPTX</span></button>
                <button class="secondary-button" data-action="exportToCanva" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("arrow-up-right")}<span>Открыть в Canva</span></button>
                <button class="secondary-button" data-action="importFromCanva" data-args='${JSON.stringify([d.draft_id, null])}'>${uiIcon("arrow-down-left")}<span>Импорт из Canva</span></button>
              </div>
            ` : ""}
            ${renderMoveButton(d.draft_id)}
          </div>
          ${d.kind === "carousel" ? (() => {
            const curLayout = p.layout_style || "overlay";
            return `<div class="carousel-layout-switcher">
              <p class="field-label">Раскладка слайда</p>
              <div class="layout-option-row">
                <label class="layout-option${curLayout === "overlay" ? " layout-option--active" : ""}">
                  <input type="radio" name="detail_layout_style" value="overlay" ${curLayout === "overlay" ? "checked" : ""} hidden>
                  <div class="layout-preview layout-preview--overlay"><div class="lp-image"></div><div class="lp-text-overlay"></div></div>
                  <span>Полное фото</span>
                </label>
                <label class="layout-option${curLayout === "editorial" ? " layout-option--active" : ""}">
                  <input type="radio" name="detail_layout_style" value="editorial" ${curLayout === "editorial" ? "checked" : ""} hidden>
                  <div class="layout-preview layout-preview--editorial"><div class="lp-image" style="height:55%"></div><div class="lp-text-block"><span class="lp-highlight"></span><span class="lp-line"></span></div></div>
                  <span>Редакционная</span>
                </label>
              </div>
            </div>`;
          })() : ""}
        </div>
        ${payloadSection("Превью", fullPreview(d))}
        ${payloadSection("Угол", p.angle)}
        ${payloadSection("Текст", mainText)}
        ${payloadSection("CTA", p.cta)}
        ${generationStateMarkup(d, "draft")}
        ${reviewActions}
        ${renderPublishPanel(d.draft_id, d.status, { kind: d.kind, hasMedia: _hasMedia(d) })}
        ${d.status === "published" ? `<section class="section metrics-section" id="metricsSection_${d.draft_id}"><div class="metrics-empty"><i class="ph ph-chart-bar"></i><span>Загружаю метрики...</span></div></section>` : ""}
        ${renderSlides(d.draft_id, p.slides, p.img_prompts, p.slide_images, p.img_prompt_notes, p.slide_image_versions)}
        ${promptSection("Промпт для изображения", p.visual_prompt, "Скопировать промпт", `draft:${d.draft_id}:visual`)}
        ${renderPhotoPickerSection(d.draft_id, p.stock_keywords || [], p.image || null, p.stock_suggestions || null)}
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
      // Layout switcher
      elements.draftDetail.querySelectorAll('[name="detail_layout_style"]').forEach((radio) => {
        radio.addEventListener("change", async () => {
          const newStyle = radio.value;
          elements.draftDetail.querySelectorAll(".layout-option").forEach((lbl) =>
            lbl.classList.toggle("layout-option--active", lbl.querySelector("input")?.value === newStyle));
          try {
            const updated = await fetchJson(`/api/carousel/${d.draft_id}/layout`, {
              method: "POST", body: JSON.stringify({ layout_style: newStyle }),
            });
            mergeDraftIntoState(updated);
            callbacks.renderDraftList?.();
          } catch (_err) {
            showUiNotice("Не удалось сменить раскладку", "error");
          }
        });
      });
    } else if (d.generation_pending) {
      scheduleDraftRefresh(d.draft_id);
    }
  }


  // -- Metrics helpers --

  const PLATFORM_METRICS = {
    threads: [
      { key: "views", icon: "eye", label: "Просмотры" },
      { key: "likes", icon: "heart", label: "Лайки" },
      { key: "replies", icon: "chat-circle", label: "Ответы" },
      { key: "reposts", icon: "repeat", label: "Репосты" },
      { key: "quotes", icon: "quotes", label: "Цитаты" },
    ],
    instagram: [
      { key: "impressions", icon: "eye", label: "Показы" },
      { key: "reach", icon: "users", label: "Охват" },
      { key: "likes", icon: "heart", label: "Лайки" },
      { key: "comments", icon: "chat-circle", label: "Комментарии" },
    ],
  };

  function _renderMetricsHTML(draftId, data) {
    const items = data.metrics || [];
    if (!items.length) {
      return `<div class="metrics-empty"><i class="ph ph-chart-bar"></i><span>Метрики ещё не собраны</span></div>
        <div class="actions-row"><button class="secondary-button" type="button" data-action="refreshDraftMetrics" data-args='${JSON.stringify([draftId, null])}'><i class="ph ph-arrow-clockwise"></i> Обновить</button></div>`;
    }
    let html = `<div class="section-heading"><h3><i class="ph ph-chart-bar"></i> Эффективность</h3></div>`;
    for (const entry of items) {
      const defs = PLATFORM_METRICS[entry.platform] || [];
      if (!defs.length) continue;
      const m = entry.metrics || {};
      html += `<p class="metrics-platform-label">${escapeHtml(entry.platform)}</p><div class="metrics-grid">`;
      for (const def of defs) {
        const val = m[def.key];
        if (val === undefined || val === null) continue;
        html += `<div class="metric-card"><i class="ph ph-${def.icon}"></i><span class="metric-value">${Number(val).toLocaleString("ru-RU")}</span><span class="metric-label">${escapeHtml(def.label)}</span></div>`;
      }
      html += `</div>`;
    }
    const latestFetch = items.reduce((acc, i) => (!acc || i.fetched_at > acc) ? i.fetched_at : acc, null);
    if (latestFetch) {
      const dt = new Date(latestFetch);
      const ts = dt.toLocaleDateString("ru-RU") + " " + dt.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
      html += `<p class="metrics-updated">Последнее обновление: ${ts}</p>`;
    }
    html += `<div class="actions-row"><button class="secondary-button" type="button" data-action="refreshDraftMetrics" data-args='${JSON.stringify([draftId, null])}'><i class="ph ph-arrow-clockwise"></i> Обновить</button></div>`;
    return html;
  }

  async function _loadMetricsSection(draftId) {
    const container = document.getElementById(`metricsSection_${draftId}`);
    if (!container) return;
    try {
      const data = await fetchJson(`/api/drafts/${draftId}/metrics`);
      container.innerHTML = _renderMetricsHTML(draftId, data);
    } catch (_e) {
      container.innerHTML = `<div class="metrics-empty"><i class="ph ph-chart-bar"></i><span>Метрики ещё не собраны</span></div>
        <div class="actions-row"><button class="secondary-button" type="button" data-action="refreshDraftMetrics" data-args='${JSON.stringify([draftId, null])}'><i class="ph ph-arrow-clockwise"></i> Обновить</button></div>`;
    }
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
          actionLabel: "Создать черновик",
          action: "openCreateTool()",
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

  // ── Content Series Detail ──────────────────────────────────────────
  function renderContentSeriesDetail(d) {
    const p = d.payload || {};
    const posts = p.series_posts || [];
    const coherenceScore = p.coherence_score;
    const roleLabels = { intro: "Вступление", middle: "Основной", climax: "Кульминация", cta: "Призыв" };
    const roleColors = { intro: "var(--brand)", middle: "var(--muted)", climax: "var(--accent, var(--brand))", cta: "var(--success, #4CAF50)" };

    const isApproved = d.status === "approved" || d.status === "scheduled" || d.status === "published";
    const postsHtml = posts.map((post, i) => {
      const charCount = (post.caption || "").length;
      const isOver = charCount > 2200;
      return `
      <div class="series-post-card" data-index="${i}">
        <div class="series-post-header">
          <span class="series-role-badge" style="background:${roleColors[post.role] || "var(--muted)"}">${roleLabels[post.role] || post.role}</span>
          <strong>${escapeHtml(post.title || `Пост ${i + 1}`)}</strong>
        </div>
        ${!isApproved ? `
        <textarea class="series-post-textarea" id="seriesCaption_${d.draft_id}_${i}"
          placeholder="Текст публикации"
          data-on-input="_syncSeriesCharCount" data-count-target="seriesCharCount_${d.draft_id}_${i}">${escapeHtml(post.caption || "")}</textarea>
        <div class="threads-char-counter${isOver ? " is-over" : ""}" id="seriesCharCount_${d.draft_id}_${i}">${charCount}</div>
        <div class="series-post-regen-row">
          <input class="threads-regen-input" id="seriesNote_${d.draft_id}_${i}" type="text"
            placeholder="Замечание к перегенерации (необязательно)">
        </div>
        <div class="series-post-actions">
          <button class="secondary-button" type="button" data-action="saveSeriesPost" data-args='${JSON.stringify([d.draft_id, i, null])}'>${uiIcon("save", 14)}<span>Сохранить</span></button>
          <button class="secondary-button" type="button" data-action="regenSeriesPost" data-args='${JSON.stringify([d.draft_id, i, null])}'>${uiIcon("refresh-cw", 14)}<span>Переписать</span></button>
        </div>
        ` : `
        <div class="series-post-preview">${escapeHtml(post.caption || "")}</div>
        `}
      </div>
    `}).join("");

    const coherenceHtml = coherenceScore != null ? `
      <div class="series-coherence">
        <span class="series-coherence-score">Связность: <strong style="color:${coherenceScore >= 0.7 ? "var(--success, green)" : coherenceScore >= 0.5 ? "var(--brand)" : "var(--error, red)"}">${(coherenceScore * 100).toFixed(0)}%</strong></span>
        ${(p.coherence_issues || []).length ? `<ul class="series-issues">${p.coherence_issues.map(i => `<li class="series-issue-item">${escapeHtml(i)}</li>`).join("")}</ul>` : ""}
      </div>
    ` : "";

    elements.draftDetail.innerHTML = `
      <div class="detail-grid series-detail-grid">
        ${renderBackButton()}
        <div class="detail-top series-detail-top">
          <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}</span></p>
          <h2 class="detail-title">${escapeHtml(d.topic || "Контент-серия")}</h2>
          <p class="series-meta">${posts.length} постов${p.template_key && p.template_key !== "custom" ? ` · ${escapeHtml(p.template_key)}` : ""}</p>
        </div>
        ${coherenceHtml}
        <div class="series-posts-timeline">${postsHtml}</div>
        <div class="actions-row detail-actions">
          <button class="primary-button" type="button" data-action="coherenceCheck" data-args='${JSON.stringify([d.draft_id])}'>${uiIcon("check-circle")}<span>Проверить связность</span></button>
          <button class="secondary-button" type="button" data-action="regenSeriesAll" data-args='${JSON.stringify([d.draft_id])}'>${uiIcon("refresh-cw")}<span>Перегенерировать всё</span></button>
          ${d.status === "draft" ? `<button class="primary-button" type="button" data-action="updateDraft" data-args='["status",{"status":"approved"},null]'>${uiIcon("check")}<span>Утвердить</span></button>` : ""}
        </div>
      </div>
    `;
    syncMobileNavigation();
  }

  async function saveSeriesPost(draftId, index, _btn) {
    const textarea = document.getElementById(`seriesCaption_${draftId}_${index}`);
    const caption = textarea?.value ?? "";
    const btn = _btn || document.querySelector(`[data-action="saveSeriesPost"][data-args*="${draftId}"]`);
    await withButtonFeedback(btn, "Сохраняю...", async () => {
      await fetchJson(`/api/series/${draftId}/post/${index}`, {
        method: "PATCH",
        body: JSON.stringify({ caption }),
      });
      showUiNotice("Сохранено", "success");
    });
  }

  async function regenSeriesPost(draftId, index, _btn) {
    const noteEl = document.getElementById(`seriesNote_${draftId}_${index}`);
    const note = noteEl?.value?.trim() || null;
    const btn = _btn || document.querySelector(`[data-action="regenSeriesPost"][data-args*='"${index}"']`);
    await withButtonFeedback(btn, "Переписываю...", async () => {
      await fetchJson(`/api/series/${draftId}/regen-post/${index}`, {
        method: "POST",
        body: JSON.stringify(note ? { note } : {}),
        timeout: 30000,
      });
      await openDraft(draftId);
    });
  }

  async function regenSeriesAll(draftId) {
    try {
      await fetchJson(`/api/series/${draftId}/regen-all`, { method: "POST", timeout: 90000 });
      showUiNotice("Серия перегенерируется...", "info");
      await openDraft(draftId);
    } catch (e) { showRequestError(e); }
  }

  async function coherenceCheck(draftId) {
    try {
      const result = await fetchJson(`/api/series/${draftId}/coherence-check`, { method: "POST", timeout: 30000 });
      showUiNotice(`Связность: ${(result.score * 100).toFixed(0)}%`, result.score >= 0.7 ? "success" : "warning");
      await openDraft(draftId);
    } catch (e) { showRequestError(e); }
  }

  // ── Hashtag Recommender ──────────────────────────────────────────
  async function recommendHashtags(draftId) {
    const captionEl = document.getElementById("contentCaptionField");
    const text = captionEl?.value || "";
    if (!text.trim()) { showUiNotice("Нет текста для анализа", "warning"); return; }
    try {
      const data = await fetchJson("/api/hashtags/recommend", {
        method: "POST", timeout: 20000,
        body: JSON.stringify({ text, platform: "instagram", count: 12 }),
      });
      const container = document.getElementById("hashtagRecommendations");
      if (container && data.hashtags) {
        const tierColors = { high: "#4CAF50", medium: "#2196F3", niche: "#9C27B0" };
        container.innerHTML = data.hashtags.map(h =>
          `<span class="keyword-chip" style="border-color:${tierColors[h.tier] || "#999"};cursor:pointer" data-tag="${escapeHtml(h.tag)}">#${escapeHtml(h.tag)}</span>`
        ).join(" ") + `<button class="secondary-button" type="button" data-action="applyRecommendedHashtags" data-args='${JSON.stringify([draftId, data.hashtags.map(h => h.tag)])}'>${uiIcon("check", 14)}<span>Применить все</span></button>`;
        container.hidden = false;
      }
    } catch (e) { showRequestError(e); }
  }

  async function applyRecommendedHashtags(draftId, tags) {
    try {
      await fetchJson("/api/hashtags/apply", {
        method: "POST",
        body: JSON.stringify({ draft_id: draftId, hashtags: tags }),
      });
      const field = document.getElementById("contentHashtagsField");
      if (field) field.value = tags.map(t => `#${t}`).join(" ");
      showUiNotice("Хэштеги применены", "success");
    } catch (e) { showRequestError(e); }
  }

  // ── Tone Adapter ─────────────────────────────────────────────────
  async function adaptTone(draftId, tone) {
    try {
      const data = await fetchJson(`/api/drafts/${draftId}/tone/adapt`, {
        method: "POST", timeout: 30000,
        body: JSON.stringify({ tone }),
      });
      if (data.adapted_text) {
        const captionEl = document.getElementById("contentCaptionField");
        if (captionEl) captionEl.value = data.adapted_text;
        showUiNotice(`Тон "${data.label}" применён`, "success");
      }
    } catch (e) { showRequestError(e); }
  }

  // ── Smart Schedule ───────────────────────────────────────────────
  async function loadScheduleRecommendations(topic, container) {
    try {
      const data = await fetchJson(`/api/schedule/recommend?topic=${encodeURIComponent(topic)}&platform=instagram`);
      if (data.slots && data.slots.length && container) {
        const slotsHtml = data.slots.map(s =>
          `<button type="button" class="keyword-chip schedule-slot-chip" data-day="${s.day}" data-hour="${s.hour_msk}" title="${escapeHtml(s.reason)}">${s.day.substring(0, 2).toUpperCase()} ${s.hour_msk}:00 (${(s.score * 100).toFixed(0)}%)</button>`
        ).join(" ");
        container.innerHTML = `<div class="schedule-recommend-label">${uiIcon("clock", 14)} Рекомендация${data.cold_start ? " (wellness defaults)" : ""}:</div>${slotsHtml}`;
        container.hidden = false;
      }
    } catch (_e) { /* optional */ }
  }

  // ── Repurpose Engine ─────────────────────────────────────────────
  async function startRepurpose(draftId) {
    const formats = ["carousel", "reels_v2", "threads_series"];
    try {
      const data = await fetchJson("/api/repurpose/start", {
        method: "POST", timeout: 15000,
        body: JSON.stringify({ source_draft_id: draftId, formats }),
      });
      showUiNotice(`Адаптация запущена: ${formats.length} форматов`, "success");
    } catch (e) { showRequestError(e); }
  }

  return {
    saveContentReviewDraft,
    saveThreadsReviewDraft,
    polishContentDraft,
    renderDraftList,
    openDraft,
    renderDraftDetail,
    renderContentSeriesDetail,
    renderThreadsSeriesDetail,
    renderEmptyDetail,
    refreshDraftMetrics,
    moveDraftToTeam,
    renderMoveButton,
    recommendHashtags,
    applyRecommendedHashtags,
    adaptTone,
    loadScheduleRecommendations,
    startRepurpose,
    saveSeriesPost,
    regenSeriesPost,
    regenSeriesAll,
    coherenceCheck,
  };
}
