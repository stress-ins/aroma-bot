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
  let _dailyOilData = null;
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
  let _filtersExpanded = false;

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

  async function openReference(slug, tabId = state.tab, { quiet = false } = {}) {
    const meta = HANDBOOK_CATEGORY_META[tabId];
    if (!slug || !meta) return;
    if (!quiet) {
      elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю карточку справочника")}`;
      enterDetailView();
    }
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
        return `<button class="crossref-chip" data-action="openReference" data-args='${JSON.stringify([slug, targetTab])}'>${icon ? `<span class="chip-icon">${icon}</span>` : ''}${escapeHtml(display)}</button>`;
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
        ? `<button class="crossref-chip" data-action="openReference" data-args='${JSON.stringify([slug, "aromas"])}'>${escapeHtml(displayName)}</button>`
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
    return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview exp-section-wrap"><div class="exp-collapsed">${escapeHtml(preview)}… <button class="exp-btn" data-action="expandSection" data-args='[null]'>Читать далее <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg></button></div><div class="exp-expanded" hidden>${escapeHtml(str)}</div></div></section>`;
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
      `<button class="filter-chip${allActive ? " active" : ""}" data-action="setReferenceFilter" data-args='[""]'>Все</button>`,
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
        return `<button class="filter-chip${isActive ? " active" : ""}" data-action="setReferenceFilter" data-args='${JSON.stringify([v])}'>${escapeHtml(label)}</button>`;
      }),
    ];
    if (!_filtersExpanded && values.length > 0) {
      const toggleLabel = `Ещё ${values.length}`;
      return `<div class="filter-chips filter-chips-collapsed">${chips[0]}<button class="filter-chip filter-toggle" data-action="toggleReferenceFilters" data-args='[]'>${escapeHtml(toggleLabel)}</button></div>`;
    }
    if (_filtersExpanded && values.length > 0) {
      return `<div class="filter-chips">${chips.join("")}<button class="filter-chip filter-toggle" data-action="toggleReferenceFilters" data-args='[]'>Свернуть</button></div>`;
    }
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
      `<button class="filter-chip${allActive ? " active" : ""}" data-action="setReferenceFilter" data-args='[""]'>Все</button>`,
      ...parentGroups.map((p) => {
        const icon = SYMPTOM_PARENT_GROUP_ICONS?.[p] ? SYMPTOM_PARENT_GROUP_ICONS[p] + "\u00a0" : "";
        const isActive = activeParent === p || activeFilter === p;
        return `<button class="filter-chip${isActive ? " active" : ""}" data-action="setSymptomParentFilter" data-args='${JSON.stringify([p])}'>${escapeHtml(icon + toSentenceCase(p))}</button>`;
      }),
    ];

    let childChips = "";
    if (activeParent && childrenByParent[activeParent]?.size > 0) {
      const children = [...childrenByParent[activeParent]];
      const childButtons = children.map((c) => {
        const isActive = activeFilter === c;
        return `<button class="filter-chip filter-chip--child${isActive ? " active" : ""}" data-action="setReferenceFilter" data-args='${JSON.stringify([c])}'>${escapeHtml(toSentenceCase(c))}</button>`;
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

    const countText = query
      ? `Найдено ${filtered.length} из ${items.length}`
      : meta.count(items);

    const searchHint = meta.searchPlaceholder || "Масло, аромат, симптом...";

    /* Render inline search bar inside draftCount area */
    if (!document.getElementById("smartSearchInput")) {
      elements.draftCount.innerHTML = `
        <div class="smart-search-bar smart-search-bar--inline" id="smartSearchBar">
          <span class="smart-search-icon"><svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="6.5" cy="6.5" r="4.5"/><line x1="10" y1="10" x2="13.5" y2="13.5"/></svg></span>
          <input type="text" class="smart-search-input" id="smartSearchInput"
            placeholder="${escapeHtml(searchHint)}"
            data-on-input="handleSmartSearch" data-args='[]'
            data-on-keydown="runSmartSearch" data-keydown-guard="Enter" data-args-keydown='[]'>
          <span class="smart-search-count" id="smartSearchCount">${escapeHtml(countText)}</span>
          <button class="smart-search-clear" id="smartSearchClear" data-action="clearSmartSearch" hidden>\u2715</button>
        </div>`;
      document.getElementById("smartSearchInput")?.addEventListener("input", (e) => {
        state.referenceSearch = e.target.value;
      });
    } else {
      const searchInput = document.getElementById("smartSearchInput");
      if (searchInput) {
        searchInput.value = state.referenceSearch;
      }
      const countEl = document.getElementById("smartSearchCount");
      if (countEl) countEl.textContent = countText;
    }

    setEmptyState(filtered.length > 0, query
      ? { eyebrow: meta.title, title: "Ничего не найдено", body: "Попробуйте другой запрос или сбросьте фильтр." }
      : meta.empty);

    let listContainer = document.getElementById("referenceListContainer");
    if (!listContainer) {
      elements.draftList.innerHTML = `
        ${renderSmartSearchHero()}
        <div id="dailyOilBanner"></div>
        <div id="referenceFilterChips"></div>
        <div id="referenceListContainer" class="plans-list"></div>
      `;
      listContainer = document.getElementById("referenceListContainer");
      if (tabId === "aromas") _loadDailyOilBanner();
    }
    const filterChipsEl = document.getElementById("referenceFilterChips");
    if (filterChipsEl) filterChipsEl.innerHTML = renderFilterChips(items, tabId);

    // Hide daily oil banner when searching
    const dailyOilEl = document.getElementById("dailyOilBanner");
    if (dailyOilEl) dailyOilEl.hidden = !!query;

    listContainer.innerHTML = filtered.map((item) => `
      <article ${interactiveCardAttrs(`Открыть карточку ${item.name}`)} class="draft-card overview-card reference-card${state.tab === "concepts" ? " is-theory concept-card" : ""}${item.slug === reference?.slug ? " active" : ""} interactive-card" data-action="openReference" data-args='${JSON.stringify([item.slug, state.tab])}'>
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
      const _dOil = state._dailyOil;
      state._dailyOil = null;
      const dailyOilHtml = _dOil && (_dOil.reason || _dOil.fact || _dOil.daily_practice)
        ? `<section class="section daily-oil-detail-section">
            <h3><i data-lucide="sparkles"></i> Масло дня</h3>
            ${_dOil.reason ? `<p class="daily-oil-detail-reason">💡 ${escapeHtml(_dOil.reason)}</p>` : ""}
            ${_dOil.fact ? `<p>${escapeHtml(_dOil.fact)}</p>` : ""}
            ${_dOil.daily_practice ? `<p><strong>Практика дня:</strong> ${escapeHtml(_dOil.daily_practice)}</p>` : ""}
          </section>` : "";
      detailHtml = `
        <div class="detail-grid">
          ${renderBackButton()}
          ${renderReferenceImage(reference)}
          ${dailyOilHtml}
          ${aromaHtmlSection("Паспорт аромата", renderReferencePassport(reference))}
          ${renderCollapsibleDescription(reference)}
          ${blendsChips ? `<section class="section"><h3>🌀 Входит в смеси</h3><div class="detail-preview">${blendsChips}</div></section>` : ""}
          ${symptomChips ? `<section class="section"><h3>💊 Помогает при</h3><div class="detail-preview">${symptomChips}</div></section>` : ""}
          ${compChips ? `<section class="section"><h3>🌿 Комплементарные масла</h3><div class="detail-preview">${compChips}</div></section>` : ""}
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
          ${renderApplicationsWithIcons(reference.applications)}
          ${renderStructuredList("Меры предосторожности", reference.precautions)}
          ${aromaSection("Материалы курса", reference.course_notes)}
          ${renderCollapsibleSection("Исторические сведения", reference.history, 280)}
          <div class="actions-row" style="margin-top:var(--space-3)">
            <button class="secondary-button" type="button" data-action="createContentFromOil" data-args='${JSON.stringify([reference.name])}'><i data-lucide="plus" style="width:16px;height:16px"></i><span>Создать контент</span></button>
          </div>
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
        <button class="blend-constructor-cta" data-action="openBlendConstructor">\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c \u043f\u043e\u0434 \u0437\u0430\u0434\u0430\u0447\u0443</button>
        <button class="reco-cta-btn" data-action="openRecommendationsWizard">Подобрать масло</button>
        <button class="my-blends-btn" data-action="openSavedBlends">\u2665 \u0421\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u043e\u0435</button>
      </div>`;
  }

  async function loadAllReferencesForSearch() {
    const tabs = ["aromas", "blends", "symptoms", "concepts", "practices", "sounds"];
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
    const countEl = document.getElementById("smartSearchCount");
    if (clearBtn) clearBtn.hidden = !value.trim();
    if (countEl) countEl.hidden = !!value.trim();
    _smartSearchDebounce = setTimeout(() => {
      if (value.trim().length >= 2) runSmartSearch(value);
      else if (!value.trim()) clearSmartSearch();
    }, 300);
  }

  async function runSmartSearch(query) {
    if (!query.trim()) { clearSmartSearch(); return; }
    const input = document.getElementById("smartSearchInput");
    const clearBtn = document.getElementById("smartSearchClear");
    if (clearBtn) clearBtn.hidden = false;

    await loadAllReferencesForSearch();
    const q = query.toLowerCase();

    // Build cross-reference: find symptoms matching query, collect their recommended slugs
    const _symptomBoostSlugs = {}; // slug → [symptom names]
    for (const sym of (_searchCache.symptoms || [])) {
      const symName = (sym.name || "").toLowerCase();
      if (symName.includes(q)) {
        for (const slug of (sym.recommended_oil_slugs || [])) {
          (_symptomBoostSlugs[slug] = _symptomBoostSlugs[slug] || []).push(sym.name);
        }
        for (const slug of (sym.recommended_blend_slugs || [])) {
          (_symptomBoostSlugs[slug] = _symptomBoostSlugs[slug] || []).push(sym.name);
        }
      }
    }

    const allItems = [
      ...(_searchCache.aromas || []),
      ...(_searchCache.blends || []),
      ...(_searchCache.symptoms || []),
      ...(_searchCache.concepts || []),
      ...(_searchCache.practices || []),
      ...(_searchCache.sounds || []),
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
      // Cross-reference boost: if this item is recommended by a matching symptom
      const _matchedSymptoms = _symptomBoostSlugs[item.slug];
      if (_matchedSymptoms) {
        score += 5;
        return {...item, _score: score, _matchedSymptoms};
      }
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
    const _countEl = document.getElementById("smartSearchCount");
    if (_countEl) {
      _countEl.textContent = `${items.length} результатов`;
    } else {
      elements.draftCount.textContent = `${items.length} результатов по запросу «${query}»`;
    }
    if (items.length === 0) {
      listContainer.innerHTML = `<div class="search-empty"><p>\u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e.</p>
        <button class="blend-constructor-cta" data-action="openBlendConstructor" data-args='${JSON.stringify([query])}'>\ud83e\uddea \u0421\u043e\u0437\u0434\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c \u043f\u043e\u0434 \u044d\u0442\u0443 \u0437\u0430\u0434\u0430\u0447\u0443 \u2197</button></div>`;
      return;
    }
    const groupLabels = {aroma: "\u0410\u0440\u043e\u043c\u0430\u0442\u044b", blend: "\u0421\u043c\u0435\u0441\u0438", symptom: "\u0421\u0438\u043c\u043f\u0442\u043e\u043c\u044b", concept: "\u041a\u043e\u043d\u0446\u0435\u043f\u0446\u0438\u0438", practice: "\u041f\u0440\u0430\u043a\u0442\u0438\u043a\u0438", sound: "\u0417\u0432\u0443\u043a\u0438"};
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
    const typeLabels = {aroma: "\u043c\u0430\u0441\u043b\u043e", blend: "\u0441\u043c\u0435\u0441\u044c", symptom: "\u0441\u0438\u043c\u043f\u0442\u043e\u043c", concept: "\u043a\u043e\u043d\u0446\u0435\u043f\u0446\u0438\u044f", practice: "\u043f\u0440\u0430\u043a\u0442\u0438\u043a\u0430", sound: "\u0437\u0432\u0443\u043a"};
    const typeIcons = {aroma: "\ud83c\udf3f", blend: "\ud83e\uddea", symptom: "\ud83e\ude7a", concept: "\ud83d\udca1", practice: "\ud83d\udcbf", sound: "\ud83c\udfb5"};
    const typeLabel = typeLabels[item._type] || item._type;
    const typeIcon = typeIcons[item._type] || "";
    const tabId = item._type + "s";
    const name = item.name_ru || item.name || "";
    return `<article ${interactiveCardAttrs("\u041e\u0442\u043a\u0440\u044b\u0442\u044c " + name)} class="draft-card overview-card interactive-card"
      data-action="openReference" data-args='${JSON.stringify([item.slug, tabId])}'>
      <div class="overview-card-top"><span class="search-type-badge">${typeIcon} ${escapeHtml(typeLabel)}</span></div>
      <h3 class="draft-topic">${escapeHtml(name)}</h3>
      ${item.name_en ? `<div class="reference-name-en">${escapeHtml(item.name_en)}</div>` : ""}
      <div class="draft-preview">${escapeHtml(stripMarkdown(item.description_short || item.description || item.indications || "").slice(0, 100))}...</div>
      ${item._matchedSymptoms ? `<span class="search-symptom-tag">Помогает при: ${escapeHtml(item._matchedSymptoms.join(", "))}</span>` : ""}
    </article>`;
  }

  function toggleReferenceFilters() {
    _filtersExpanded = !_filtersExpanded;
    renderReferences();
  }

  function createContentFromOil(oilName) {
    if (typeof window.openCreateTool === "function") window.openCreateTool("content");
    let attempts = 0;
    const tryFill = () => {
      attempts++;
      const selectors = ["[data-create-content] [name=topic]", "#createForm textarea"];
      for (const sel of selectors) {
        const ta = document.querySelector(sel);
        if (ta && !ta.value) { ta.value = oilName; ta.dispatchEvent(new Event("input")); return; }
      }
      if (attempts < 15) setTimeout(tryFill, 80);
    };
    setTimeout(tryFill, 80);
  }

  function clearSmartSearch() {
    clearTimeout(_smartSearchDebounce);
    const input = document.getElementById("smartSearchInput");
    if (input) input.value = "";
    const clearBtn = document.getElementById("smartSearchClear");
    if (clearBtn) clearBtn.hidden = true;
    const countEl = document.getElementById("smartSearchCount");
    if (countEl) countEl.hidden = false;
    state.referenceSearch = "";
    renderReferences();
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

  async function openDailyOilReference(slug) {
    if (_dailyOilData) {
      state._dailyOil = {
        reason: _dailyOilData.reason || "",
        fact: _dailyOilData.fact || "",
        daily_practice: _dailyOilData.daily_practice || "",
      };
    }
    await openReference(slug, "aromas");
  }

  /* ── Daily Oil Banner ── */
  async function _loadDailyOilBanner() {
    const el = document.getElementById("dailyOilBanner");
    if (!el) return;
    try {
      const oil = await fetchJson("/api/references/daily-oil");
      _dailyOilData = oil;
      el.innerHTML = `
        <div class="daily-oil-banner" data-action="openDailyOilReference" data-args='${JSON.stringify([oil.slug])}'>
          <div class="daily-oil-header">
            <i data-lucide="sparkles" class="daily-oil-icon"></i>
            <span class="daily-oil-label">\u041c\u0430\u0441\u043b\u043e \u0434\u043d\u044f</span>
          </div>
          <h3 class="daily-oil-name">${escapeHtml(oil.name)}</h3>
          ${oil.reason ? `<p class="daily-oil-reason"><i data-lucide="lightbulb" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px"></i>${escapeHtml(oil.reason)}</p>` : ""}
          <span class="daily-oil-cta">\u0423\u0437\u043d\u0430\u0442\u044c \u0431\u043e\u043b\u044c\u0448\u0435 <i data-lucide="chevron-right"></i></span>
        </div>`;
      if (window.lucide) lucide.createIcons();
    } catch {
      el.innerHTML = "";
    }
  }

  return {
    currentHandbookMeta,
    loadReferenceAccess,
    loadReferences,
    openReference,
    openDailyOilReference,
    renderReferences,
    renderReferencesLocked,
    renderReferencesUnavailable,
    openAroma,
    renderAromas,
    renderAromasLocked,
    handleSmartSearch,
    runSmartSearch,
    clearSmartSearch,
    createContentFromOil,
    toggleReferenceFilters,
  };
}
