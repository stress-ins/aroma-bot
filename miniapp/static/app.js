const state = {
  mode: "content", // 'content' or 'handbook'
  tab: new URLSearchParams(window.location.search).get("tab") || "drafts",
  draftId: new URLSearchParams(window.location.search).get("draft_id") || "",
  aromaAccess: false,
  aromas: [],
  aromaSearch: "",
  aromaEditing: false,
  selectedAroma: null,
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
  ],
  handbook: [
    { id: "aromas", label: "Ароматы" },
    { id: "keywords", label: "Ключи" },
    { id: "status", label: "Статус" },
  ],
};

let reelRefreshTimer = null;

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
  refreshButton: document.getElementById("refreshButton"),
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

async function loadAromaAccess() {
  try {
    const payload = await fetchJson("/api/aromas/access");
    state.aromaAccess = Boolean(payload?.allowed);
  } catch (_e) { state.aromaAccess = false; }
}

async function loadAromas() {
  if (!state.aromaAccess) {
    renderAromasLocked();
    return;
  }
  const data = await fetchJson("/api/aromas");
  state.aromas = data.items || [];
  const selectedSlug = state.selectedAroma?.slug || state.aromas[0]?.slug || "";
  if (selectedSlug) await openAroma(selectedSlug);
  else renderAromas();
}

async function openAroma(slug) {
  if (!slug) return;
  state.aromaEditing = false;
  state.selectedAroma = await fetchJson(`/api/aromas/${encodeURIComponent(slug)}`);
  renderAromas();
  enterDetailView();
}

function renderCreate() {
  elements.listTitle.textContent = "Инструменты";
  elements.draftCount.textContent = "4 типа";
  setEmptyState(true);
  elements.draftList.innerHTML = `
    <div class="create-list">
      <article class="create-card" onclick="document.querySelector('[data-create-content]').scrollIntoView({behavior:'smooth'})">
        <div class="draft-kind">контент</div>
        <h3 class="draft-topic">Пост для соцсетей</h3>
        <div class="draft-preview">Тредс, Инстаграм или Телеграм.</div>
      </article>
      <article class="create-card" onclick="document.querySelector('[data-create-reels]').scrollIntoView({behavior:'smooth'})">
        <div class="draft-kind">рилсы</div>
        <h3 class="draft-topic">Сценарий + раскадровка</h3>
        <div class="draft-preview">Сценарий и 4 кадра визуализации.</div>
      </article>
      <article class="create-card" onclick="document.querySelector('[data-create-plan]').scrollIntoView({behavior:'smooth'})">
        <div class="draft-kind">план</div>
        <h3 class="draft-topic">Контент-план</h3>
        <div class="draft-preview">Сбор трендов и план на неделю.</div>
      </article>
      <article class="create-card" onclick="document.querySelector('[data-create-carousel]').scrollIntoView({behavior:'smooth'})">
        <div class="draft-kind">карусель</div>
        <h3 class="draft-topic">Карусель</h3>
        <div class="draft-preview">5 слайдов с промптами для картинок.</div>
      </article>
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
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
      <section class="section">
        <h3>Создать рилс</h3>
        <form class="create-form" data-create-reels>
          <label>Тема<textarea name="topic" placeholder="Например: вечерний сенсорный ритуал"></textarea></label>
          <button class="primary-button" type="submit">Сгенерировать раскадровку</button>
        </form>
      </section>
      <section class="section">
        <h3>Создать план</h3>
        <form class="create-form" data-create-plan>
          <div class="detail-preview">Собирает актуальные тренды и сохраняет недельный план.</div>
          <button class="primary-button" type="submit">Собрать план на неделю</button>
        </form>
      </section>
      <section class="section">
        <h3>Создать карусель</h3>
        <form class="create-form" data-create-carousel>
          <label>Тема<textarea name="topic" placeholder="Например: утренний ритуал с маслами"></textarea></label>
          <button class="primary-button" type="submit">Сгенерировать карусель</button>
        </form>
      </section>
    </div>
  `;
  syncMobileNavigation();

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

function renderAromas() {
  const items = state.aromas || [];
  const query = (state.aromaSearch || "").trim().toLowerCase();
  const filtered = items.filter((i) => `${i.name} ${i.description || ""}`.toLowerCase().includes(query));
  const aroma = state.selectedAroma;
  elements.listTitle.textContent = "Справочник";
  elements.draftCount.textContent = `${items.length} масел`;
  setEmptyState(filtered.length > 0, "Масла не найдены.");

  let listContainer = document.getElementById("aromaListContainer");
  if (!listContainer) {
    elements.draftList.innerHTML = `
      <div class="aroma-search">
        <label>Поиск масла<input id="aromaSearchInput" type="search" placeholder="Например: лаванда" value="${escapeHtml(state.aromaSearch)}" /></label>
      </div>
      <div id="aromaListContainer" class="plans-list"></div>
    `;
    listContainer = document.getElementById("aromaListContainer");
    document.getElementById("aromaSearchInput")?.addEventListener("input", (e) => {
      state.aromaSearch = e.target.value; renderAromas();
    });
  }

  listContainer.innerHTML = filtered.map((i) => `
    <article class="draft-card${i.slug === aroma?.slug ? " active" : ""}" onclick="openAroma('${i.slug}')">
      <div class="draft-kind">масло</div>
      <h3 class="draft-topic">${escapeHtml(i.name)}</h3>
      <div class="draft-preview">${escapeHtml(i.description || "")}</div>
    </article>
  `).join("");

  if (!aroma) {
    elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">Выберите масло из списка.</div>`;
    syncMobileNavigation();
    return;
  }

  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <section class="section aroma-hero">
        <img class="aroma-image" src="${escapeHtml(aroma.image_url)}" alt="${escapeHtml(aroma.image_alt)}" />
        <div class="aroma-image-caption">${escapeHtml(aroma.image_alt)}</div>
      </section>
      ${aromaSection("Паспорт масла", `Ключ: ${aroma.key || ""}\nСемейство: ${aroma.botanical_family || ""}\nСтрана: ${aroma.origin_countries || ""}\nМетод: ${aroma.extraction_method || ""}`)}
      ${aromaSection("Описание", aroma.description)}
      ${aromaSection("Терапия", aroma.therapeutic_properties)}
      ${aromaSection("Психология", aroma.psychological_properties)}
      ${aromaSection('Ресурс "+"', aroma.resource_values?.plus)}
      ${aromaSection('Ресурс "-"', aroma.resource_values?.minus)}
    </div>
  `;
  syncMobileNavigation();
}

function aromaSection(title, content) {
  if (!content) return "";
  return `<section class="section"><h3>${escapeHtml(title)}</h3><div class="detail-preview">${escapeHtml(content)}</div></section>`;
}

function renderAromasLocked() {
  elements.listTitle.textContent = "Ароматы"; setEmptyState(true);
  elements.draftList.innerHTML = `<div class="detail-preview">Доступ ограничен.</div>`;
  elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">Нет доступа.</div>`;
  syncMobileNavigation();
}

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
      ${payloadSection("Текст", p.caption || p.scenario)}
      ${payloadSection("CTA", p.cta)}
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
  if (state.tab === "aromas") return await loadAromas();
  if (state.tab === "status") return await loadStatus();
  if (state.tab === "keywords") return await loadKeywords();
  await loadDrafts();
}

async function bootstrap() {
  applyTelegramTheme();
  elements.modeContent.addEventListener("click", () => { setMode("content"); loadCurrentTab(); });
  elements.modeHandbook.addEventListener("click", () => { setMode("handbook"); loadCurrentTab(); });
  elements.refreshButton.addEventListener("click", () => loadCurrentTab());
  [elements.kindFilter, elements.statusFilter, elements.feedbackFilter].forEach(f => f.addEventListener("change", loadDrafts));
  elements.queryFilter.addEventListener("input", () => { clearTimeout(reelRefreshTimer); reelRefreshTimer = setTimeout(loadDrafts, 300); });
  await loadAromaAccess();
  if (MODE_TABS.handbook.find(t => t.id === state.tab)) state.mode = "handbook";
  setMode(state.mode);
  await loadCurrentTab();
}

bootstrap();

// Global Window functions
window.openDraft = openDraft;
window.openAroma = openAroma;
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
      <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
      ${payloadSection("Сценарий", r.payload?.scenario)}
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
