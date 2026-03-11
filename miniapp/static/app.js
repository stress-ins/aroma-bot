const state = {
  mode: "content", // 'content' or 'handbook'
  tab: new URLSearchParams(window.location.search).get("tab") || "drafts",
  draftId: new URLSearchParams(window.location.search).get("draft_id") || "",
  selectedCreateTool: null,
  referenceAccess: false,
  referenceItems: [],
  referenceSearch: "",
  selectedReference: null,
  inbox: [],
  inboxKind: "all",
  drafts: [],
  plans: [],
  reels: [],
  selectedPlan: null,
  selected: null,
  selectedReels: null,
  selectedFrameIndex: 0,
  status: null,
  keywords: null,
  mobileView: "list", // 'list' or 'detail'
};

const MODE_TABS = {
  content: [
    { id: "create", label: "Создать" },
    { id: "inbox", label: "Согласование" },
    { id: "drafts", label: "Черновики" },
    { id: "plans", label: "Планы" },
    { id: "reels", label: "Рилсы" },
    { id: "keywords", label: "Ключи" },
    { id: "status", label: "Статус" },
  ],
  handbook: [
    { id: "aromas", label: "Ароматы" },
    { id: "practices", label: "Практики" },
    { id: "sounds", label: "Звуки" },
  ],
};

let reelRefreshTimer = null;
let carouselRefreshTimer = null;

const elements = {
  tabsContainer: document.getElementById("tabsContainer"),
  filtersContainer: document.getElementById("filtersContainer"),
  listPanel: document.getElementById("listPanel"),
  detailPanel: document.getElementById("detailPanel"),
  draftList: document.getElementById("draftList"),
  draftDetail: document.getElementById("draftDetail"),
  draftCount: document.getElementById("draftCount"),
  listTitle: document.getElementById("listTitle"),
  emptyState: document.getElementById("emptyState"),
  kindFilter: document.getElementById("kindFilter"),
  statusFilter: document.getElementById("statusFilter"),
  feedbackFilter: document.getElementById("feedbackFilter"),
  queryFilter: document.getElementById("queryFilter"),
  modeContent: document.getElementById("modeContent"),
  modeHandbook: document.getElementById("modeHandbook"),
};

const RU_KIND_LABELS = {
  threads: "Тредс",
  instagram: "Инстаграм",
  telegram: "Телеграм",
  reels: "Рилсы",
  carousel: "Карусель",
};

const RU_STATUS_LABELS = {
  draft: "Черновик",
  in_review: "На согласовании",
  approved: "Согласовано",
  published: "Опубликовано",
};

const RU_FEEDBACK_LABELS = {
  worked: "Сработало",
  missed: "Не сработало",
};

const HANDBOOK_CATEGORY_META = {
  aromas: {
    category: "aroma",
    label: "аромат",
    title: "Ароматы",
    searchLabel: "Поиск аромата",
    searchPlaceholder: "Например: лаванда",
    empty: "Ароматы не найдены.",
    selectPrompt: "Выберите аромат из списка.",
    locked: "Доступ к справочнику ароматов ограничен.",
    count: (items) => `${items.length} карточек`,
  },
  practices: {
    category: "practice",
    label: "практика",
    title: "Практики",
    searchLabel: "Поиск практики",
    searchPlaceholder: "Например: квадратное дыхание",
    empty: "Практики не найдены.",
    selectPrompt: "Выберите практику из списка.",
    locked: "Доступ к справочнику практик ограничен.",
    count: (items) => `${items.length} карточек`,
  },
  sounds: {
    category: "sound",
    label: "звук",
    title: "Звуки",
    searchLabel: "Поиск звука",
    searchPlaceholder: "Например: гонг",
    empty: "Звуки не найдены.",
    selectPrompt: "Выберите звуковую карточку из списка.",
    locked: "Доступ к справочнику звуков ограничен.",
    count: (items) => `${items.length} карточек`,
  },
};

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function payloadSection(title, content) {
  if (!content) return "";
  return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview">${escapeHtml(content)}</div></section>`;
}

function promptSection(title, prompt, copyLabel = "Скопировать промпт") {
  if (!prompt) return "";
  return `
    <section class="section">
      <h3>${escapeHtml(title)}</h3>
      <div class="detail-preview prompt-preview">${escapeHtml(prompt)}</div>
      <div class="actions-row prompt-actions">
        <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(String(prompt))})'>${escapeHtml(copyLabel)}</button>
      </div>
    </section>
  `;
}

function renderSlides(slides = [], prompts = [], slideImages = []) {
  const slideItems = Array.isArray(slides) ? slides : [];
  const promptItems = Array.isArray(prompts) ? prompts : [];
  const imageItems = Array.isArray(slideImages) ? slideImages : [];
  if (!slideItems.length) return "";
  const readyCount = imageItems.filter(Boolean).length;
  const header = readyCount > 0
    ? `Слайды карусели <span class="meta">${readyCount} / ${slideItems.length} с картинкой</span>`
    : "Слайды карусели";
  return `
    <section class="section">
      <h3>${header}</h3>
      <div class="slides">
        ${slideItems.map((slide, index) => {
          const img = imageItems[index];
          const imgHtml = img?.url
            ? `<img class="frame-image" src="${escapeHtml(img.url)}" alt="Слайд ${index + 1}" />`
            : `<div class="frame-loading">⏳ Картинка генерируется…</div>`;
          return `
            <article class="slide">
              <strong>Слайд ${index + 1}</strong>
              ${imgHtml}
              <div class="detail-preview">${escapeHtml(slide)}</div>
              ${promptItems[index] ? `
                <div class="prompt-card">
                  <div class="detail-preview prompt-preview">${escapeHtml(promptItems[index])}</div>
                  <div class="actions-row prompt-actions">
                    <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(String(promptItems[index]))})'>Скопировать промпт</button>
                  </div>
                </div>
              ` : ""}
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function renderReelsFrames(frames = []) {
  const frameItems = Array.isArray(frames) ? frames : [];
  if (!frameItems.length) return "";
  return `
    <section class="section">
      <h3>Кадры и промпты</h3>
      <div class="storyboard">
        ${frameItems.map((frame, index) => {
          const prompt = frame.gemini_prompt || "";
          const assetUrl = frame.current_asset?.url || "";
          return `
            <article class="storyboard-frame">
              <strong>Кадр ${index + 1}${frame.timecode ? ` • ${escapeHtml(frame.timecode)}` : ""}</strong>
              ${frame.scene ? `<div class="detail-preview">${escapeHtml(frame.scene)}</div>` : ""}
              ${frame.angle ? `<div class="detail-preview frame-meta-line">Ракурс: ${escapeHtml(frame.angle)}</div>` : ""}
              ${assetUrl
                ? `<img class="frame-image" src="${escapeHtml(assetUrl)}" alt="Кадр ${index + 1}" />`
                : `<div class="frame-loading">Картинка ещё не готова. Используйте промпт ниже для ручной генерации.</div>`}
              ${prompt ? `
                <div class="prompt-card">
                  <div class="detail-preview prompt-preview">${escapeHtml(prompt)}</div>
                  <div class="actions-row prompt-actions">
                    <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(String(prompt))})'>Скопировать промпт кадра</button>
                  </div>
                </div>
              ` : ""}
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function kindLabel(value) {
  return RU_KIND_LABELS[String(value || "").toLowerCase()] || String(value || "");
}

function statusLabel(value) {
  return RU_STATUS_LABELS[String(value || "").toLowerCase()] || String(value || "");
}

function feedbackLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) return "Без реакции";
  return RU_FEEDBACK_LABELS[normalized] || String(value || "");
}

function setEmptyState(hidden, text = "Ничего не найдено.") {
  elements.emptyState.hidden = hidden;
  elements.emptyState.textContent = text;
  elements.emptyState.style.display = hidden ? "none" : "block";
}

function showRequestError(prefix, error) {
  const message = error?.message || String(error || "unknown_error");
  alert(`${prefix}: ${message}`);
}

async function copyText(value) {
  const text = String(value || "").trim();
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "readonly");
      field.style.position = "absolute";
      field.style.left = "-9999px";
      document.body.appendChild(field);
      field.select();
      document.execCommand("copy");
      document.body.removeChild(field);
    }
  } catch (error) {
    showRequestError("Не удалось скопировать промпт", error);
    return;
  }
  const tg = window.Telegram?.WebApp;
  if (tg?.showAlert) tg.showAlert("Промпт скопирован");
}

function syncMobileNavigation() {
  const isMobile = window.matchMedia("(max-width: 760px)").matches;
  if (!isMobile) {
    elements.listPanel.classList.remove("hidden-mobile");
    elements.detailPanel.classList.remove("hidden-mobile");
    return;
  }

  if (state.mobileView === "detail") {
    elements.listPanel.classList.add("hidden-mobile");
    elements.detailPanel.classList.remove("hidden-mobile");
  } else {
    elements.listPanel.classList.remove("hidden-mobile");
    elements.detailPanel.classList.add("hidden-mobile");
  }
}

function renderBackButton() {
  const isMobile = window.matchMedia("(max-width: 760px)").matches;
  if (!isMobile) return "";
  return `<button class="back-button visible" onclick="goBackToList()">← Назад к списку</button>`;
}

window.goBackToList = () => {
  state.mobileView = "list";
  syncMobileNavigation();
};

function enterDetailView() {
  state.mobileView = "detail";
  syncMobileNavigation();
  window.scrollTo(0, 0);
}

function bindTopicForm(form, config) {
  const topicField = form.querySelector("textarea[name='topic']");
  const submitButton = form.querySelector("button[type='submit']");
  if (!topicField || !submitButton) return;

  const updateState = () => {
    submitButton.disabled = !topicField.value.trim();
  };

  updateState();
  topicField.addEventListener("input", updateState);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const topic = topicField.value.trim();
    if (!topic) {
      topicField.focus();
      return;
    }
    const originalText = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = config.pendingText;
    try {
      await config.onSubmit(topic);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalText;
      updateState();
    }
  });
}

function applyTelegramTheme() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  tg.ready();
  tg.expand();
  const bgColor = tg.themeParams.secondary_bg_color;
  const textColor = tg.themeParams.text_color;
  if (bgColor) document.documentElement.style.setProperty("--panel", bgColor);
  if (textColor) document.documentElement.style.setProperty("--text", textColor);
}

function filtersToQueryString() {
  const params = new URLSearchParams();
  if (elements.kindFilter.value) params.set("kind", elements.kindFilter.value);
  if (elements.statusFilter.value) params.set("status", elements.statusFilter.value);
  if (elements.feedbackFilter.value) params.set("feedback", elements.feedbackFilter.value);
  if (elements.queryFilter.value.trim()) params.set("query", elements.queryFilter.value.trim());
  params.set("limit", "100");
  return params.toString();
}

function _initDataHeader() {
  const initData = window.Telegram?.WebApp?.initData;
  return initData ? { "X-Telegram-Init-Data": initData } : {};
}

function scheduleReelsRefresh(draftId, attempts = 10) {
  if (!draftId || attempts <= 0) return;
  window.clearTimeout(reelRefreshTimer);
  reelRefreshTimer = window.setTimeout(async () => {
    try {
      const reel = await fetchJson(`/api/reels/${draftId}`);
      const readyFrames = Array.isArray(reel.frames) ? reel.frames.filter((i) => i.current_asset?.url).length : 0;
      state.selectedReels = reel;
      state.reels = state.reels.map((i) => i.draft_id === reel.draft_id ? { ...i, ...reel } : i);
      renderReels();
      renderReelsDetail(reel);
      if (readyFrames < (reel.frame_count || 0)) scheduleReelsRefresh(draftId, attempts - 1);
    } catch (_e) { scheduleReelsRefresh(draftId, attempts - 1); }
  }, 4000);
}

function scheduleCarouselRefresh(draftId, attempts = 12) {
  if (!draftId || attempts <= 0) return;
  window.clearTimeout(carouselRefreshTimer);
  carouselRefreshTimer = window.setTimeout(async () => {
    try {
      const draft = await fetchJson(`/api/carousel/${draftId}`);
      const payload = draft.payload || {};
      const slideImages = Array.isArray(payload.slide_images) ? payload.slide_images : [];
      const slideCount = Array.isArray(payload.slides) ? payload.slides.length : 0;
      const readyCount = slideImages.filter(Boolean).length;
      state.selected = draft;
      state.drafts = state.drafts.map((d) => d.draft_id === draft.draft_id ? { ...d, ...draft } : d);
      renderDraftDetail(draft);
      if (readyCount < slideCount) scheduleCarouselRefresh(draftId, attempts - 1);
    } catch (_e) { scheduleCarouselRefresh(draftId, attempts - 1); }
  }, 5000);
}

async function fetchJson(url, options = {}) {
  const extraHeaders = url.startsWith("/api/") ? _initDataHeader() : {};
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...extraHeaders },
    ...options,
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload?.detail ? ` (${payload.detail})` : "";
    } catch (_e) {}
    throw new Error(`${response.status} ${response.statusText}${detail}`);
  }
  return response.json();
}

async function loadDrafts() {
  const data = await fetchJson(`/api/drafts?${filtersToQueryString()}`);
  state.drafts = data.items || [];
  renderDraftList();
  const preferredId = state.draftId || state.drafts[0]?.draft_id || "";
  if (preferredId) await openDraft(preferredId);
  else renderEmptyDetail();
}

async function loadInbox() {
  const params = new URLSearchParams();
  params.set("limit", "100");
  if (state.inboxKind && state.inboxKind !== "all") params.set("kind", state.inboxKind);
  const data = await fetchJson(`/api/inbox?${params.toString()}`);
  state.inbox = data.items || [];
  state.inboxKind = data.kind || "all";
  renderInbox();
}

async function loadStatus() {
  state.status = await fetchJson("/api/status");
  renderStatus();
}

async function loadPlans() {
  const data = await fetchJson("/api/plans?limit=20");
  state.plans = data.items || [];
  renderPlans();
}

async function loadReels() {
  const data = await fetchJson("/api/reels?limit=30");
  state.reels = data.items || [];
  renderReels();
}

async function loadKeywords() {
  state.keywords = await fetchJson("/api/keywords");
  renderKeywords();
}

function currentHandbookMeta() {
  return HANDBOOK_CATEGORY_META[state.tab] || HANDBOOK_CATEGORY_META.aromas;
}

async function loadReferenceAccess() {
  try {
    const payload = await fetchJson("/api/references/access");
    state.referenceAccess = Boolean(payload?.allowed);
  } catch (_e) { state.referenceAccess = false; }
}

async function loadReferences(tabId = state.tab) {
  const meta = HANDBOOK_CATEGORY_META[tabId];
  if (!meta) return;
  if (!state.referenceAccess) {
    renderReferencesLocked();
    return;
  }
  const data = await fetchJson(`/api/references/${meta.category}`);
  state.referenceItems = data.items || [];
  
  // Do not automatically pick the first card if nothing is selected
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
  ].filter(Boolean);
  return parts.join("\n");
}

function renderReferences() {
  const meta = currentHandbookMeta();
  const items = state.referenceItems || [];
  const query = (state.referenceSearch || "").trim().toLowerCase();
  const filtered = items.filter((item) => `${item.name} ${item.description || ""}`.toLowerCase().includes(query));
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
    <article class="draft-card${item.slug === reference?.slug ? " active" : ""}" onclick="openReference('${item.slug}', '${state.tab}')">
      <div class="draft-kind">${escapeHtml(meta.label)}</div>
      <h3 class="draft-topic">${escapeHtml(item.name)}</h3>
      <div class="draft-preview">${escapeHtml(item.description || "")}</div>
    </article>
  `).join("");

  if (!reference) {
    elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${escapeHtml(meta.selectPrompt)}</div>`;
    syncMobileNavigation();
    return;
  }

  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <section class="section aroma-hero">
        <img class="aroma-image" src="${escapeHtml(reference.image_url)}" alt="${escapeHtml(reference.image_alt)}" />
        <div class="aroma-image-caption">${escapeHtml(reference.image_alt)}</div>
      </section>
      ${aromaSection("Паспорт карточки", renderReferencePassport(reference))}
      ${aromaSection("Описание", reference.description)}
      ${aromaSection("Какие вопросы поднимает", reference.questions)}
      ${aromaSection("Действие на НПС", reference.nps_effect)}
      ${aromaSection("Терапевтические свойства", reference.therapeutic_properties)}
      ${aromaSection("Психологические свойства", reference.psychological_properties)}
      ${aromaSection('Ресурс "+"', reference.resource_values?.plus)}
      ${aromaSection('Ресурс "-"', reference.resource_values?.minus)}
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
  elements.draftList.innerHTML = `<div class="detail-preview">${escapeHtml(meta.locked)}</div>`;
  elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${escapeHtml(meta.locked)}</div>`;
  syncMobileNavigation();
}

async function openAroma(slug) {
  if (!slug) return;
  await openReference(slug, "aromas");
}

function renderCreate() {
  elements.listTitle.textContent = "Инструменты";
  elements.draftCount.textContent = "4 типа";
  setEmptyState(true);
  
  elements.draftList.innerHTML = `
    <div class="create-list">
      <article class="create-card${state.selectedCreateTool === 'content' ? ' active' : ''}" onclick="renderCreateTool('content')">
        <div class="draft-kind">контент</div>
        <h3 class="draft-topic">Пост для соцсетей</h3>
        <div class="draft-preview">Тредс, Инстаграм или Телеграм.</div>
      </article>
      <article class="create-card${state.selectedCreateTool === 'reels' ? ' active' : ''}" onclick="renderCreateTool('reels')">
        <div class="draft-kind">рилсы</div>
        <h3 class="draft-topic">Сценарий + раскадровка</h3>
        <div class="draft-preview">Сценарий и 4 кадра визуализации.</div>
      </article>
      <article class="create-card${state.selectedCreateTool === 'plan' ? ' active' : ''}" onclick="renderCreateTool('plan')">
        <div class="draft-kind">план</div>
        <h3 class="draft-topic">Контент-план</h3>
        <div class="draft-preview">Сбор трендов и план на неделю.</div>
      </article>
      <article class="create-card${state.selectedCreateTool === 'carousel' ? ' active' : ''}" onclick="renderCreateTool('carousel')">
        <div class="draft-kind">карусель</div>
        <h3 class="draft-topic">Карусель</h3>
        <div class="draft-preview">5 слайдов с промптами для картинок.</div>
      </article>
    </div>
  `;

  if (!state.selectedCreateTool) {
    elements.draftDetail.innerHTML = `<div class="detail-empty">Выберите инструмент слева.</div>`;
    syncMobileNavigation();
    return;
  }

  renderCreateTool(state.selectedCreateTool);
}

function renderCreateTool(toolId) {
  state.selectedCreateTool = toolId;
  
  // Update active state in the list
  elements.draftList.querySelectorAll(".create-card").forEach(card => {
    const isTarget = (toolId === 'content' && card.querySelector('.draft-kind').textContent === 'контент') ||
                     (toolId === 'reels' && card.querySelector('.draft-kind').textContent === 'рилсы') ||
                     (toolId === 'plan' && card.querySelector('.draft-kind').textContent === 'план') ||
                     (toolId === 'carousel' && card.querySelector('.draft-kind').textContent === 'карусель');
    card.classList.toggle("active", isTarget);
  });

  let formHtml = '';
  if (toolId === 'content') {
    formHtml = `
      <section class="section">
        <h3>Создать контент</h3>
        <form class="create-form" data-create-content>
          <label>Тема<textarea name="topic" placeholder="Например: как мягко переключиться после рабочего дня"></textarea></label>
          <div class="field-grid">
            <label>Цель<select name="goal_key"><option value="trust">Доверие</option><option value="authority">Экспертность</option><option value="engagement">Вовлечённость</option><option value="sales">Продажи</option></select></label>
            <label>Формат<select name="format_key"><option value="threads">Тредс</option><option value="instagram">Инстаграм</option><option value="telegram">Телеграм</option></select></label>
          </div>
          <button class="primary-button" type="submit">Сгенерировать текст</button>
        </form>
      </section>
    `;
  } else if (toolId === 'reels') {
    formHtml = `
      <section class="section">
        <h3>Создать рилс</h3>
        <form class="create-form" data-create-reels>
          <label>Тема<textarea name="topic" placeholder="Например: вечерний сенсорный ритуал"></textarea></label>
          <button class="primary-button" type="submit">Сгенерировать раскадровку</button>
        </form>
      </section>
    `;
  } else if (toolId === 'plan') {
    formHtml = `
      <section class="section">
        <h3>Создать план</h3>
        <form class="create-form" data-create-plan>
          <div class="detail-preview">Собирает актуальные тренды и сохраняет недельный план.</div>
          <button class="primary-button" type="submit">Собрать план на неделю</button>
        </form>
      </section>
    `;
  } else if (toolId === 'carousel') {
    formHtml = `
      <section class="section">
        <h3>Создать карусель</h3>
        <form class="create-form" data-create-carousel>
          <label>Тема<textarea name="topic" placeholder="Например: утренний ритуал с маслами"></textarea></label>
          <button class="primary-button" type="submit">Сгенерировать карусель</button>
        </form>
      </section>
    `;
  }

  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      ${formHtml}
    </div>
  `;
  
  enterDetailView();

  // Re-bind forms
  const cForm = elements.draftDetail.querySelector("[data-create-content]");
  if (cForm) bindTopicForm(cForm, { pendingText: "Создаю...", onSubmit: async (t) => {
    const g = cForm.querySelector("select[name='goal_key']").value;
    const f = cForm.querySelector("select[name='format_key']").value;
    const d = await fetchJson("/api/generate/content", { method: "POST", body: JSON.stringify({ topic: t, goal_key: g, format_key: f }) });
    state.draftId = d.draft_id; setTab("drafts"); await loadDrafts();
  }});

  const rForm = elements.draftDetail.querySelector("[data-create-reels]");
  if (rForm) bindTopicForm(rForm, { pendingText: "Создаю...", onSubmit: async (t) => {
    const r = await fetchJson("/api/generate/reels", { method: "POST", body: JSON.stringify({ topic: t }) });
    state.selectedReels = r; state.selectedFrameIndex = 0; setTab("reels"); await loadReels(); await openReels(r.draft_id);
  }});

  const pForm = elements.draftDetail.querySelector("[data-create-plan]");
  if (pForm) pForm.addEventListener("submit", async (e) => {
    e.preventDefault(); const b = pForm.querySelector("button"); b.disabled = true; b.textContent = "Собираю...";
    try { const p = await fetchJson("/api/generate/plan", { method: "POST", body: JSON.stringify({}) });
      state.selectedPlan = p; setTab("plans"); await loadPlans(); renderPlanDetail(p); enterDetailView();
    } finally { b.disabled = false; b.textContent = "Собрать план на неделю"; }
  });

  const carForm = elements.draftDetail.querySelector("[data-create-carousel]");
  if (carForm) bindTopicForm(carForm, { pendingText: "Создаю...", onSubmit: async (t) => {
    const d = await fetchJson("/api/generate/carousel", { method: "POST", body: JSON.stringify({ topic: t }) });
    state.draftId = d.draft_id; setTab("drafts"); await loadDrafts();
  }});
}

function renderAromas() { renderReferences(); }

function aromaSection(title, content) {
  if (!content) return "";
  return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview">${escapeHtml(content)}</div></section>`;
}

function renderAromasLocked() { renderReferencesLocked(); }

function renderDraftList() {
  elements.listTitle.textContent = "Черновики";
  elements.draftCount.textContent = `${state.drafts.length} шт`;
  setEmptyState(state.drafts.length > 0);
  elements.draftList.innerHTML = state.drafts.map((d) => `
    <article class="draft-card${d.draft_id === state.draftId ? " active" : ""}" onclick="openDraft('${d.draft_id}')">
      <div class="draft-kind">${escapeHtml(kindLabel(d.kind))}</div>
      <h3 class="draft-topic">${escapeHtml(d.topic)}</h3>
      <div class="draft-preview">${escapeHtml(d.preview || "Без превью")}</div>
      <div class="draft-meta">
        <span class="tag">${escapeHtml(statusLabel(d.status))}</span>
        <span class="tag">${escapeHtml(kindLabel(d.source))}</span>
      </div>
    </article>
  `).join("");
  syncMobileNavigation();
}

async function openDraft(id) {
  const d = await fetchJson(`/api/drafts/${id}`);
  state.selected = d; state.draftId = id;
  renderDraftList(); renderDraftDetail(d); enterDetailView();
}

function renderDraftDetail(d) {
  const p = d.payload || {};
  const mainText = p.caption || p.scenario || "";
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <div class="detail-top">
        <p class="eyebrow">${escapeHtml(kindLabel(d.kind))} • ${escapeHtml(kindLabel(d.source))}</p>
        <h2 class="detail-title">${escapeHtml(d.topic)}</h2>
        <div class="draft-meta"><span class="tag">${escapeHtml(statusLabel(d.status))}</span></div>
        <div class="actions-row">
          <button class="secondary-button" onclick="updateDraft('status', {status:'approved'})">Согласовать</button>
          <button class="secondary-button" onclick="sendDraftToChat('${d.draft_id}')">В чат</button>
        </div>
      </div>
      ${payloadSection("Превью", d.preview)}
      ${payloadSection("Угол", p.angle)}
      ${payloadSection("Текст", mainText)}
      ${payloadSection("CTA", p.cta)}
      ${renderSlides(p.slides, p.img_prompts)}
      ${promptSection("Промпт для изображения", p.visual_prompt)}
      <section class="section"><h3>JSON</h3><pre class="json-block">${escapeHtml(JSON.stringify(p, null, 2))}</pre></section>
    </div>
  `;
}

function renderEmptyDetail() {
  elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">Выберите элемент из списка слева.</div>`;
  syncMobileNavigation();
}

function setMode(m) {
  state.mode = m;
  elements.modeContent.classList.toggle("active", m === "content");
  elements.modeHandbook.classList.toggle("active", m === "handbook");
  const tabs = MODE_TABS[m] || [];
  elements.tabsContainer.innerHTML = tabs.map(t => `
    <button class="tab-button${state.tab === t.id ? ' active' : ''}" data-tab="${t.id}" type="button">${t.label}</button>
  `).join("");
  elements.tabsContainer.querySelectorAll(".tab-button").forEach(b => {
    b.addEventListener("click", () => { setTab(b.dataset.tab); loadCurrentTab(); });
  });
  if (!tabs.find(t => t.id === state.tab)) setTab(tabs[0].id);
}

function setTab(t) {
  state.tab = t; state.mobileView = "list";
  if (t === "create") {
    state.selectedCreateTool = null;
  }
  if (HANDBOOK_CATEGORY_META[t]) {
    state.referenceSearch = "";
    if (state.selectedReference?.category !== HANDBOOK_CATEGORY_META[t].category) {
      state.selectedReference = null;
    }
  }
  const p = new URLSearchParams(window.location.search); p.set("tab", t);
  history.replaceState({}, "", `${window.location.pathname}?${p.toString()}`);
  elements.tabsContainer.querySelectorAll(".tab-button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
  elements.filtersContainer.hidden = (t !== "drafts");
  syncMobileNavigation();
}

async function loadCurrentTab() {
  if (state.tab === "create") return renderCreate();
  if (state.tab === "inbox") return await loadInbox();
  if (state.tab === "plans") return await loadPlans();
  if (state.tab === "reels") return await loadReels();
  if (HANDBOOK_CATEGORY_META[state.tab]) return await loadReferences(state.tab);
  if (state.tab === "status") return await loadStatus();
  if (state.tab === "keywords") return await loadKeywords();
  await loadDrafts();
}

async function bootstrap() {
  applyTelegramTheme();
  elements.modeContent.addEventListener("click", () => { setMode("content"); loadCurrentTab(); });
  elements.modeHandbook.addEventListener("click", () => { setMode("handbook"); loadCurrentTab(); });

  [elements.kindFilter, elements.statusFilter, elements.feedbackFilter].forEach(f => f.addEventListener("change", loadDrafts));

  elements.queryFilter.addEventListener("input", () => { clearTimeout(reelRefreshTimer); reelRefreshTimer = setTimeout(loadDrafts, 300); });
  await loadReferenceAccess();
  if (MODE_TABS.handbook.find(t => t.id === state.tab)) state.mode = "handbook";
  setMode(state.mode);
  await loadCurrentTab();
}

bootstrap();

// Global Window functions
window.openDraft = openDraft;
window.openAroma = openAroma;
window.openReference = openReference;
window.copyText = copyText;
window.openReels = async (id) => {
  const r = await fetchJson(`/api/reels/${id}`);
  state.selectedReels = r; renderReelsDetail(r); enterDetailView();
};
window.openPlan = async (id) => {
  const p = await fetchJson(`/api/plans/${id}`);
  state.selectedPlan = p; renderPlanDetail(p); enterDetailView();
};
window.updateDraft = async (action, payload) => {
  const d = await fetchJson(`/api/drafts/${state.draftId}/${action}`, { method: "POST", body: JSON.stringify(payload) });
  state.selected = d; renderDraftDetail(d); renderDraftList();
};
window.sendDraftToChat = sendDraftToChat;

function renderInbox() {
  elements.listTitle.textContent = "Согласование";
  elements.draftCount.textContent = `${state.inbox.length} на проверке`;
  setEmptyState(state.inbox.length > 0, "Очередь пуста.");
  elements.draftList.innerHTML = state.inbox.map(i => `
    <article class="draft-card" onclick="openDraft('${i.draft_id}')">
      <div class="draft-kind">${escapeHtml(kindLabel(i.kind))}</div>
      <h4 class="draft-topic">${escapeHtml(i.topic)}</h4>
      <div class="draft-preview">${escapeHtml(i.preview || "")}</div>
    </article>
  `).join("");
  syncMobileNavigation();
}

function renderStatus() {
  elements.listTitle.textContent = "Статус";
  const items = state.status?.items || [];
  elements.draftList.innerHTML = items.map(i => `
    <article class="status-card"><strong>${escapeHtml(i.source)}</strong> <span class="${i.enabled ? 'status-good' : 'status-bad'}">${i.enabled ? 'вкл' : 'выкл'}</span></article>
  `).join("");
  syncMobileNavigation();
}

function renderPlans() {
  elements.listTitle.textContent = "Планы";
  elements.draftList.innerHTML = state.plans.map(p => `
    <article class="plan-card" onclick="openPlan('${p.plan_id}')">
      <h3 class="draft-topic">${escapeHtml(p.plan_id)}</h3>
      <div class="draft-preview">${escapeHtml(p.raw_text || "")}</div>
    </article>
  `).join("");
  syncMobileNavigation();
}

function renderReels() {
  elements.listTitle.textContent = "Рилсы";
  elements.draftList.innerHTML = state.reels.map(r => `
    <article class="reels-card" onclick="openReels('${r.draft_id}')">
      <h3 class="draft-topic">${escapeHtml(r.topic)}</h3>
      <div class="draft-preview">${escapeHtml(r.preview || "")}</div>
    </article>
  `).join("");
  syncMobileNavigation();
}

function renderReelsDetail(r) {
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <div class="detail-top">
        <p class="eyebrow">Рилсы • ${escapeHtml(r.source || "/miniapp")}</p>
        <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
        <div class="draft-meta">
          <span class="tag">${escapeHtml(statusLabel(r.status || "draft"))}</span>
          <span class="tag">${escapeHtml(`${r.images_ready || 0}/${r.frame_count || 0} кадров`)}</span>
        </div>
      </div>
      ${payloadSection("Сценарий", r.payload?.scenario)}
      ${renderReelsFrames(r.frames)}
      <section class="section"><h3>JSON</h3><pre class="json-block">${escapeHtml(JSON.stringify(r.payload, null, 2))}</pre></section>
    </div>
  `;
}

function renderPlanDetail(p) {
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <h2 class="detail-title">${escapeHtml(p.plan_id)}</h2>
      <pre class="json-block">${escapeHtml(p.raw_text)}</pre>
    </div>
  `;
}

function renderKeywords() {
  elements.listTitle.textContent = "Ключи";
  elements.draftList.innerHTML = (state.keywords?.items || []).map(t => `
    <article class="keyword-topic"><h3>${escapeHtml(t.name)}</h3></article>
  `).join("");
  syncMobileNavigation();
}
