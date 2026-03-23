/**
 * Stock Photo Picker module — search Unsplash/Pexels, select, upload, or AI fallback.
 */
export function createStockPhotosModule(deps) {
  const {
    escapeHtml,
    uiIcon,
    fetchJson,
    withButtonFeedback,
    showUiNotice,
    showRequestError,
    mergeDraftIntoState,
    initDataHeaders,
  } = deps;

  // Cache search results per draft to avoid re-fetching on re-render
  const _searchCache = new Map();

  // ── Render ────────────────────────────────────────────────────────────

  /**
   * Render the stock photo picker section for a draft.
   * @param {string} draftId
   * @param {string[]} keywords - stock_keywords from payload
   * @param {object|null} currentImage - payload.image (selected photo)
   * @param {object[]} suggestions - payload.stock_suggestions (pre-searched)
   * @param {number} slideIndex - -1 for main image, 0+ for carousel slide
   * @returns {string} HTML
   */
  function renderPhotoPickerSection(draftId, keywords, currentImage, suggestions, slideIndex = -1) {
    if (!keywords || !keywords.length) return "";

    const sectionId = slideIndex >= 0 ? `stockPhotos_${draftId}_${slideIndex}` : `stockPhotos_${draftId}`;
    const keywordsStr = keywords.join(", ");
    const cacheKey = `${draftId}:${slideIndex}`;
    const cached = _searchCache.get(cacheKey);
    const photos = cached || suggestions || [];

    const currentHtml = currentImage && currentImage.url
      ? `<div class="stock-photo-current">
           <img src="${escapeHtml(currentImage.url)}" alt="Выбранное фото" loading="lazy">
           ${currentImage.attribution ? `<span class="stock-photo-attr">${escapeHtml(currentImage.attribution)}</span>` : ""}
         </div>`
      : "";

    const gridHtml = photos.length
      ? `<div class="stock-photo-grid" id="${sectionId}_grid">
           ${photos.map((p, i) => `
             <div class="stock-photo-cell" data-action="selectStockPhoto"
                  data-args='${JSON.stringify([draftId, i, slideIndex, null])}'>
               <img src="${escapeHtml(p.url_thumb || p.url_regular)}" alt="${escapeHtml(p.alt_text || "")}" loading="lazy">
               <span class="stock-photo-attribution">${escapeHtml(p.photographer || "")} · ${p.source || ""}</span>
             </div>
           `).join("")}
         </div>`
      : "";

    return `
      <section class="section section-primary" id="${sectionId}">
        <div class="section-heading">
          <h3>${uiIcon("image")}Фото для публикации</h3>
          <p>Выберите фото из стоков, загрузите своё или сгенерируйте с AI</p>
        </div>
        ${currentHtml}
        <div class="stock-keywords-row">
          ${keywords.map(k => `<span class="stock-keyword-chip">${escapeHtml(k)}</span>`).join("")}
        </div>
        <div class="stock-photo-actions">
          <button class="secondary-button" type="button" data-action="searchStockPhotos"
                  data-args='${JSON.stringify([draftId, keywordsStr, slideIndex, null])}'>
            ${uiIcon("search")}<span>Найти фото</span>
          </button>
          <button class="secondary-button" type="button" data-action="uploadDraftPhoto"
                  data-args='${JSON.stringify([draftId, slideIndex, null])}'>
            ${uiIcon("upload")}<span>Загрузить своё</span>
          </button>
        </div>
        ${gridHtml}
      </section>
    `;
  }

  // ── Actions ───────────────────────────────────────────────────────────

  async function searchStockPhotos(draftId, keywordsStr, slideIndex, _btn) {
    const btn = _btn || document.querySelector(`[data-action="searchStockPhotos"][data-args*="${draftId}"]`);
    const cacheKey = `${draftId}:${slideIndex}`;

    await withButtonFeedback(btn, "Ищу…", async () => {
      const resp = await fetchJson(
        `/api/stock-photos/search?keywords=${encodeURIComponent(keywordsStr)}&orientation=portrait`
      );
      if (!resp.photos || !resp.photos.length) {
        showUiNotice("Фото не найдены. Попробуйте изменить ключевые слова.", "warn");
        return;
      }
      _searchCache.set(cacheKey, resp.photos);

      // Render grid into the section
      const sectionId = slideIndex >= 0 ? `stockPhotos_${draftId}_${slideIndex}` : `stockPhotos_${draftId}`;
      const container = document.getElementById(sectionId);
      if (!container) return;

      const existing = container.querySelector(".stock-photo-grid");
      const gridHtml = `<div class="stock-photo-grid">
        ${resp.photos.map((p, i) => `
          <div class="stock-photo-cell" data-action="selectStockPhoto"
               data-args='${JSON.stringify([draftId, i, slideIndex, null])}'>
            <img src="${escapeHtml(p.url_thumb || p.url_regular)}" alt="${escapeHtml(p.alt_text || "")}" loading="lazy">
            <span class="stock-photo-attribution">${escapeHtml(p.photographer || "")} · ${p.source || ""}</span>
          </div>
        `).join("")}
      </div>`;

      if (existing) {
        existing.outerHTML = gridHtml;
      } else {
        container.insertAdjacentHTML("beforeend", gridHtml);
      }
    }, "Готово");
  }

  async function selectStockPhoto(draftId, photoIndex, slideIndex, _btn) {
    const cacheKey = `${draftId}:${slideIndex}`;
    const photos = _searchCache.get(cacheKey) || [];
    const photo = photos[photoIndex];
    if (!photo) return;

    // Highlight selected cell
    const cells = document.querySelectorAll(`#stockPhotos_${draftId}${slideIndex >= 0 ? "_" + slideIndex : ""} .stock-photo-cell`);
    cells.forEach((c, i) => c.classList.toggle("is-selected", i === photoIndex));

    const btn = cells[photoIndex];
    await withButtonFeedback(btn, null, async () => {
      const resp = await fetchJson("/api/stock-photos/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_id: draftId,
          photo_id: photo.id,
          source: photo.source,
          url: photo.url_regular || photo.url_full,
          photographer: photo.photographer,
          photographer_url: photo.photographer_url,
          slide_index: slideIndex,
        }),
      });
      if (resp.ok) {
        showUiNotice("Фото сохранено", "success");
        await mergeDraftIntoState(draftId);
      }
    });
  }

  async function uploadDraftPhoto(draftId, slideIndex, _btn) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/jpeg,image/png,image/webp";

    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;

      // Client-side quick checks
      if (file.size > 10 * 1024 * 1024) {
        showUiNotice("Файл слишком большой (макс. 10 МБ)", "error");
        return;
      }

      const btn = document.querySelector(`[data-action="uploadDraftPhoto"][data-args*="${draftId}"]`);
      await withButtonFeedback(btn, "Загружаю…", async () => {
        const formData = new FormData();
        formData.append("file", file);

        const headers = initDataHeaders ? initDataHeaders() : {};
        const resp = await fetch(
          `/api/drafts/${draftId}/upload-photo?slide_index=${slideIndex}`,
          { method: "POST", headers, body: formData }
        );
        const data = await resp.json();

        if (!data.ok) {
          const errors = (data.validation?.errors || []).join("\n");
          showUiNotice(errors || "Не удалось загрузить фото", "error");
          return;
        }

        // Show warnings if any
        const warnings = data.validation?.warnings || [];
        if (warnings.length) {
          showUiNotice(warnings.join("\n"), "warn");
        }

        showUiNotice("Фото загружено", "success");
        await mergeDraftIntoState(draftId);
      }, "Готово");
    });

    input.click();
  }

  // ── Public API ────────────────────────────────────────────────────────

  return {
    renderPhotoPickerSection,
    searchStockPhotos,
    selectStockPhoto,
    uploadDraftPhoto,
  };
}
