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
    isPromptDisclosureOpen,
    fetchJson,
    withButtonFeedback,
    showRequestError,
    confirmAction,
    mergeReelsIntoState,
    scheduleReelsRefresh,
    callbacks,
  } = deps;

  const regenInProgressKeys = new Set();
  const frameOverlaySaveTimers = {};

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

  function reelsFrameStatusMarkup(frame = {}, isRegenerating = false) {
    if (isRegenerating) {
      return `<div class="slide-status is-pending">${uiIcon("sparkle")}<span>Обновляю кадр…</span></div>`;
    }
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

    const payloadStoryboard = Array.isArray(reel.payload?.storyboard) ? reel.payload.storyboard : [];
    if (!shotList.length && !requiredNotes.length && !optionalNotes.length && !totalFrames && !payloadStoryboard.length) return "";

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
        ${!shotList.length && payloadStoryboard.length ? `
          <div class="reels-storyboard-list">
            ${payloadStoryboard.map((frame, i) => `
              <div class="reels-storyboard-item">
                <strong>Кадр ${i + 1}${frame.timecode ? " · " + escapeHtml(frame.timecode) : ""}</strong>
                ${frame.scene ? `<div class="detail-preview">${escapeHtml(frame.scene)}</div>` : ""}
                ${frame.angle ? `<div class="reels-storyboard-meta">${escapeHtml(frame.angle)}</div>` : ""}
              </div>
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
    const revisionNote = String(document.getElementById("reelsRevisionNoteField")?.value || "").trim();
    await withButtonFeedback(button, "Сохраняю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/scenario`, {
        method: "POST",
        body: JSON.stringify({ scenario, concept, revision_note: revisionNote }),
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
    const key = frameDraftKey(draftId, frameIndex);
    regenInProgressKeys.add(key);
    if (state.selectedReels?.draft_id === draftId) callbacks.renderReelsDetail?.(state.selectedReels);
    try {
      await withButtonFeedback(button, "Запускаю...", async () => {
        const prompt = String(document.getElementById(`reelsFramePrompt${frameIndex}`)?.value || bufferedReelsPrompt(draftId, frameIndex, "")).trim();
        const note = String(document.getElementById(`reelsFrameNote${frameIndex}`)?.value || bufferedReelsNote(draftId, frameIndex, "")).trim();
        if (prompt) await persistReelsFramePrompt(draftId, frameIndex, prompt);
        if (note) await persistReelsFrameNote(draftId, frameIndex, note);
        const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/regenerate`, {
          method: "POST",
          body: "{}",
          timeout: 90000,
        });
        mergeReelsIntoState(draft);
        callbacks.renderReels?.();
        callbacks.renderReelsDetail?.(draft);
        scheduleReelsRefresh(draft.draft_id);
      }, "Запущено");
    } catch (error) {
      showRequestError("Не удалось обновить кадр", error);
    } finally {
      regenInProgressKeys.delete(key);
      if (state.selectedReels?.draft_id === draftId) callbacks.renderReelsDetail?.(state.selectedReels);
    }
  }

  function renderReelsFrames(draftId, frames = []) {
    const frameItems = Array.isArray(frames) ? frames : [];
    if (!frameItems.length) return "";
    const readyCount = frameItems.filter((frame) => frame?.current_asset?.url).length;
    const header = readyCount > 0
      ? `Кадры и промпты <span class="meta">${readyCount} / ${frameItems.length} готовы</span>`
      : "Кадры и промпты";
    const swipeHint = frameItems.length > 1 ? `<span class="storyboard-swipe-hint"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>свайп<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg></span>` : "";
    return `
      <section class="section">
        <h3>${sectionHeadingIcon("Кадры и промпты")}${header}${swipeHint}</h3>
        <div class="storyboard">
          ${frameItems.map((frame, index) => {
            const prompt = bufferedReelsPrompt(draftId, index, frame.gemini_prompt || "");
            const note = bufferedReelsNote(draftId, index, frame.review_note || "");
            const assetUrl = frame.current_asset?.url || "";
            const isRegenerating = regenInProgressKeys.has(frameDraftKey(draftId, index));
            return `
              <article class="storyboard-frame">
                <strong>Кадр ${index + 1}${frame.timecode ? ` • ${escapeHtml(frame.timecode)}` : ""}</strong>
                ${reelsFrameStatusMarkup(frame, isRegenerating)}
                ${renderReelsFrameNarrative(frame)}
                ${assetUrl
                  ? `<img class="frame-image" src="${escapeHtml(assetUrl)}" alt="Кадр ${index + 1}" />`
                  : `<div class="frame-loading">Картинка ещё не готова. Карточка обновится автоматически, как только кадр будет сгенерирован.</div>`}
                ${(() => {
                  const discOpen = isPromptDisclosureOpen(`reels:${draftId}:${index}`, !assetUrl);
                  const openLbl = prompt ? "Открыть редактирование кадра" : "Открыть описание кадра";
                  return `
                <div class="prompt-disclosure${discOpen ? " is-open" : ""}" data-prompt-key="${escapeHtml(`reels:${draftId}:${index}`)}">
                  <button class="secondary-button prompt-toggle" type="button" aria-expanded="${discOpen ? "true" : "false"}" data-default-open="${!assetUrl ? "true" : "false"}" data-open-label="${escapeHtml(openLbl)}" data-close-label="Скрыть редактирование кадра" onclick='togglePromptDisclosure(${JSON.stringify(`reels:${draftId}:${index}`)}, this)'>${actionLabel("eye", discOpen ? "Скрыть редактирование кадра" : openLbl)}</button>
                  <div class="prompt-card"${discOpen ? "" : " hidden"}>
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
                `;
                })()}
              </article>
            `;
          }).join("")}
        </div>
      </section>
    `;
  }

  // ── V2 utilities ────────────────────────────────────────────────────────

  function autoResize(el) {
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }

  function scheduleFrameOverlaySave(draftId, frameId, value) {
    const key = `${draftId}:${frameId}`;
    window.clearTimeout(frameOverlaySaveTimers[key]);
    frameOverlaySaveTimers[key] = window.setTimeout(async () => {
      try {
        await fetchJson(`/api/reels/${draftId}/frame`, {
          method: "PATCH",
          body: JSON.stringify({ frame_id: frameId, overlay_text: value }),
        });
      } catch (_e) {}
    }, 600);
  }

  async function saveFrameImagePrompt(draftId, frameId, btn) {
    const textarea = document.querySelector(`.reels-frame-image-prompt[data-frame-id="${frameId}"]`);
    const prompt = String(textarea?.value || "").trim();
    await withButtonFeedback(btn, "Сохраняю...", async () => {
      await fetchJson(`/api/reels/${draftId}/frame`, {
        method: "PATCH",
        body: JSON.stringify({ frame_id: frameId, image_prompt: prompt }),
      });
    }, "Сохранено");
  }

  async function regenConcept(draftId, btn) {
    await withButtonFeedback(btn, "Генерирую...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/regen-concept`, {
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

  async function regenScenario(draftId, btn) {
    await withButtonFeedback(btn, "Генерирую...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/regen-scenario`, {
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

  async function regenCaption(draftId, btn) {
    await withButtonFeedback(btn, "Генерирую...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/regen-caption`, {
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

  async function generateReelsImages(draftId, btn) {
    try {
      await withButtonFeedback(btn, "Запускаю...", async () => {
        const draft = await fetchJson(`/api/reels/${draftId}/generate-images`, {
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
      showRequestError("Не удалось запустить генерацию картинок", error);
    }
  }

  async function regenFrameImage(draftId, frameId, btn) {
    await withButtonFeedback(btn, "Генерирую...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/regen-frame-image`, {
        method: "POST",
        body: JSON.stringify({ frame_id: frameId }),
        timeout: 60000,
      });
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
      scheduleReelsRefresh(draft.draft_id);
    }, "Запущено");
  }

  async function regenFrameImageWithPrompt(draftId, frameId, btn) {
    const textarea = document.querySelector(`.reels-frame-image-prompt[data-frame-id="${frameId}"]`);
    const prompt = String(textarea?.value || "").trim();
    await withButtonFeedback(btn, "Генерирую...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/regen-frame-image`, {
        method: "POST",
        body: JSON.stringify({ frame_id: frameId, prompt }),
        timeout: 60000,
      });
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
      scheduleReelsRefresh(draft.draft_id);
    }, "Запущено");
  }

  async function approveReels(draftId, btn) {
    const frames = state.selectedReels?.frames || [];
    const allReady = frames.length > 0 && frames.every((f) => f.image_status === "ready");
    if (!allReady) {
      showRequestError("Согласование невозможно", { message: "Не все кадры готовы. Дождитесь завершения генерации изображений." });
      return;
    }
    await withButtonFeedback(btn, "Согласую...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/approve`, {
        method: "PATCH",
        body: JSON.stringify({ shooting_deadline_days: 3 }),
      });
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Согласовано");
  }

  // ── V2 frame card renderer ─────────────────────────────────────────────

  function renderFrameV2(frame, draftId, n) {
    const frameId = frame.id || frame.frame_id || String(n);
    const timecode = frame.timecode ? escapeHtml(frame.timecode) : `${(n - 1) * 3}–${n * 3} сек`;
    const imageStatus = frame.image_status || "pending";
    const imageUrl = frame.image_url || frame.current_asset?.url || "";
    const versions = Array.isArray(frame.image_versions) ? frame.image_versions : [];

    let imageAreaHtml = "";
    if (imageStatus === "generating") {
      imageAreaHtml = `
        <div class="reels-frame-v2-image-generating">
          <div class="brand-loader">
            <span class="brand-loader-ring"></span>
            <span class="brand-loader-letter">A</span>
          </div>
          <span style="font-size:12px;color:var(--hint);margin-top:8px">Генерирую...</span>
        </div>
      `;
    } else if (imageStatus === "ready" && imageUrl) {
      imageAreaHtml = `<img src="${escapeHtml(imageUrl)}" style="width:100%;height:100%;object-fit:cover;cursor:pointer" alt="Кадр ${n}" data-overlay="${escapeHtml(frame.overlay_text || '')}" data-frame-id="${escapeHtml(frameId)}" data-draft-id="${escapeHtml(draftId)}" onclick="openReelsPreview(this.src, this.dataset.overlay, this.dataset.frameId, this.dataset.draftId)" />`;
    } else if (imageStatus === "error") {
      imageAreaHtml = `
        <div class="reels-frame-v2-image-generating">
          <span style="color:var(--danger);font-size:13px">Ошибка генерации</span>
          <button class="secondary-button compact" style="margin-top:8px" onclick="regenFrameImage('${escapeHtml(draftId)}', '${escapeHtml(frameId)}', this)">↺ Повторить</button>
        </div>
      `;
    } else {
      imageAreaHtml = `
        <div class="reels-frame-v2-image-generating">
          <span style="font-size:12px;color:var(--hint)">Изображение ещё не готово</span>
        </div>
      `;
    }

    const versionsHtml = versions.length > 0 ? `
      <div class="reels-frame-versions">
        ${versions.map((v, vi) => `
          <div class="reels-frame-version-thumb${v.is_current ? " is-current" : ""}" title="Версия ${vi + 1}">
            ${v.url ? `<img src="${escapeHtml(v.url)}" style="width:100%;height:100%;object-fit:cover" />` : ""}
          </div>
        `).join("")}
      </div>
    ` : "";

    return `
      <div class="reels-frame-v2" data-frame-id="${escapeHtml(frameId)}">
        <div class="reels-frame-v2-header">
          <span class="reels-frame-v2-title">Кадр ${n}</span>
          <span class="reels-frame-v2-timecode">${timecode}</span>
        </div>
        <div class="reels-frame-v2-image-wrap">
          ${imageAreaHtml}
        </div>
        ${versionsHtml}
        <div style="padding:8px 12px;border-top:1px solid var(--border)">
          <button class="secondary-button compact" onclick="regenFrameImage('${escapeHtml(draftId)}', '${escapeHtml(frameId)}', this)">↺ Ещё версия</button>
        </div>
        <div class="reels-frame-v2-field">
          <label>
            <span>Надпись на экране</span>
            <textarea class="reels-frame-overlay-text" data-frame-id="${escapeHtml(frameId)}"
              oninput="autoResize(this); scheduleFrameOverlaySave('${escapeHtml(draftId)}', '${escapeHtml(frameId)}', this.value)"
              placeholder="Текст который будет показан зрителю">${escapeHtml(frame.overlay_text || "")}</textarea>
          </label>
        </div>
        <div class="reels-frame-v2-field">
          <label>
            <span>Промпт для изображения</span>
            <textarea class="reels-frame-image-prompt" data-frame-id="${escapeHtml(frameId)}"
              oninput="autoResize(this)">${escapeHtml(frame.image_prompt || "")}</textarea>
          </label>
          <button class="secondary-button compact" style="margin-top:6px" onclick="regenFrameImageWithPrompt('${escapeHtml(draftId)}', '${escapeHtml(frameId)}', this)">↺ Перегенерировать с этим промптом</button>
        </div>
      </div>
    `;
  }

  // ── V2 screen renderers ────────────────────────────────────────────────

  function renderScreen2Generating(r) {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС · Генерируется</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup("Генерируется", "progress")}
          </div>
        </div>
        <div class="brand-loader">
          <span class="brand-loader-ring"></span>
          <span class="brand-loader-letter">A</span>
        </div>
        <div class="detail-loader-copy">
          <strong>${escapeHtml(r.generation_message || "Генерирую концепцию и сценарий")}</strong>
          <span>Изображения догенерируются в фоне — можно закрыть приложение</span>
        </div>
        <div class="reels-skeleton-section">
          <div class="reels-skeleton-bar" style="width:60%"></div>
          <div class="reels-skeleton-bar" style="width:90%"></div>
          <div class="reels-skeleton-bar" style="width:75%"></div>
        </div>
        <div class="reels-skeleton-section">
          <div class="reels-skeleton-bar" style="width:80%"></div>
          <div class="reels-skeleton-bar" style="width:55%"></div>
        </div>
      </div>
    `;
  }

  function renderScreen3Edit(r) {
    const frames = Array.isArray(r.frames) ? r.frames : [];
    const allFramesReady = frames.length > 0 && frames.every((f) => f?.image_status === "ready");
    const concept = r.concept || r.payload?.concept || "";
    const scenario = r.scenario || r.payload?.scenario || "";
    const caption = r.caption || r.payload?.caption || "";

    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          ${concept ? `<p class="detail-summary">${escapeHtml(concept.slice(0, 120))}${concept.length > 120 ? "…" : ""}</p>` : ""}
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status || "draft"), statusTone(r.status || "draft"))}
            ${tagMarkup(`${frames.filter((f) => f?.image_status === "ready").length}/${frames.length} кадров`, "progress")}
            ${tagMarkup(sourceLabel(r.source || "/miniapp"), sourceTone(r.source || "/miniapp"))}
          </div>
        </div>

        <div class="actions-row">
          <button class="primary-button${allFramesReady ? "" : " is-disabled"}" type="button"
            ${allFramesReady ? "" : "disabled"}
            onclick="approveReels('${r.draft_id}', this)">
            ${actionLabel("approve", "Согласовать")}
          </button>
          <button class="danger-button" type="button" onclick="deleteDraft('${r.draft_id}', 'reels', this)">
            ${actionLabel("trash", "Удалить")}
          </button>
          <button class="secondary-button" type="button" onclick="sendDraftToChat('${r.draft_id}', this)">
            ${actionLabel("chat", "В чат")}
          </button>
        </div>

        <section class="section">
          <h3>${sectionHeadingIcon("Концепция")}Концепция</h3>
          ${concept ? `<div class="detail-markdown">${renderMarkdown(concept)}</div>` : `<p class="detail-empty">Концепция не задана</p>`}
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button compact" type="button" onclick="regenConcept('${r.draft_id}', this)">↺ Перегенерировать концепцию</button>
          </div>
        </section>

        <section class="section">
          <h3>${sectionHeadingIcon("Сценарий")}Сценарий</h3>
          ${scenario ? `<div class="detail-markdown">${renderMarkdown(scenario)}</div>` : `<p class="detail-empty">Сценарий не задан</p>`}
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button compact" type="button" onclick="regenScenario('${r.draft_id}', this)">↺ Перегенерировать сценарий</button>
          </div>
        </section>

        ${frames.length ? `
          <section class="section">
            <h3>${sectionHeadingIcon("Кадры")}Кадры</h3>
            ${frames.some((f) => !f?.image_url && f?.image_status !== "ready") ? `
              <div class="actions-row" style="margin-bottom:12px">
                <button class="primary-button" type="button" onclick="generateReelsImages('${r.draft_id}', this)">
                  ${actionLabel("reel", "Сгенерировать все картинки")}
                </button>
              </div>
            ` : ""}
            ${frames.map((frame, i) => renderFrameV2(frame, r.draft_id, i + 1)).join("")}
          </section>
        ` : ""}

        <section class="section">
          <h3 style="display:flex;align-items:center">
            ${sectionHeadingIcon("Описание")}Описание рилса
            ${caption ? `<button class="icon-btn" style="margin-left:auto" onclick="copyReelsCaption('${r.draft_id}', this)" title="Скопировать">${uiIcon("copy")}</button>` : ""}
          </h3>
          ${caption ? `<div class="detail-markdown">${renderMarkdown(caption)}</div>` : `<p class="detail-empty">Описание не задано</p>`}
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button compact" type="button" onclick="regenCaption('${r.draft_id}', this)">↺ Перегенерировать описание</button>
          </div>
        </section>
      </div>
    `;
  }

  function renderScreen4Shooting(r) {
    const deadlineDays = Number(r.shooting_deadline_days || 3);
    const deadlineDate = new Date();
    deadlineDate.setDate(deadlineDate.getDate() + deadlineDays);
    const dateStr = deadlineDate.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
    const concept = r.concept || r.payload?.concept || "";
    const scenario = r.scenario || r.payload?.scenario || "";

    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС · Согласован</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status || "approved"), statusTone(r.status || "approved"))}
          </div>
        </div>

        <div class="reels-shooting-deadline">
          <div class="reels-deadline-header">Дедлайн съёмки</div>
          <div class="reels-deadline-meta">Снять и загрузить видео до ${dateStr}</div>
          <div class="reels-deadline-grid">
            <div class="reels-deadline-stat">
              <span class="reels-deadline-n">${deadlineDays}</span>
              <span class="reels-deadline-l">дней осталось</span>
            </div>
            <div class="reels-deadline-stat">
              <span class="reels-deadline-n">${(Array.isArray(r.frames) ? r.frames.length : 0)}</span>
              <span class="reels-deadline-l">кадров в сценарии</span>
            </div>
          </div>
        </div>

        <div class="reels-upload-zone">
          <div class="reels-upload-title">Загрузить видео</div>
          <div class="reels-upload-hint">Запишите рилс по сценарию и загрузите через Telegram-бот командой /upload</div>
          <button class="secondary-button" type="button" onclick="sendDraftToChat('${r.draft_id}', this)">
            ${actionLabel("chat", "Открыть в боте")}
          </button>
        </div>

        ${concept ? `
          <section class="section">
            <h3>${sectionHeadingIcon("Концепция")}Концепция</h3>
            <div class="detail-markdown">${renderMarkdown(concept)}</div>
          </section>
        ` : ""}

        ${scenario ? `
          <section class="section">
            <h3>${sectionHeadingIcon("Сценарий")}Сценарий</h3>
            <div class="detail-markdown">${renderMarkdown(scenario)}</div>
          </section>
        ` : ""}
      </div>
    `;
  }

  function renderScreen5VideoCheck(r) {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС · Видео загружено</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status), statusTone(r.status))}
          </div>
        </div>
        <div class="reels-video-preview">
          <div class="reels-video-thumb">🎬</div>
          <div>
            <div style="font-weight:600;font-size:14px;margin-bottom:4px">Видео на проверке</div>
            <div style="font-size:12px;color:var(--hint)">Проверьте видео и опубликуйте его</div>
          </div>
        </div>
        <div class="actions-row">
          <button class="secondary-button" type="button" onclick="sendDraftToChat('${r.draft_id}', this)">
            ${actionLabel("chat", "Открыть в боте")}
          </button>
        </div>
      </div>
    `;
  }

  function renderScreen6Publish(r) {
    const caption = r.caption || r.payload?.caption || "";
    const captionLen = caption.length;
    const captionWarning = captionLen > 2200
      ? `<div style="color:var(--danger);font-size:12px;margin-top:4px">Описание слишком длинное (${captionLen} симв). Рекомендуем сократить до 2200 для Instagram.</div>`
      : "";

    const publishStatus = Array.isArray(r.publish_status) ? r.publish_status : [];
    const statusByPlatform = {};
    publishStatus.forEach((entry) => {
      if (entry?.platform) statusByPlatform[entry.platform] = entry.status || "";
    });

    const platforms = ["instagram", "threads"];
    const platformLabels = { instagram: "Instagram", threads: "Threads" };

    const publishStatusHtml = publishStatus.length ? `
      <section class="section">
        <h3>${sectionHeadingIcon("publish")}Статус публикации</h3>
        ${publishStatus.map((entry) => {
          if (!entry?.platform) return "";
          const isOk = entry.status === "success";
          const isFail = entry.status === "failed";
          return `
            <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span>${escapeHtml(platformLabels[entry.platform] || entry.platform)}</span>
              <span style="color:${isOk ? "var(--positive)" : isFail ? "var(--danger)" : "var(--hint)"};font-size:13px">
                ${isOk ? "✅ Опубликовано" : isFail ? "❌ Ошибка" : "⏳ В процессе"}
              </span>
              ${isFail ? `
                <button class="secondary-button compact" onclick="retryPlatform('${escapeHtml(r.draft_id)}', '${escapeHtml(entry.platform)}', this)">Повторить</button>
              ` : ""}
            </div>
          `;
        }).join("")}
      </section>
    ` : "";

    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС · Публикация</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status), statusTone(r.status))}
          </div>
        </div>

        ${publishStatusHtml}

        <section class="section">
          <h3>${sectionHeadingIcon("Описание")}Описание</h3>
          <div class="detail-markdown">${renderMarkdown(caption)}</div>
          ${captionWarning}
        </section>

        <section class="section">
          <h3>${sectionHeadingIcon("publish")}Опубликовать</h3>
          <div class="field-grid">
            ${platforms.map((p) => `
              <label class="platform-format-option">
                <input type="checkbox" name="publish_platform" value="${p}" ${statusByPlatform[p] === "success" ? "disabled checked" : ""}>
                <span>${platformLabels[p]}</span>
              </label>
            `).join("")}
          </div>
          <div class="field-grid" style="margin-top:12px">
            <label>Дата
              <input type="date" id="publishDate" style="width:100%" />
            </label>
            <label>Время
              <input type="time" id="publishTime" style="width:100%" />
            </label>
          </div>
          <p class="field-help">Оставьте дату пустой для немедленной публикации.</p>
          <button class="primary-button" type="button" onclick="publishReels('${escapeHtml(r.draft_id)}', this)">
            ${actionLabel("publish", "Опубликовать")}
          </button>
        </section>
      </div>
    `;
  }

  async function publishReels(draftId, btn) {
    const checkboxes = document.querySelectorAll("input[name='publish_platform']:checked");
    const platforms = Array.from(checkboxes).map((cb) => cb.value);
    if (!platforms.length) {
      showRequestError("Выберите платформу", { message: "Нужно выбрать хотя бы одну платформу для публикации." });
      return;
    }
    const date = String(document.getElementById("publishDate")?.value || "");
    const time = String(document.getElementById("publishTime")?.value || "");
    await withButtonFeedback(btn, "Публикую...", async () => {
      const result = await fetchJson(`/api/reels/${draftId}/publish`, {
        method: "POST",
        body: JSON.stringify({ platforms, date, time }),
        timeout: 60000,
      });
      const draft = await fetchJson(`/api/reels/${draftId}`);
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Опубликовано");
  }

  async function retryPlatform(draftId, platform, btn) {
    await withButtonFeedback(btn, "Повторяю...", async () => {
      const result = await fetchJson(`/api/reels/${draftId}/retry-platform`, {
        method: "POST",
        body: JSON.stringify({ platform }),
        timeout: 60000,
      });
      const draft = await fetchJson(`/api/reels/${draftId}`);
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Готово");
  }

  function renderScreen7Published(r) {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС · Опубликован</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status), statusTone(r.status))}
          </div>
        </div>
        <section class="section">
          <div class="detail-preview" style="text-align:center;padding:24px 0">
            <div style="font-size:32px;margin-bottom:8px">✅</div>
            <div style="font-weight:600;margin-bottom:4px">Рилс опубликован</div>
            <div style="font-size:12px;color:var(--hint)">Рилс успешно опубликован в Instagram</div>
          </div>
        </section>
      </div>
    `;
  }

  // ── Role gates (Phase 5) ─────────────────────────────────────────────

  function canEditReels() { return ["expert", "assistant"].includes(state.userRole || "assistant"); }
  function canApproveReels() { return (state.userRole || "assistant") === "expert"; }
  function canPublishReels() { return ["expert", "publisher"].includes(state.userRole || "assistant"); }

  // ── Main render dispatcher ─────────────────────────────────────────────

  function renderReelsDetail(r) {
    // Detect v2 reels by kind or v2-specific frame fields
    const isV2 = r.kind === "reels_v2" || (
      Array.isArray(r.frames) && r.frames.length > 0 && r.frames[0] &&
      ("image_status" in r.frames[0] || "overlay_text" in r.frames[0])
    );

    if (!isV2) {
      // V1 rendering path (original logic)
      const frames = normalizedReelsFrames(r);
      const hasFrames = frames.length > 0;
      return `
        <div class="detail-grid">
          ${renderBackButton()}
          <div class="detail-top">
            <p class="eyebrow">${uiIcon("reel")}<span>Рилсы${sourceLabel(r.source || "/miniapp") ? " • " + escapeHtml(sourceLabel(r.source || "/miniapp")) : ""}</span></p>
            <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
            <div class="draft-meta">
              ${tagMarkup(statusLabel(r.status || "draft"), statusTone(r.status || "draft"))}
              ${r.generation_pending && draftGenerationLabel({ ...r, kind: "reels" }) ? tagMarkup(draftGenerationLabel({ ...r, kind: "reels" }), "pending") : ""}
              ${tagMarkup(`${reelsReadyCount(r)}/${reelsFrameCount(r)} кадров`, "progress")}
              ${tagMarkup(sourceLabel(r.source || "/miniapp"), sourceTone(r.source || "/miniapp"))}
            </div>
            <div class="actions-row">
              <button class="primary-button" type="button" onclick="saveReelsScenario('${r.draft_id}', this)">${actionLabel("text", "Сохранить концепцию и сценарий")}</button>
              <div class="detail-icon-actions">
                <button class="secondary-button" title="Пересобрать раскадровку" type="button" onclick="regenerateReelsStoryboard('${r.draft_id}', this)">${uiIcon("regenerate")}</button>
                <button class="secondary-button" title="Обновить все кадры" type="button" onclick="regenerateAllReelsFrames('${r.draft_id}', this)">${uiIcon("reel")}</button>
                <button class="secondary-button" title="Вернуть на доработку" type="button" onclick="updateDraft('status', {status:'rejected'}, this)">${uiIcon("reject")}</button>
                <button class="secondary-button" title="Отправить в чат" type="button" onclick="sendDraftToChat('${r.draft_id}', this)">${uiIcon("chat")}</button>
              </div>
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
            <label class="prompt-note-field">
              <span>Замечания для переработки</span>
              <textarea id="reelsRevisionNoteField" placeholder="Опишите что изменить: тон, акценты, структуру…">${escapeHtml(r.payload?.revision_note || "")}</textarea>
            </label>
            <button class="secondary-button" type="button" onclick="regenerateReelsStoryboard('${r.draft_id}', this)">${actionLabel("regenerate", "Перегенерировать с учётом замечаний")}</button>
          </section>
          ${renderReelsProductionOverview(r)}
          ${generationStateMarkup(r, "reels")}
          ${r.generation_pending ? `<div class="actions-row" style="padding: 0 var(--space-4)"><button class="secondary-button compact" type="button" onclick="retryCurrentTab()">Обновить вручную</button></div>` : ""}
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

    // V2 routing by status and generation_pending
    if (r.generation_pending === true) {
      return renderScreen2Generating(r);
    }

    const status = r.status || "draft";

    if (status === "approved") {
      return renderScreen4Shooting(r);
    }

    if (status === "video_uploaded" || status === "checking") {
      return renderScreen5VideoCheck(r);
    }

    if (status === "passed") {
      return renderScreen6Publish(r);
    }

    if (status === "publishing" || status === "published") {
      const hasFailures = Array.isArray(r.publish_status) && r.publish_status.some((e) => e?.status === "failed");
      if (status === "publishing" || hasFailures) {
        return renderScreen6Publish(r);
      }
      return renderScreen7Published(r);
    }

    // Default: "draft" (Screen 3 — Edit)
    return renderScreen3Edit(r);
  }

  async function copyReelsCaption(draftId, btn) {
    const draft = state.selectedReels;
    const caption = draft?.caption || draft?.payload?.caption || "";
    if (!caption) return;
    try {
      await navigator.clipboard.writeText(caption);
      const icon = btn.querySelector("[data-lucide]");
      if (icon) {
        const orig = icon.getAttribute("data-lucide");
        icon.setAttribute("data-lucide", "check");
        if (window.lucide) lucide.createIcons();
        setTimeout(() => {
          icon.setAttribute("data-lucide", orig);
          if (window.lucide) lucide.createIcons();
        }, 1500);
      }
    } catch (_e) {}
  }

  function openReelsPreview(url, overlayText, frameId, draftId) {
    const existing = document.getElementById("reels-img-modal");
    if (existing) existing.remove();
    const hasOverlay = overlayText && overlayText.trim();
    const overlayHtml = hasOverlay
      ? `<div class="reels-overlay-text reels-overlay-loading" id="reels-overlay-text" style="top:8%;left:10%;max-width:80%">${escapeHtml(overlayText)}</div>`
      : "";
    const backdrop = document.createElement("div");
    backdrop.id = "reels-img-modal";
    backdrop.className = "preview-modal-backdrop";
    backdrop.innerHTML = `
      <div class="preview-modal" style="max-width:400px">
        <div class="preview-modal-header">
          <h3>Предпросмотр</h3>
          <button class="secondary-button compact preview-modal-close" id="reels-preview-close">✕</button>
        </div>
        <div class="preview-modal-body reels-preview-body">
          <img src="${escapeHtml(url)}" alt="Предпросмотр кадра" />
          ${overlayHtml}
        </div>
      </div>
    `;
    document.body.appendChild(backdrop);
    document.body.style.overflow = "hidden";
    function closeModal() {
      backdrop.remove();
      document.body.style.overflow = "";
    }
    backdrop.querySelector("#reels-preview-close").addEventListener("click", closeModal);
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeModal();
    });
    if (hasOverlay && draftId && frameId) {
      fetchJson(`/api/reels/${draftId}/frame/${frameId}/analyze-placement`, {
        method: "POST",
        timeout: 15000,
      }).then((data) => {
        const el = document.getElementById("reels-overlay-text");
        if (!el) return;
        const p = data.placement || {};
        const t = data.typography || {};
        if (p.y_percent !== undefined) el.style.top = p.y_percent + "%";
        if (p.x_percent !== undefined) el.style.left = p.x_percent + "%";
        if (p.max_width_percent) el.style.maxWidth = p.max_width_percent + "%";
        if (t.color_hex) el.style.color = t.color_hex;
        if (t.shadow_color) el.style.textShadow = `0 1px 4px ${t.shadow_color}, 0 0 12px ${t.shadow_color}`;
        if (t.font_size_px) el.style.fontSize = t.font_size_px + "px";
        if (t.font_weight) el.style.fontWeight = t.font_weight;
        el.classList.remove("reels-overlay-loading");
      }).catch(() => {
        const el = document.getElementById("reels-overlay-text");
        if (el) el.classList.remove("reels-overlay-loading");
      });
    }
  }

  function openReelsImageFullscreen(url, n) {
    openReelsPreview(url, "", "", "");
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
    // V2 new exports
    regenConcept,
    regenScenario,
    regenCaption,
    regenFrameImage,
    regenFrameImageWithPrompt,
    generateReelsImages,
    approveReels,
    scheduleFrameOverlaySave,
    saveFrameImagePrompt,
    autoResize,
    // Phase 4 exports
    publishReels,
    retryPlatform,
    // Phase 5 role gates
    canEditReels,
    canApproveReels,
    canPublishReels,
    // Feature: copy caption + fullscreen image
    copyReelsCaption,
    openReelsImageFullscreen,
    openReelsPreview,
  };
}
