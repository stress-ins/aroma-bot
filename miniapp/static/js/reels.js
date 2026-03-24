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
    getInitDataHeaders,
    callbacks,
  } = deps;

  const regenInProgressKeys = new Set();
  const frameOverlaySaveTimers = {};

  function _pluralize(n, one, few, many) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return `${n} ${one}`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${n} ${few}`;
    return `${n} ${many}`;
  }

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
    const r = state.selectedReels;
    const isLightweight = r?.lightweight || r?.payload?.lightweight;
    if (!isLightweight) {
      const frames = r?.frames || [];
      const allReady = frames.length > 0 && frames.every((f) => f.image_status === "ready");
      if (!allReady) {
        showRequestError("Согласование невозможно", { message: "Не все кадры готовы. Дождитесь завершения генерации изображений." });
        return;
      }
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

  function reelsStepperMarkup(status, generationPending, draftId) {
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
      const clickable = i <= activeIdx && draftId;
      const attrs = clickable
        ? `data-action="jumpToReelsStep" data-args='${JSON.stringify([draftId, s.key, null])}' class="reels-step ${cls} clickable" role="button" tabindex="0"`
        : `class="reels-step ${cls}"`;
      return `<div ${attrs}><span class="reels-step-dot"></span><span class="reels-step-label">${s.label}</span></div>`;
    }).join("")}</div>`;
  }

  // ── V2 screen renderers ────────────────────────────────────────────────

  function renderScreen2Generating(r) {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, true, r.draft_id)}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("reel")} <span>РИЛС · Генерируется</span></p>
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
        ${reelsStepperMarkup(r.status, false, r.draft_id)}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("reel")} <span>РИЛС${isLightweight ? " · Быстрое планирование" : ""}</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          ${concept ? `<p class="detail-summary">${escapeHtml(concept.slice(0, 120))}${concept.length > 120 ? "…" : ""}</p>` : ""}
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status || "draft"), statusTone(r.status || "draft"))}
            ${isLightweight ? tagMarkup("Лёгкий режим", "status-neutral") : tagMarkup(`${frames.filter((f) => f?.image_status === "ready").length}/${frames.length} кадров`, "progress")}
            ${tagMarkup(sourceLabel(r.source || "/miniapp"), sourceTone(r.source || "/miniapp"))}
          </div>
        </div>

        <div class="actions-row" style="flex-direction:column">
          ${isLightweight ? `
            <button class="primary-button" type="button"
              data-action="approveReels" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("approve", "Согласовать")}
            </button>
            <button class="secondary-button" type="button"
              data-action="upgradeToFull" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("slides", "Добавить раскадровку")}
            </button>
          ` : frames.length === 0 && (concept || scenario) ? `
            <button class="primary-button" type="button"
              data-action="regenerateReelsStoryboard" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("slides", "Сгенерировать раскадровку")}
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
        ${reelsStepperMarkup(r.status, false, r.draft_id)}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("reel")} <span>РИЛС · Съёмка</span></p>
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

        ${frames.length ? `
        <section class="section reels-compose-zone">
          <h3>${sectionHeadingIcon("Видео")}Собрать видео из кадров</h3>
          <div class="reels-compose-hint" style="font-size:13px;color:var(--muted);margin-bottom:12px">
            AI автоматически создаст видео из ваших кадров с Ken Burns анимацией, переходами и текстом
          </div>

          <div class="reels-compose-options" style="display:flex;flex-direction:column;gap:10px;margin-bottom:12px">
            <label style="font-size:13px;font-weight:500;color:var(--text)">
              Движок
              <select id="composeRenderer" class="compose-select" style="margin-left:8px">
                <option value="ffmpeg">Быстрая сборка</option>
                <option value="remotion">С анимацией</option>
              </select>
            </label>

            <div id="remotionOptions" style="display:none;flex-direction:column;gap:8px;padding-left:12px;border-left:2px solid var(--border)">
              <label style="font-size:13px;font-weight:500;color:var(--text)">
                Шаблон
                <select id="composeTemplate" class="compose-select" style="margin-left:8px">
                  <option value="aroma">Классический</option>
                  <option value="educational">Обучающий</option>
                  <option value="promo">Промо</option>
                </select>
              </label>
              <label style="font-size:13px;font-weight:500;color:var(--text)">
                Анимация текста
                <select id="composeAnimation" class="compose-select" style="margin-left:8px">
                  <option value="fade">Плавное появление</option>
                  <option value="slide-up">Выезд снизу</option>
                  <option value="typewriter">Печатная машинка</option>
                  <option value="scale-in">Масштабирование</option>
                </select>
              </label>
            </div>
          </div>

          <div style="display:flex;align-items:center;gap:12px">
            <button class="primary-button compact" type="button" data-action="composeReelVideo" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("video", "Собрать видео")}
            </button>
            <span id="composeStatusText" style="font-size:12px;color:var(--muted)"></span>
          </div>
        </section>
        ` : ""}

        <section class="section">
        <div class="reels-upload-zone">
          <div class="reels-upload-title">Загрузить своё видео</div>
          <div class="reels-upload-hint">Или запишите рилс по сценарию и загрузите файл</div>
          <input type="file" id="videoFileInput" accept="video/*" style="display:none">
          <label for="videoFileInput" class="secondary-button compact" style="cursor:pointer;text-align:center">
            ${actionLabel("file-video", "Выбрать видео")}
          </label>
          <button class="primary-button compact" type="button" data-action="uploadReelsVideo" data-args='${JSON.stringify([r.draft_id, null])}' style="display:none" id="reelsUploadBtn">
            ${actionLabel("upload", "Загрузить")}
          </button>
          <div id="reelsSelectedFileName" style="font-size:12px;color:var(--muted);margin-top:4px;display:none"></div>
          <div id="reelsUploadProgressZone" class="reels-upload-progress-zone" style="display:${state.videoUpload.active && state.videoUpload.draftId === r.draft_id ? "" : "none"}">
            <div class="reels-upload-progress-track">
              <div class="reels-upload-progress-fill" id="reelsUploadProgressBar" style="width:${state.videoUpload.active ? state.videoUpload.progress : 0}%"></div>
            </div>
            <div class="reels-upload-progress-text" id="reelsUploadProgressText">${state.videoUpload.active ? Math.round(state.videoUpload.progress) + "%" : ""}</div>
          </div>
          <div class="reels-upload-hint" style="margin-top:8px;font-size:12px;color:var(--muted)">или загрузите через бот (до 20 МБ)</div>
          <button class="secondary-button compact" type="button" data-action="openBotUploadLink" data-args='${JSON.stringify([r.draft_id])}'>
            ${actionLabel("bot", "Загрузить через бот")}
          </button>
        </div>
        </section>

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
    const p = r.payload || {};
    const videoFilename = p.video_filename || "";
    const videoUrl = videoFilename ? `/generated/reels_video/${r.draft_id}/${videoFilename}` : "";
    const techCheck = p.tech_check || null;
    const cleaningStatus = p.cleaning_status || "";
    const cleaningResult = p.cleaning_result || null;
    const cleanedPath = p.cleaned_video_path || "";
    const isPassed = r.status === "passed" || (techCheck && techCheck.passed);

    // Tech-check results
    const techHtml = techCheck ? `
      <section class="section">
        <h3>${sectionHeadingIcon("tech-check")}Результаты проверки</h3>
        <div class="field-grid" style="gap:8px">
          ${techCheck.info?.file_size_mb != null ? `<div class="tech-row"><span>Размер</span><span>${techCheck.info.file_size_mb} МБ</span></div>` : ""}
          ${techCheck.info?.duration_seconds != null ? `<div class="tech-row"><span>Длительность</span><span>${techCheck.info.duration_seconds} сек</span></div>` : ""}
          ${techCheck.info?.width ? `<div class="tech-row"><span>Разрешение</span><span>${techCheck.info.width}×${techCheck.info.height}</span></div>` : ""}
        </div>
        ${techCheck.passed
          ? `<div style="margin-top:8px;color:var(--positive);font-size:13px">${uiIcon("check")} Все проверки пройдены</div>`
          : `<div style="margin-top:8px">${(techCheck.issues || []).map(i => `<div style="color:var(--danger);font-size:13px;margin:4px 0">${uiIcon("alert-circle")} ${escapeHtml(i)}</div>`).join("")}</div>`
        }
      </section>
    ` : "";

    // Cleaning results
    const cleanedVideoUrl = cleanedPath ? `/generated/reels_video/${r.draft_id}/${escapeHtml(cleanedPath)}` : "";
    const keepIntervals = Array.isArray(p.keep_intervals) ? p.keep_intervals : [];
    const splitClips = Array.isArray(p.split_clips) ? p.split_clips : [];
    const splitStatus = p.split_status || "";
    const cleanHtml = cleaningStatus === "completed" && cleaningResult ? `
      <div style="margin-top:8px;padding:10px;border:1px solid var(--border);border-radius:8px;font-size:13px">
        <div style="font-weight:600;margin-bottom:4px">${uiIcon("check")} Очистка завершена</div>
        <div>Вход: ${cleaningResult.input_duration}с → Выход: ${cleaningResult.output_duration}с (удалено ${cleaningResult.removed_duration}с, ${_pluralize(cleaningResult.clip_count, "фрагмент", "фрагмента", "фрагментов")})</div>
        ${cleanedVideoUrl ? `
          <div style="margin-top:8px">
            <video src="${cleanedVideoUrl}" controls playsinline preload="metadata"
              style="width:100%;max-height:300px;border-radius:8px;background:#000"></video>
          </div>
          <div style="margin-top:6px;display:flex;gap:8px;flex-wrap:wrap">
            <a href="${cleanedVideoUrl}" download style="color:var(--brand);font-size:13px">${uiIcon("download")} Скачать очищенное</a>
            <button class="secondary-button compact" type="button" data-action="splitReelsClips" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${uiIcon("scissors")} Нарезать на клипы
            </button>
          </div>
        ` : ""}
        ${splitStatus === "running" ? `<div style="margin-top:8px;color:var(--hint);font-size:12px">${uiIcon("loader")} Нарезаю клипы...</div>` : ""}
        ${splitClips.length > 0 ? `
          <div style="margin-top:8px">
            <div style="font-weight:600;margin-bottom:4px">${uiIcon("film")} Клипы (${splitClips.length})</div>
            ${splitClips.map((clip, i) => {
              const clipUrl = `/generated/reels_video/${r.draft_id}/${escapeHtml(clip.filename)}`;
              const start = clip.start != null ? clip.start.toFixed(1) : "?";
              const end = clip.end != null ? clip.end.toFixed(1) : "?";
              return `<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);font-size:12px">
                <span>Клип ${i + 1} (${start}с – ${end}с)</span>
                <a href="${clipUrl}" download style="color:var(--brand)">${uiIcon("download")} Скачать</a>
              </div>`;
            }).join("")}
          </div>
        ` : ""}
      </div>
    ` : "";

    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, false, r.draft_id)}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("reel")} <span>РИЛС · ${statusLabel(r.status)}</span></p>
          <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(r.status), statusTone(r.status))}
          </div>
        </div>

        ${videoUrl ? `
          <section class="section">
            <h3>${sectionHeadingIcon("video")}Предпросмотр</h3>
            <video src="${videoUrl}" controls playsinline preload="metadata"
              style="width:100%;max-height:400px;border-radius:8px;background:#000"></video>
          </section>
        ` : ""}

        ${techHtml}

        <section class="section">
          <h3>${sectionHeadingIcon("tools")}Инструменты</h3>
          <div class="actions-row" style="flex-wrap:wrap;gap:8px">
            <button class="secondary-button compact" type="button" data-action="runTechCheck" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${uiIcon("scan")} Проверить видео
            </button>
            <button class="secondary-button compact" type="button" data-action="reuploadVideo" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${uiIcon("upload")} Загрузить другое
            </button>
            <input type="file" id="reuploadInput" accept="video/*" style="display:none" />
          </div>
        </section>

        <section class="section">
          <h3>${sectionHeadingIcon("scissors")}Нарезка от слов-паразитов</h3>
          <div class="field-grid" style="gap:8px">
            <label>Мин. пауза (сек)
              <input type="range" id="cleanPauseDuration" min="0.1" max="2.0" step="0.1" value="0.4" style="width:100%" />
              <span id="cleanPauseValue" style="font-size:12px;color:var(--hint)">0.4 с</span>
            </label>
            <label>Порог тишины (дБ)
              <input type="range" id="cleanSilenceThreshold" min="-60" max="-10" step="1" value="-35" style="width:100%" />
              <span id="cleanThresholdValue" style="font-size:12px;color:var(--hint)">-35 дБ</span>
            </label>
          </div>
          <label style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
            <input type="checkbox" id="cleanUseWhisper" checked /> Whisper транскрипция
          </label>
          <button class="secondary-button" type="button" data-action="cleanReelsVideo" data-args='${JSON.stringify([r.draft_id, null])}'>
            ${actionLabel("scissors", "Очистить видео")}
          </button>
          <div id="cleanStatusContainer">${cleanHtml}</div>
        </section>

        <section class="section">
          <h3>${sectionHeadingIcon("film")}Сборка из кадров</h3>
          <div class="reels-form-fields">
            <label class="reels-field-label">Движок видео
              <select id="composeRenderer" class="reels-select">
                <option value="ffmpeg">Быстрая сборка</option>
                <option value="remotion">С анимацией и шаблонами</option>
              </select>
            </label>
            <div id="remotionOptions" class="reels-sub-fields" style="display:none">
              <label class="reels-field-label">Шаблон
                <select id="composeTemplate" class="reels-select">
                  <option value="aroma">Аромат</option>
                  <option value="educational">Образовательный</option>
                  <option value="promo">Промо</option>
                </select>
              </label>
              <label class="reels-field-label">Анимация текста
                <select id="composeTextAnimation" class="reels-select">
                  <option value="fade">Проявление</option>
                  <option value="slide-up">Снизу вверх</option>
                  <option value="typewriter">Печатная машинка</option>
                  <option value="scale-in">Масштабирование</option>
                </select>
              </label>
            </div>
          </div>
          <button class="secondary-button" type="button" data-action="composeReelsVideo" data-args='${JSON.stringify([r.draft_id, null])}' style="margin-top:8px">
            ${actionLabel("film", "Собрать видео")}
          </button>
          <div id="composeStatusContainer"></div>
        </section>

        <div class="actions-row" style="margin-top:12px">
          ${isPassed ? `
            <button class="primary-button" type="button" data-action="proceedToPublish" data-args='${JSON.stringify([r.draft_id, null])}'>
              ${actionLabel("publish", "Перейти к публикации")}
            </button>
          ` : ""}
          <button class="secondary-button" type="button" data-action="jumpToReelsStep" data-args='${JSON.stringify([r.draft_id, "draft", null])}'>
            ${uiIcon("arrow-left")} К сценарию
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

    const platforms = ["instagram", "threads", "youtube"];
    const platformLabels = { instagram: "Instagram", threads: "Threads", youtube: "YouTube" };

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
        ${reelsStepperMarkup(r.status, false, r.draft_id)}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("reel")} <span>РИЛС · Публикация</span></p>
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
          <div id="youtubeFields" style="display:none;margin-top:12px;padding:12px;border:1px solid var(--border);border-radius:8px">
            <p style="font-weight:600;font-size:13px;margin:0 0 8px;color:var(--text)">Настройки YouTube</p>
            <div class="field-grid">
              <label>Заголовок
                <input type="text" id="youtubeTitle" placeholder="${escapeHtml((r.topic || '').slice(0, 100))}" maxlength="100" style="width:100%" />
              </label>
              <label>Приватность
                <select id="youtubePrivacy" style="width:100%">
                  <option value="public">Публичное</option>
                  <option value="unlisted">По ссылке</option>
                  <option value="private">Приватное</option>
                </select>
              </label>
            </div>
          </div>
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
    const youtubeTitle = String(document.getElementById("youtubeTitle")?.value || "");
    const youtubePrivacy = String(document.getElementById("youtubePrivacy")?.value || "public");
    await withButtonFeedback(btn, "Публикую...", async () => {
      const body = { platforms, date, time };
      if (platforms.includes("youtube")) {
        body.youtube_title = youtubeTitle;
        body.youtube_privacy = youtubePrivacy;
      }
      const result = await fetchJson(`/api/reels/${draftId}/publish`, {
        method: "POST",
        body: JSON.stringify(body),
        timeout: 120000,
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


  // ── Video compose (AI-generated from frames) ─────────────────────────────

  let _composePollTimer = null;

  async function composeReelVideo(draftId, btn) {
    const rendererEl = document.getElementById("composeRenderer");
    const templateEl = document.getElementById("composeTemplate");
    const animationEl = document.getElementById("composeAnimation");
    const renderer = rendererEl ? rendererEl.value : "ffmpeg";
    const template = templateEl ? templateEl.value : "aroma";
    const textAnimation = animationEl ? animationEl.value : "fade";

    const params = new URLSearchParams({ renderer, template, text_animation: textAnimation });

    await withButtonFeedback(btn, "Запускаю…", async () => {
      await fetchJson(`/api/reels/${draftId}/compose?${params}`, { method: "POST" });
      _startComposePoll(draftId);
      showUiNotice("Видео создаётся — это займёт несколько минут", "info");
    }, "Запущено");
  }

  function _startComposePoll(draftId) {
    if (_composePollTimer) clearInterval(_composePollTimer);
    const statusEl = document.getElementById("composeStatusText");
    if (statusEl) statusEl.textContent = "Создаётся…";

    _composePollTimer = setInterval(async () => {
      try {
        const st = await fetchJson(`/api/reels/${draftId}/compose-status`);
        if (statusEl) {
          if (st.status === "running") statusEl.textContent = "Рендеринг видео…";
          else if (st.status === "completed") statusEl.textContent = "Готово!";
          else if (st.status === "failed") statusEl.textContent = "Ошибка: " + (st.error || "неизвестная");
        }
        if (st.status === "completed" || st.status === "failed") {
          clearInterval(_composePollTimer);
          _composePollTimer = null;
          const draft = await fetchJson(`/api/reels/${draftId}`);
          mergeReelsIntoState(draft);
          callbacks.renderReelsDetail?.(draft);
          if (st.status === "completed") {
            showUiNotice("Видео готово!", "success");
          } else {
            showUiNotice("Ошибка создания видео: " + (st.error || ""), "error");
          }
        }
      } catch (_e) {
        clearInterval(_composePollTimer);
        _composePollTimer = null;
      }
    }, 3000);
  }

  // ── Video upload & cleaning handlers ───────────────────────────────────

  document.addEventListener("change", (e) => {
    if (e.target && e.target.id === "composeRenderer") {
      const opts = document.getElementById("remotionOptions");
      if (opts) opts.style.display = e.target.value === "remotion" ? "flex" : "none";
    }
  });

  document.addEventListener("input", (e) => {
    if (e.target && e.target.id === "cleanPauseDuration") {
      const valEl = document.getElementById("cleanPauseVal");
      if (valEl) valEl.textContent = e.target.value + "с";
    }
  });

  document.addEventListener("change", (e) => {
    if (e.target && e.target.id === "videoFileInput") {
      const uploadBtn = document.getElementById("reelsUploadBtn");
      const nameEl = document.getElementById("reelsSelectedFileName");
      if (e.target.files.length) {
        if (uploadBtn) {
          uploadBtn.style.display = "";
          // Store draft ID for direct click handler fallback
          uploadBtn._draftId = uploadBtn.dataset.args
            ? JSON.parse(uploadBtn.dataset.args)[0]
            : null;
        }
        if (nameEl) {
          nameEl.style.display = "";
          nameEl.textContent = e.target.files[0].name;
        }
      } else {
        if (uploadBtn) uploadBtn.style.display = "none";
        if (nameEl) nameEl.style.display = "none";
      }
    }
  });

  function _updateUploadProgressUI() {
    const { videoUpload } = state;
    // Update inline progress bar (on reels detail screen)
    const progressBar = document.getElementById("reelsUploadProgressBar");
    const progressText = document.getElementById("reelsUploadProgressText");
    const progressZone = document.getElementById("reelsUploadProgressZone");
    if (progressZone) {
      progressZone.style.display = videoUpload.active ? "" : "none";
    }
    if (progressBar) {
      progressBar.style.width = `${videoUpload.progress}%`;
    }
    if (progressText) {
      progressText.textContent = videoUpload.error
        ? `Ошибка: ${videoUpload.error}`
        : `${Math.round(videoUpload.progress)}%`;
    }
    // Update floating indicator (visible on any screen)
    _updateFloatingIndicator();
  }

  function _updateFloatingIndicator() {
    const { videoUpload } = state;
    let indicator = document.getElementById("videoUploadFloatingIndicator");
    if (!videoUpload.active) {
      if (indicator) indicator.remove();
      return;
    }
    if (!indicator) {
      indicator = document.createElement("div");
      indicator.id = "videoUploadFloatingIndicator";
      indicator.className = "video-upload-floating";
      document.body.appendChild(indicator);
    }
    const pct = Math.round(videoUpload.progress);
    indicator.innerHTML = `
      <div class="video-upload-floating-content">
        <i class="ph ph-upload" style="font-size:16px"></i>
        <span class="video-upload-floating-label">Загрузка видео ${pct}%</span>
      </div>
      <div class="video-upload-floating-track">
        <div class="video-upload-floating-fill" style="width:${pct}%"></div>
      </div>
    `;
  }

  // Direct click handler as fallback for data-action delegation
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("#reelsUploadBtn");
    if (!btn) return;
    try {
      const draftId = btn.dataset.args ? JSON.parse(btn.dataset.args)[0] : null;
      if (draftId) uploadReelsVideo(draftId, btn);
    } catch (err) {
      console.error("Upload click error:", err);
      showUiNotice("Ошибка: " + (err.message || err), "error");
    }
  });

  function uploadReelsVideo(draftId, _btn) {
    const fileInput = document.getElementById("videoFileInput");
    if (!fileInput || !fileInput.files.length) {
      showRequestError("Выберите файл", { message: "Сначала выберите видео файл." });
      return;
    }
    if (state.videoUpload.active) {
      showUiNotice("Загрузка уже идёт — дождитесь завершения", "warning");
      return;
    }
    showUiNotice("Начинаю загрузку...", "info");
    const file = fileInput.files[0];
    if (file.size > 2 * 1024 * 1024 * 1024) {
      showRequestError("Файл слишком большой", { message: "Максимальный размер — 2 ГБ." });
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    state.videoUpload = { active: true, draftId, progress: 0, fileName: file.name, error: null, xhr };
    _updateUploadProgressUI();

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        state.videoUpload.progress = (e.loaded / e.total) * 100;
        _updateUploadProgressUI();
      }
    });

    xhr.addEventListener("load", async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          await fetchJson(`/api/reels/${draftId}/check-video`, { method: "POST" });
          const draft = await fetchJson(`/api/reels/${draftId}`);
          mergeReelsIntoState(draft);
          callbacks.renderReels?.();
          callbacks.renderReelsDetail?.(draft);
          showUiNotice("Видео загружено", "success");
        } catch (err) {
          showUiNotice("Видео загружено, но проверка не удалась: " + (err.message || err), "error");
        }
      } else {
        showUiNotice("Ошибка загрузки видео: HTTP " + xhr.status, "error");
      }
      state.videoUpload = { active: false, draftId: null, progress: 0, fileName: "", error: null, xhr: null };
      _updateUploadProgressUI();
    });

    xhr.addEventListener("error", () => {
      state.videoUpload.error = "Сетевая ошибка";
      _updateUploadProgressUI();
      showUiNotice("Ошибка сети при загрузке видео", "error");
      state.videoUpload = { active: false, draftId: null, progress: 0, fileName: "", error: null, xhr: null };
      _updateUploadProgressUI();
    });

    xhr.addEventListener("abort", () => {
      state.videoUpload = { active: false, draftId: null, progress: 0, fileName: "", error: null, xhr: null };
      _updateUploadProgressUI();
      showUiNotice("Загрузка видео отменена", "info");
    });

    xhr.open("POST", `/api/reels/${draftId}/upload-video`);
    const hdrs = getInitDataHeaders();
    Object.entries(hdrs).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.send(formData);
  }

  let _cleanPollTimer = null;
  let _cleanEventSource = null;

  function _cleanAuthQs() {
    const d = window.Telegram?.WebApp?.initData;
    return d ? `?init_data=${encodeURIComponent(d)}` : "";
  }

  const CLEAN_STEP_LABELS = {
    preparing: "Подготовка файла…",
    analyzing: "Анализ аудиодорожки…",
    transcribing: "Транскрипция через Whisper…",
    detecting_silence: "Поиск пауз и тишины…",
    assembling: "Сборка очищенного видео…",
  };

  function _renderCleanProgress(step, progress, extra) {
    const label = CLEAN_STEP_LABELS[step] || "Обработка…";
    const pct = Math.min(Math.max(progress || 0, 0), 100);
    const estimate = pct < 30 ? "~2-4 мин" : pct < 70 ? "~1-2 мин" : "меньше минуты";
    return `
      <div class="reels-progress-container">
        <div class="reels-progress-header">
          <span class="button-spinner"></span>
          <span class="reels-progress-label">${escapeHtml(label)}</span>
        </div>
        <div class="reels-progress-bar-track">
          <div class="reels-progress-bar-fill" style="width:${pct}%"></div>
        </div>
        <div class="reels-progress-footer">
          <span>${pct}%</span>
          <span>Осталось ${estimate}</span>
        </div>
        <div class="reels-progress-hint">Можно закрыть приложение — процесс продолжится на сервере.</div>
      </div>`;
  }

  let _cleanRunning = false;

  async function cleanReelsVideo(draftId, btn) {
    if (_cleanRunning) {
      showUiNotice("Очистка уже запущена — дождитесь завершения", "warning");
      return;
    }
    const pauseInput = document.getElementById("cleanPauseDuration");
    const thresholdInput = document.getElementById("cleanSilenceThreshold");
    const whisperInput = document.getElementById("cleanUseWhisper");
    const minPause = pauseInput ? parseFloat(pauseInput.value) : 0.4;
    const threshold = thresholdInput ? parseFloat(thresholdInput.value) : -35.0;
    const useWhisper = whisperInput ? whisperInput.checked : true;

    _cleanRunning = true;
    if (btn) { btn.disabled = true; btn.style.opacity = "0.5"; }

    // Show initial progress immediately
    const container = document.getElementById("cleanStatusContainer");
    if (container) container.innerHTML = _renderCleanProgress("preparing", 5);

    try {
      await fetchJson(`/api/reels/${draftId}/clean-video`, {
        method: "POST",
        body: JSON.stringify({
          min_pause_duration: minPause,
          silence_threshold_db: threshold,
          use_whisper: useWhisper,
        }),
      });
      _startCleanPoll(draftId);
    } catch (e) {
      _cleanRunning = false;
      if (btn) { btn.disabled = false; btn.style.opacity = ""; }
      if (container) container.innerHTML = "";
      showUiNotice("Не удалось запустить очистку: " + (e.message || ""), "error");
    }
  }

  function _updateCleanProgressUI(st) {
    const container = document.getElementById("cleanStatusContainer");
    if (!container) return;
    if (st.status === "running" || st.status === "pending") {
      container.innerHTML = _renderCleanProgress(st.step || "preparing", st.progress || 5);
    }
  }

  async function _onCleanDone(draftId, status) {
    _cleanRunning = false;
    const draft = await fetchJson(`/api/reels/${draftId}`);
    mergeReelsIntoState(draft);
    callbacks.renderReelsDetail?.(draft);
    if (status === "completed") showUiNotice("Видео очищено от пауз", "success");
    else showUiNotice("Очистка не удалась", "error");
  }

  function _startCleanPoll(draftId) {
    if (_cleanPollTimer) { clearInterval(_cleanPollTimer); _cleanPollTimer = null; }
    if (_cleanEventSource) { _cleanEventSource.close(); _cleanEventSource = null; }
    if (typeof EventSource !== "undefined") {
      const es = new EventSource(`/api/reels/${draftId}/clean-video-stream${_cleanAuthQs()}`);
      _cleanEventSource = es;
      es.onmessage = async (event) => {
        try {
          const st = JSON.parse(event.data);
          _updateCleanProgressUI(st);
          if (st.status === "completed" || st.status === "failed") {
            es.close(); _cleanEventSource = null;
            await _onCleanDone(draftId, st.status);
          }
        } catch (_e) { /* ignore */ }
      };
      es.onerror = () => { es.close(); _cleanEventSource = null; _fallbackCleanPoll(draftId); };
    } else {
      _fallbackCleanPoll(draftId);
    }
  }

  function _fallbackCleanPoll(draftId) {
    _cleanPollTimer = setInterval(async () => {
      try {
        const st = await fetchJson(`/api/reels/${draftId}/clean-video-status`);
        _updateCleanProgressUI(st);
        if (st.status === "completed" || st.status === "failed") {
          clearInterval(_cleanPollTimer); _cleanPollTimer = null;
          await _onCleanDone(draftId, st.status);
        }
      } catch (_e) { clearInterval(_cleanPollTimer); _cleanPollTimer = null; }
    }, 2000);
  }

  async function splitReelsClips(draftId, btn) {
    await withButtonFeedback(btn, "Нарезаю...", async () => {
      await fetchJson(`/api/reels/${draftId}/split-clips`, { method: "POST" });
      _startSplitPoll(draftId);
    }, "Нарезка запущена");
  }

  let _splitPollTimer = null;
  function _startSplitPoll(draftId) {
    if (_splitPollTimer) { clearInterval(_splitPollTimer); _splitPollTimer = null; }
    _splitPollTimer = setInterval(async () => {
      try {
        const st = await fetchJson(`/api/reels/${draftId}/split-clips-status`);
        if (st.status === "completed" || st.status === "failed") {
          clearInterval(_splitPollTimer); _splitPollTimer = null;
          const draft = await fetchJson(`/api/reels/${draftId}`);
          mergeReelsIntoState(draft);
          callbacks.renderReelsDetail?.(draft);
          if (st.status === "completed") showUiNotice("Клипы готовы к скачиванию");
        }
      } catch (_e) { clearInterval(_splitPollTimer); _splitPollTimer = null; }
    }, 2000);
  }

  async function checkAndPublish(draftId, btn) {
    await withButtonFeedback(btn, "Проверяю...", async () => {
      await fetchJson(`/api/reels/${draftId}/check-video`, { method: "POST" });
      const draft = await fetchJson(`/api/reels/${draftId}`);
      mergeReelsIntoState(draft);
      callbacks.renderReels?.();
      callbacks.renderReelsDetail?.(draft);
    }, "Проверено");
  }

  function renderScreen7Published(r) {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        ${reelsStepperMarkup(r.status, false, r.draft_id)}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("reel")} <span>РИЛС · Опубликован</span></p>
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
    if (String(draftId || "").startsWith("pending-")) {
      showRequestError("Рилс ещё создаётся", { message: "Дождитесь завершения генерации." });
      return;
    }
    try {
      await withButtonFeedback(btn, "Переключаю...", async () => {
        const draft = await fetchJson(`/api/reels/${draftId}/force-edit`, {
          method: "PATCH",
          body: "{}",
        });
        mergeReelsIntoState(draft);
        callbacks.renderReels?.();
        callbacks.renderReelsDetail?.(draft);
      }, "Готово");
    } catch (error) {
      showRequestError("Не удалось переключить в режим редактирования", error);
    }
  }

  async function copyReelsCaption(draftId, btn) {
    const draft = state.selectedReels;
    const caption = draft?.caption || draft?.payload?.caption || "";
    if (!caption) return;
    try {
      await navigator.clipboard.writeText(caption);
      const icon = btn.querySelector(".ph");
      if (icon) {
        const origClass = [...icon.classList].find(c => c.startsWith("ph-") && c !== "ph");
        if (origClass) {
          icon.classList.remove(origClass);
          icon.classList.add("ph-check");
          setTimeout(() => {
            icon.classList.remove("ph-check");
            icon.classList.add(origClass);
          }, 1500);
        }
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

  function openBotUploadLink(draftId) {
    const botUsername = window.__BOT_USERNAME || "Stress_ins_bot";
    const url = `https://t.me/${botUsername}?start=upload_${draftId}`;
    const tg = window.Telegram?.WebApp;
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(url);
    } else {
      window.open(url, "_blank");
    }
  }

  // ── Screen 5 action functions ────────────────────────────────────────

  async function jumpToReelsStep(draftId, stepKey, btn) {
    const draft = await fetchJson(`/api/reels/${draftId}`);
    if (!draft) return;
    mergeReelsIntoState(draft);
    const r = { ...draft, draft_id: draftId };
    if (stepKey === "draft") r.status = "draft";
    else if (stepKey === "approved") r.status = "approved";
    else if (stepKey === "video_uploaded") r.status = "video_uploaded";
    else if (stepKey === "published") r.status = "passed";
    callbacks.renderReelsDetail?.(r);
  }

  async function runTechCheck(draftId, btn) {
    await withButtonFeedback(btn, "Проверяю...", async () => {
      await fetchJson(`/api/reels/${draftId}/check-video`, { method: "POST" });
      const draft = await fetchJson(`/api/reels/${draftId}`);
      mergeReelsIntoState(draft);
      callbacks.renderReelsDetail?.(draft);
    }, "Проверено");
  }

  let _composeRunning = false;

  function _renderComposeProgress(step) {
    const labels = {
      pending: "Подготовка кадров…",
      running: "Рендеринг видео…",
      encoding: "Кодирование…",
    };
    const label = labels[step] || "Сборка видео…";
    return `
      <div class="reels-progress-container">
        <div class="reels-progress-header">
          <span class="button-spinner"></span>
          <span class="reels-progress-label">${escapeHtml(label)}</span>
        </div>
        <div class="reels-progress-bar-track">
          <div class="reels-progress-bar-fill reels-progress-bar-fill--indeterminate"></div>
        </div>
        <div class="reels-progress-footer">
          <span>~1-3 мин</span>
        </div>
        <div class="reels-progress-hint">Можно закрыть приложение — процесс продолжится на сервере.</div>
      </div>`;
  }

  async function composeReelsVideo(draftId, btn) {
    if (_composeRunning) {
      showUiNotice("Сборка уже запущена — дождитесь завершения", "warning");
      return;
    }
    const renderer = document.getElementById("composeRenderer")?.value || "ffmpeg";
    const template = document.getElementById("composeTemplate")?.value || "aroma";
    const textAnimation = document.getElementById("composeTextAnimation")?.value || "fade";
    const qs = `renderer=${renderer}&template=${template}&text_animation=${textAnimation}`;

    _composeRunning = true;
    if (btn) { btn.disabled = true; btn.style.opacity = "0.5"; }

    const container = document.getElementById("composeStatusContainer");
    if (container) container.innerHTML = _renderComposeProgress("pending");

    try {
      await fetchJson(`/api/reels/${draftId}/compose?${qs}`, { method: "POST" });
      _startComposePoll2(draftId);
    } catch (e) {
      _composeRunning = false;
      if (btn) { btn.disabled = false; btn.style.opacity = ""; }
      if (container) container.innerHTML = "";
      showUiNotice("Не удалось запустить сборку: " + (e.message || ""), "error");
    }
  }

  function _startComposePoll2(draftId) {
    const timer = setInterval(async () => {
      try {
        const st = await fetchJson(`/api/reels/${draftId}/compose-status`);
        if (st.status === "completed" || st.status === "failed") {
          clearInterval(timer);
          _composeRunning = false;
          const draft = await fetchJson(`/api/reels/${draftId}`);
          mergeReelsIntoState(draft);
          callbacks.renderReelsDetail?.(draft);
          if (st.status === "completed") showUiNotice("Видео собрано", "success");
          else showUiNotice("Ошибка сборки: " + (st.error || ""), "error");
        } else {
          const el = document.getElementById("composeStatusContainer");
          if (el) el.innerHTML = _renderComposeProgress(st.status || "running");
        }
      } catch (_e) { clearInterval(timer); _composeRunning = false; }
    }, 3000);
  }

  async function reuploadVideo(draftId, btn) {
    // Find existing input or create one dynamically (survives re-renders)
    let input = document.getElementById("reuploadInput");
    if (!input) {
      input = document.createElement("input");
      input.id = "reuploadInput";
      input.type = "file";
      input.accept = "video/*";
      input.style.display = "none";
      document.body.appendChild(input);
    }
    // Clear previous value so onchange fires even for the same file
    input.value = "";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      if (file.size > 2 * 1024 * 1024 * 1024) {
        showUiNotice("Файл слишком большой (макс. 2 ГБ)", "error");
        return;
      }
      showUiNotice("Загрузка видео…", "info");
      const formData = new FormData();
      formData.append("file", file);
      try {
        const hdrs = getInitDataHeaders();
        const resp = await fetch(`/api/reels/${draftId}/upload-video`, {
          method: "POST",
          headers: hdrs,
          body: formData,
        });
        if (!resp.ok) {
          const errText = await resp.text().catch(() => `HTTP ${resp.status}`);
          throw new Error(errText);
        }
        await fetchJson(`/api/reels/${draftId}/check-video`, { method: "POST" }).catch(() => {});
        const draft = await fetchJson(`/api/reels/${draftId}`);
        mergeReelsIntoState(draft);
        callbacks.renderReelsDetail?.(draft);
        showUiNotice("Видео загружено", "success");
      } catch (e) {
        showUiNotice("Ошибка загрузки: " + (e.message || "неизвестная ошибка"), "error");
      }
    };
    input.click();
  }

  async function proceedToPublish(draftId, btn) {
    await withButtonFeedback(btn, "Переключаю...", async () => {
      // Set status to "passed" so the publish screen shows
      const draft = await fetchJson(`/api/reels/${draftId}`);
      mergeReelsIntoState(draft);
      callbacks.renderReelsDetail?.(draft);
    }, "Готово");
  }

  // Toggle YouTube settings visibility when checkbox changes
  document.body.addEventListener("change", (e) => {
    if (e.target?.name === "publish_platform" && e.target?.value === "youtube") {
      const ytFields = document.getElementById("youtubeFields");
      if (ytFields) ytFields.style.display = e.target.checked ? "block" : "none";
    }
    // Slider value displays
    if (e.target?.id === "cleanPauseDuration") {
      const el = document.getElementById("cleanPauseValue");
      if (el) el.textContent = `${e.target.value} с`;
    }
    if (e.target?.id === "cleanSilenceThreshold") {
      const el = document.getElementById("cleanThresholdValue");
      if (el) el.textContent = `${e.target.value} дБ`;
    }
    // Renderer toggle
    if (e.target?.id === "composeRenderer") {
      const opts = document.getElementById("remotionOptions");
      if (opts) opts.style.display = e.target.value === "remotion" ? "block" : "none";
    }
  });

  // Also handle input events for sliders (real-time updates)
  document.body.addEventListener("input", (e) => {
    if (e.target?.id === "cleanPauseDuration") {
      const el = document.getElementById("cleanPauseValue");
      if (el) el.textContent = `${e.target.value} с`;
    }
    if (e.target?.id === "cleanSilenceThreshold") {
      const el = document.getElementById("cleanThresholdValue");
      if (el) el.textContent = `${e.target.value} дБ`;
    }
  });

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
    // Video compose & upload & cleaning
    composeReelVideo,
    uploadReelsVideo,
    cleanReelsVideo,
    splitReelsClips,
    checkAndPublish,
    // Phase 5 role gates
    canEditReels,
    canApproveReels,
    canPublishReels,
    forceEditReels,
    // Feature: copy caption + fullscreen image
    copyReelsCaption,
    openReelsImageFullscreen,
    openReelsPreview,
    openBotUploadLink,
    // Screen 5 video tools
    jumpToReelsStep,
    runTechCheck,
    composeReelsVideo,
    reuploadVideo,
    proceedToPublish,
  };
}
