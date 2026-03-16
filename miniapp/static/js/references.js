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
  const _aromaSlugMap = {};

  function lookupNameRu(slug) {
    return slug ? (_aromaSlugMap[slug] || "") : "";
  }

  function findSlugByName(name) {
    if (!name) return null;
    const lower = name.trim().toLowerCase();
    for (const [slug, nameRu] of Object.entries(_aromaSlugMap)) {
      if (String(nameRu).toLowerCase() === lower) return slug;
    }
    return null;
  }

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
    aromaHtmlSection,
    fetchJson,
    enterDetailView,
    syncMobileNavigation,
    setEmptyState,
    conceptTypeMeta,
    formatCourseSourceLabel,
    tagMarkup,
    stripMarkdown,
    toSentenceCase,
    showUiNotice,
    SOURCE_TYPE_ICONS,
    SYMPTOM_CATEGORY_ICONS,
    SYMPTOM_PARENT_GROUP_ICONS,
    BLEND_CATEGORY_ICONS,
    CONCEPT_TYPE_ICONS,
    PRACTICE_TYPE_ICONS,
    PRACTICE_RU_LABELS,
  } = deps;

  /* ── Smart Search state ── */
  const _searchCache = {};
  let _smartSearchDebounce = null;

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
    // Clear stale items before fetch to prevent cross-category contamination
    state.referenceItems = [];
    renderReferences();
    const data = await fetchJson(`/api/references/${meta.category}`);
    // Client-side guard: filter out any items that belong to a different category
    state.referenceItems = (data.items || []).filter(
      (i) => !i.category || i.category === meta.category
    );
    if (meta.category === "aromas") {
      state.referenceItems.forEach(item => {
        if (item.slug && (item.name_ru || item.name)) _aromaSlugMap[item.slug] = item.name_ru || item.name;
      });
    }
    // Pre-fill aroma slug map for cross-reference lookups (e.g. blend ingredients)
    if (meta.category !== "aromas" && Object.keys(_aromaSlugMap).length === 0) {
      fetchJson("/api/references/aroma").then((aromaData) => {
        (aromaData.items || []).forEach(item => {
          if (item.slug && (item.name_ru || item.name)) _aromaSlugMap[item.slug] = item.name_ru || item.name;
        });
      }).catch(() => {});
    }

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
      // Track cross-tab navigation context for back button
      // Only set _fromContext when explicitly navigating cross-tab from a detail view
      if (tabId !== state.tab && state.selectedReference?.slug) {
        state._fromContext = { tab: state.tab, slug: state.selectedReference.slug };
      } else {
        // Same-tab navigation or no prior card: always clear stale context
        state._fromContext = null;
      }
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

  function zipNamesAndSlugs(names, slugs, metas) {
    const nameArr = Array.isArray(names) ? names : [];
    const slugArr = Array.isArray(slugs) ? slugs : [];
    const metaArr = Array.isArray(metas) ? metas : [];
    return nameArr.map((name, i) => ({ name, slug: slugArr[i] || null, meta: metaArr[i] || null }));
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
    const s = String(text);

    // 1. Normalize PDF "z " bullet → "•" (PDF font artifact)
    const normalized = s
      .replace(/(^|\n)z\s+/g, "$1• ")
      .replace(/(?<![а-яёА-ЯЁa-zA-Z0-9])z\s+(?=[А-ЯЁа-яёA-Za-z])/g, "• ");

    // 2. Split on "•" — single unified bullet marker
    const rawParts = normalized.split(/\n?•\s*/);

    // 3. Clean each item: join internal line-breaks, strip page numbers, fix hyphen-splits
    const items = rawParts.map((part) => {
      let result = "";
      for (const rawLine of part.split(/\n/)) {
        const line = rawLine.trim();
        if (!line) continue;
        if (/^\d{1,3}$/.test(line)) continue;      // skip standalone page numbers
        if (result.endsWith("-")) result = result + line;  // rejoin "V-\n6"
        else result = result ? result + " " + line : line;
      }
      return result.trim();
    }).filter((s) => s.length > 3);

    if (!items.length) return "";
    if (items.length === 1) return aromaSection(title, items[0]);

    return `<section class="section"><h3>${escapeHtml(title)}</h3><ul class="card-list">${
      items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")
    }</ul></section>`;
  }

  // Normalize symptom names that contain mixed-case PDF artifacts.
  // "Боль ГОЛОВНАЯ ПРИ СИНУСИТЕ" → "Боль головная при синусите"
  function normalizePdfSymptomName(raw) {
    const s = String(raw || "").replace(/[.\s]+$/, "").trim();
    if (!s) return s;
    // If contains all-caps word (3+ letters) AND has lowercase letters → mixed PDF artifact
    if (/\b[А-ЯЁA-Z]{3,}\b/.test(s) && /[а-яёa-z]/.test(s)) {
      return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
    }
    return toSentenceCase(s);
  }

  function renderCrossRefChips(pairs, targetTab) {
    if (!pairs || !pairs.length) return "";
    const seen = new Set();
    const chips = pairs.map(({ slug, name, meta }) => {
      if (!name) return "";
      const trimmed = name.trim();
      if (trimmed.length < 3 || trimmed.length > 50) return "";
      if (/^(который|которая|которое|которые|где|что|как|при|для|и|в|с|на|по|действует|гормон)/i.test(trimmed)) return "";
      if (/действует|гормон|надпочечник|коры\b/i.test(trimmed)) return "";
      const key = slug || name;
      if (seen.has(key)) return "";
      seen.add(key);
      const display = targetTab === "symptoms" ? normalizePdfSymptomName(name) : name;
      let icon = "";
      if (meta) {
        if (targetTab === "aromas") {
          const ic = SOURCE_TYPE_ICONS[String(meta)];
          if (ic) icon = ic;
        } else if (targetTab === "blends") {
          const ic = meta ? BLEND_CATEGORY_ICONS[String(meta).toUpperCase()] : null;
          icon = (ic || "🧪");
        } else if (targetTab === "symptoms") {
          const ic = SYMPTOM_PARENT_GROUP_ICONS[String(meta).toUpperCase()];
          if (ic) icon = ic;
        }
      }
      // Filter out empty/placeholder slugs that would open nothing
      if (slug && String(slug).trim() !== "") {
        return `<button class="crossref-chip" onclick='openReference(${JSON.stringify(slug)}, ${JSON.stringify(targetTab)})'>${icon ? `<span class="chip-icon">${icon}</span>` : ''}${escapeHtml(display)}</button>`;
      }
      return `<span class="crossref-chip crossref-chip--plain">${icon ? `<span class="chip-icon">${icon}</span>` : ''}${escapeHtml(display)}</span>`;
    }).filter(Boolean).join("");
    if (!chips) return "";
    return `<div class="crossref-chips">${chips}</div>`;
  }

  function renderCollapsibleDescription(reference) {
    // description_short = comprehensive AI synthesis of all card fields (shown in full, no collapse)
    // description = original raw text (not shown separately to avoid duplication)
    const text = String(reference.description_short || reference.description || "").trim();
    if (!text) return "";
    return `<section class="section"><h3>Описание</h3><div class="detail-preview">${escapeHtml(text)}</div></section>`;
  }

  const APPLICATION_METHOD_ICONS = [
    { keywords: ["диффуз", "аромалампа", "аромадиффузор"], icon: "💨" },
    { keywords: ["массаж", "втирать", "наносить на кожу"], icon: "💆" },
    { keywords: ["топикально", "локально", "нанесение на кожу", "нанести", "нанес"], icon: "🩹" },
    { keywords: ["ванн", "ванна", "купание"], icon: "🛁" },
    { keywords: ["внутрь", "перорально", "капсул"], icon: "💊" },
    { keywords: ["ингаляц", "вдыхать", "пары"], icon: "🌬️" },
    { keywords: ["компресс"], icon: "🩼" },
    { keywords: ["спрей", "распылить"], icon: "🌫️" },
    { keywords: ["полоскани", "полость рта"], icon: "🪥" },
    { keywords: ["vita flex", "виталекс", "точки vita"], icon: "⚡" },
    { keywords: ["в мёд", "в напиток", "добавить в"], icon: "🍯" },
  ];

  function renderVerificationBadge(reference) {
    const byExpert = !!reference.verified_by_expert;
    const byDoctor = !!reference.verified_by_doctor;
    if (byExpert && byDoctor) {
      return `<div class="verification-badge is-verified">✓ Проверено ароматерапевтом и врачом</div>`;
    }
    return "";
  }

  function renderMedicalDisclaimer() {
    return `<div class="medical-disclaimer">Информация носит ознакомительный характер и не является медицинской рекомендацией. Перед применением проконсультируйтесь с врачом.</div>`;
  }

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

  function renderRecipeDrops(ref) {
    const namesEn = ref.ingredient_names || [];
    const namesRu = ref.ingredient_names_ru || [];
    const slugs = ref.ingredient_slugs || [];
    const drops = ref.ingredient_drops || [];
    if (!drops.length || drops.length !== namesEn.length) return "";
    const lines = namesEn.map((nameEn, i) => {
      const d = drops[i];
      const unit = d === 1 ? "капля" : (d >= 2 && d <= 4) ? "капли" : "капель";
      const displayName = (namesRu[i] || lookupNameRu(slugs[i]) || nameEn || "").trim();
      const slug = slugs[i] || findSlugByName(displayName);
      const nameHtml = slug
        ? `<button class="crossref-chip" onclick='openReference(${JSON.stringify(slug)}, "aromas")'>${escapeHtml(displayName)}</button>`
        : `<span class="crossref-chip crossref-chip--plain">${escapeHtml(displayName)}</span>`;
      return `<div class="recipe-line">${d} ${unit} ${nameHtml}</div>`;
    });
    return `<section class="section"><h3>📋 Рецепт</h3><div class="detail-preview recipe-drops">${lines.join("")}</div></section>`;
  }

  function renderCollapsibleSection(title, text, maxChars = 280) {
    const str = String(text || "").trim();
    if (!str) return "";
    if (str.length <= maxChars) {
      return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview">${escapeHtml(str)}</div></section>`;
    }
    const cutAt = str.lastIndexOf(" ", maxChars) || maxChars;
    const preview = str.slice(0, cutAt);
    return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview exp-section-wrap"><div class="exp-collapsed">${escapeHtml(preview)}… <button class="exp-btn" onclick="expandSection(this)">Читать далее <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg></button></div><div class="exp-expanded" hidden>${escapeHtml(str)}</div></div></section>`;
  }

  const COUNTRY_FLAGS = {
    "США": "🇺🇸", "Юта": "🇺🇸", "Калифорния": "🇺🇸", "Флорида": "🇺🇸",
    "Франция": "🇫🇷", "Прованс": "🇫🇷", "Индия": "🇮🇳", "Гватемала": "🇬🇹",
    "Южная Африка": "🇿🇦", "Бразилия": "🇧🇷", "Марокко": "🇲🇦", "Болгария": "🇧🇬",
    "Австралия": "🇦🇺", "Япония": "🇯🇵", "Китай": "🇨🇳", "Россия": "🇷🇺",
    "Шри-Ланка": "🇱🇰", "Мадагаскар": "🇲🇬", "Италия": "🇮🇹", "Испания": "🇪🇸",
    "Израиль": "🇮🇱", "Египет": "🇪🇬", "Сомали": "🇸🇴", "Эфиопия": "🇪🇹",
    "Оман": "🇴🇲", "Перу": "🇵🇪", "Мексика": "🇲🇽", "Канада": "🇨🇦",
    "Германия": "🇩🇪", "Непал": "🇳🇵", "Индонезия": "🇮🇩", "Вьетнам": "🇻🇳",
  };

  function addCountryFlags(text) {
    if (!text) return "";
    return text.split(/[,;]/).map((seg) => {
      const t = seg.trim();
      for (const [country, flag] of Object.entries(COUNTRY_FLAGS)) {
        if (t.includes(country)) return `${flag}\u00a0${t}`;
      }
      return t;
    }).filter(Boolean).join(", ");
  }

  function renderVolatilityScale(v) {
    if (!v) return v;
    const s = String(v).toLowerCase();
    if (s.includes("высок")) return '<span class="vol-dot vol-high"></span> Высокая';
    if (s.includes("средн")) return '<span class="vol-dot vol-mid"></span> Средняя';
    if (s.includes("низк"))  return '<span class="vol-dot vol-low"></span> Низкая';
    return v;
  }

  function shortExtractionMethod(val) {
    if (!val) return val;
    const cutMarkers = [". Из ", ". из ", "; из ", ". Получ", ". Сырь", ". Из 1"];
    for (const m of cutMarkers) {
      const i = val.indexOf(m);
      if (i > 0) return val.slice(0, i).trim();
    }
    if (val.length > 60) {
      const i = val.indexOf(",");
      if (i > 10) return val.slice(0, i).trim();
    }
    return val;
  }

  /* ── Sound Audio Player ── */

  function renderAudioPlayer(reference) {
    if (reference.category !== "sound" || !reference.slug) return "";
    const audioUrl = `/sounds/${encodeURIComponent(reference.slug)}.mp3`;
    return `
      <section class="section sound-player-section">
        <h3><i data-lucide="volume-2" style="width:16px;height:16px"></i> Прослушать</h3>
        <div class="sound-player" data-audio-url="${escapeHtml(audioUrl)}">
          <button class="sound-player-btn" type="button" aria-label="Воспроизвести">
            <span class="sound-player-icon-play"><i data-lucide="play"></i></span>
            <span class="sound-player-icon-pause" hidden><i data-lucide="pause"></i></span>
          </button>
          <div class="sound-player-progress">
            <div class="sound-player-bar">
              <div class="sound-player-fill"></div>
            </div>
            <span class="sound-player-time">0:00</span>
          </div>
        </div>
      </section>
    `;
  }

  function initSoundPlayer(container) {
    const url = container.dataset.audioUrl;
    const audio = new Audio(url);
    const btn = container.querySelector(".sound-player-btn");
    const playIcon = container.querySelector(".sound-player-icon-play");
    const pauseIcon = container.querySelector(".sound-player-icon-pause");
    const fill = container.querySelector(".sound-player-fill");
    const timeEl = container.querySelector(".sound-player-time");
    const bar = container.querySelector(".sound-player-bar");

    function fmt(sec) {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${m}:${String(s).padStart(2, "0")}`;
    }

    btn.addEventListener("click", () => {
      if (audio.paused) audio.play().catch(() => {});
      else audio.pause();
    });

    bar.addEventListener("click", (e) => {
      if (!audio.duration) return;
      const rect = bar.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });

    audio.addEventListener("play", () => { playIcon.hidden = true; pauseIcon.hidden = false; });
    audio.addEventListener("pause", () => { playIcon.hidden = false; pauseIcon.hidden = true; });
    audio.addEventListener("ended", () => {
      playIcon.hidden = false; pauseIcon.hidden = true;
      fill.style.width = "0%"; timeEl.textContent = "0:00";
    });
    audio.addEventListener("timeupdate", () => {
      if (!audio.duration) return;
      fill.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
      timeEl.textContent = fmt(audio.currentTime);
    });
    audio.addEventListener("error", () => {
      container.innerHTML = '<span class="sound-player-unavailable">Аудио недоступно</span>';
    });
  }

  function renderReferencePassport(reference) {
    const rows = [
      reference.article_number && { icon: "🔖", label: "Артикул", value: reference.article_number },
      reference.botanical_family && { icon: "🌿", label: "Семейство", value: reference.botanical_family },
      reference.origin_countries && { icon: "📍", label: "Происхождение", value: addCountryFlags(reference.origin_countries) },
      reference.extraction_method && { icon: "⚗️", label: "Метод", value: shortExtractionMethod(reference.extraction_method) },
      reference.volatility && (() => {
        const isDuration = reference.category === "practice" || reference.category === "sound";
        return {
          icon: isDuration ? "⏱" : "💨",
          label: isDuration ? "Длительность" : "Летучесть",
          value: isDuration ? reference.volatility : renderVolatilityScale(reference.volatility),
          raw: !isDuration, // volatility scale returns HTML (vol-dot spans)
        };
      })(),
      reference.chakra_focus && { icon: "✦", label: "Чакры", value: reference.chakra_focus },
      reference.polarity && { icon: "⚡", label: "Полярность", value: reference.polarity },
      reference.course_source && { icon: "📚", label: "Курс", value: formatCourseSourceLabel(reference.course_source) },
    ].filter(Boolean);
    if (!rows.length) return "";
    return `<div class="passport-grid">${rows.map((row) =>
      `<div class="passport-row">
        <span class="passport-icon">${row.icon}</span>
        <span class="passport-label">${escapeHtml(row.label)}</span>
        <span class="passport-value">${row.raw ? row.value : escapeHtml(row.value)}</span>
      </div>`
    ).join("")}</div>`;
  }

  function cardCategoryIcon(reference) {
    const icons = {
      citrus: "🍊", herb: "🌿", flower: "🌸", tree: "🌲", resin: "🪨",
      spice: "🌶", grass: "🌾", root: "🌱", wood: "🪵",
      blend: "🧪", symptom: "🩺", practice: "📿", concept: "💡",
    };
    return icons[reference.source_type] || icons[reference.category] || handbookCategoryIcon(state.tab);
  }

  function renderReferenceImage(reference) {
    const heroClass = state.tab === "concepts" ? "reference-hero-card is-theory" : "reference-hero-card";
    let eyebrowLabel;
    if (state.tab === "concepts") {
      eyebrowLabel = `${cardCategoryIcon(reference)}<span>${escapeHtml(currentHandbookMeta().title)} · учебный модуль</span>`;
    } else if (state.tab === "symptoms") {
      const eyebrowText = toSentenceCase(String(reference.parent_group || reference.category_group || currentHandbookMeta().title));
      const groupIcon = SYMPTOM_PARENT_GROUP_ICONS[String(reference.parent_group || "").toUpperCase()] || "🩺";
      eyebrowLabel = `${groupIcon}<span>${escapeHtml(eyebrowText)}</span>`;
    } else {
      eyebrowLabel = `${cardCategoryIcon(reference)}<span>${escapeHtml(currentHandbookMeta().title)}</span>`;
    }
    // Keyline: for aromas always use source_type family label
    let keyline;
    if (state.tab === "symptoms") {
      keyline = toSentenceCase(reference.category_group || reference.parent_group || "");
    } else if (state.tab === "aromas") {
      keyline = REFERENCE_SOURCE_TYPE_LABELS[reference.source_type]
        || handbookCardBadge(state.tab, reference)
        || currentHandbookMeta().title;
    } else {
      const rawKeyline = reference.key || handbookCardBadge(state.tab, reference) || currentHandbookMeta().title;
      keyline = (rawKeyline && rawKeyline !== reference.name)
        ? rawKeyline
        : (REFERENCE_SOURCE_TYPE_LABELS[reference.source_type] || currentHandbookMeta().title);
    }
    // Subtitle line below the card title — only for aromas (EN name + family)
    let subtitle = "";
    if (state.tab === "aromas") {
      const parts = [reference.name_en, keyline ? `(${keyline})` : ""].filter(Boolean);
      subtitle = parts.join(" ");
    }
    // Compact EN name for blends (mirrors card list style)
    const blendNameEn = state.tab === "blends" && reference.name_en ? reference.name_en : "";
    return `
      <section class="section aroma-hero ${heroClass}">
        <div class="reference-hero-copy">
          <p class="eyebrow">${eyebrowLabel}</p>
          <h2 class="detail-title">${escapeHtml(state.tab === "symptoms" ? normalizePdfSymptomName(reference.name) : reference.name)}</h2>
          ${subtitle ? `<p class="reference-keyline">${escapeHtml(subtitle)}</p>` : ""}
          ${blendNameEn ? `<div class="reference-name-en">${escapeHtml(blendNameEn)}</div>` : ""}
          ${state.tab === "blends" && reference.article_number ? `<span class="reference-meta-article">🔖 ${escapeHtml(reference.article_number)}</span>` : ""}
        </div>
        <div class="reference-hero-media">
          <img class="aroma-image" src="${escapeHtml(reference.image_url)}" alt="${escapeHtml(reference.image_alt)}" />
        </div>
      </section>
    `;
  }

  function renderFilterChips(items, tabId) {
    if (!["aromas", "blends", "symptoms", "concepts", "practices"].includes(tabId)) return "";

    if (tabId === "symptoms") {
      return renderSymptomFilterChips(items);
    }

    const seen = new Set();
    const values = [];
    for (const item of items) {
      let raw = "";
      if (tabId === "aromas") raw = String(item.source_type || "").trim().toLowerCase();
      else if (tabId === "blends") raw = String(item.blend_category || "").trim();
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
        } else if (tabId === "blends") {
          const icon = BLEND_CATEGORY_ICONS?.[v] ? BLEND_CATEGORY_ICONS[v] + "\u00a0" : "";
          label = icon + v;
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
        const icon = SYMPTOM_PARENT_GROUP_ICONS?.[p] ? SYMPTOM_PARENT_GROUP_ICONS[p] + "\u00a0" : "";
        const isActive = activeParent === p || activeFilter === p;
        return `<button class="filter-chip${isActive ? " active" : ""}" onclick='setSymptomParentFilter(${JSON.stringify(p)})'>${escapeHtml(icon + toSentenceCase(p))}</button>`;
      }),
    ];

    let childChips = "";
    if (activeParent && childrenByParent[activeParent]?.size > 0) {
      const children = [...childrenByParent[activeParent]];
      const childButtons = children.map((c) => {
        const isActive = activeFilter === c;
        return `<button class="filter-chip filter-chip--child${isActive ? " active" : ""}" onclick='setReferenceFilter(${JSON.stringify(c)})'>${escapeHtml(toSentenceCase(c))}</button>`;
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
        if (tabId === "blends") return String(item.blend_category || "").trim() === activeFilter;
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

    setEmptyState(filtered.length > 0, query
      ? { eyebrow: meta.title, title: "Ничего не найдено", body: "Попробуйте другой запрос или сбросьте фильтр." }
      : meta.empty);

    let listContainer = document.getElementById("referenceListContainer");
    if (!listContainer) {
      elements.draftList.innerHTML = `
        ${renderSmartSearchHero()}
        <div id="referenceFilterChips"></div>
        <div id="referenceListContainer" class="plans-list"></div>
      `;
      listContainer = document.getElementById("referenceListContainer");
      document.getElementById("smartSearchInput")?.addEventListener("input", (e) => {
        state.referenceSearch = e.target.value;
      });
    } else {
      const searchInput = document.getElementById("smartSearchInput");
      if (searchInput) {
        searchInput.value = state.referenceSearch;
      }
    }
    const filterChipsEl = document.getElementById("referenceFilterChips");
    if (filterChipsEl) filterChipsEl.innerHTML = renderFilterChips(items, tabId);

    listContainer.innerHTML = filtered.map((item) => `
      <article ${interactiveCardAttrs(`Открыть карточку ${item.name}`)} class="draft-card overview-card reference-card${state.tab === "concepts" ? " is-theory concept-card" : ""}${item.slug === reference?.slug ? " active" : ""} interactive-card" onclick='openReference(${JSON.stringify(item.slug)}, ${JSON.stringify(state.tab)})'>
        <div class="overview-card-top">
          <div class="draft-kind">${!["symptoms", "concepts", "blends"].includes(state.tab) ? `<span class="kind-glyph handbook-glyph" aria-hidden="true">${aromaCardIcon(item, state.tab)}</span>` : ""}${handbookCardBadge(state.tab, item) ? `<span>${state.tab === "concepts" ? `<span class="concept-kind-mark" aria-hidden="true">${escapeHtml(aromaCardIcon(item, state.tab))}</span>` : ""}${escapeHtml(handbookCardBadge(state.tab, item))}</span>` : ""}</div>
          ${(() => { const courseLabel = formatCourseSourceLabel(item.course_source); const dateLabel = courseLabel || (state.tab !== "aromas" ? REFERENCE_SOURCE_TYPE_LABELS[item.source_type] || "" : ""); return dateLabel ? `<span class="overview-card-date">${escapeHtml(dateLabel)}</span>` : ""; })()}
        </div>
        <h3 class="draft-topic">${escapeHtml(state.tab === "symptoms" ? normalizePdfSymptomName(item.name) : item.name)}</h3>
        ${item.name_en ? `<div class="reference-name-en">${escapeHtml(item.name_en)}</div>` : ""}
        <div class="draft-preview">${escapeHtml(stripMarkdown(
          (state.tab === "concepts" ? item.key : null)
          || item.description_short || item.description || item.course_notes || ""
        ))}</div>
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
      const recipeHtml = renderRecipeDrops(reference);
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${renderCollapsibleDescription(reference)}
          ${aromaSection("Терапевтические свойства", reference.therapeutic_properties)}
          ${renderStructuredList("При каких состояниях", reference.conditions_for_use)}
          ${recipeHtml}
          ${!recipeHtml && ingredientChips ? `<section class="section"><h3>🧪 Состав</h3><div class="detail-preview">${ingredientChips}</div></section>` : ""}
          ${compChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compChips}</div></section>` : ""}
          ${symptomChips ? `<section class="section"><h3>💊 Помогает при</h3><div class="detail-preview">${symptomChips}</div></section>` : ""}
          ${renderStructuredList("Применение", reference.applications)}
          ${renderStructuredList("Меры предосторожности", reference.precautions)}
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
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${renderVerificationBadge(reference)}
          ${aromaSection("Описание", reference.description)}
          ${oilChips ? `<section class="section"><h3>🌿 Рекомендуемые масла</h3><div class="detail-preview">${oilChips}</div></section>` : ""}
          ${blendChips ? `<section class="section"><h3>🌀 Рекомендуемые смеси</h3><div class="detail-preview">${blendChips}</div></section>` : ""}
          ${renderApplicationsWithIcons(reference.applications)}
          ${renderMedicalDisclaimer()}
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
          ${aromaHtmlSection("О практике", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${renderCollapsibleSection("Психологические свойства", reference.psychological_properties, 280)}
          ${renderCollapsibleSection("Терапевтические свойства", reference.therapeutic_properties, 280)}
          ${compOilChips ? `<section class="section"><h3>🌿 Масла для практики</h3><div class="detail-preview">${compOilChips}</div></section>` : ""}
          ${blendPracticeChips ? `<section class="section"><h3>🌀 Рекомендуемые смеси</h3><div class="detail-preview">${blendPracticeChips}</div></section>` : ""}
          ${renderStructuredList("📋 Применение", reference.applications)}
          ${renderStructuredList("Меры предосторожности", reference.precautions)}
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
          ${aromaHtmlSection("О концепции", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${renderCollapsibleSection("Психологические свойства", reference.psychological_properties, 280)}
          ${aromaSection('Ресурс "+"', reference.resource_values?.plus)}
          ${aromaSection('Ресурс "-"', reference.resource_values?.minus)}
          ${aromaSection("Какие вопросы поднимает", reference.questions)}
          ${compOilChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compOilChips}</div></section>` : ""}
          ${practiceChips ? `<section class="section"><h3>🧘 Практики</h3><div class="detail-preview">${practiceChips}</div></section>` : ""}
          ${blendsChips ? `<section class="section"><h3>🌀 Входит в смеси</h3><div class="detail-preview">${blendsChips}</div></section>` : ""}
          ${aromaSection("Материалы курса", reference.course_notes)}
        </div>
      `;
    } else if (state.tab === "sounds") {
      const compOilChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.complementary_oil_names, reference.complementary_oil_slugs),
        "aromas"
      );
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${renderAudioPlayer(reference)}
          ${aromaHtmlSection("О звуке", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${renderCollapsibleSection("Психологические свойства", reference.psychological_properties, 280)}
          ${renderCollapsibleSection("Терапевтические свойства", reference.therapeutic_properties, 280)}
          ${compOilChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compOilChips}</div></section>` : ""}
          ${renderStructuredList("📋 Применение", reference.applications)}
          ${renderStructuredList("Меры предосторожности", reference.precautions)}
          ${aromaSection("Материалы курса", reference.course_notes)}
        </div>
      `;
    } else {
      // Aroma detail view
      const compChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.complementary_oil_names, reference.complementary_oil_slugs, reference.complementary_oil_source_types),
        "aromas"
      );
      const blendsChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.blends_containing_names, reference.blends_containing_slugs, reference.blends_containing_categories),
        "blends"
      );
      const symptomChips = renderCrossRefChips(
        zipNamesAndSlugs(reference.related_symptom_names, reference.related_symptom_slugs, reference.related_symptom_parent_groups),
        "symptoms"
      );
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${aromaHtmlSection("Паспорт аромата", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${renderCollapsibleSection("Психологические свойства", reference.psychological_properties, 280)}
          ${aromaSection('Ресурс "+"', reference.resource_values?.plus)}
          ${aromaSection('Ресурс "-"', reference.resource_values?.minus)}
          ${aromaSection("Какие вопросы поднимает", reference.questions)}
          ${aromaSection("Действие на НПС", reference.nps_effect)}
          ${renderCollapsibleSection("Терапевтические свойства", reference.therapeutic_properties, 280)}
          ${renderCollapsibleSection("Влияние на здоровье", reference.health_effects)}
          ${renderCollapsibleSection("Влияние на ум", reference.mind_effect)}
          ${renderCollapsibleSection("Духовное и эмоциональное воздействие", reference.spiritual_emotional)}
          ${renderCollapsibleSection("При каких состояниях", reference.conditions_for_use)}
          ${compChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compChips}</div></section>` : ""}
          ${blendsChips ? `<section class="section"><h3>🌀 Входит в смеси</h3><div class="detail-preview">${blendsChips}</div></section>` : ""}
          ${symptomChips ? `<section class="section"><h3>💊 Помогает при</h3><div class="detail-preview">${symptomChips}</div></section>` : ""}
          ${renderApplicationsWithIcons(reference.applications)}
          ${renderStructuredList("Меры предосторожности", reference.precautions)}
          ${aromaSection("Материалы курса", reference.course_notes)}
          ${renderCollapsibleSection("Исторические сведения", reference.history, 280)}
        </div>
      `;
    }
    elements.draftDetail.innerHTML = detailHtml;
    // Init audio player for sound cards
    const playerEl = elements.draftDetail.querySelector(".sound-player");
    if (playerEl) initSoundPlayer(playerEl);
    if (window.lucide) lucide.createIcons();
    syncMobileNavigation();
  }

  /* ── Smart Search ── */

  function renderSmartSearchHero() {
    return `
      <div class="smart-search-hero">
        <div class="smart-search-bar" id="smartSearchBar">
          <span class="smart-search-icon"><svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.5"/><line x1="10" y1="10" x2="13.5" y2="13.5"/></svg></span>
          <input type="text" class="smart-search-input" id="smartSearchInput"
            placeholder="\u0420\u0430\u0441\u0441\u043b\u0430\u0431\u043b\u0435\u043d\u0438\u0435, \u0442\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e, \u043d\u0430\u0441\u043c\u043e\u0440\u043a, \u0441\u0442\u0440\u0435\u0441\u0441..."
            oninput="handleSmartSearch(this.value)"
            onkeydown="if(event.key==='Enter') runSmartSearch(this.value)">
          <button class="smart-search-clear" id="smartSearchClear" onclick="clearSmartSearch()" hidden>\u2715</button>
        </div>
        <button class="blend-constructor-cta" onclick="openBlendConstructor()">\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c \u043f\u043e\u0434 \u0437\u0430\u0434\u0430\u0447\u0443</button>
        <button class="my-blends-btn" onclick="openSavedBlends()">\u2665 \u0421\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u043e\u0435</button>
      </div>`;
  }

  async function loadAllReferencesForSearch() {
    const tabs = ["aromas", "blends", "symptoms"];
    const promises = tabs.filter(t => !_searchCache[t]).map(async (tabId) => {
      const meta = HANDBOOK_CATEGORY_META[tabId];
      if (!meta) return;
      try {
        const data = await fetchJson(`/api/references/${meta.category}`);
        _searchCache[tabId] = (data.items || []).map(i => ({...i, _type: tabId.replace(/s$/, "")}));
      } catch { _searchCache[tabId] = []; }
    });
    await Promise.all(promises);
  }

  function handleSmartSearch(value) {
    clearTimeout(_smartSearchDebounce);
    const clearBtn = document.getElementById("smartSearchClear");
    if (clearBtn) clearBtn.hidden = !value.trim();
    _smartSearchDebounce = setTimeout(() => {
      if (value.trim().length >= 2) runSmartSearch(value);
      else if (!value.trim()) clearSmartSearch();
    }, 300);
  }

  async function runSmartSearch(query) {
    if (!query.trim()) { clearSmartSearch(); return; }
    const input = document.getElementById("smartSearchInput");
    if (input && input.value !== query) input.value = query;
    const clearBtn = document.getElementById("smartSearchClear");
    if (clearBtn) clearBtn.hidden = false;

    await loadAllReferencesForSearch();
    const q = query.toLowerCase();
    const allItems = [
      ...(_searchCache.aromas || []),
      ...(_searchCache.blends || []),
      ...(_searchCache.symptoms || []),
    ];
    const scored = allItems.map(item => {
      let score = 0;
      const fields = [
        item.name, item.name_en, item.name_ru,
        item.description, item.description_short,
        item.therapeutic_properties, item.indications,
        item.key_theme, item.conditions_for_use,
        ...(item.alt_names || []),
      ].filter(Boolean).map(f => String(f).toLowerCase());
      fields.forEach(f => {
        if (f === q) score += 10;
        else if (f.startsWith(q)) score += 7;
        else if (f.includes(q)) score += 3;
      });
      return {...item, _score: score};
    }).filter(i => i._score > 0);
    const currentType = state.tab.replace(/s$/, "");
    scored.sort((a, b) => {
      const aMatch = a._type === currentType ? 1 : 0;
      const bMatch = b._type === currentType ? 1 : 0;
      if (aMatch !== bMatch) return bMatch - aMatch;
      return b._score - a._score;
    });
    renderSearchResults(scored, query);
  }

  function renderSearchResults(items, query) {
    const listContainer = document.getElementById("referenceListContainer");
    if (!listContainer) return;
    const filterChipsEl = document.getElementById("referenceFilterChips");
    if (filterChipsEl) filterChipsEl.innerHTML = "";
    elements.draftCount.textContent = `${items.length} \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u0432 \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443 \u00ab${query}\u00bb`;
    if (items.length === 0) {
      listContainer.innerHTML = `<div class="search-empty"><p>\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e.</p>
        <button class="blend-constructor-cta" onclick="openBlendConstructor('${escapeHtml(query)}')">\ud83e\uddea \u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c \u043f\u043e\u0434 \u044d\u0442\u0443 \u0437\u0430\u0434\u0430\u0447\u0443 \u2197</button></div>`;
      return;
    }
    const groupLabels = {aroma: "\u0410\u0440\u043e\u043c\u0430\u0442\u044b", blend: "\u0421\u043c\u0435\u0441\u0438", symptom: "\u0421\u0438\u043c\u043f\u0442\u043e\u043c\u044b"};
    let lastType = null;
    const cardsHtml = items.slice(0, 50).map(item => {
      let header = "";
      if (item._type !== lastType) {
        header = `<div class="search-group-header">${groupLabels[item._type] || item._type}</div>`;
        lastType = item._type;
      }
      return header + renderSearchResultCard(item);
    }).join("");
    listContainer.innerHTML = `<div class="search-results-header">${items.length} \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u0432</div>${cardsHtml}`;
  }

  function renderSearchResultCard(item) {
    const typeLabels = {aroma: "\u043c\u0430\u0441\u043b\u043e", blend: "\u0441\u043c\u0435\u0441\u044c", symptom: "\u0441\u0438\u043c\u043f\u0442\u043e\u043c"};
    const typeIcons = {aroma: "\ud83c\udf3f", blend: "\ud83e\uddea", symptom: "\ud83e\ude7a"};
    const typeLabel = typeLabels[item._type] || item._type;
    const typeIcon = typeIcons[item._type] || "";
    const tabId = item._type + "s";
    const name = item.name_ru || item.name || "";
    return `<article ${interactiveCardAttrs("\u041e\u0442\u043a\u0440\u044b\u0442\u044c " + name)} class="draft-card overview-card interactive-card"
      onclick='openReference(${JSON.stringify(item.slug)}, ${JSON.stringify(tabId)})'>
      <div class="overview-card-top"><span class="search-type-badge">${typeIcon} ${escapeHtml(typeLabel)}</span></div>
      <h3 class="draft-topic">${escapeHtml(name)}</h3>
      ${item.name_en ? `<div class="reference-name-en">${escapeHtml(item.name_en)}</div>` : ""}
      <div class="draft-preview">${escapeHtml(stripMarkdown(item.description_short || item.description || item.indications || "").slice(0, 100))}...</div>
    </article>`;
  }

  function clearSmartSearch() {
    const input = document.getElementById("smartSearchInput");
    if (input) input.value = "";
    const clearBtn = document.getElementById("smartSearchClear");
    if (clearBtn) clearBtn.hidden = true;
    renderReferences();
  }

  /* ── Blend Constructor ── */

  let _blendState = null;

  function openBlendConstructor(prefill = "") {
    enterDetailView();
    const effects = ["\u043a\u043e\u043d\u0446\u0435\u043d\u0442\u0440\u0430\u0446\u0438\u044f","\u0442\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e","\u0440\u0430\u0441\u0441\u043b\u0430\u0431\u043b\u0435\u043d\u0438\u0435","\u044d\u043d\u0435\u0440\u0433\u0438\u044f","\u0441\u043e\u043d","\u0431\u0430\u043b\u0430\u043d\u0441","\u0437\u0430\u0449\u0438\u0442\u0430"];
    const speeds = [["\u0431\u044b\u0441\u0442\u0440\u043e\u0435","fast"],["\u0441\u0440\u0435\u0434\u043d\u0435\u0435","medium"],["\u043f\u0440\u043e\u043b\u043e\u043d\u0433\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435","extended"]];
    const apps = [["\u0414\u0438\u0444\u0444\u0443\u0437\u043e\u0440","diffuser"],["\u041d\u0430\u043d\u0435\u0441\u0435\u043d\u0438\u0435","topical"],["\u0412\u043d\u0443\u0442\u0440\u044c","internal"],["\u041b\u044e\u0431\u043e\u0439","any"]];
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      <p class="eyebrow">\u041a\u041e\u041d\u0421\u0422\u0420\u0423\u041a\u0422\u041e\u0420 \u0421\u041c\u0415\u0421\u0418</p>
      <h2 class="detail-title">\u041e\u043f\u0438\u0448\u0438\u0442\u0435 \u0437\u0430\u0434\u0430\u0447\u0443</h2>
      <section class="section"><label class="field-label">\u0427\u0442\u043e \u043d\u0443\u0436\u043d\u043e \u043e\u0442 \u0441\u043c\u0435\u0441\u0438?
        <textarea id="blendBrief" class="field-textarea" placeholder="\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0441\u043c\u0435\u0441\u044c \u0434\u043b\u044f \u043a\u043e\u043d\u0446\u0435\u043d\u0442\u0440\u0430\u0446\u0438\u0438 \u0438 \u0442\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u0430" oninput="updateConstructBtn()">${escapeHtml(prefill)}</textarea>
      </label></section>
      <section class="section"><h3>\u0416\u0435\u043b\u0430\u0435\u043c\u044b\u0439 \u044d\u0444\u0444\u0435\u043a\u0442</h3>
        <div class="chip-list">${effects.map(e => `<button class="chip chip-selectable" data-effect="${e}" onclick="toggleEffect(this)">${e}</button>`).join("")}</div>
        <input type="text" id="blendCustomEffect" class="field-input" style="margin-top:8px" placeholder="\u0421\u0432\u043e\u0439 \u044d\u0444\u0444\u0435\u043a\u0442, \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0431\u043e\u0434\u0440\u043e\u0441\u0442\u044c \u0441 \u0443\u0442\u0440\u0430">
      </section>
      <section class="section"><h3>\u0421\u043a\u043e\u0440\u043e\u0441\u0442\u044c \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f</h3>
        <div class="radio-row">${speeds.map(([l,v]) => `<button class="chip chip-selectable ${v==="medium"?"is-selected":""}" data-speed="${v}" onclick="selectSpeed(this)">${l}</button>`).join("")}</div>
      </section>
      <section class="section"><h3>\u0421\u043f\u043e\u0441\u043e\u0431 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u0438\u044f</h3>
        <div class="radio-row">${apps.map(([l,v]) => `<button class="chip chip-selectable ${v==="any"?"is-selected":""}" data-app="${v}" onclick="selectApp(this)">${l}</button>`).join("")}</div>
      </section>
      <section class="section"><label class="field-label">\u041f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043a\u0430\u0437\u0430\u043d\u0438\u044f (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)
        <input type="text" id="blendContra" placeholder="\u0411\u0435\u0440\u0435\u043c\u0435\u043d\u043d\u043e\u0441\u0442\u044c, \u0430\u043b\u043b\u0435\u0440\u0433\u0438\u044f, \u0434\u0435\u0442\u0438..." class="field-input">
      </label></section>
      <button class="primary-button" id="constructBtn" onclick="submitBlendConstructor(this)" ${!prefill ? "disabled" : ""}>\u041f\u043e\u0434\u043e\u0431\u0440\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
    </div>`;
  }

  function toggleEffect(btn) { btn.classList.toggle("is-selected"); }
  function selectSpeed(btn) { btn.closest(".radio-row").querySelectorAll(".chip-selectable").forEach(c => c.classList.remove("is-selected")); btn.classList.add("is-selected"); }
  function selectApp(btn) { btn.closest(".radio-row").querySelectorAll(".chip-selectable").forEach(c => c.classList.remove("is-selected")); btn.classList.add("is-selected"); }
  function updateConstructBtn() { const btn = document.getElementById("constructBtn"); const brief = document.getElementById("blendBrief"); if (btn && brief) btn.disabled = !brief.value.trim(); }

  function submitBlendConstructor(btn) {
    const brief = document.getElementById("blendBrief")?.value.trim();
    if (!brief) return;
    const effects = [...document.querySelectorAll(".chip-selectable.is-selected[data-effect]")].map(c => c.dataset.effect);
    const customEffect = document.getElementById("blendCustomEffect")?.value.trim();
    if (customEffect) effects.push(customEffect);
    const speed = document.querySelector("[data-speed].is-selected")?.dataset.speed || "medium";
    const application = document.querySelector("[data-app].is-selected")?.dataset.app || "any";
    const contraindications = document.getElementById("blendContra")?.value.trim() || "";
    btn.disabled = true;
    btn.textContent = "\u0413\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u044e \u0441\u043c\u0435\u0441\u044c...";
    fetchJson("/api/blend-constructor/construct", {
      method: "POST",
      body: JSON.stringify({brief, effects, speed, application, contraindications}),
    }).then(result => {
      _blendState = { origRequest: {brief, effects, speed, application, contraindications} };
      renderBlendResult(result);
    }).catch(() => {
      btn.disabled = false;
      btn.textContent = "\u041f\u043e\u0434\u043e\u0431\u0440\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c";
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c.", "error");
    });
  }

  /* ── Blend Result ── */

  function renderBlendResult(result) {
    _blendState = Object.assign(_blendState || {}, { oils: result.oils.map(o => ({...o, active: true, _origDrops: o.drops})), result });
    const blendState = _blendState;
    function recalcDrops() {
      const active = blendState.oils.filter(o => o.active);
      if (!active.length) return;
      const sum = active.reduce((s, o) => s + o.drops, 0);
      const target = result.total_drops;
      const scale = target / sum;
      active.forEach(o => { o.displayDrops = Math.max(1, Math.round(o.drops * scale)); });
      const tot = active.reduce((s, o) => s + (o.displayDrops || o.drops), 0);
      const diff = target - tot;
      if (diff !== 0) active[0].displayDrops = (active[0].displayDrops || active[0].drops) + diff;
    }
    function renderOils() {
      return blendState.oils.map(o => {
        const d = o.displayDrops || o.drops;
        const changed = o.active && d !== o._origDrops;
        const id = o.db_id || o.name_ru;
        return `<div class="oil-edit-row ${o.active ? "" : "is-removed"}">
          <button class="oil-edit-toggle ${o.active ? "is-on" : "is-off"}" onclick="blendToggleOil('${escapeHtml(id)}')">${o.active ? "\u2713" : "\u2715"}</button>
          <span class="oil-edit-name">${escapeHtml(o.name_ru)}</span>
          <span class="oil-edit-drops ${changed ? "is-recalculated" : ""}">${o.active ? d + " \u043a\u0430\u043f." : "\u2014"}</span>
          <span class="oil-edit-role">${escapeHtml(o.role)}</span>
        </div>`;
      }).join("");
    }
    function renderProfileBars(p) {
      return [["\u041a\u043e\u043d\u0446\u0435\u043d\u0442\u0440\u0430\u0446\u0438\u044f","focus"],["\u0422\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e","creativity"],["\u042d\u043d\u0435\u0440\u0433\u0438\u044f","energy"],["\u0421\u043f\u043e\u043a\u043e\u0439\u0441\u0442\u0432\u0438\u0435","calm"]]
        .filter(([, k]) => (p[k] || 0) > 0)
        .map(([lbl, k]) => `<div class="profile-bar-row"><div class="profile-bar-label"><span>${lbl}</span><span>${p[k]}%</span></div><div class="profile-bar"><div class="profile-bar-fill" style="width:${p[k]}%"></div></div></div>`).join("");
    }
    window.blendToggleOil = (oilId) => {
      const oil = blendState.oils.find(o => (o.db_id || o.name_ru) === oilId);
      if (!oil) return;
      if (oil.active && blendState.oils.filter(o => o.active).length <= 1) return;
      oil.active = !oil.active;
      recalcDrops();
      rerender();
    };
    function rerender() {
      const active = blendState.oils.filter(o => o.active);
      const total = active.reduce((s, o) => s + (o.displayDrops || o.drops), 0);
      const el = (id) => document.getElementById(id);
      if (el("blendOilsList")) el("blendOilsList").innerHTML = renderOils();
      if (el("blendTotalDrops")) el("blendTotalDrops").textContent = total;
      if (el("blendTotalLabel")) el("blendTotalLabel").textContent = `${total} \u043a\u0430\u043f. \u00b7 10 \u043c\u043b \u0431\u0430\u0437\u044b`;
      if (el("blendProfileBars")) el("blendProfileBars").innerHTML = renderProfileBars(result.profile);
      const warn = el("blendWarn");
      if (warn) { warn.hidden = active.length > 1; if (active.length === 1) warn.textContent = "\u041e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u043e\u0434\u043d\u043e \u043c\u0430\u0441\u043b\u043e \u2014 \u0441\u0438\u043d\u0435\u0440\u0433\u0438\u044f \u043f\u043e\u0442\u0435\u0440\u044f\u043d\u0430."; }
    }
    recalcDrops();
    const p = result.profile || {};
    const totalDrops = blendState.oils.filter(o => o.active).reduce((s, o) => s + (o.displayDrops || o.drops), 0);
    const safetyColor = {safe: "var(--good)", caution: "var(--brand)", warning: "var(--bad)"}[result.safety_status] || "var(--good)";
    const safetyLabel = {safe: "\u2713 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e", caution: "\u26a0 \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e", warning: "\u26d4 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f"}[result.safety_status] || "\u2713 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e";
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      <p class="eyebrow">\u041a\u041e\u041d\u0421\u0422\u0420\u0423\u041a\u0422\u041e\u0420 \u0421\u041c\u0415\u0421\u0418</p>
      <h2 class="detail-title">${escapeHtml(result.title)}</h2>
      <div class="draft-meta">${(result.tags || []).map(t => tagMarkup(t, "brand")).join("")}</div>
      <section class="section">
        <h3>\ud83d\udccb \u0420\u0435\u0446\u0435\u043f\u0442 \u00b7 <span id="blendTotalDrops">${totalDrops}</span> \u043a\u0430\u043f. <span class="section-hint">\u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u2713 \u0447\u0442\u043e\u0431\u044b \u0443\u0431\u0440\u0430\u0442\u044c \u043c\u0430\u0441\u043b\u043e</span></h3>
        <div id="blendOilsList">${renderOils()}</div>
        <div class="blend-total-row"><span>\u0418\u0442\u043e\u0433\u043e:</span><span id="blendTotalLabel">${totalDrops} \u043a\u0430\u043f. \u00b7 10 \u043c\u043b \u0431\u0430\u0437\u044b</span></div>
      </section>
      <div class="field-help blend-warn" id="blendWarn" hidden></div>
      <section class="section"><h3>\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0441\u043c\u0435\u0441\u0438</h3><div id="blendProfileBars">${renderProfileBars(p)}</div></section>
      <div class="blend-expert-card blend-expert-aroma">
        <div class="blend-expert-header"><span class="blend-expert-icon">\ud83c\udf3f</span><div><div class="blend-expert-name">\u042d\u043a\u0441\u043f\u0435\u0440\u0442-\u0430\u0440\u043e\u043c\u0430\u0442\u0435\u0440\u0430\u043f\u0435\u0432\u0442</div><div class="blend-expert-sub">\u0421\u0438\u043d\u0435\u0440\u0433\u0438\u044f \u043c\u0430\u0441\u0435\u043b</div></div></div>
        <p class="blend-expert-text">${escapeHtml(result.expert_note)}</p>
        ${result.application_guide ? `<div class="blend-application"><span class="blend-application-label">\u041a\u0430\u043a \u043f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c:</span> ${escapeHtml(result.application_guide)}</div>` : ""}
      </div>
      <div class="blend-expert-card blend-expert-doctor">
        <div class="blend-expert-header"><span class="blend-expert-icon">\u2695\ufe0f</span><div><div class="blend-expert-name">\u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430</div></div><span class="blend-safety-badge" style="color:${safetyColor}">${safetyLabel}</span></div>
        <p class="blend-expert-text">${escapeHtml(result.doctor_note)}</p>
        ${result.restrictions?.length ? `<div class="blend-restrictions">${result.restrictions.map(r => `<div class="blend-restriction-row"><span class="chip chip-bad">${escapeHtml(r.condition)}</span><span>\u0438\u0441\u043a\u043b\u044e\u0447\u0438\u0442\u044c ${(r.oils_to_exclude || []).join(", ")}</span></div>`).join("")}</div>` : ""}
      </div>
      ${result.incompatible_oils?.length ? `<section class="section section-warning"><h3>\u26a0\ufe0f \u041d\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u044f\u0442\u044c \u0432 \u044d\u0442\u0443 \u0441\u043c\u0435\u0441\u044c</h3>${result.incompatible_oils.map(o => `<div class="incompat-row"><span class="chip chip-bad">${escapeHtml(o.name_ru)}</span><span>${escapeHtml(o.reason)}</span></div>`).join("")}</section>` : ""}
      <section class="section section-adjust">
        <h3>\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0432\u043e\u0451 \u043c\u0430\u0441\u043b\u043e</h3>
        <p class="field-help">\u0423\u043a\u0430\u0436\u0438\u0442\u0435 \u043c\u0430\u0441\u043b\u043e \u2014 \u0418\u0418 \u043f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442 \u0441\u043c\u0435\u0441\u044c \u0441 \u0435\u0433\u043e \u0443\u0447\u0451\u0442\u043e\u043c</p>
        <div class="blend-adjust-row">
          <input type="text" id="blendCustomOilInput" class="field-input" placeholder="\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u041b\u0430\u0432\u0430\u043d\u0434\u0430">
          <button class="secondary-button" id="blendAdjustBtn" type="button" onclick="blendAdjustWithOil(this)">\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c</button>
        </div>
        <button class="secondary-button" id="blendRegenBtn" type="button" style="margin-top:8px;width:100%" onclick="blendRegenerate(this)">\u041f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
      </section>
      <div class="blend-actions-stack">
        <div class="actions-grid-two">
          <button class="primary-button" id="blendSaveBtn" type="button" onclick="blendSaveCurrentBlend(this)">\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
          <button class="secondary-button" type="button" onclick="blendCreateContent()">\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043a\u043e\u043d\u0442\u0435\u043d\u0442</button>
        </div>
        <div id="blendContentPicker" hidden style="margin-top:6px">
          <p class="field-help" style="margin-bottom:6px">\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0444\u043e\u0440\u043c\u0430\u0442:</p>
          <div class="chip-list">
            <button class="chip chip-selectable" onclick="blendLaunchContent('content')">\u041f\u043e\u0441\u0442</button>
            <button class="chip chip-selectable" onclick="blendLaunchContent('threads_series')">\u0421\u0435\u0440\u0438\u044f Threads</button>
            <button class="chip chip-selectable" onclick="blendLaunchContent('carousel')">\u041a\u0430\u0440\u0443\u0441\u0435\u043b\u044c</button>
          </div>
        </div>
        <div class="actions-grid-two">
          <button class="secondary-button" onclick="openBlendConstructor()">\u041d\u043e\u0432\u0430\u044f \u0441\u043c\u0435\u0441\u044c</button>
          <button class="secondary-button" onclick="clearSmartSearch()">\u041a \u0431\u0430\u0437\u0435</button>
        </div>
      </div>
    </div>`;
  }

  async function openSavedBlends() {
    enterDetailView();
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      <p class="eyebrow">\u0421\u041e\u0425\u0420\u0410\u041d\u0401\u041d\u041d\u042b\u0415 \u0421\u041c\u0415\u0421\u0418</p>
      <div id="savedBlendsList" class="saved-blends-list"><p class="field-help">\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</p></div>
      <button class="primary-button" onclick="openBlendConstructor()">\u041d\u043e\u0432\u0430\u044f \u0441\u043c\u0435\u0441\u044c</button>
    </div>`;
    try {
      const data = await fetchJson("/api/blend-constructor/saved");
      const items = data.items || [];
      const el = document.getElementById("savedBlendsList");
      if (!el) return;
      if (!items.length) {
        el.innerHTML = `<p class="field-help">\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u044b\u0445 \u0441\u043c\u0435\u0441\u0435\u0439</p>`;
        return;
      }
      el.innerHTML = items.map(b => `
        <div class="saved-blend-card">
          <h3>${escapeHtml(b.title)}</h3>
          ${b.brief ? `<p class="field-help">${escapeHtml(b.brief)}</p>` : ""}
          <div class="draft-meta">${(b.tags || []).map(t => tagMarkup(t, "brand")).join("")}</div>
          <div class="saved-blend-oils">${(b.oils || []).map(o => `${escapeHtml(o.name_ru)} ${o.drops}\u043a.`).join(" \u00b7 ")}</div>
          <button class="danger-button" style="margin-top:6px" onclick="deleteSavedBlend('${escapeHtml(b.id || b._id)}',this)">\u0423\u0434\u0430\u043b\u0438\u0442\u044c</button>
        </div>`).join("");
    } catch {
      const el = document.getElementById("savedBlendsList");
      if (el) el.innerHTML = `<p class="field-help">\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c</p>`;
    }
  }

  async function deleteSavedBlend(id, btn) {
    if (btn) { btn.disabled = true; btn.textContent = "\u0423\u0434\u0430\u043b\u044f\u044e..."; }
    try {
      await fetchJson(`/api/blend-constructor/saved/${id}`, { method: "DELETE" });
      showUiNotice("\u0421\u043c\u0435\u0441\u044c \u0443\u0434\u0430\u043b\u0435\u043d\u0430", "success");
      openSavedBlends();
    } catch {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c", "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u0423\u0434\u0430\u043b\u0438\u0442\u044c"; }
    }
  }

  function blendSaveCurrentBlend(btn) {
    if (!_blendState?.result) return;
    const r = _blendState.result;
    const req = _blendState.origRequest || {};
    if (btn) { btn.disabled = true; btn.textContent = "\u0421\u043e\u0445\u0440\u0430\u043d\u044f\u044e..."; }
    fetchJson("/api/blend-constructor/saved", {
      method: "POST",
      body: JSON.stringify({
        title: r.title,
        brief: req.brief || "",
        tags: r.tags || [],
        oils: (_blendState.oils || r.oils).filter(o => o.active !== false).map(o => ({name_ru: o.name_ru, name_en: o.name_en, drops: o.displayDrops || o.drops, role: o.role})),
        total_drops: r.total_drops,
        profile: r.profile || {},
        expert_note: r.expert_note || "",
        application_guide: r.application_guide || "",
        safety_status: r.safety_status || "safe",
      }),
    }).then(() => {
      showUiNotice("\u0421\u043c\u0435\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430", "success");
      if (btn) { btn.textContent = "\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e"; }
    }).catch(() => {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c", "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c"; }
    });
  }

  function blendCreateContent() {
    const picker = document.getElementById("blendContentPicker");
    if (picker) picker.hidden = !picker.hidden;
  }

  function blendLaunchContent(toolId) {
    if (!_blendState?.result) return;
    const r = _blendState.result;
    const req = _blendState.origRequest || {};
    const oilsList = (_blendState.oils || r.oils).filter(o => o.active !== false).map(o => `${o.name_ru} ${o.displayDrops || o.drops} \u043a\u0430\u043f.`).join(", ");
    const topic = `${r.title}${req.brief ? ": " + req.brief : ""}. \u0421\u043e\u0441\u0442\u0430\u0432: ${oilsList}.`;
    if (typeof window.openCreateTool === "function") window.openCreateTool(toolId);
    let attempts = 0;
    const tryFill = () => {
      attempts++;
      const selectors = ["[data-create-content] [name=topic]", "[data-create-threads-series] [name=topic]", "[data-create-carousel] [name=topic]", "#createForm textarea"];
      for (const sel of selectors) {
        const ta = document.querySelector(sel);
        if (ta && !ta.value) { ta.value = topic; ta.dispatchEvent(new Event("input")); return; }
      }
      if (attempts < 15) setTimeout(tryFill, 80);
    };
    setTimeout(tryFill, 80);
  }

  function blendRegenerate(btn) {
    if (!_blendState?.origRequest) return;
    const req = _blendState.origRequest;
    const prevResult = _blendState.result;
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      ${renderDetailLoader("\u041f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u044e \u0441\u043c\u0435\u0441\u044c", "\u0421\u043e\u0441\u0442\u0430\u0432\u043b\u044f\u044e \u043d\u043e\u0432\u044b\u0439 \u0432\u0430\u0440\u0438\u0430\u043d\u0442 \u0440\u0435\u0446\u0435\u043f\u0442\u0430 \u0441 \u0442\u0435\u043c\u0438 \u0436\u0435 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u0430\u043c\u0438.")}
    </div>`;
    fetchJson("/api/blend-constructor/construct", {
      method: "POST",
      body: JSON.stringify(req),
    }).then(result => {
      renderBlendResult(result);
    }).catch(() => {
      if (prevResult) renderBlendResult(prevResult);
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437.", "error");
    });
  }

  function blendAdjustWithOil(btn) {
    const input = document.getElementById("blendCustomOilInput");
    const oil = input?.value.trim();
    if (!oil || !_blendState?.origRequest) return;
    const req = _blendState.origRequest;
    if (btn) { btn.disabled = true; btn.textContent = "\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u044e..."; }
    fetchJson("/api/blend-constructor/adjust", {
      method: "POST",
      body: JSON.stringify({...req, custom_oils: [oil]}),
    }).then(result => {
      _blendState.origRequest = {...req, custom_oils: [oil]};
      renderBlendResult(result);
    }).catch(() => {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c", "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c"; }
    });
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

  async function shareBlend(savedId, title) {
    const shareUrl = `https://t.me/aromara_bot?start=blend_${savedId}`;
    const shareText = `${title || "\u0421\u043c\u0435\u0441\u044c"} \u2014 \u0441\u043e\u0437\u0434\u0430\u043d\u043e \u0432 Aroma Trends`;
    if (navigator.share) {
      try {
        await navigator.share({ title: shareText, url: shareUrl });
        return;
      } catch { /* user cancelled — fall through to clipboard */ }
    }
    try {
      await navigator.clipboard.writeText(shareUrl);
      showUiNotice("\u0421\u0441\u044b\u043b\u043a\u0430 \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0430", "success");
    } catch {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443", "error");
    }
  }

  async function openSharedBlend(savedId) {
    enterDetailView();
    elements.draftDetail.innerHTML = `<div class="detail-grid">${renderDetailLoader()}</div>`;
    try {
      const blend = await fetchJson(`/api/blend-constructor/shared/${savedId}`);
      const safetyColors = { safe: "#22c55e", caution: "#f59e0b", warning: "#ef4444" };
      const safetyLabels = { safe: "\u0411\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e", caution: "\u041e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e", warning: "\u041e\u043f\u0430\u0441\u043d\u043e" };
      const safetyColor = safetyColors[blend.safety_status] || safetyColors.safe;
      const safetyLabel = safetyLabels[blend.safety_status] || blend.safety_status;
      function renderProfileBars(profile) {
        if (!profile || !Object.keys(profile).length) return "";
        const labels = { focus: "\u0424\u043e\u043a\u0443\u0441", energy: "\u042d\u043d\u0435\u0440\u0433\u0438\u044f", creativity: "\u0422\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e", calm: "\u0421\u043f\u043e\u043a\u043e\u0439\u0441\u0442\u0432\u0438\u0435" };
        return Object.entries(profile).map(([k, v]) => `<div class="profile-bar-row"><span class="profile-bar-label">${escapeHtml(labels[k] || k)}</span><div class="profile-bar-track"><div class="profile-bar-fill" style="width:${v}%"></div></div><span class="profile-bar-value">${v}</span></div>`).join("");
      }
      elements.draftDetail.innerHTML = `<div class="detail-grid">
        ${renderBackButton()}
        <p class="eyebrow">\u0421\u041c\u0415\u0421\u042c</p>
        <h2>${escapeHtml(blend.title)}</h2>
        ${blend.brief ? `<p class="field-help">${escapeHtml(blend.brief)}</p>` : ""}
        ${(blend.tags || []).length ? `<div class="draft-meta">${blend.tags.map(t => tagMarkup(t, "brand")).join("")}</div>` : ""}
        <section class="section">
          <h3>\ud83d\udccb \u0420\u0435\u0446\u0435\u043f\u0442 \u00b7 ${blend.total_drops} \u043a\u0430\u043f.</h3>
          <div class="saved-blend-oils-detail">${(blend.oils || []).map(o => `<div class="oil-row"><span class="oil-name">${escapeHtml(o.name_ru)}${o.name_en ? ` <span class="oil-name-en">${escapeHtml(o.name_en)}</span>` : ""}</span><span class="oil-drops">${o.drops} \u043a\u0430\u043f.</span>${o.role ? `<span class="oil-role">${escapeHtml(o.role)}</span>` : ""}</div>`).join("")}</div>
          <div class="blend-total-row"><span>\u0418\u0442\u043e\u0433\u043e:</span><span>${blend.total_drops} \u043a\u0430\u043f. \u00b7 10 \u043c\u043b \u0431\u0430\u0437\u044b</span></div>
        </section>
        ${Object.keys(blend.profile || {}).length ? `<section class="section"><h3>\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0441\u043c\u0435\u0441\u0438</h3>${renderProfileBars(blend.profile)}</section>` : ""}
        ${blend.expert_note ? `<div class="blend-expert-card blend-expert-aroma"><div class="blend-expert-header"><span class="blend-expert-icon">\ud83c\udf3f</span><div><div class="blend-expert-name">\u042d\u043a\u0441\u043f\u0435\u0440\u0442-\u0430\u0440\u043e\u043c\u0430\u0442\u0435\u0440\u0430\u043f\u0435\u0432\u0442</div></div></div><p class="blend-expert-text">${escapeHtml(blend.expert_note)}</p>${blend.application_guide ? `<div class="blend-application"><span class="blend-application-label">\u041a\u0430\u043a \u043f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c:</span> ${escapeHtml(blend.application_guide)}</div>` : ""}</div>` : ""}
        <div class="blend-expert-card blend-expert-doctor"><div class="blend-expert-header"><span class="blend-expert-icon">\u2695\ufe0f</span><div><div class="blend-expert-name">\u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430</div></div><span class="blend-safety-badge" style="color:${safetyColor}">${safetyLabel}</span></div></div>
      </div>`;
      if (window.lucide) lucide.createIcons();
    } catch {
      elements.draftDetail.innerHTML = `<div class="detail-grid">${renderBackButton()}<p class="field-help">\u0421\u043c\u0435\u0441\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430 \u0438\u043b\u0438 \u0431\u044b\u043b\u0430 \u0443\u0434\u0430\u043b\u0435\u043d\u0430</p></div>`;
    }
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
    handleSmartSearch,
    runSmartSearch,
    clearSmartSearch,
    openBlendConstructor,
    toggleEffect,
    selectSpeed,
    selectApp,
    updateConstructBtn,
    submitBlendConstructor,
    blendSaveCurrentBlend,
    blendCreateContent,
    blendLaunchContent,
    blendRegenerate,
    blendAdjustWithOil,
    openSavedBlends,
    deleteSavedBlend,
    shareBlend,
    openSharedBlend,
  };
}
