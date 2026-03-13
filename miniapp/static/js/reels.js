export function createReelsModule(deps) {
  const {
    state,
    reelsNoteSaveTimers,
    reelsPromptSaveTimers,
    frameDraftKey,
    escapeHtml,
    uiIcon,
    sectionHeadingIcon,
    actionLabel,
    tagMarkup,
    statusLabel,
    statusTone,
    sourceLabel,
    sourceTone,
    draftGenerationLabel,
    generationStateMarkup,
    renderBackButton,
    renderDetailLoader,
    renderMarkdown,
    fetchJson,
    withButtonFeedback,
    showRequestError,
    confirmAction,
    mergeReelsIntoState,
    scheduleReelsRefresh,
    callbacks,
  } = deps;

  function bufferedReelsNote(draftId, index, fallback = "") {
    const key = frameDraftKey(draftId, index);
    return Object.prototype.hasOwnProperty.call(state.pendingReelsNotes, key)
      ? state.pendingReelsNotes[key]
      : String(fallback || "");
  }

  function bufferedReelsPrompt(draftId, index, fallback = "") {
    const key = frameDraftKey(draftId, index);
    return Object.prototype.hasOwnProperty.call(state.pendingReelsPrompts, key)
      ? state.pendingReelsPrompts[key]
      : String(fallback || "");
  }

  function reelsFrameStatusMarkup(frame = {}) {
    if (frame.current_asset?.url) {
      return `<div class="slide-status is-ready">${uiIcon("approve")}<span>Кадр готов</span></div>`;
    }
    if (String(frame.gemini_prompt || "").trim()) {
      return `<div class="slide-status is-pending">${uiIcon("sparkle")}<span>Кадр генерируется по промпту</span></div>`;
    }
    return `<div class="slide-status is-empty">${uiIcon("image")}<span>Кадр еще не подготовлен</span></div>`;
  }

  function normalizedReelsFrames(reel = {}) {
    if (Array.isArray(reel.frames) && reel.frames.length) return reel.frames;
    const payloadStoryboard = reel.payload?.storyboard;
    return Array.isArray(payloadStoryboard) ? payloadStoryboard : [];
  }

  function reelsFrameCount(reel = {}) {
    return normalizedReelsFrames(reel).length || Number(reel.frame_count || 0);
  }

  function reelsReadyCount(reel = {}) {
    const payloadReady = Number(reel.images_ready || 0);
    const derivedReady = normalizedReelsFrames(reel).filter((frame) => frame?.current_asset?.url).length;
    return Math.max(payloadReady, derivedReady);
  }

  function renderReelsFrameNarrative(frame = {}) {
    const sections = [
      { label: "Видеоряд", value: frame.scene || "" },
      { label: "Ракурс", value: frame.angle || "" },
      { label: "Таймкод", value: frame.timecode || "" },
    ].filter((item) => String(item.value || "").trim());

    if (!sections.length) return "";

    return `
      <div class="reels-frame-narrative">
        ${sections.map((item) => `
          <div class="reels-frame-section">
            <span class="reels-frame-section-label">${escapeHtml(item.label)}</span>
            <div class="reels-frame-section-value detail-markdown">${renderMarkdown(item.value)}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderReelsProductionOverview(reel = {}) {
    const shotList = Array.isArray(reel.shot_list) ? reel.shot_list : [];
    const productionNotes = reel.production_notes && typeof reel.production_notes === "object"
      ? reel.production_notes
      : { required: [], optional: [] };
    const requiredNotes = Array.isArray(productionNotes.required) ? productionNotes.required : [];
    const optionalNotes = Array.isArray(productionNotes.optional) ? productionNotes.optional : [];
    const readyFrames = reelsReadyCount(reel);
    const totalFrames = reelsFrameCount(reel);

    if (!shotList.length && !requiredNotes.length && !optionalNotes.length && !totalFrames) return "";

    return `
      <section class="section section-accent">
        <div class="section-heading">
          <h3>${uiIcon("slides")}План рилса</h3>
          <p>${totalFrames ? `Готово ${readyFrames} из ${totalFrames} кадров. Карточка обновляется по мере генерации.` : "Собираем раскадровку и production notes."}</p>
        </div>
        ${shotList.length ? `
          <div class="reels-overview-grid">
            ${shotList.map((shot) => `
              <article class="reels-overview-card">
                <strong>${escapeHtml(shot.title || `Shot ${Number(shot.frame_index || 0) + 1}`)}</strong>
                <div class="draft-meta">
                  ${shot.timecode ? tagMarkup(shot.timecode, "status-neutral") : ""}
                  ${shot.asset_ready ? tagMarkup("кадр готов", "status-positive") : tagMarkup("в очереди", "progress")}
                </div>
                ${shot.action ? `<div class="detail-preview">${escapeHtml(shot.action)}</div>` : ""}
              </article>
            `).join("")}
          </div>
        ` : ""}
        ${requiredNotes.length || optionalNotes.length ? `
          <div class="reels-production-notes">
            ${requiredNotes.length ? `
              <div class="reels-production-column">
                <span class="reels-production-title">Обязательно</span>
                <ul>
                  ${requiredNotes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                </ul>
              </div>
            ` : ""}
            ${optionalNotes.length ? `
              <div class="reels-production-column">
                <span class="reels-production-title">Опционально</span>
                <ul>
                  ${optionalNotes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                </ul>
              </div>
            ` : ""}
          </div>
        ` : ""}
      </section>
    `;
  }

  async function saveReelsScenario(draftId, button) {
    const scenario = String(document.getElementById("reelsScenarioField")?.value || "").trim();
    const concept = String(document.getElementById("reelsConceptField")?.value || "").trim();
    await withButtonFeedback(button, "Сохраняю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/scenario`, {
        method: "POST",
        body: JSON.stringify({ scenario, concept }),
      });
      state.selectedReels = draft;
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Сохранено");
  }

  async function regenerateReelsStoryboard(draftId, button) {
    const confirmed = await confirmAction("Пересобрать раскадровку? Текущие кадры и промпты будут заменены.");
    if (!confirmed) return;
    await withButtonFeedback(button, "Запускаю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/storyboard/regenerate`, {
        method: "POST",
        body: "{}",
        timeout: 30000,
      });
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
      scheduleReelsRefresh(draft.draft_id);
    }, "Запущено");
  }

  async function regenerateAllReelsFrames(draftId, button) {
    try {
      await withButtonFeedback(button, "Запускаю...", async () => {
        const draft = await fetchJson(`/api/reels/${draftId}/frames/regenerate-all`, {
          method: "POST",
          body: "{}",
          timeout: 30000,
        });
        mergeReelsIntoState(draft);
        callbacks.renderReels?.();
        callbacks.renderReelsDetail?.(draft);
        scheduleReelsRefresh(draft.draft_id);
      }, "Запущено");
    } catch (error) {
      showRequestError("Не удалось запустить генерацию кадров", error);
    }
  }

  async function saveReelsFrameFields(draftId, frameIndex, button) {
    const scene = String(document.getElementById(`reelsFrameScene${frameIndex}`)?.value || "").trim();
    const angle = String(document.getElementById(`reelsFrameAngle${frameIndex}`)?.value || "").trim();
    const timecode = String(document.getElementById(`reelsFrameTimecode${frameIndex}`)?.value || "").trim();
    await withButtonFeedback(button, "Сохраняю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/fields`, {
        method: "POST",
        body: JSON.stringify({ scene, angle, timecode }),
      });
      state.selectedReels = draft;
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Сохранено");
  }

  async function saveReelsFramePrompt(draftId, frameIndex, button) {
    const prompt = String(document.getElementById(`reelsFramePrompt${frameIndex}`)?.value || "").trim();
    await withButtonFeedback(button, "Сохраняю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/prompt`, {
        method: "POST",
        body: JSON.stringify({ prompt }),
      });
      const key = frameDraftKey(draftId, frameIndex);
      state.pendingReelsPrompts[key] = prompt;
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Сохранено");
  }

  async function persistReelsFramePrompt(draftId, frameIndex, prompt) {
    const key = frameDraftKey(draftId, frameIndex);
    state.pendingReelsPrompts[key] = String(prompt || "");
    const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/prompt`, {
      method: "POST",
      body: JSON.stringify({ prompt: String(prompt || "") }),
    });
    mergeReelsIntoState(draft);
    state.pendingReelsPrompts[key] = String(prompt || "");
    return draft;
  }

  function handleReelsFramePromptInput(draftId, frameIndex, value) {
    const key = frameDraftKey(draftId, frameIndex);
    state.pendingReelsPrompts[key] = String(value || "");
    window.clearTimeout(reelsPromptSaveTimers[key]);
    reelsPromptSaveTimers[key] = window.setTimeout(() => {
      const prompt = String(state.pendingReelsPrompts[key] || "").trim();
      if (!prompt) return;
      void persistReelsFramePrompt(draftId, frameIndex, prompt).catch(() => {});
    }, 600);
  }

  async function saveReelsFrameNote(draftId, frameIndex, button) {
    const note = String(document.getElementById(`reelsFrameNote${frameIndex}`)?.value || "").trim();
    await withButtonFeedback(button, "Сохраняю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/note`, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
      const key = frameDraftKey(draftId, frameIndex);
      state.pendingReelsNotes[key] = note;
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Сохранено");
  }

  async function persistReelsFrameNote(draftId, frameIndex, note) {
    const key = frameDraftKey(draftId, frameIndex);
    state.pendingReelsNotes[key] = String(note || "");
    const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/note`, {
      method: "POST",
      body: JSON.stringify({ note: String(note || "") }),
    });
    mergeReelsIntoState(draft);
    state.pendingReelsNotes[key] = String(note || "");
    return draft;
  }

  function handleReelsFrameNoteInput(draftId, frameIndex, value) {
    const key = frameDraftKey(draftId, frameIndex);
    state.pendingReelsNotes[key] = String(value || "");
    window.clearTimeout(reelsNoteSaveTimers[key]);
    reelsNoteSaveTimers[key] = window.setTimeout(() => {
      void persistReelsFrameNote(draftId, frameIndex, state.pendingReelsNotes[key]).catch(() => {});
    }, 600);
  }

  async function regenerateReelsFrame(draftId, frameIndex, button) {
    await withButtonFeedback(button, "Запускаю...", async () => {
      const prompt = String(document.getElementById(`reelsFramePrompt${frameIndex}`)?.value || bufferedReelsPrompt(draftId, frameIndex, "")).trim();
      const note = String(document.getElementById(`reelsFrameNote${frameIndex}`)?.value || bufferedReelsNote(draftId, frameIndex, "")).trim();
      if (prompt) await persistReelsFramePrompt(draftId, frameIndex, prompt);
      if (note) await persistReelsFrameNote(draftId, frameIndex, note);
      const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/regenerate`, {
        method: "POST",
        body: "{}",
      });
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
      scheduleReelsRefresh(draft.draft_id);
    }, "Запущено");
  }

  function renderReelsFrames(draftId, frames = []) {
    const frameItems = Array.isArray(frames) ? frames : [];
    if (!frameItems.length) return "";
    const readyCount = frameItems.filter((frame) => frame?.current_asset?.url).length;
    const header = readyCount > 0
      ? `Кадры и промпты <span class="meta">${readyCount} / ${frameItems.length} готовы</span>`
      : "Кадры и промпты";
    return `
      <section class="section">
        <h3>${sectionHeadingIcon("Кадры и промпты")}${header}</h3>
        <div class="storyboard">
          ${frameItems.map((frame, index) => {
            const prompt = bufferedReelsPrompt(draftId, index, frame.gemini_prompt || "");
            const note = bufferedReelsNote(draftId, index, frame.review_note || "");
            const assetUrl = frame.current_asset?.url || "";
            return `
              <article class="storyboard-frame">
                <strong>Кадр ${index + 1}${frame.timecode ? ` • ${escapeHtml(frame.timecode)}` : ""}</strong>
                ${reelsFrameStatusMarkup(frame)}
                ${renderReelsFrameNarrative(frame)}
                ${assetUrl
                  ? `<img class="frame-image" src="${escapeHtml(assetUrl)}" alt="Кадр ${index + 1}" />`
                  : `<div class="frame-loading">Картинка ещё не готова. Карточка обновится автоматически, как только кадр будет сгенерирован.</div>`}
                <div class="prompt-disclosure${!assetUrl ? " is-open" : ""}" data-prompt-key="${escapeHtml(`reels:${draftId}:${index}`)}">
                  <button class="secondary-button prompt-toggle" type="button" aria-expanded="${!assetUrl ? "true" : "false"}" data-default-open="${!assetUrl ? "true" : "false"}" data-open-label="${escapeHtml(prompt ? "Открыть редактирование кадра" : "Открыть описание кадра")}" data-close-label="Скрыть редактирование кадра" onclick='togglePromptDisclosure(${JSON.stringify(`reels:${draftId}:${index}`)}, this)'>${actionLabel("eye", !assetUrl ? "Скрыть редактирование кадра" : (prompt ? "Открыть редактирование кадра" : "Открыть описание кадра"))}</button>
                  <div class="prompt-card"${!assetUrl ? "" : " hidden"}>
                    <div class="reels-frame-edit-grid">
                      <label class="prompt-note-field">
                        <span>Текст / действие кадра</span>
                        <textarea id="reelsFrameScene${index}" placeholder="Что происходит в кадре">${escapeHtml(frame.scene || "")}</textarea>
                      </label>
                      <label class="prompt-note-field">
                        <span>Ракурс</span>
                        <input id="reelsFrameAngle${index}" type="text" placeholder="Например: макро, фронтальный, средний план" value="${escapeHtml(frame.angle || "")}" />
                      </label>
                      <label class="prompt-note-field">
                        <span>Таймкод</span>
                        <input id="reelsFrameTimecode${index}" type="text" placeholder="Например: 0-3 сек" value="${escapeHtml(frame.timecode || "")}" />
                      </label>
                    </div>
                    ${prompt ? `
                      <label class="prompt-note-field">
                        <span>Промпт кадра</span>
                        <textarea id="reelsFramePrompt${index}" placeholder="Какой кадр нужно сгенерировать и в каком настроении" oninput="handleReelsFramePromptInput('${draftId}', ${index}, this.value)">${escapeHtml(prompt)}</textarea>
                      </label>
                      <label class="prompt-note-field">
                        <span>Замечание к кадру</span>
                        <textarea id="reelsFrameNote${index}" placeholder="Например: теплее, меньше деталей, крупнее объект" oninput="handleReelsFrameNoteInput('${draftId}', ${index}, this.value)">${escapeHtml(note)}</textarea>
                      </label>
                      <div class="actions-row prompt-actions">
                        <button class="secondary-button" type="button" onclick="saveReelsFrameFields('${draftId}', ${index}, this)">${actionLabel("text", "Сохранить описание кадра")}</button>
                        <button class="secondary-button" type="button" onclick="saveReelsFramePrompt('${draftId}', ${index}, this)">${actionLabel("prompt", "Сохранить промпт кадра")}</button>
                        <button class="secondary-button" type="button" onclick="saveReelsFrameNote('${draftId}', ${index}, this)">${actionLabel("note", "Сохранить замечание")}</button>
                        <button class="secondary-button" type="button" onclick="regenerateReelsFrame('${draftId}', ${index}, this)">${actionLabel("regenerate", "Обновить кадр")}</button>
                        <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(String(prompt))})'>${actionLabel("prompt", "Скопировать промпт кадра")}</button>
                      </div>
                    ` : `
                      <div class="actions-row prompt-actions">
                        <button class="secondary-button" type="button" onclick="saveReelsFrameFields('${draftId}', ${index}, this)">${actionLabel("text", "Сохранить описание кадра")}</button>
                      </div>
                    `}
                  </div>
                </div>
              </article>
            `;
          }).join("")}
        </div>
      </section>
    `;
  }

  function renderReelsDetail(r) {
    const frames = normalizedReelsFrames(r);
    const hasFrames = frames.length > 0;
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("reel")}<span>Рилсы • ${escapeHtml(sourceLabel(r.source || "/miniapp"))}</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status || "draft"), statusTone(r.status || "draft"))}
            ${r.generation_pending ? tagMarkup(draftGenerationLabel({ ...r, kind: "reels" }), "pending") : ""}
            ${tagMarkup(`${reelsReadyCount(r)}/${reelsFrameCount(r)} кадров`, "progress")}
            ${tagMarkup(sourceLabel(r.source || "/miniapp"), sourceTone(r.source || "/miniapp"))}
          </div>
          <div class="actions-row">
            <button class="primary-button" type="button" onclick="saveReelsScenario('${r.draft_id}', this)">${actionLabel("text", "Сохранить концепцию и сценарий")}</button>
            <button class="secondary-button" type="button" onclick="regenerateReelsStoryboard('${r.draft_id}', this)">${actionLabel("regenerate", "Пересобрать раскадровку")}</button>
            <button class="secondary-button" type="button" onclick="regenerateAllReelsFrames('${r.draft_id}', this)">${actionLabel("reel", "Обновить все кадры")}</button>
            <button class="secondary-button" type="button" onclick="updateDraft('status', {status:'rejected'}, this)">${actionLabel("reject", "Вернуть на доработку")}</button>
            <button class="secondary-button" type="button" onclick="sendDraftToChat('${r.draft_id}', this)">${actionLabel("chat", "Отправить в чат")}</button>
            <button class="danger-button" type="button" onclick="deleteDraft('${r.draft_id}', 'reels', this)">${actionLabel("trash", "Удалить рилс")}</button>
          </div>
        </div>
        <section class="section">
          <h3>${sectionHeadingIcon("Сценарий")}Концепция и сценарий</h3>
          <label class="prompt-note-field">
            <span>Концепция</span>
            <textarea id="reelsConceptField" placeholder="Коротко: идея, настроение, обещание результата">${escapeHtml(r.payload?.concept || "")}</textarea>
          </label>
          <label class="prompt-note-field">
            <span>Сценарий</span>
            <textarea id="reelsScenarioField" placeholder="Соберите полный сценарий с переходами между кадрами">${escapeHtml(r.payload?.scenario || "")}</textarea>
          </label>
        </section>
        ${renderReelsProductionOverview(r)}
        ${generationStateMarkup(r, "reels")}
        ${hasFrames ? renderReelsFrames(r.draft_id, frames) : `
          <section class="section section-accent">
            <div class="section-heading">
              <h3>${uiIcon("slides")}Кадры и промпты</h3>
              <p>${escapeHtml(r.generation_message || "Подготавливаю раскадровку и кадры для рилса.")}</p>
            </div>
            ${renderDetailLoader("Собираю раскадровку", r.generation_message || "Подождите ещё немного, и здесь появятся кадры.", "detail-loader-card-compact")}
          </section>
        `}
      </div>
    `;
  }

  return {
    renderReelsDetail,
    saveReelsScenario,
    regenerateReelsStoryboard,
    regenerateAllReelsFrames,
    saveReelsFrameFields,
    saveReelsFramePrompt,
    saveReelsFrameNote,
    regenerateReelsFrame,
    handleReelsFramePromptInput,
    handleReelsFrameNoteInput,
  };
}
