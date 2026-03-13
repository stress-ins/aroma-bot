export function createReferencesModule(deps) {
  const {
    state,
    elements,
    HANDBOOK_CATEGORY_META,
    escapeHtml,
    renderMarkdown,
    interactiveCardAttrs,
    renderBackButton,
    renderDetailLoader,
    renderGuidedState,
    handbookCategoryIcon,
    handbookCardBadge,
    aromaSection,
    fetchJson,
    enterDetailView,
    syncMobileNavigation,
    setEmptyState,
    conceptTypeMeta,
    formatCourseSourceLabel,
    tagMarkup,
    stripMarkdown,
  } = deps;

  function currentHandbookMeta() {
    return HANDBOOK_CATEGORY_META[state.tab] || HANDBOOK_CATEGORY_META.aromas;
  }

  async function loadReferenceAccess() {
    if (state.referenceAccess !== null) return state.referenceAccess;
    try {
      const payload = await fetchJson("/api/references/access");
      state.referenceAccess = Boolean(payload?.allowed);
      state.referenceAccessError = "";
    } catch (error) {
      const message = String(error?.message || "");
      if (message.includes("reference_access_denied") || message.includes("403 Forbidden")) {
        state.referenceAccess = false;
        state.referenceAccessError = "";
      } else {
        state.referenceAccess = null;
        state.referenceAccessError = message || "reference_temporarily_unavailable";
      }
    }
    return state.referenceAccess;
  }

  async function loadReferences(tabId = state.tab) {
    const meta = HANDBOOK_CATEGORY_META[tabId];
    if (!meta) return;
    if (state.referenceAccess === null) {
      await loadReferenceAccess();
    }
    if (state.referenceAccess === null) {
      renderReferencesUnavailable();
      return;
    }
    if (!state.referenceAccess) {
      renderReferencesLocked();
      return;
    }
    const data = await fetchJson(`/api/references/${meta.category}`);
    state.referenceItems = data.items || [];

    const selectedSlug = state.selectedReference?.category === meta.category
      ? state.selectedReference?.slug
      : "";

    if (selectedSlug) {
      await openReference(selectedSlug, tabId);
    } else {
      renderReferences();
    }
  }

  async function openReference(slug, tabId = state.tab) {
    const meta = HANDBOOK_CATEGORY_META[tabId];
    if (!slug || !meta) return;
    elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю карточку справочника")}`;
    enterDetailView();
    state.selectedReference = await fetchJson(`/api/references/${meta.category}/${encodeURIComponent(slug)}`);
    state.selectedReference.category = meta.category;
    state.tab = tabId;
    elements.tabsContainer.querySelectorAll(".tab-button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
    renderReferences();
    enterDetailView();
  }

  function renderReferencePassport(reference) {
    const parts = [
      reference.key ? `Ключ: ${reference.key}` : "",
      reference.botanical_family ? `Семейство / тип: ${reference.botanical_family}` : "",
      reference.origin_countries ? `Источник / традиция: ${reference.origin_countries}` : "",
      reference.extraction_method ? `Форма / метод: ${reference.extraction_method}` : "",
      reference.volatility ? `Длительность / летучесть: ${reference.volatility}` : "",
      reference.chakra_focus ? `Фокус / чакры: ${reference.chakra_focus}` : "",
      reference.polarity ? `Полярность: ${reference.polarity}` : "",
      reference.course_source ? `Источник курса: ${formatCourseSourceLabel(reference.course_source)}` : "",
    ].filter(Boolean);
    return parts.join("\n");
  }

  function renderReferenceImage(reference) {
    const heroClass = state.tab === "concepts" ? "reference-hero-card is-theory" : "reference-hero-card";
    const eyebrowLabel = state.tab === "concepts"
      ? `${handbookCategoryIcon(state.tab)}<span>${escapeHtml(currentHandbookMeta().title)} · учебный модуль</span>`
      : `${handbookCategoryIcon(state.tab)}<span>${escapeHtml(currentHandbookMeta().title)}</span>`;
    return `
      <section class="section aroma-hero ${heroClass}">
        <div class="reference-hero-copy">
          <p class="eyebrow">${eyebrowLabel}</p>
          <h2 class="detail-title">${escapeHtml(reference.name)}</h2>
          <p class="reference-keyline">${escapeHtml(reference.key || handbookCardBadge(state.tab, reference) || currentHandbookMeta().title)}</p>
          <p class="reference-summary">${escapeHtml(stripMarkdown(reference.description || reference.course_notes || ""))}</p>
        </div>
        <div class="reference-hero-media">
          <img class="aroma-image" src="${escapeHtml(reference.image_url)}" alt="${escapeHtml(reference.image_alt)}" />
          <div class="aroma-image-caption">${escapeHtml(reference.image_alt)}</div>
        </div>
      </section>
    `;
  }

  function renderReferences() {
    const meta = currentHandbookMeta();
    const items = state.referenceItems || [];
    const query = (state.referenceSearch || "").trim().toLowerCase();
    const filtered = items.filter((item) => `${item.name} ${item.description || ""} ${item.course_notes || ""}`.toLowerCase().includes(query));
    const reference = state.selectedReference;

    elements.listTitle.textContent = meta.title;
    elements.draftCount.textContent = query
      ? `Найдено ${filtered.length} из ${items.length}`
      : meta.count(items);

    setEmptyState(filtered.length > 0, meta.empty);

    let listContainer = document.getElementById("referenceListContainer");
    if (!listContainer) {
      elements.draftList.innerHTML = `
        <div class="aroma-search">
          <label>${escapeHtml(meta.searchLabel)}<input id="referenceSearchInput" type="search" placeholder="${escapeHtml(meta.searchPlaceholder)}" value="${escapeHtml(state.referenceSearch)}" /></label>
        </div>
        <div id="referenceListContainer" class="plans-list"></div>
      `;
      listContainer = document.getElementById("referenceListContainer");
      document.getElementById("referenceSearchInput")?.addEventListener("input", (e) => {
        state.referenceSearch = e.target.value;
        renderReferences();
      });
    } else {
      const searchInput = document.getElementById("referenceSearchInput");
      if (searchInput) {
        searchInput.placeholder = meta.searchPlaceholder;
        searchInput.value = state.referenceSearch;
        const label = searchInput.closest("label");
        if (label) {
          label.firstChild.textContent = meta.searchLabel;
        }
      }
    }

    listContainer.innerHTML = filtered.map((item) => `
      <article ${interactiveCardAttrs(`Открыть карточку ${item.name}`)} class="draft-card overview-card reference-card${state.tab === "concepts" ? " is-theory concept-card" : ""}${item.slug === reference?.slug ? " active" : ""} interactive-card" onclick="openReference('${item.slug}', '${state.tab}')">
        <div class="overview-card-top">
          <div class="draft-kind">${handbookCategoryIcon(state.tab)}${handbookCardBadge(state.tab, item) ? `<span>${state.tab === "concepts" ? `<span class="concept-kind-mark" aria-hidden="true">${escapeHtml(conceptTypeMeta(item.source_type).icon)}</span>` : ""}${escapeHtml(handbookCardBadge(state.tab, item))}</span>` : ""}</div>
          <span class="overview-card-date">${escapeHtml(formatCourseSourceLabel(item.course_source) || meta.title)}</span>
        </div>
        <h3 class="draft-topic">${escapeHtml(item.name)}</h3>
        <div class="draft-preview">${escapeHtml(stripMarkdown(item.description || item.course_notes || ""))}</div>
        <div class="draft-meta overview-card-footer">
          ${item.chakra_focus ? tagMarkup(item.chakra_focus, "source") : ""}
          ${item.polarity ? tagMarkup(item.polarity, "feedback") : ""}
        </div>
      </article>
    `).join("");

    if (!reference) {
      elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({
        eyebrow: meta.title,
        title: `Откройте ${meta.label} из списка`,
        body: meta.selectPrompt,
      })}</div>`;
      syncMobileNavigation();
      return;
    }

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        ${renderReferenceImage(reference)}
        ${aromaSection("Паспорт карточки", renderReferencePassport(reference))}
        ${aromaSection("Описание", reference.description)}
        ${aromaSection("Психологические свойства", reference.psychological_properties)}
        ${aromaSection('Ресурс "+"', reference.resource_values?.plus)}
        ${aromaSection('Ресурс "-"', reference.resource_values?.minus)}
        ${aromaSection("Какие вопросы поднимает", reference.questions)}
        ${aromaSection("Действие на НПС", reference.nps_effect)}
        ${aromaSection("Терапевтические свойства", reference.therapeutic_properties)}
        ${aromaSection("Материалы курса", reference.course_notes)}
        ${aromaSection("Исторические сведения", reference.history)}
      </div>
    `;
    syncMobileNavigation();
  }

  function renderReferencesLocked() {
    const meta = currentHandbookMeta();
    elements.listTitle.textContent = meta.title;
    elements.draftCount.textContent = "";
    setEmptyState(true);
    elements.draftList.innerHTML = renderGuidedState({
      eyebrow: meta.title,
      title: "Доступ пока закрыт",
      body: meta.locked,
    });
    elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({
      eyebrow: meta.title,
      title: "Доступ пока закрыт",
      body: meta.locked,
    })}</div>`;
    syncMobileNavigation();
  }

  function renderReferencesUnavailable() {
    const meta = currentHandbookMeta();
    const message = "Справочник временно недоступен. Попробуйте открыть раздел ещё раз.";
    elements.listTitle.textContent = meta.title;
    elements.draftCount.textContent = "";
    setEmptyState(true);
    elements.draftList.innerHTML = renderGuidedState({
      eyebrow: meta.title,
      title: "Не удалось открыть справочник",
      body: message,
      actionLabel: "Повторить",
      action: "retryCurrentTab()",
    });
    elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({
      eyebrow: meta.title,
      title: "Не удалось открыть справочник",
      body: message,
      actionLabel: "Повторить",
      action: "retryCurrentTab()",
    })}</div>`;
    syncMobileNavigation();
  }

  async function openAroma(slug) {
    if (!slug) return;
    await openReference(slug, "aromas");
  }

  function renderAromas() {
    renderReferences();
  }

  function renderAromasLocked() {
    renderReferencesLocked();
  }

  return {
    currentHandbookMeta,
    loadReferenceAccess,
    loadReferences,
    openReference,
    renderReferences,
    renderReferencesLocked,
    renderReferencesUnavailable,
    openAroma,
    renderAromas,
    renderAromasLocked,
  };
}
