export function createCarouselModule(deps) {
  const {
    state,
    carouselNoteSaveTimers,
    frameDraftKey,
    escapeHtml,
    uiIcon,
    actionLabel,
    formatPlanDate,
    fetchJson,
    withButtonFeedback,
    showRequestError,
    confirmAction,
    authQueryString,
    isCurrentDraftDetail,
    isPromptDisclosureOpen,
    mergeDraftIntoState,
    renderDraftList,
    renderDraftDetail,
    scheduleCarouselRefresh,
  } = deps;

  function slideNoteId(index) {
    return `carouselSlideNote${index}`;
  }

  function slideTextId(index) {
    return `carouselSlideText${index}`;
  }

  function bufferedCarouselNote(draftId, index, fallback = "") {
    const key = frameDraftKey(draftId, index);
    return Object.prototype.hasOwnProperty.call(state.pendingCarouselNotes, key)
      ? state.pendingCarouselNotes[key]
      : String(fallback || "");
  }

  function carouselSlideOperation(draftId, index) {
    return state.pendingCarouselOps[frameDraftKey(draftId, index)] || "";
  }

  function setCarouselSlideOperation(draftId, index, value = "") {
    const key = frameDraftKey(draftId, index);
    if (!value) {
      delete state.pendingCarouselOps[key];
      return;
    }
    state.pendingCarouselOps[key] = String(value);
  }

  function hasPendingCarouselOperations(draftId = "") {
    const prefix = draftId ? `${draftId}:` : "";
    return Object.keys(state.pendingCarouselOps).some((key) => key.startsWith(prefix));
  }

  function carouselSlideStatusMarkup(draftId, index, hasImage) {
    const operation = carouselSlideOperation(draftId, index);
    if (operation) {
      return `<div class="slide-status is-pending">${uiIcon("sparkle")}<span>${escapeHtml(operation)}</span></div>`;
    }
    if (hasImage) {
      return `<div class="slide-status is-ready">${uiIcon("approve")}<span>Картинка готова</span></div>`;
    }
    return "";
  }

  function renderSlideVersions(draftId, slideIndex, currentImage, versions = []) {
    const items = Array.isArray(versions) ? versions : [];
    if (items.length <= 1) return "";
    const currentFilename = String(currentImage?.filename || "").trim();
    return `
      <div class="slide-versions">
        <div class="slide-versions-head">
          <strong>${uiIcon("image")}Версии</strong>
          <span class="meta">${items.length} шт</span>
        </div>
        <div class="slide-version-grid">
          ${items.map((version, versionIndex) => {
            const isCurrent = String(version?.filename || "").trim() === currentFilename;
            return `
              <article class="slide-version-card${isCurrent ? " is-current" : ""}">
                <button
                  class="slide-version-thumb"
                  type="button"
                  onclick='selectCarouselSlideVersion(${JSON.stringify(draftId)}, ${slideIndex}, ${versionIndex}, this)'
                  aria-label="${isCurrent ? "Текущая версия" : "Сделать текущей"}"
                >
                  <img src="${escapeHtml(version.url || "")}" alt="Версия ${versionIndex + 1} для слайда ${slideIndex + 1}" />
                </button>
                <div class="slide-version-meta">
                  <span>${isCurrent ? "Текущая" : `Версия ${versionIndex + 1}`}</span>
                  <span class="meta">${escapeHtml(formatPlanDate(version.generated_at) || "сейчас")}</span>
                </div>
                <div class="actions-row slide-version-actions actions-grid-two">
                  ${isCurrent ? "" : `<button class="secondary-button" type="button" onclick='selectCarouselSlideVersion(${JSON.stringify(draftId)}, ${slideIndex}, ${versionIndex}, this)'>${actionLabel("approve", "Сделать текущей")}</button>`}
                  ${items.length > 1 ? `<button class="secondary-button" type="button" onclick='deleteCarouselSlideVersion(${JSON.stringify(draftId)}, ${slideIndex}, ${versionIndex}, this)'>${actionLabel("trash", "Удалить")}</button>` : ""}
                </div>
              </article>
            `;
          }).join("")}
        </div>
      </div>
    `;
  }

  // ── Swiper state ──────────────────────────────────────────────────────────
  let _swiperIndex = 0;
  let _swiperDraftId = "";
  let _swiperCaptionTimer = 0;

  function _swiperSaveCaption(draftId, fromIndex) {
    const textField = document.getElementById(slideTextId(fromIndex));
    if (!textField) return;
    const text = String(textField.value || "").trim();
    const original = textField.dataset.original || "";
    if (text === original) return;
    void saveCarouselSlideText(draftId, fromIndex);
  }

  function _swiperGoTo(index, total, draftId) {
    if (index < 0 || index >= total) return;
    const prevIndex = _swiperIndex;
    // debounced save of previous slide caption
    if (prevIndex !== index && draftId) {
      window.clearTimeout(_swiperCaptionTimer);
      const saveIdx = prevIndex;
      _swiperCaptionTimer = window.setTimeout(() => _swiperSaveCaption(draftId, saveIdx), 800);
    }
    _swiperIndex = index;
    const track = document.querySelector(".slides-swiper-track");
    if (track) track.style.transform = `translateX(-${index * 100}%)`;
    document.querySelectorAll(".slides-dot").forEach((dot, i) => {
      dot.classList.toggle("is-active", i === index);
    });
  }

  function initSwiper(container, total, draftId) {
    const track = container.querySelector(".slides-swiper-track");
    if (!track) return;
    let startX = 0, startY = 0, currentX = 0, dragging = false, locked = false;
    const threshold = 40;

    track.addEventListener("touchstart", (e) => {
      if (e.touches.length > 1) return;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      currentX = 0;
      dragging = true;
      locked = false;
      track.classList.add("is-dragging");
    }, { passive: true });

    track.addEventListener("touchmove", (e) => {
      if (!dragging) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      if (!locked) {
        if (Math.abs(dy) > Math.abs(dx)) { dragging = false; track.classList.remove("is-dragging"); return; }
        locked = true;
      }
      currentX = dx;
      const base = -_swiperIndex * 100;
      const pct = (dx / container.offsetWidth) * 100;
      track.style.transform = `translateX(${base + pct}%)`;
    }, { passive: true });

    track.addEventListener("touchend", () => {
      if (!dragging) return;
      dragging = false;
      track.classList.remove("is-dragging");
      if (currentX < -threshold && _swiperIndex < total - 1) {
        _swiperGoTo(_swiperIndex + 1, total, draftId);
      } else if (currentX > threshold && _swiperIndex > 0) {
        _swiperGoTo(_swiperIndex - 1, total, draftId);
      } else {
        track.style.transform = `translateX(-${_swiperIndex * 100}%)`;
      }
    }, { passive: true });
  }

  function renderSlides(draftId, slides = [], prompts = [], slideImages = [], promptNotes = [], slideVersions = []) {
    const slideItems = Array.isArray(slides) ? slides : [];
    const promptItems = Array.isArray(prompts) ? prompts : [];
    const imageItems = Array.isArray(slideImages) ? slideImages : [];
    const noteItems = Array.isArray(promptNotes) ? promptNotes : [];
    const versionItems = Array.isArray(slideVersions) ? slideVersions : [];
    if (!slideItems.length) return "";
    const readyCount = imageItems.filter(Boolean).length;
    const header = readyCount > 0
      ? `Слайды карусели <span class="meta">${readyCount} / ${slideItems.length} с картинкой</span>`
      : "Слайды карусели";

    if (draftId !== _swiperDraftId) { _swiperIndex = 0; _swiperDraftId = draftId; }
    const idx = Math.min(_swiperIndex, slideItems.length - 1);

    const dotsHtml = slideItems.map((_, i) =>
      `<button class="slides-dot${i === idx ? " is-active" : ""}" type="button" onclick="carouselSwiperGoTo(${i})" aria-label="Слайд ${i + 1}"></button>`
    ).join("");

    const slidesHtml = slideItems.map((slide, index) => {
      const img = imageItems[index];
      const prompt = String(promptItems[index] || "");
      const note = bufferedCarouselNote(draftId, index, String(noteItems[index] || ""));
      const versions = Array.isArray(versionItems[index]) ? versionItems[index] : [];
      const imgHtml = img?.url
        ? `<div class="carousel-slide-image-wrap"><img src="${escapeHtml(img.url)}" alt="Слайд ${index + 1}" style="cursor:pointer" onclick="openImageFullscreen(this.src, 'Слайд ${index + 1}')" /></div>`
        : `<div class="carousel-slide-image-wrap"><div class="frame-loading"><div class="frame-loading-inner"><span class="button-spinner" aria-hidden="true"></span><span>Изображение ещё готовится</span></div></div></div>`;
      return `
        <article class="slide">
          <strong>Слайд ${index + 1}</strong>
          ${carouselSlideStatusMarkup(draftId, index, Boolean(img?.url))}
          ${imgHtml}
          <label class="prompt-note-field">
            <span>Подпись слайда</span>
            <textarea id="${slideTextId(index)}" data-original="${escapeHtml(slide)}" placeholder="Текст для этого слайда">${escapeHtml(slide)}</textarea>
          </label>
          <p class="field-help">После правки нажмите «Сохранить подпись», чтобы обновить этот слайд в черновике.</p>
          <div class="actions-row prompt-actions actions-grid-two">
            <button class="primary-button" type="button" aria-label="Сохранить текст слайда" onclick='saveCarouselSlideText(${JSON.stringify(draftId)}, ${index}, this)'>${actionLabel("text", "Сохранить подпись")}</button>
            <button class="secondary-button" type="button" ${!img?.url ? "disabled" : ""} onclick='previewCarouselSlide(${JSON.stringify(draftId)}, ${index}, this)'>${actionLabel("eye", "Предпросмотр")}</button>
          </div>
          ${prompt ? (() => {
              const discOpen = isPromptDisclosureOpen(`carousel:${draftId}:${index}`, !img?.url);
              return `
            <div class="prompt-disclosure${discOpen ? " is-open" : ""}" data-prompt-key="${escapeHtml(`carousel:${draftId}:${index}`)}">
              <button class="secondary-button prompt-toggle" type="button" aria-expanded="${discOpen ? "true" : "false"}" data-default-open="${!img?.url ? "true" : "false"}" data-open-label="Показать промпт" data-close-label="Скрыть промпт" onclick='togglePromptDisclosure(${JSON.stringify(`carousel:${draftId}:${index}`)}, this)'>${actionLabel("eye", discOpen ? "Скрыть промпт" : "Показать промпт")}</button>
              <div class="prompt-card"${discOpen ? "" : " hidden"}>
                <div class="detail-preview prompt-preview">${escapeHtml(prompt)}</div>
                <label class="prompt-note-field">
                  <span>Замечание к картинке</span>
                  <textarea id="${slideNoteId(index)}" placeholder="Например: теплее свет, крупнее объект, меньше деталей на фоне" oninput='handleCarouselSlideNoteInput(${JSON.stringify(draftId)}, ${index}, this.value)'>${escapeHtml(note)}</textarea>
                </label>
                <div class="actions-row prompt-actions actions-grid-two">
                  <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(prompt)})'>${actionLabel("prompt", "Скопировать промпт слайда")}</button>
                  <button class="secondary-button" type="button" onclick='regenerateCarouselSlide(${JSON.stringify(draftId)}, ${index}, this)'>${actionLabel("regenerate", "Обновить изображение")}</button>
                  <button class="primary-button" type="button" onclick='regenerateCarouselSlide(${JSON.stringify(draftId)}, ${index}, this)'>${actionLabel("note", "Обновить по замечанию")}</button>
                </div>
              </div>
            </div>
          `;
            })() : ""}
          ${renderSlideVersions(draftId, index, img, versions)}
        </article>
      `;
    }).join("");

    // Schedule swiper init after DOM render
    const total = slideItems.length;
    const dId = draftId;
    requestAnimationFrame(() => {
      const el = document.querySelector(".slides-swiper");
      if (el) initSwiper(el, total, dId);
      if (window.lucide) lucide.createIcons();
    });

    return `
      <section class="section">
        <h3>${uiIcon("slides")}${header}</h3>
        <div class="slides-swiper">
          <div class="slides-swiper-track" style="transform:translateX(-${idx * 100}%)">
            ${slidesHtml}
          </div>
        </div>
        <div class="slides-dots">${dotsHtml}</div>
      </section>
    `;
  }

  function carouselSwiperGoTo(index) {
    const track = document.querySelector(".slides-swiper-track");
    if (!track) return;
    const total = track.children.length;
    _swiperGoTo(index, total, _swiperDraftId);
  }

  async function saveCarouselSlideText(draftId, slideIndex, button) {
    const textField = document.getElementById(slideTextId(slideIndex));
    const text = String(textField?.value || "").trim();
    const apply = async () => {
      const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/text`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      state.selected = draft;
      mergeDraftIntoState(draft);
      renderDraftList();
      if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
    };
    if (button instanceof HTMLElement) {
      await withButtonFeedback(button, "Сохраняю...", apply, "Сохранено");
      return;
    }
    await apply();
  }

  async function persistCarouselSlideNote(draftId, slideIndex, note) {
    const key = frameDraftKey(draftId, slideIndex);
    state.pendingCarouselNotes[key] = String(note || "");
    const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/note`, {
      method: "POST",
      body: JSON.stringify({ note: String(note || "") }),
    });
    mergeDraftIntoState(draft);
    state.pendingCarouselNotes[key] = String(note || "");
    return draft;
  }

  function handleCarouselSlideNoteInput(draftId, slideIndex, value) {
    const key = frameDraftKey(draftId, slideIndex);
    state.pendingCarouselNotes[key] = String(value || "");
    window.clearTimeout(carouselNoteSaveTimers[key]);
    carouselNoteSaveTimers[key] = window.setTimeout(() => {
      void persistCarouselSlideNote(draftId, slideIndex, state.pendingCarouselNotes[key]).catch(() => {});
    }, 600);
  }

  async function regenerateCarouselSlide(draftId, slideIndex, button) {
    const noteField = document.getElementById(slideNoteId(slideIndex));
    const currentNote = String(noteField?.value || bufferedCarouselNote(draftId, slideIndex, "")).trim();
    const note = currentNote || null;
    const apply = async () => {
      setCarouselSlideOperation(
        draftId,
        slideIndex,
        note ? "Учитываю замечание и собираю новый вариант" : "Генерирую новый вариант картинки",
      );
      if (isCurrentDraftDetail(draftId) && state.selected?.draft_id === draftId) {
        renderDraftDetail(state.selected);
      }
      if (currentNote) {
        await persistCarouselSlideNote(draftId, slideIndex, currentNote);
      }
      const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/regenerate`, {
        method: "POST",
        body: JSON.stringify({ note }),
        timeout: 60000,
      });
      mergeDraftIntoState(draft);
      renderDraftList();
      if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
      scheduleCarouselRefresh(draft.draft_id);
    };
    try {
      if (button instanceof HTMLElement) {
        await withButtonFeedback(button, "Генерирую...", apply, "Готово");
        return;
      }
      await apply();
    } catch (error) {
      showRequestError("Не удалось перегенерировать картинку", error);
    } finally {
      setCarouselSlideOperation(draftId, slideIndex, "");
      if (isCurrentDraftDetail(draftId) && state.selected?.draft_id === draftId) {
        renderDraftDetail(state.selected);
      }
    }
  }

  async function regenerateCarouselAll(draftId, button) {
    try {
      await withButtonFeedback(button, "Запускаю...", async () => {
        const draft = await fetchJson(`/api/carousel/${draftId}/regenerate-all`, {
          method: "POST",
          body: "{}",
          timeout: 30000,
        });
        state.selected = draft;
        state.draftId = draft.draft_id;
        mergeDraftIntoState(draft);
        renderDraftList();
        if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
        scheduleCarouselRefresh(draft.draft_id);
      }, "Запущено");
    } catch (error) {
      showRequestError("Не удалось запустить перегенерацию всех картинок", error);
    }
  }

  async function selectCarouselSlideVersion(draftId, slideIndex, versionIndex, button) {
    try {
      await withButtonFeedback(button, "Выбираю...", async () => {
        const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/versions/${versionIndex}/select`, {
          method: "POST",
          body: "{}",
        });
        mergeDraftIntoState(draft);
        renderDraftList();
        if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
      }, "Выбрано");
    } catch (error) {
      showRequestError("Не удалось выбрать версию картинки", error);
    }
  }

  async function deleteCarouselSlideVersion(draftId, slideIndex, versionIndex, button) {
    const confirmed = await confirmAction("Удалить эту версию картинки?");
    if (!confirmed) return;
    try {
      await withButtonFeedback(button, "Удаляю...", async () => {
        const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/versions/${versionIndex}`, {
          method: "DELETE",
        });
        mergeDraftIntoState(draft);
        renderDraftList();
        if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
      }, "Удалено");
    } catch (error) {
      showRequestError("Не удалось удалить версию картинки", error);
    }
  }

  function showPreviewModal(imageUrl, title) {
    const existing = document.getElementById("previewModal");
    if (existing) existing.remove();
    const modal = document.createElement("div");
    modal.id = "previewModal";
    modal.className = "preview-modal-backdrop";
    modal.innerHTML = `
      <div class="preview-modal" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="preview-modal-header">
          <h3>${escapeHtml(title)}</h3>
          <button class="secondary-button preview-modal-close" type="button">${uiIcon("x")}</button>
        </div>
        <div class="preview-modal-body">
          <img src="${imageUrl}" alt="${escapeHtml(title)}" />
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    if (window.lucide) lucide.createIcons();
    const cleanup = () => { URL.revokeObjectURL(imageUrl); modal.remove(); };
    modal.querySelector(".preview-modal-close").addEventListener("click", cleanup);
    modal.addEventListener("click", (e) => { if (e.target === modal) cleanup(); });
  }

  async function previewCarouselSlide(draftId, slideIndex, button) {
    try {
      await withButtonFeedback(button, "Генерирую...", async () => {
        const previewUrl = `/api/carousel/${draftId}/slides/${slideIndex}/preview${authQueryString()}`;
        const resp = await fetch(previewUrl, {
          headers: deps.initDataHeaders ? deps.initDataHeaders() : {},
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const objectUrl = URL.createObjectURL(blob);
        showPreviewModal(objectUrl, `Слайд ${slideIndex + 1} — предпросмотр`);
      }, "Готово");
    } catch (error) {
      showRequestError("Не удалось сгенерировать предпросмотр", error);
    }
  }

  async function importCarouselPptx(draftId, button) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pptx";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      if (button instanceof HTMLElement) button.textContent = "Загружаю...";
      const formData = new FormData();
      formData.append("file", file);
      try {
        const resp = await fetch(`/api/carousel/${draftId}/pptx/import`, {
          method: "POST",
          headers: deps.initDataHeaders ? deps.initDataHeaders() : {},
          body: formData,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        if (button instanceof HTMLElement) {
          button.textContent = "Импортировано";
          button.classList.add("did-complete");
          window.setTimeout(() => button.classList.remove("did-complete"), 900);
        }
        // Refresh the draft detail
        if (window.openDraft) window.openDraft(draftId);
      } catch (err) {
        if (button instanceof HTMLElement) button.textContent = "Ошибка импорта";
        console.error("PPTX import failed", err);
      }
    };
    input.click();
  }

  async function downloadCarouselPptx(draftId, button) {
    const downloadUrl = `${window.location.origin}/api/carousel/${draftId}/pptx${authQueryString()}`;
    if (button instanceof HTMLElement) {
      button.classList.add("did-complete");
      window.setTimeout(() => button.classList.remove("did-complete"), 900);
    }
    const tg = window.Telegram?.WebApp;
    if (tg?.openLink) {
      tg.openLink(downloadUrl);
      return;
    }
    window.open(downloadUrl, "_blank", "noopener,noreferrer");
  }

  return {
    slideNoteId,
    slideTextId,
    bufferedCarouselNote,
    carouselSlideOperation,
    setCarouselSlideOperation,
    hasPendingCarouselOperations,
    renderSlides,
    saveCarouselSlideText,
    handleCarouselSlideNoteInput,
    regenerateCarouselSlide,
    regenerateCarouselAll,
    selectCarouselSlideVersion,
    deleteCarouselSlideVersion,
    previewCarouselSlide,
    carouselSwiperGoTo,
    downloadCarouselPptx,
    importCarouselPptx,
  };
}
