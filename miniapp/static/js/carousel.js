import { sseQueryString } from "./sse-auth.js";

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
    showUiNotice,
    confirmAction,
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

  function clearAllCarouselOperations(draftId) {
    const prefix = draftId ? `${draftId}:` : "";
    for (const key of Object.keys(state.pendingCarouselOps)) {
      if (key.startsWith(prefix)) delete state.pendingCarouselOps[key];
    }
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
                  data-action="selectCarouselSlideVersion" data-args='${JSON.stringify([draftId, slideIndex, versionIndex, null])}'
                  aria-label="${isCurrent ? "Текущая версия" : "Сделать текущей"}"
                >
                  <img src="${escapeHtml(version.thumb_url || version.url || "")}" alt="Версия ${versionIndex + 1} для слайда ${slideIndex + 1}" />
                </button>
                <div class="slide-version-meta">
                  <span>${isCurrent ? "Текущая" : `Версия ${versionIndex + 1}`}</span>
                  <span class="meta">${escapeHtml(formatPlanDate(version.generated_at) || "сейчас")}</span>
                </div>
                <div class="actions-row slide-version-actions actions-grid-two">
                  ${version.url ? `<a class="secondary-button" href="${escapeHtml(version.url)}" target="_blank" rel="noopener">${actionLabel("download", "Скачать")}</a>` : ""}
                  ${isCurrent ? "" : `<button class="secondary-button" type="button" data-action="selectCarouselSlideVersion" data-args='${JSON.stringify([draftId, slideIndex, versionIndex, null])}'>${actionLabel("approve", "Сделать текущей")}</button>`}
                  ${items.length > 1 ? `<button class="secondary-button" type="button" data-action="deleteCarouselSlideVersion" data-args='${JSON.stringify([draftId, slideIndex, versionIndex, null])}'>${actionLabel("trash", "Удалить")}</button>` : ""}
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
  let _slidesViewMode = "swiper"; // "swiper" | "grid"
  let _swiperAbort = null; // AbortController for touch listeners

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
    // Abort previous listeners to prevent stacking on re-render
    if (_swiperAbort) _swiperAbort.abort();
    _swiperAbort = new AbortController();
    const signal = _swiperAbort.signal;
    // Sync transform & dots with current _swiperIndex — it may have changed
    // between renderSlides (which read idx) and this rAF callback (e.g. if a
    // touchend on a detached track updated _swiperIndex in between).
    const safeIndex = Math.min(_swiperIndex, total - 1);
    if (safeIndex !== _swiperIndex) _swiperIndex = safeIndex;
    track.style.transform = `translateX(-${_swiperIndex * 100}%)`;
    document.querySelectorAll(".slides-dot").forEach((dot, i) => {
      dot.classList.toggle("is-active", i === _swiperIndex);
    });
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
    }, { passive: true, signal });

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
    }, { passive: true, signal });

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
    }, { passive: true, signal });
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

    const isGrid = _slidesViewMode === "grid";
    const viewToggle = `
      <div class="slides-view-toggle">
        <button class="slides-view-btn${!isGrid ? " is-active" : ""}" type="button" data-action="setSlidesViewMode" data-args='["swiper"]'>${uiIcon("list")} Лента</button>
        <button class="slides-view-btn${isGrid ? " is-active" : ""}" type="button" data-action="setSlidesViewMode" data-args='["grid"]'>${uiIcon("grid")} Сетка</button>
      </div>
    `;

    if (draftId !== _swiperDraftId) { _swiperIndex = 0; _swiperDraftId = draftId; }
    const idx = Math.min(_swiperIndex, slideItems.length - 1);

    const dotsHtml = slideItems.map((_, i) =>
      `<button class="slides-dot${i === idx ? " is-active" : ""}" type="button" data-action="carouselSwiperGoTo" data-args='${JSON.stringify([i])}' aria-label="Слайд ${i + 1}"></button>`
    ).join("");

    const slidesHtml = slideItems.map((slide, index) => {
      const img = imageItems[index];
      const prompt = String(promptItems[index] || "");
      const note = bufferedCarouselNote(draftId, index, String(noteItems[index] || ""));
      const versions = Array.isArray(versionItems[index]) ? versionItems[index] : [];
      const genFailed = !img?.url && state.selected?.generation_stage === "error" && !state.selected?.generation_pending;
      const slideOp = carouselSlideOperation(draftId, index);
      const _slideSrc = img?.thumb_url || img?.url;
      const imgHtml = slideOp && img?.url
        ? `<div class="carousel-slide-image-wrap carousel-slide-regenerating"><img src="${escapeHtml(_slideSrc)}" data-full="${escapeHtml(img.url)}" alt="Слайд ${index + 1}" class="progressive-carousel-img" /><div class="carousel-slide-loading-overlay"><span class="button-spinner" aria-hidden="true"></span></div></div>`
        : img?.url
        ? `<div class="carousel-slide-image-wrap"><img src="${escapeHtml(_slideSrc)}" data-full="${escapeHtml(img.url)}" alt="Слайд ${index + 1}" class="progressive-carousel-img" style="cursor:pointer" data-action="openImageFullscreen" data-args='${JSON.stringify([img.url, `Слайд ${index + 1}`])}' /></div>`
        : genFailed
          ? `<div class="carousel-slide-image-wrap"><div class="frame-loading"><div class="frame-loading-inner"><i class="ph ph-warning"></i><span>Не удалось сгенерировать картинку. Нажмите «Новый вариант» чтобы попробовать снова.</span></div></div></div>`
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
            <button class="primary-button" type="button" aria-label="Сохранить текст слайда" data-action="saveCarouselSlideText" data-args='${JSON.stringify([draftId, index, null])}'>${actionLabel("text", "Сохранить подпись")}</button>
            <button class="secondary-button" type="button" ${!img?.url ? "disabled" : ""} data-action="previewCarouselSlide" data-args='${JSON.stringify([draftId, index, null])}'>${actionLabel("eye", "Предпросмотр")}</button>
          </div>
          <div class="actions-row prompt-actions actions-grid-two">
            ${img?.url ? `<a class="secondary-button" href="${escapeHtml(img.url)}" target="_blank" rel="noopener">${actionLabel("download", "Скачать")}</a>` : `<span class="secondary-button" disabled>${actionLabel("download", "Скачать")}</span>`}
            <label class="secondary-button upload-slide-label">${actionLabel("upload", "Загрузить")}<input type="file" accept="image/jpeg,image/png,image/webp" style="position:absolute;width:1px;height:1px;opacity:0;overflow:hidden" data-on-change="uploadSlideImageFromInput" data-args='${JSON.stringify([draftId, index])}' /></label>
          </div>
          ${prompt ? (() => {
              const discOpen = isPromptDisclosureOpen(`carousel:${draftId}:${index}`, !img?.url);
              return `
            <div class="prompt-disclosure${discOpen ? " is-open" : ""}" data-prompt-key="${escapeHtml(`carousel:${draftId}:${index}`)}">
              <button class="secondary-button prompt-toggle" type="button" aria-expanded="${discOpen ? "true" : "false"}" data-default-open="${!img?.url ? "true" : "false"}" data-open-label="Показать промпт" data-close-label="Скрыть промпт" data-action="togglePromptDisclosure" data-args='${JSON.stringify([`carousel:${draftId}:${index}`, null])}'>${actionLabel(discOpen ? "chevron-up" : "chevron-down", discOpen ? "Скрыть промпт" : "Показать промпт")}</button>
              <div class="prompt-card"${discOpen ? "" : " hidden"}>
                <div class="detail-preview prompt-preview">${escapeHtml(prompt)}</div>
                <label class="prompt-note-field">
                  <span>Замечание к картинке</span>
                  <textarea id="${slideNoteId(index)}" placeholder="Например: теплее свет, крупнее объект, меньше деталей на фоне" data-on-input="handleCarouselSlideNoteInput" data-args='${JSON.stringify([draftId, index])}'>${escapeHtml(note)}</textarea>
                </label>
                <div class="actions-row prompt-actions actions-grid-two">
                  <button class="secondary-button" type="button" data-action="copyText" data-args='${JSON.stringify([prompt])}'>${actionLabel("copy", "Скопировать промпт слайда")}</button>
                  <button class="secondary-button" type="button" data-action="regenerateCarouselSlide" data-args='${JSON.stringify([draftId, index, null])}'>${actionLabel("regenerate", "Обновить изображение")}</button>
                  <button class="primary-button" type="button" data-action="regenerateCarouselSlide" data-args='${JSON.stringify([draftId, index, null])}'>${actionLabel("note", "Обновить по замечанию")}</button>
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
      if (el) {
        initSwiper(el, total, dId);
        // Broken image fallback via delegation (Task 29)
        el.addEventListener("error", (e) => {
          if (e.target.tagName === "IMG") e.target.classList.add("is-broken");
        }, true);
      }
    });

    // Avatar warning banner
    const draft = state.selected;
    const hasAvatar = Boolean(draft?.has_avatar || draft?.payload?.brand_avatar_path);
    const layoutStyle = draft?.payload?.layout_style || "overlay";
    const avatarBanner = (!hasAvatar && layoutStyle === "editorial")
      ? `<div class="avatar-missing-banner">
           <div class="avatar-missing-text">${uiIcon("alert-circle")}<span>Аватарка не загружена — на слайдах будет заглушка</span></div>
           <button class="secondary-button avatar-missing-btn" type="button" data-action="openSettingsSection" data-args='["team"]'>${uiIcon("upload")}<span>Загрузить в настройках</span></button>
         </div>`
      : "";

    // Divider style picker (editorial only)
    const currentDivider = draft?.payload?.divider_style || "divider_06_arrow_line";
    const dividerPicker = layoutStyle === "editorial" ? `
      <div class="divider-picker">
        <label class="divider-picker-label">${uiIcon("sparkles")}<span>Разделитель</span></label>
        <div class="divider-picker-grid">
          ${[
            ["divider_01_pike_thick", "Толстые пики"],
            ["divider_02_pike_thin", "Тонкие пики"],
            ["divider_03_wave", "Волна"],
            ["divider_04_wave_sharp", "Острая волна"],
            ["divider_05_bold", "Жирный"],
            ["divider_06_arrow_line", "Стрелки"],
            ["divider_07_medium", "Средний"],
            ["divider_08_tall", "Высокий"],
            ["divider_09_round", "Круглый"],
            ["divider_10_rounder", "Закруглённый"],
            ["divider_11_line_dots", "Линия+точки"],
            ["divider_12_asymm", "Асимметрия"],
          ].map(([id, label]) => `
            <button class="divider-option${id === currentDivider ? " is-active" : ""}" type="button"
              data-action="setDividerStyle" data-args='${JSON.stringify([draftId, id])}'
              title="${escapeHtml(label)}">
              <img src="/assets/carousel_dividers/${id}.png" alt="${escapeHtml(label)}" />
            </button>
          `).join("")}
        </div>
      </div>` : "";

    return `
      <section class="section">
        <h3>${uiIcon("slides")}${header}</h3>
        ${avatarBanner}
        ${dividerPicker}
        ${viewToggle}
        <div class="slides-swiper${isGrid ? " slides-grid" : ""}">
          <div class="slides-swiper-track${isGrid ? " slides-grid-track" : ""}" style="${isGrid ? "" : `transform:translateX(-${idx * 100}%)`}">
            ${slidesHtml}
          </div>
        </div>
        ${isGrid ? "" : `<div class="slides-dots">${dotsHtml}</div>`}
      </section>
    `;
  }

  function setSlidesViewMode(mode) {
    _slidesViewMode = mode === "grid" ? "grid" : "swiper";
    if (state.selected?.draft_id && isCurrentDraftDetail(state.selected.draft_id)) {
      renderDraftDetail(state.selected);
    }
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
      // Auto-refresh preview in background
      _refreshSlidePreview(draftId, slideIndex);
    };
    if (button instanceof HTMLElement) {
      await withButtonFeedback(button, "Сохраняю...", apply, "Сохранено");
      return;
    }
    await apply();
  }

  /** Fetch fresh preview PNG and update the slide image in-place. */
  async function _refreshSlidePreview(draftId, slideIndex) {
    try {
      setCarouselSlideOperation(draftId, slideIndex, "Обновляю превью…");
      // Show loading overlay on current slide without full re-render to avoid
      // destroying the swiper track and causing slide-skip on next swipe.
      const slideArticles = document.querySelectorAll(".slides-swiper-track > .slide");
      const slideEl = slideArticles[slideIndex];
      if (slideEl) {
        const wrap = slideEl.querySelector(".carousel-slide-image-wrap");
        if (wrap && !wrap.querySelector(".carousel-slide-loading-overlay")) {
          wrap.classList.add("carousel-slide-regenerating");
          const overlay = document.createElement("div");
          overlay.className = "carousel-slide-loading-overlay";
          overlay.innerHTML = '<span class="button-spinner" aria-hidden="true"></span>';
          wrap.appendChild(overlay);
        }
      }

      const previewUrl = `/api/carousel/${draftId}/slides/${slideIndex}/preview${authQueryString()}`;
      const resp = await fetch(previewUrl, {
        headers: deps.initDataHeaders ? deps.initDataHeaders() : {},
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      // Use data URL for Telegram WebApp compatibility
      const reader = new FileReader();
      const dataUrl = await new Promise((resolve, reject) => {
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });

      // Update slide_images in state so the new image persists across re-renders
      const current = state.selected;
      if (current && current.draft_id === draftId) {
        const imgs = current.payload?.slide_images || [];
        if (imgs[slideIndex]) {
          imgs[slideIndex] = { ...imgs[slideIndex], url: dataUrl };
        }
      }
    } catch (err) {
      // Preview refresh is best-effort — don't block the user
      console.warn("Auto-refresh preview failed:", err);
    } finally {
      setCarouselSlideOperation(draftId, slideIndex, "");
      const draft = state.selected;
      if (isCurrentDraftDetail(draftId) && draft) renderDraftDetail(draft);
    }
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
      // Mark all slides as pending before sending request
      const currentPayload = state.selected?.payload || {};
      const slideCount = (currentPayload.slides || currentPayload.img_prompts || []).length;
      for (let i = 0; i < slideCount; i++) {
        setCarouselSlideOperation(draftId, i, "Перегенерирую картинку…");
      }
      if (isCurrentDraftDetail(draftId) && state.selected) renderDraftDetail(state.selected);

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
      // Clear slide operations on error
      const currentPayload = state.selected?.payload || {};
      const slideCount = (currentPayload.slides || currentPayload.img_prompts || []).length;
      for (let i = 0; i < slideCount; i++) {
        setCarouselSlideOperation(draftId, i, "");
      }
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
    document.body.style.overflow = "hidden";
    const cleanup = () => {
      document.body.style.overflow = "";
      if (imageUrl.startsWith("blob:")) URL.revokeObjectURL(imageUrl);
      modal.remove();
    };
    modal.querySelector(".preview-modal-close").addEventListener("click", cleanup);
    // Tap anywhere except the image itself to close
    modal.addEventListener("click", (e) => {
      if (e.target.tagName !== "IMG") cleanup();
    });
  }

  async function previewCarouselSlide(draftId, slideIndex, button) {
    // If Canva-imported, show the image directly (it already has text from Canva)
    const draft = state.selected;
    if (draft?.payload?.canva_design_id) {
      const imgs = draft.payload.slide_images || [];
      const img = imgs[slideIndex];
      if (img?.url) {
        showPreviewModal(img.url, `Слайд ${slideIndex + 1} — Canva`);
        return;
      }
    }
    try {
      await withButtonFeedback(button, "Генерирую...", async () => {
        const qs = await sseQueryString();
        const previewUrl = `/api/carousel/${draftId}/slides/${slideIndex}/preview${qs}`;
        const resp = await fetch(previewUrl, {
          headers: deps.initDataHeaders ? deps.initDataHeaders() : {},
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        // Use data URL instead of blob URL for Telegram WebApp compatibility
        const reader = new FileReader();
        const dataUrl = await new Promise((resolve, reject) => {
          reader.onload = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
        showPreviewModal(dataUrl, `Слайд ${slideIndex + 1} — предпросмотр`);
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
    const qs = await sseQueryString();
    const downloadUrl = `${window.location.origin}/api/carousel/${draftId}/pptx${qs}`;
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

  async function exportToCanva(draftId, button) {
    await withButtonFeedback(button, "Экспорт в Canva…", async () => {
      const resp = await fetchJson(`/api/carousel/${draftId}/canva/export`, {
        method: "POST",
        body: "{}",
        timeout: 30000,
      });
      if (resp?.task_id) {
        showUiNotice("Экспорт в Canva запущен…", "info");
        _startCanvaTaskPoll(draftId, "canva_export");
      } else if (resp?.edit_url) {
        // Fallback for direct response (shouldn't happen but safe)
        _openCanvaUrl(resp.edit_url);
      }
    }, "Экспорт запущен");
  }

  async function importFromCanva(draftId, button) {
    try {
      await withButtonFeedback(button, "Загрузка…", async () => {
        const data = await fetchJson(`/api/carousel/${draftId}/canva/designs`);
        const designs = data?.designs || [];

        if (!designs.length) {
          showUiNotice("В Canva нет дизайнов для импорта", "error");
          return;
        }

        // Show design picker modal
        _showCanvaDesignPicker(draftId, designs);
      }, "Canva");
    } catch (error) {
      showRequestError("Не удалось загрузить дизайны из Canva", error);
    }
  }

  function _showCanvaDesignPicker(draftId, designs) {
    const existing = document.getElementById("canvaDesignPicker");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "canvaDesignPicker";
    modal.className = "preview-modal-backdrop";

    const designItems = designs.map((d) => `
      <button class="canva-design-item" type="button" data-action="selectCanvaDesign" data-args='${JSON.stringify([draftId, d.design_id, null])}'>
        ${d.thumbnail_url ? `<img src="${escapeHtml(d.thumbnail_url)}" alt="${escapeHtml(d.title)}" class="canva-design-thumb" />` : `<div class="canva-design-thumb canva-design-thumb--empty">${uiIcon("image")}</div>`}
        <span class="canva-design-title">${escapeHtml(d.title || "Без названия")}</span>
      </button>
    `).join("");

    modal.innerHTML = `
      <div class="preview-modal" role="dialog" aria-modal="true" aria-label="Выберите дизайн из Canva">
        <div class="preview-modal-header">
          <h3>Импорт из Canva</h3>
          <button class="secondary-button preview-modal-close" type="button">${uiIcon("x")}</button>
        </div>
        <p class="canva-picker-hint">Нажмите на дизайн для импорта</p>
        <div class="preview-modal-body canva-design-grid">
          ${designItems}
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    document.body.style.overflow = "hidden";

    const cleanup = () => { document.body.style.overflow = ""; modal.remove(); };
    modal.querySelector(".preview-modal-close").addEventListener("click", cleanup);
    modal.addEventListener("click", (e) => { if (e.target === modal) cleanup(); });
  }

  async function selectCanvaDesign(draftId, designId, button) {
    const modal = document.getElementById("canvaDesignPicker");
    if (modal) { document.body.style.overflow = ""; modal.remove(); }
    showUiNotice("Импорт из Canva запущен…", "info");
    try {
      const resp = await fetchJson(`/api/carousel/${draftId}/canva/import`, {
        method: "POST",
        body: JSON.stringify({ design_id: designId }),
        timeout: 30000,
      });
      if (resp?.task_id) {
        _startCanvaTaskPoll(draftId, "canva_import");
      }
    } catch (error) {
      showRequestError("Не удалось запустить импорт из Canva", error);
    }
  }

  /* ── Canva background task polling (SSE + fallback) ─────────────── */

  let _canvaEventSource = null;
  let _canvaPollTimer = null;

  function _openCanvaUrl(url) {
    const tg = window.Telegram?.WebApp;
    if (tg?.openLink) {
      tg.openLink(url);
    } else {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  }

  async function _startCanvaTaskPoll(draftId, taskType) {
    _stopCanvaPoll();

    if (typeof EventSource !== "undefined") {
      const qs = await sseQueryString();
      const es = new EventSource(`/api/carousel/${draftId}/canva/stream${qs}`);
      _canvaEventSource = es;
      es.onmessage = (event) => {
        const st = JSON.parse(event.data);
        if (st.status === "completed" || st.status === "failed") {
          es.close();
          _canvaEventSource = null;
          _onCanvaTaskDone(draftId, taskType, st);
        }
      };
      es.onerror = () => {
        es.close();
        _canvaEventSource = null;
        _fallbackCanvaPoll(draftId, taskType);
      };
    } else {
      _fallbackCanvaPoll(draftId, taskType);
    }
  }

  function _fallbackCanvaPoll(draftId, taskType) {
    _canvaPollTimer = setInterval(async () => {
      try {
        const st = await fetchJson(`/api/carousel/${draftId}/canva/task-status`);
        if (st.status === "completed" || st.status === "failed") {
          _stopCanvaPoll();
          _onCanvaTaskDone(draftId, taskType, st);
        }
      } catch (_) { /* retry on next interval */ }
    }, 2000);
  }

  function _stopCanvaPoll() {
    if (_canvaPollTimer) { clearInterval(_canvaPollTimer); _canvaPollTimer = null; }
    if (_canvaEventSource) { _canvaEventSource.close(); _canvaEventSource = null; }
  }

  async function _onCanvaTaskDone(draftId, taskType, st) {
    if (st.status === "failed") {
      showUiNotice(`Canva ${taskType === "canva_export" ? "экспорт" : "импорт"} не удался: ${st.error || "неизвестная ошибка"}`, "error");
      return;
    }

    if (taskType === "canva_export" && st.result?.edit_url) {
      showUiNotice("Дизайн создан в Canva. Открываю редактор…", "success");
      _openCanvaUrl(st.result.edit_url);
    } else if (taskType === "canva_import") {
      try {
        const draft = await fetchJson(`/api/carousel/${draftId}`);
        mergeDraftIntoState(draft);
        renderDraftList();
        if (isCurrentDraftDetail(draft.draft_id)) {
          renderDraftDetail(draft);
          requestAnimationFrame(() => {
            const slidesSection = document.querySelector(".slides-swiper");
            if (slidesSection) slidesSection.scrollIntoView({ behavior: "smooth", block: "start" });
          });
        }
        const readyCount = (draft.payload?.slide_images || []).filter(Boolean).length;
        showUiNotice(`Импорт из Canva завершён: ${readyCount} слайдов`, "success");
      } catch (error) {
        showRequestError("Импорт завершён, но не удалось обновить UI", error);
      }
    }
  }

  async function downloadSlideImage(url, slideIndex, button) {
    if (!url) { showUiNotice("Картинка ещё не готова", "error"); return; }
    if (button instanceof HTMLElement) button.textContent = "Скачиваю...";
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `slide_${(slideIndex || 0) + 1}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
      showUiNotice("Скачано", "success");
    } catch (err) {
      // Fallback: open externally
      const fullUrl = `${window.location.origin}${url}`;
      const tg = window.Telegram?.WebApp;
      if (tg?.openLink) tg.openLink(fullUrl);
      else window.open(fullUrl, "_blank");
    }
    if (button instanceof HTMLElement) button.textContent = "Скачать";
  }

  async function uploadSlideImage(draftId, slideIndex, button) {
    showUiNotice(`Загрузка для слайда ${slideIndex + 1}...`, "info");
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/jpeg,image/png,image/webp";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      if (file.size > 10 * 1024 * 1024) {
        showUiNotice("Файл слишком большой (макс. 10 МБ)", "error");
        return;
      }
      showUiNotice("Загружаю картинку...", "info");
      if (button instanceof HTMLElement) button.textContent = "Загружаю...";
      const formData = new FormData();
      formData.append("file", file);
      try {
        const headers = {};
        const initData = window.Telegram?.WebApp?.initData;
        if (initData) headers["X-Telegram-Init-Data"] = initData;
        const resp = await fetch(`/api/carousel/${draftId}/slides/${slideIndex}/upload`, {
          method: "POST",
          headers,
          body: formData,
        });
        if (!resp.ok) {
          const body = await resp.text();
          throw new Error(`HTTP ${resp.status}: ${body}`);
        }
        const data = await resp.json();
        mergeDraftIntoState(data);
        if (isCurrentDraftDetail(draftId)) renderDraftDetail(state.selected);
        showUiNotice("Картинка загружена", "success");
      } catch (err) {
        showRequestError("Не удалось загрузить картинку", err);
        if (button instanceof HTMLElement) button.textContent = "Своя картинка";
      }
    };
    input.click();
  }

  async function uploadSlideImageFromInput(draftId, slideIndex, _value, inputEl) {
    const file = inputEl?.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      showUiNotice("Файл слишком большой (макс. 10 МБ)", "error");
      return;
    }
    showUiNotice("Загружаю картинку...", "info");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const headers = {};
      const initData = window.Telegram?.WebApp?.initData;
      if (initData) headers["X-Telegram-Init-Data"] = initData;
      const resp = await fetch(`/api/carousel/${draftId}/slides/${slideIndex}/upload`, {
        method: "POST",
        headers,
        body: formData,
      });
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${body}`);
      }
      const data = await resp.json();
      mergeDraftIntoState(data);
      if (isCurrentDraftDetail(draftId)) renderDraftDetail(state.selected);
      showUiNotice("Картинка загружена", "success");
    } catch (err) {
      showRequestError("Не удалось загрузить картинку", err);
    } finally {
      inputEl.value = "";
    }
  }

  async function setDividerStyle(draftId, style) {
    try {
      const data = await fetchJson(`/api/carousel/${draftId}/divider-style`, {
        method: "PATCH",
        body: JSON.stringify({ style }),
      });
      mergeDraftIntoState(data);
      if (isCurrentDraftDetail(draftId)) renderDraftDetail(state.selected);
    } catch (err) {
      showRequestError("Не удалось сменить разделитель", err);
    }
  }

  // ── Carousel Publish Screen ────────────────────────────────────────────

  const _PLATFORM_SVG = {
    threads: `<svg class="publish-platform-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M15 12a3 3 0 1 1-3-3c2 0 3.5 1 3.5 3s-1.5 3-3.5 3"/></svg>`,
    instagram: `<svg class="publish-platform-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>`,
    telegram: `<svg class="publish-platform-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
  };

  function _renderCarouselPublishScreen(d) {
    const p = d.payload || {};
    const caption = p.caption || "";
    const captionLen = caption.length;
    const slideImages = (p.slide_images || []).filter(Boolean);

    return `
      <div class="detail-grid">
        <button class="back-button visible" data-action="showCarouselPublishBack" data-args='${JSON.stringify([d.draft_id])}'>${uiIcon("back")}<span>Назад к карусели</span></button>

        <div class="detail-top detail-hero">
          <div class="detail-hero-copy">
            <p class="eyebrow"><i class="ph ph-images-square"></i><span>Карусель · Публикация</span></p>
            <h2 class="detail-title">${escapeHtml(d.topic)}</h2>
          </div>
        </div>

        <section class="section">
          <div class="section-heading">
            <h3><i class="ph ph-eye"></i> Превью слайдов</h3>
            <p>${slideImages.length} слайд${slideImages.length === 1 ? "" : slideImages.length < 5 ? "а" : "ов"}</p>
          </div>
          <div class="carousel-publish-thumbs">
            ${slideImages.map((img, i) => {
              const url = img?.thumb_url || img?.url || "";
              return `<div class="carousel-publish-thumb">
                <img src="${escapeHtml(url)}" alt="Слайд ${i + 1}" loading="lazy" />
                <span class="carousel-publish-thumb-num">${i + 1}</span>
              </div>`;
            }).join("")}
          </div>
        </section>

        <section class="section">
          <div class="section-heading">
            <h3><i class="ph ph-text-aa"></i> Описание поста</h3>
          </div>
          <textarea id="carouselPublishCaption" class="publish-caption-field" rows="5"
            placeholder="Напишите описание к посту…">${escapeHtml(caption)}</textarea>
          <div class="caption-counter ${captionLen > 2200 ? "caption-counter--warn" : ""}" id="captionCounter">
            ${captionLen} / 2200
          </div>
          <div class="actions-row" style="margin-top:8px">
            <button class="secondary-button" type="button"
              data-action="saveCarouselCaption" data-args='${JSON.stringify([d.draft_id, null])}'>
              <i class="ph ph-floppy-disk"></i> Сохранить
            </button>
            <button class="secondary-button" type="button"
              data-action="regenCarouselCaption" data-args='${JSON.stringify([d.draft_id, null])}'>
              <i class="ph ph-sparkle"></i> Сгенерировать AI
            </button>
          </div>
        </section>

        <section class="section">
          <div class="section-heading">
            <h3><i class="ph ph-share-network"></i> Платформы</h3>
          </div>
          <div class="publish-platforms">
            <label class="publish-platform-toggle">
              <input type="checkbox" name="carouselPubPlatform" value="instagram" checked>
              ${_PLATFORM_SVG.instagram}<span>Instagram</span>
            </label>
            <label class="publish-platform-toggle">
              <input type="checkbox" name="carouselPubPlatform" value="threads">
              ${_PLATFORM_SVG.threads}<span>Threads</span>
            </label>
            <label class="publish-platform-toggle">
              <input type="checkbox" name="carouselPubPlatform" value="telegram">
              ${_PLATFORM_SVG.telegram}<span>Telegram</span>
            </label>
          </div>
        </section>

        <section class="section">
          <div class="section-heading">
            <h3><i class="ph ph-calendar"></i> Расписание</h3>
          </div>
          <div class="publish-schedule-row">
            <label class="publish-schedule-label"><span>Запланировать на</span>
              <input type="datetime-local" id="carouselPubScheduleAt" class="publish-datetime">
            </label>
          </div>
          <p class="field-help">Оставьте пустым для немедленной публикации.</p>
        </section>

        <section class="section">
          <div class="actions-row">
            <button class="primary-button" type="button"
              data-action="publishCarousel" data-args='${JSON.stringify([d.draft_id, false, null])}'>
              <i class="ph ph-paper-plane-tilt"></i> Опубликовать сейчас
            </button>
            <button class="secondary-button" type="button"
              data-action="publishCarousel" data-args='${JSON.stringify([d.draft_id, true, null])}'>
              <i class="ph ph-calendar-check"></i> Запланировать
            </button>
          </div>
          <div id="publishStatusContainer"></div>
        </section>
      </div>
    `;
  }

  async function showCarouselPublishScreen(draftId) {
    const container = document.getElementById("draftDetail");
    if (!container) return;
    try {
      const draft = await fetchJson(`/api/carousel/${draftId}`);
      mergeDraftIntoState(draft);
      container.innerHTML = _renderCarouselPublishScreen(draft);
      // Live caption counter
      const textarea = document.getElementById("carouselPublishCaption");
      const counter = document.getElementById("captionCounter");
      if (textarea && counter) {
        textarea.addEventListener("input", () => {
          const len = textarea.value.length;
          counter.textContent = `${len} / 2200`;
          counter.classList.toggle("caption-counter--warn", len > 2200);
        });
      }
    } catch (err) {
      showRequestError("Не удалось открыть экран публикации", err);
    }
  }

  async function showCarouselPublishBack(draftId) {
    try {
      const draft = await fetchJson(`/api/carousel/${draftId}`);
      mergeDraftIntoState(draft);
      renderDraftDetail(draft);
    } catch (err) {
      showRequestError("Не удалось загрузить карусель", err);
    }
  }

  async function saveCarouselCaption(draftId, btn) {
    const caption = document.getElementById("carouselPublishCaption")?.value || "";
    await withButtonFeedback(btn, "Сохраняю…", async () => {
      await fetchJson(`/api/carousel/${draftId}/caption`, {
        method: "POST",
        body: JSON.stringify({ caption }),
      });
      showUiNotice("Описание сохранено", "success");
    }, "Сохранено");
  }

  async function regenCarouselCaption(draftId, btn) {
    await withButtonFeedback(btn, "Генерирую…", async () => {
      await fetchJson(`/api/carousel/${draftId}/regen-caption`, { method: "POST" });
      // Poll for generation completion
      const poll = setInterval(async () => {
        try {
          const draft = await fetchJson(`/api/carousel/${draftId}`);
          if (!draft.generation_pending) {
            clearInterval(poll);
            const caption = draft.payload?.caption || "";
            const textarea = document.getElementById("carouselPublishCaption");
            if (textarea) textarea.value = caption;
            const counter = document.getElementById("captionCounter");
            if (counter) {
              counter.textContent = `${caption.length} / 2200`;
              counter.classList.toggle("caption-counter--warn", caption.length > 2200);
            }
            showUiNotice("Описание сгенерировано", "success");
          }
        } catch (_) { clearInterval(poll); }
      }, 2000);
      setTimeout(() => clearInterval(poll), 30000);
    }, "Готово");
  }

  async function publishCarousel(draftId, withSchedule, btn) {
    // Save caption first
    const caption = document.getElementById("carouselPublishCaption")?.value || "";
    await fetchJson(`/api/carousel/${draftId}/caption`, {
      method: "POST",
      body: JSON.stringify({ caption }),
    });

    const checkboxes = document.querySelectorAll("input[name='carouselPubPlatform']:checked");
    const platforms = Array.from(checkboxes).map((cb) => cb.value);
    if (!platforms.length) {
      showUiNotice("Выберите хотя бы одну платформу", "error");
      return;
    }

    const body = { platforms };
    if (withSchedule) {
      const dt = document.getElementById("carouselPubScheduleAt")?.value;
      if (!dt) {
        showUiNotice("Укажите дату и время", "error");
        return;
      }
      body.scheduled_at = new Date(dt).toISOString();
    } else {
      const ok = confirm("Опубликовать карусель сейчас?");
      if (!ok) return;
    }

    await withButtonFeedback(btn, withSchedule ? "Планирую…" : "Публикую…", async () => {
      await fetchJson(`/api/drafts/${draftId}/publish`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const draft = await fetchJson(`/api/carousel/${draftId}`);
      mergeDraftIntoState(draft);
      // Re-render publish screen with status
      const container = document.getElementById("draftDetail");
      if (container) container.innerHTML = _renderCarouselPublishScreen(draft);
      // Start SSE status poll
      _startCarouselPublishPoll(draftId);
    }, withSchedule ? "Запланировано" : "Отправлено");
  }

  let _carouselPublishEs = null;

  async function _startCarouselPublishPoll(draftId) {
    if (_carouselPublishEs) { _carouselPublishEs.close(); _carouselPublishEs = null; }
    if (typeof EventSource !== "undefined") {
      const qs = await sseQueryString();
      const es = new EventSource(`/api/drafts/${draftId}/publish-stream${qs}`);
      _carouselPublishEs = es;
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          _renderCarouselPublishStatus(data.logs || []);
          if (data.error === "not_found" || data.done) {
            es.close();
            _carouselPublishEs = null;
          }
        } catch (_) { /* ignore */ }
      };
      es.onerror = () => { es.close(); _carouselPublishEs = null; };
    }
  }

  function _renderCarouselPublishStatus(logs) {
    const container = document.getElementById("publishStatusContainer");
    if (!container || !logs.length) return;
    const STATUS_TEXT = { success: "Опубликовано", failed: "Ошибка", pending: "В процессе…" };
    container.innerHTML = `
      <div class="publish-status-list">
        ${logs.map((l) => `
          <div class="publish-status-item publish-status-${l.status}">
            <span class="publish-status-platform">${_PLATFORM_SVG[l.platform] || escapeHtml(l.platform)}</span>
            <span class="publish-status-action">${escapeHtml(l.action || "")}</span>
            <span class="publish-status-badge publish-status-badge--${l.status}">${STATUS_TEXT[l.status] || l.status}</span>
            ${l.error_message ? `<span class="publish-status-error">${escapeHtml(l.error_message)}</span>` : ""}
          </div>
        `).join("")}
      </div>
    `;
  }

  return {
    slideNoteId,
    slideTextId,
    bufferedCarouselNote,
    carouselSlideOperation,
    setCarouselSlideOperation,
    hasPendingCarouselOperations,
    clearAllCarouselOperations,
    renderSlides,
    setSlidesViewMode,
    downloadSlideImage,
    uploadSlideImage,
    uploadSlideImageFromInput,
    setDividerStyle,
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
    exportToCanva,
    importFromCanva,
    selectCanvaDesign,
    showCarouselPublishScreen,
    showCarouselPublishBack,
    saveCarouselCaption,
    regenCarouselCaption,
    publishCarousel,
  };
}
