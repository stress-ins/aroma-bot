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
    showUiNotice,
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
      void persistReelsFramePrompt(draftId, frameIndex, prompt).then(() => {
        if (showUiNotice) showUiNotice("Промпт сохранён", "success");
      }).catch(() => {});
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
      void persistReelsFrameNote(draftId, frameIndex, state.pendingReelsNotes[key]).then(() => {
        if (showUiNotice) showUiNotice("Заметка сохранена", "success");
      }).catch(() => {});
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
        if (showUiNotice) showUiNotice("Сохранено", "success");
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

  async function upgradeToFull(draftId, btn) {
    await withButtonFeedback(btn, "Запускаю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/upgrade-to-full`, {
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

  async function recoverFrameImage(draftId, frameId, btn) {
    await withButtonFeedback(btn, "Восстанавливаю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameId}/recover`, {
        method: "POST",
        timeout: 30000,
      });
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Восстановлено");
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
            <span class="brand-loader-letter">А</span>
          </div>
          <span style="font-size:12px;color:var(--hint);margin-top:8px">Генерирую...</span>
        </div>
      `;
    } else if (imageStatus === "ready" && imageUrl) {
      imageAreaHtml = `<img src="${escapeHtml(imageUrl)}" style="width:100%;height:100%;object-fit:cover;cursor:pointer" alt="Кадр ${n}" data-overlay="${escapeHtml(frame.overlay_text || '')}" data-frame-id="${escapeHtml(frameId)}" data-draft-id="${escapeHtml(draftId)}" data-action="openReelsPreview" data-args='${JSON.stringify([imageUrl, frame.overlay_text || "", frameId, draftId])}' />`;
    } else if (imageStatus === "error") {
      const errorReason = frame.error_message || frame.error || "";
      const hasKieTask = !!frame.kie_task_id;
      imageAreaHtml = `
        <div class="reels-frame-v2-image-generating">
          <span style="color:var(--danger);font-size:13px">Ошибка генерации</span>
          ${errorReason ? `<span style="color:var(--hint);font-size:11px;margin-top:4px;text-align:center">${escapeHtml(errorReason)}</span>` : ""}
          <div style="display:flex;gap:6px;margin-top:8px">
            ${hasKieTask ? `<button class="secondary-button compact" data-action="recoverFrameImage" data-args='${JSON.stringify([draftId, frameId])}'>Восстановить</button>` : ""}
            <button class="secondary-button compact" data-action="regenFrameImage" data-args='${JSON.stringify([draftId, frameId, null])}'>↺ Повторить</button>
          </div>
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
          <button class="secondary-button compact" data-action="regenFrameImage" data-args='${JSON.stringify([draftId, frameId, null])}'>↺ Ещё версия</button>
        </div>
        <div class="reels-frame-v2-field">
          <label>
            <span>Надпись на экране</span>
            <textarea class="reels-frame-overlay-text" data-frame-id="${escapeHtml(frameId)}"
              data-on-input="_overlayTextareaInput" data-draft-id="${escapeHtml(draftId)}"
              placeholder="Текст который будет показан зрителю">${escapeHtml(frame.overlay_text || "")}</textarea>
          </label>
        </div>
        <div class="reels-frame-v2-field">
          <label>
            <span>Промпт для изображения</span>
            <textarea class="reels-frame-image-prompt" data-frame-id="${escapeHtml(frameId)}"
              data-on-input="autoResize">${escapeHtml(frame.image_prompt || "")}</textarea>
          </label>
          <button class="secondary-button compact" style="margin-top:6px" data-action="regenFrameImageWithPrompt" data-args='${JSON.stringify([draftId, frameId, null])}'>↺ Перегенерировать с этим промптом</button>
        </div>
      </div>
    `;
  }

  // ── V2 stepper ───────────────────────────────────────────────────────

  function reelsStepperMarkup(status, generationPending) {
    const steps = [
      { key: "generating", label: "Генерация" },
      { key: "draft", label: "Черновик" },
      { key: "approved", label: "Съёмка" },
      { key: "video_uploaded", label: "Видео" },
      { key: "published", label: "Публикация" },
    ];
    let activeIdx = 0;
    if (generationPending) {
      activeIdx = 0;
    } else if (status === "draft") {
      activeIdx = 1;
    } else if (status === "approved") {
      activeIdx = 2;
    } else if (status === "video_uploaded" || status === "checking" || status === "passed") {
      activeIdx = 3;
    } else if (status === "publishing" || status === "published") {
      activeIdx = 4;
    }
    return `<div class="reels-stepper">${steps.map((s, i) => {
      const cls = i < activeIdx ? "done" : i === activeIdx ? "active" : "";
      return `<div class="reels-step ${cls}"><span class="reels-step-dot"></span><span class="reels-step-label">${s.label}</span></div>`;
    }).join("")}</div>`;
  }

  // ── V2 screen renderers ────────────────────────────────────────────────

  function renderScreen2Generating(r) {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, true)}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС · Генерируется</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup("Генерируется", "progress")}
          </div>
        </div>
        <div class="detail-loader-card detail-loader-card-compact">
          <div class="brand-loader">
            <span class="brand-loader-ring"></span>
            <span class="brand-loader-letter">А</span>
          </div>
          <div class="detail-loader-copy">
            <strong>${escapeHtml(r.generation_message || "Генерирую концепцию и сценарий")}</strong>
            <span>Изображения догенерируются в фоне — можно закрыть приложение</span>
          </div>
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
        <div class="actions-row" style="justify-content:center;padding:12px 0">
          <button class="secondary-button compact" type="button"
            data-action="forceEditReels" data-args='${JSON.stringify([r.draft_id, null])}'>
            Перейти к редактированию
          </button>
        </div>
      </div>
    `;
  }

  function renderScreen3Edit(r) {
    const isLightweight = r.lightweight || r.payload?.lightweight;
    const frames = Array.isArray(r.frames) ? r.frames : [];
    const allFramesReady = !isLightweight && frames.length > 0 && frames.every((f) => f?.image_status === "ready");
    const concept = r.concept || r.payload?.concept || "";
    const scenario = r.scenario || r.payload?.scenario || "";
    const caption = r.caption || r.payload?.caption || "";

    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, false)}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС${isLightweight ? " · Быстрое планирование" : ""}</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          ${concept ? `<p class="detail-summary">${escapeHtml(concept.slice(0, 120))}${concept.length > 120 ? "…" : ""}</p>` : ""}
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status || "draft"), statusTone(r.status || "draft"))}
            ${isLightweight ? tagMarkup("Лёгкий режим", "status-neutral") : tagMarkup(`${frames.filter((f) => f?.image_status === "ready").length}/${frames.length} кадров`, "progress")}
            ${tagMarkup(sourceLabel(r.source || "/miniapp"), sourceTone(r.source || "/miniapp"))}
          </div>
        </div>

        <div class="actions-row">
          ${isLightweight ? `
            <button class="primary-button" type="button"
              data-action="upgradeToFull" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("slides", "Перейти к полной раскадровке")}
            </button>
          ` : `
            <button class="primary-button${allFramesReady ? "" : " is-disabled"}" type="button"
              ${allFramesReady ? "" : "disabled"}
              data-action="approveReels" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("approve", "Согласовать")}
            </button>
            ${!allFramesReady ? `<span class="field-help" style="margin:0">Сгенерируйте и проверьте все кадры</span>` : ""}
          `}
          <button class="danger-button" type="button" data-action="deleteDraft" data-args='${JSON.stringify([r.draft_id, "reels", null])}'>
            ${actionLabel("trash", "Удалить")}
          </button>
          <button class="secondary-button" type="button" data-action="sendDraftToChat" data-args='${JSON.stringify([r.draft_id, null])}'>
            ${actionLabel("chat", "В чат")}
          </button>
        </div>

        <section class="section">
          <h3>${sectionHeadingIcon("Концепция")}Концепция</h3>
          ${concept ? `<div class="detail-markdown">${renderMarkdown(concept)}</div>` : `<p class="detail-empty">Концепция не задана</p>`}
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button compact" type="button" data-action="regenConcept" data-args='${JSON.stringify([r.draft_id, null])}'>↺ Перегенерировать концепцию</button>
          </div>
        </section>

        <section class="section">
          <h3>${sectionHeadingIcon("Сценарий")}Сценарий</h3>
          ${scenario ? `<div class="detail-markdown">${renderMarkdown(scenario)}</div>` : `<p class="detail-empty">Сценарий не задан</p>`}
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button compact" type="button" data-action="regenScenario" data-args='${JSON.stringify([r.draft_id, null])}'>↺ Перегенерировать сценарий</button>
          </div>
        </section>

        <section class="section">
          <h3>${sectionHeadingIcon("Замечания")}Замечания для переработки</h3>
          <label class="prompt-note-field">
            <textarea id="reelsRevisionNoteField" placeholder="Опишите что изменить: тон, акценты, структуру…">${escapeHtml(r.payload?.revision_note || "")}</textarea>
          </label>
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button compact" type="button" data-action="saveReelsScenario" data-args='${JSON.stringify([r.draft_id, null])}'>Сохранить замечания</button>
            <button class="secondary-button compact" type="button" data-action="regenerateReelsStoryboard" data-args='${JSON.stringify([r.draft_id, null])}'>↺ Перегенерировать с учётом замечаний</button>
          </div>
        </section>

        ${!isLightweight && !frames.length && (concept || scenario) ? `
          <div class="actions-row" style="justify-content:center;padding:12px 0">
            <button class="primary-button" type="button"
              data-action="regenScenario" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("slides", "Сгенерировать раскадровку")}
            </button>
          </div>
        ` : ""}

        ${!isLightweight && frames.length ? `
          <section class="section">
            <h3>${sectionHeadingIcon("Кадры")}Кадры</h3>
            <div class="actions-row" style="margin-bottom:12px">
              ${frames.some((f) => !f?.image_url && f?.image_status !== "ready") ? `
                <button class="primary-button" type="button" data-action="generateReelsImages" data-args='${JSON.stringify([r.draft_id, null])}'>
                  ${actionLabel("reel", "Сгенерировать все картинки")}
                </button>
              ` : ""}
              <button class="secondary-button compact" type="button" data-action="regenerateReelsStoryboard" data-args='${JSON.stringify([r.draft_id, null])}'>↺ Перегенерировать раскадровку</button>
            </div>
            ${frames.map((frame, i) => renderFrameV2(frame, r.draft_id, i + 1)).join("")}
          </section>
        ` : ""}

        <section class="section">
          <h3 style="display:flex;align-items:center">
            ${sectionHeadingIcon("Описание")}Описание рилса
            ${caption ? `<button class="icon-btn" style="margin-left:auto" data-action="copyReelsCaption" data-args='${JSON.stringify([r.draft_id, null])}' title="Скопировать">${uiIcon("copy")}</button>` : ""}
          </h3>
          ${caption ? `<div class="detail-markdown">${renderMarkdown(caption)}</div>` : `<p class="detail-empty">Описание не задано</p>`}
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button compact" type="button" data-action="regenCaption" data-args='${JSON.stringify([r.draft_id, null])}'>↺ Перегенерировать описание</button>
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
    const frames = Array.isArray(r.frames) ? r.frames : [];

    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, false)}
        <div class="detail-top">
          <p class="eyebrow">🎬 <span>РИЛС · Съёмка</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status || "approved"), statusTone(r.status || "approved"))}
          </div>
        </div>

        ${scenario ? `
          <section class="section">
            <h3>${sectionHeadingIcon("Сценарий")}Сценарий</h3>
            <div class="detail-markdown">${renderMarkdown(scenario)}</div>
          </section>
        ` : ""}

        ${concept ? `
          <section class="section">
            <h3>${sectionHeadingIcon("Концепция")}Концепция</h3>
            <div class="detail-markdown">${renderMarkdown(concept)}</div>
          </section>
        ` : ""}

        ${frames.length ? `
          <section class="section">
            <h3>${sectionHeadingIcon("Кадры")}Кадры</h3>
            <ol class="reels-frames-list">
              ${frames.map((f, i) => `<li>${escapeHtml(f.overlay_text || f.description || f.scene || "Кадр " + (i + 1))}</li>`).join("")}
            </ol>
          </section>
        ` : ""}

        <div class="actions-row" style="margin-top:8px;gap:8px;flex-wrap:wrap">
          <button class="secondary-button compact" type="button" data-action="updateDraft" data-args='${JSON.stringify(["status", { status: "draft" }, null])}'>
            ${actionLabel("undo", "На доработку")}
          </button>
          <button class="secondary-button compact danger" type="button" data-action="deleteDraft" data-args='${JSON.stringify([r.draft_id, "reels", null])}'>
            ${actionLabel("delete", "Удалить")}
          </button>
          <button class="secondary-button compact" type="button" data-action="sendDraftToChat" data-args='${JSON.stringify([r.draft_id, null])}'>
            ${actionLabel("chat", "В чат")}
          </button>
        </div>

        <div class="reels-upload-zone">
          <div class="reels-upload-title">Загрузить видео</div>
          <div class="reels-upload-hint">Запишите рилс по сценарию и загрузите через Telegram-бот командой /upload</div>
          <button class="secondary-button" type="button" data-action="sendDraftToChat" data-args='${JSON.stringify([r.draft_id, null])}'>
            ${actionLabel("chat", "Открыть в боте")}
          </button>
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
              <span class="reels-deadline-n">${frames.length}</span>
              <span class="reels-deadline-l">кадров в сценарии</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderScreen5VideoCheck(r) {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, false)}
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
          <button class="secondary-button" type="button" data-action="sendDraftToChat" data-args='${JSON.stringify([r.draft_id, null])}'>
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
                <button class="secondary-button compact" data-action="retryPlatform" data-args='${JSON.stringify([r.draft_id, entry.platform, null])}'>Повторить</button>
              ` : ""}
            </div>
          `;
        }).join("")}
      </section>
    ` : "";

    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, false)}
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
          <button class="primary-button" type="button" data-action="publishReels" data-args='${JSON.stringify([r.draft_id, null])}'>
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
        ${reelsStepperMarkup(r.status, false)}
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

  async function forceEditReels(draftId, btn) {
    await withButtonFeedback(btn, "Переключаю...", async () => {
      const draft = await fetchJson(`/api/reels/${draftId}/force-edit`, {
        method: "PATCH",
        body: "{}",
      });
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Готово");
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
    upgradeToFull,
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
    forceEditReels,
    // Feature: copy caption + fullscreen image
    copyReelsCaption,
    openReelsImageFullscreen,
    openReelsPreview,
  };
}
