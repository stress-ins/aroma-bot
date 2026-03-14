const REFERENCE_SOURCE_TYPE_LABELS = {
  citrus:  "Цитрусовые",
  herb:    "Травяные",
  flower:  "Цветочные",
  tree:    "Древесные",
  resin:   "Смолистые",
  spice:   "Пряные",
  grass:   "Злаковые",
  root:    "Корневые",
  wood:    "Деревянистые",
};

export function createReferencesModule(deps) {
  let openReferenceInFlight = false;
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
    aromaCardIcon,
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
    SOURCE_TYPE_ICONS,
    SYMPTOM_CATEGORY_ICONS,
    CONCEPT_TYPE_ICONS,
    PRACTICE_TYPE_ICONS,
    PRACTICE_RU_LABELS,
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

    // Skip rendering if openReference is currently in flight — it will call
    // renderReferences itself when the detail fetch completes, preventing a
    // race condition where the list load overwrites the detail with empty state.
    if (openReferenceInFlight) return;

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
    openReferenceInFlight = true;
    try {
      state.selectedReference = await fetchJson(`/api/references/${meta.category}/${encodeURIComponent(slug)}`);
      state.selectedReference.category = meta.category;
      state.tab = tabId;
      elements.tabsContainer.querySelectorAll(".tab-button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
      renderReferences();
      enterDetailView();
    } finally {
      openReferenceInFlight = false;
    }
  }

  function zipNamesAndSlugs(names, slugs) {
    const nameArr = Array.isArray(names) ? names : [];
    const slugArr = Array.isArray(slugs) ? slugs : [];
    return nameArr.map((name, i) => ({ name, slug: slugArr[i] || null }));
  }

  // Client-side filter for ingredient names — removes garbage/artifacts that slip through parsing
  function cleanIngredientNames(names) {
    return (names || []).filter((n) => {
      const s = String(n).trim();
      if (!s || s.length > 60) return false;
      if (/\.\s+[А-ЯA-Z]/.test(s)) return false;  // sentence continuation
      if (s.startsWith("•") || s.startsWith(".") || s.startsWith("-")) return false;
      return true;
    });
  }

  function renderStructuredList(title, text) {
    if (!text) return "";
    const items = String(text).split(/[\n•;]/).map((s) => s.replace(/^[-•]\s*/, "").trim()).filter((s) => s.length > 3);
    if (!items.length) return "";
    if (items.length === 1) return aromaSection(title, text);
    return `<section class="section"><h3>${escapeHtml(title)}</h3><ul class="card-list">${items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul></section>`;
  }

  function renderCrossRefChips(pairs, targetTab) {
    if (!pairs || !pairs.length) return "";
    const chips = pairs.map(({ slug, name }) => {
      if (!name) return "";
      // Filter out empty/placeholder slugs that would open nothing
      if (slug && String(slug).trim() !== "") {
        return `<button class="crossref-chip" onclick='openReference(${JSON.stringify(slug)}, ${JSON.stringify(targetTab)})'>${escapeHtml(name)}</button>`;
      }
      return `<span class="crossref-chip crossref-chip--plain">${escapeHtml(name)}</span>`;
    }).filter(Boolean).join("");
    if (!chips) return "";
    return `<div class="crossref-chips">${chips}</div>`;
  }

  function renderCollapsibleDescription(reference) {
    const short = String(reference.description_short || "").trim();
    const full = String(reference.description || "").trim();
    if (!short && !full) return "";
    // If short exists and is different from full, render collapsible
    if (short && full && short !== full) {
      return `
        <section class="section">
          <h3>Описание</h3>
          <div class="detail-preview">${escapeHtml(short)}</div>
          <details class="description-collapsible">
            <summary class="description-toggle">▼ Полный текст</summary>
            <div class="detail-preview description-full">${escapeHtml(full)}</div>
          </details>
        </section>
      `;
    }
    // Fallback to whichever is present
    return `<section class="section"><h3>Описание</h3><div class="detail-preview">${escapeHtml(short || full)}</div></section>`;
  }

  const APPLICATION_METHOD_ICONS = [
    { keywords: ["диффузи", "аромалампа", "аромадиффузор", "аромат"], icon: "💨" },
    { keywords: ["массаж", "втирать", "наносить на кожу"], icon: "💆" },
    { keywords: ["топикально", "локально", "нанесение на кожу"], icon: "🩹" },
    { keywords: ["ванн", "ванна", "купание"], icon: "🛁" },
    { keywords: ["внутрь", "перорально", "капсул"], icon: "💊" },
    { keywords: ["ингаляц", "вдыхать", "пары"], icon: "🌬️" },
    { keywords: ["компресс"], icon: "🩼" },
    { keywords: ["спрей", "распылить"], icon: "🌫️" },
  ];

  function renderApplicationsWithIcons(text) {
    if (!text) return "";
    // Split on newlines or semicolons; strip leading bullet chars
    const lines = text.split(/[\n;]/).map((l) => l.replace(/^[•\-]\s*/, "").trim()).filter(Boolean);
    const rendered = lines.map((line) => {
      const lower = line.toLowerCase();
      let icon = "•";
      for (const { keywords, icon: i } of APPLICATION_METHOD_ICONS) {
        if (keywords.some((kw) => lower.includes(kw))) {
          icon = i;
          break;
        }
      }
      return `<div class="application-line">${icon} ${escapeHtml(line)}</div>`;
    });
    return `<section class="section"><h3>💧 Применение и дозировки</h3><div class="detail-preview applications-list">${rendered.join("")}</div></section>`;
  }

  function renderCollapsibleSection(title, text, maxChars = 280) {
    const str = String(text || "").trim();
    if (!str) return "";
    if (str.length <= maxChars) {
      return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview">${escapeHtml(str)}</div></section>`;
    }
    const cutAt = str.lastIndexOf(" ", maxChars) || maxChars;
    const preview = str.slice(0, cutAt);
    return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview">${escapeHtml(preview)}…</div><details class="description-collapsible"><summary class="description-toggle">▼ Читать далее</summary><div class="detail-preview description-full">${escapeHtml(str)}</div></details></section>`;
  }

  function renderReferencePassport(reference) {
    const parts = [
      reference.article_number ? `Артикул: ${reference.article_number}` : "",
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

  function renderFilterChips(items, tabId) {
    if (!["aromas", "symptoms", "concepts", "practices"].includes(tabId)) return "";

    if (tabId === "symptoms") {
      return renderSymptomFilterChips(items);
    }

    const seen = new Set();
    const values = [];
    for (const item of items) {
      let raw = "";
      if (tabId === "aromas") raw = String(item.source_type || "").trim().toLowerCase();
      else if (tabId === "concepts") raw = String(item.source_type || "").trim().toLowerCase();
      else if (tabId === "practices") raw = String(item.source_type || "").trim().toLowerCase();
      if (raw && !seen.has(raw)) {
        seen.add(raw);
        values.push(raw);
      }
    }
    if (!values.length) return "";
    const activeFilter = state.referenceFilter || "";
    const allActive = !activeFilter;
    const chips = [
      `<button class="filter-chip${allActive ? " active" : ""}" onclick="setReferenceFilter('')">Все</button>`,
      ...values.map((v) => {
        let label;
        if (tabId === "aromas") {
          const icon = SOURCE_TYPE_ICONS?.[v] ? SOURCE_TYPE_ICONS[v] + "\u00a0" : "";
          label = icon + (REFERENCE_SOURCE_TYPE_LABELS[v] || v);
        } else if (tabId === "concepts") {
          const meta = conceptTypeMeta(v);
          const icon = meta.icon ? meta.icon + "\u00a0" : "";
          label = icon + (meta.label || v);
        } else if (tabId === "practices") {
          const icon = PRACTICE_TYPE_ICONS?.[v] ? PRACTICE_TYPE_ICONS[v] + "\u00a0" : "";
          label = icon + (PRACTICE_RU_LABELS?.[v] || v);
        } else {
          label = v;
        }
        const isActive = activeFilter === v;
        return `<button class="filter-chip${isActive ? " active" : ""}" onclick='setReferenceFilter(${JSON.stringify(v)})'>${escapeHtml(label)}</button>`;
      }),
    ];
    return `<div class="filter-chips">${chips.join("")}</div>`;
  }

  function renderSymptomFilterChips(items) {
    // Build 2-level structure: parent_group → [category_group]
    const parentGroups = [];
    const parentSeen = new Set();
    const childrenByParent = {};

    for (const item of items) {
      // L1 chips only from explicit parent_group — never fall back to category_group
      // (would show every disease as a top-level chip)
      const parent = String(item.parent_group || "").trim();
      const child = String(item.category_group || "").trim();
      if (!parent) continue;
      if (!parentSeen.has(parent)) {
        parentSeen.add(parent);
        parentGroups.push(parent);
        childrenByParent[parent] = new Set();
      }
      if (child && child !== parent) {
        childrenByParent[parent].add(child);
      }
    }

    if (!parentGroups.length) return "";

    const activeFilter = state.referenceFilter || "";
    const activeParent = state.referenceFilterParent || "";
    const allActive = !activeFilter && !activeParent;

    const parentChips = [
      `<button class="filter-chip${allActive ? " active" : ""}" onclick="setReferenceFilter('')">Все</button>`,
      ...parentGroups.map((p) => {
        const icon = SYMPTOM_CATEGORY_ICONS?.[p.split(" ")[0]] ? SYMPTOM_CATEGORY_ICONS[p.split(" ")[0]] + "\u00a0" : "";
        const isActive = activeParent === p || activeFilter === p;
        return `<button class="filter-chip${isActive ? " active" : ""}" onclick='setSymptomParentFilter(${JSON.stringify(p)})'>${escapeHtml(icon + p)}</button>`;
      }),
    ];

    let childChips = "";
    if (activeParent && childrenByParent[activeParent]?.size > 0) {
      const children = [...childrenByParent[activeParent]];
      const childButtons = children.map((c) => {
        const isActive = activeFilter === c;
        return `<button class="filter-chip filter-chip--child${isActive ? " active" : ""}" onclick='setReferenceFilter(${JSON.stringify(c)})'>${escapeHtml(c)}</button>`;
      });
      childChips = `<div class="filter-chips filter-chips--level2">${childButtons.join("")}</div>`;
    }

    return `<div class="filter-chips">${parentChips.join("")}</div>${childChips}`;
  }

  function renderReferenceAudit(items) {
    const empty = items.filter((item) => !String(item.description || item.course_notes || "").trim());
    elements.listTitle.textContent = "Аудит: пустые описания";
    elements.draftCount.textContent = `${empty.length} карточек без описания`;
    setEmptyState(empty.length > 0, "Все карточки заполнены!");
    elements.draftList.innerHTML = `
      <div class="audit-header">
        <h3>📋 Карточки без описания (требуют заполнения):</h3>
      </div>
      <ul class="audit-list">${empty.map((item) =>
        `<li class="audit-item">• <strong>${escapeHtml(item.name)}</strong> (${escapeHtml(item.category || "")}) — description пустой</li>`
      ).join("")}</ul>
    `;
    elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty"></div>`;
  }

  function renderReferences() {
    // Audit mode: ?audit=1 shows empty-description list
    if (new URLSearchParams(window.location.search).get("audit") === "1") {
      const items = state.referenceItems || [];
      if (items.length > 0) {
        renderReferenceAudit(items);
        return;
      }
    }

    const meta = currentHandbookMeta();
    const tabId = state.tab;
    const items = state.referenceItems || [];
    const activeFilter = state.referenceFilter || "";

    const activeParent = state.referenceFilterParent || "";
    let visible = items;
    if (activeFilter || activeParent) {
      visible = items.filter((item) => {
        if (tabId === "aromas") return String(item.source_type || "").trim().toLowerCase() === activeFilter;
        if (tabId === "symptoms") {
          const itemParent = String(item.parent_group || item.category_group || "").trim();
          const itemChild = String(item.category_group || "").trim();
          if (activeFilter) return itemChild === activeFilter || itemParent === activeFilter;
          if (activeParent) return itemParent === activeParent || itemChild === activeParent;
          return true;
        }
        if (tabId === "concepts" || tabId === "practices") return String(item.source_type || "").toLowerCase() === activeFilter;
        return true;
      });
    }

    const query = (state.referenceSearch || "").trim().toLowerCase();
    const filtered = visible.filter((item) =>
      `${item.name} ${item.description || ""} ${item.course_notes || ""} ${item.conditions_for_use || ""} ${item.category_group || ""}`.toLowerCase().includes(query)
    );
    const reference = state.selectedReference;

    elements.listTitle.textContent = meta.title;
    elements.draftCount.textContent = query
      ? `Найдено ${filtered.length} из ${items.length}`
      : meta.count(items);

    setEmptyState(filtered.length > 0, meta.empty);

    let listContainer = document.getElementById("referenceListContainer");
    if (!listContainer) {
      elements.draftList.innerHTML = `
        <div id="referenceFilterChips"></div>
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
    const filterChipsEl = document.getElementById("referenceFilterChips");
    if (filterChipsEl) filterChipsEl.innerHTML = renderFilterChips(items, tabId);

    listContainer.innerHTML = filtered.map((item) => `
      <article ${interactiveCardAttrs(`Открыть карточку ${item.name}`)} class="draft-card overview-card reference-card${state.tab === "concepts" ? " is-theory concept-card" : ""}${item.slug === reference?.slug ? " active" : ""} interactive-card" onclick='openReference(${JSON.stringify(item.slug)}, ${JSON.stringify(state.tab)})'>
        <div class="overview-card-top">
          <div class="draft-kind"><span class="kind-glyph handbook-glyph" aria-hidden="true">${aromaCardIcon(item, state.tab)}</span>${handbookCardBadge(state.tab, item) ? `<span>${escapeHtml(handbookCardBadge(state.tab, item))}</span>` : ""}</div>
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

    let detailHtml;
    if (state.tab === "blends") {
      // Use Russian ingredient names from backend; fall back to cleaned English names
      const rawIngredientNames = Array.isArray(reference.ingredient_names_ru) && reference.ingredient_names_ru.length
        ? reference.ingredient_names_ru
        : cleanIngredientNames(reference.ingredient_names);
      const ingredientChips = renderCrossRefChips(
        zipNamesAndSlugs(rawIngredientNames, reference.ingredient_slugs),
        "aromas"
      );
      const compChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.complementary_oil_names, reference.complementary_oil_slugs),
        "aromas"
      );
      const symptomChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.related_symptom_names, reference.related_symptom_slugs),
        "symptoms"
      );
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${aromaSection("Паспорт карточки", renderReferencePassport(reference))}
          ${aromaSection("Описание", reference.description)}
          ${aromaSection("Терапевтические свойства", reference.therapeutic_properties)}
          ${renderStructuredList("При каких состояниях", reference.conditions_for_use)}
          ${ingredientChips ? `<section class="section"><h3>🧪 Состав</h3><div class="detail-preview">${ingredientChips}</div></section>` : ""}
          ${compChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compChips}</div></section>` : ""}
          ${symptomChips ? `<section class="section"><h3>💊 Помогает при</h3><div class="detail-preview">${symptomChips}</div></section>` : ""}
          ${aromaSection("Применение", reference.applications)}
          ${aromaSection("Меры предосторожности", reference.precautions)}
        </div>
      `;
    } else if (state.tab === "symptoms") {
      const oilChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.recommended_oil_names, reference.recommended_oil_slugs),
        "aromas"
      );
      const blendChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.recommended_blend_names, reference.recommended_blend_slugs),
        "blends"
      );
      const parentGroup = reference.parent_group || "";
      const categoryGroup = reference.category_group || "";
      let breadcrumb = "";
      if (parentGroup && categoryGroup && parentGroup !== categoryGroup) {
        breadcrumb = `<section class="section"><p class="eyebrow">${escapeHtml(parentGroup)} › ${escapeHtml(categoryGroup)}</p></section>`;
      } else if (categoryGroup) {
        breadcrumb = `<section class="section"><p class="eyebrow">${escapeHtml(categoryGroup)}</p></section>`;
      }
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${breadcrumb}
          ${aromaSection("Описание", reference.description)}
          ${oilChips ? `<section class="section"><h3>🌿 Рекомендуемые масла</h3><div class="detail-preview">${oilChips}</div></section>` : ""}
          ${blendChips ? `<section class="section"><h3>🌀 Рекомендуемые смеси</h3><div class="detail-preview">${blendChips}</div></section>` : ""}
          ${renderStructuredList("Применение", reference.applications)}
        </div>
      `;
    } else if (state.tab === "practices") {
      const compOilChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.complementary_oil_names, reference.complementary_oil_slugs),
        "aromas"
      );
      const blendPracticeChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.blend_names, reference.blend_slugs),
        "blends"
      );
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${aromaSection("Паспорт карточки", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${aromaSection("Психологические свойства", reference.psychological_properties)}
          ${aromaSection("Терапевтические свойства", reference.therapeutic_properties)}
          ${compOilChips ? `<section class="section"><h3>🌿 Масла для практики</h3><div class="detail-preview">${compOilChips}</div></section>` : ""}
          ${blendPracticeChips ? `<section class="section"><h3>🌀 Рекомендуемые смеси</h3><div class="detail-preview">${blendPracticeChips}</div></section>` : ""}
          ${aromaSection("📋 Применение", reference.applications)}
          ${aromaSection("Меры предосторожности", reference.precautions)}
          ${aromaSection("Материалы курса", reference.course_notes)}
        </div>
      `;
    } else if (state.tab === "concepts") {
      const compOilChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.complementary_oil_names, reference.complementary_oil_slugs),
        "aromas"
      );
      const practiceChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.practice_names, reference.practice_slugs),
        "practices"
      );
      const blendsChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.blends_containing_names, reference.blends_containing_slugs),
        "blends"
      );
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${aromaSection("Паспорт карточки", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${aromaSection("Психологические свойства", reference.psychological_properties)}
          ${aromaSection('Ресурс "+"', reference.resource_values?.plus)}
          ${aromaSection('Ресурс "-"', reference.resource_values?.minus)}
          ${aromaSection("Какие вопросы поднимает", reference.questions)}
          ${compOilChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compOilChips}</div></section>` : ""}
          ${practiceChips ? `<section class="section"><h3>🧘 Практики</h3><div class="detail-preview">${practiceChips}</div></section>` : ""}
          ${blendsChips ? `<section class="section"><h3>🌀 Входит в смеси</h3><div class="detail-preview">${blendsChips}</div></section>` : ""}
          ${aromaSection("Материалы курса", reference.course_notes)}
        </div>
      `;
    } else {
      // Aroma detail view
      const compChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.complementary_oil_names, reference.complementary_oil_slugs),
        "aromas"
      );
      const blendsChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.blends_containing_names, reference.blends_containing_slugs),
        "blends"
      );
      const symptomChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.related_symptom_names, reference.related_symptom_slugs),
        "symptoms"
      );
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${aromaSection("Паспорт карточки", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${aromaSection("Психологические свойства", reference.psychological_properties)}
          ${aromaSection('Ресурс "+"', reference.resource_values?.plus)}
          ${aromaSection('Ресурс "-"', reference.resource_values?.minus)}
          ${aromaSection("Какие вопросы поднимает", reference.questions)}
          ${aromaSection("Действие на НПС", reference.nps_effect)}
          ${renderCollapsibleSection("Терапевтические свойства", reference.therapeutic_properties)}
          ${renderCollapsibleSection("Влияние на здоровье", reference.health_effects)}
          ${renderCollapsibleSection("Влияние на ум", reference.mind_effect)}
          ${renderCollapsibleSection("Духовное и эмоциональное воздействие", reference.spiritual_emotional)}
          ${renderCollapsibleSection("При каких состояниях", reference.conditions_for_use)}
          ${compChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compChips}</div></section>` : ""}
          ${blendsChips ? `<section class="section"><h3>🌀 Входит в смеси</h3><div class="detail-preview">${blendsChips}</div></section>` : ""}
          ${symptomChips ? `<section class="section"><h3>💊 Помогает при</h3><div class="detail-preview">${symptomChips}</div></section>` : ""}
          ${renderApplicationsWithIcons(reference.applications)}
          ${renderCollapsibleSection("Меры предосторожности", reference.precautions)}
          ${aromaSection("Материалы курса", reference.course_notes)}
          ${renderCollapsibleSection("Исторические сведения", reference.history)}
        </div>
      `;
    }
    elements.draftDetail.innerHTML = detailHtml;
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
