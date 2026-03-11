const state = {
  tab: new URLSearchParams(window.location.search).get("tab") || "drafts",
  draftId: new URLSearchParams(window.location.search).get("draft_id") || "",
  aromaAccess: false,
  aromas: [],
  aromaSearch: "",
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
};

let reelRefreshTimer = null;

const elements = {
  draftList: document.getElementById("draftList"),
  draftDetail: document.getElementById("draftDetail"),
  detailPanel: document.querySelector(".detail-panel"),
  draftCount: document.getElementById("draftCount"),
  listTitle: document.getElementById("listTitle"),
  emptyState: document.getElementById("emptyState"),
  kindFilter: document.getElementById("kindFilter"),
  statusFilter: document.getElementById("statusFilter"),
  feedbackFilter: document.getElementById("feedbackFilter"),
  queryFilter: document.getElementById("queryFilter"),
  refreshButton: document.getElementById("refreshButton"),
  tabButtons: Array.from(document.querySelectorAll("[data-tab]")),
  aromaTabButton: document.querySelector('[data-tab="aromas"]'),
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
  if (!content) {
    return "";
  }
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
  if (!normalized) {
    return "Без реакции";
  }
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

function bindTopicForm(form, config) {
  const topicField = form.querySelector("textarea[name='topic']");
  const submitButton = form.querySelector("button[type='submit']");
  if (!topicField || !submitButton) {
    return;
  }

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

function bindPress(element, handler) {
  if (!element) {
    return;
  }

  let lastTouchTs = 0;

  element.addEventListener("pointerup", async (event) => {
    if (event.pointerType !== "touch") {
      return;
    }
    lastTouchTs = Date.now();
    event.preventDefault();
    await handler(event);
  });

  element.addEventListener("click", async (event) => {
    if (Date.now() - lastTouchTs < 700) {
      event.preventDefault();
      return;
    }
    await handler(event);
  });
}

function syncDetailPanelState(isEmpty) {
  if (!elements.detailPanel) {
    return;
  }
  const hideOnMobile = Boolean(isEmpty) && window.matchMedia("(max-width: 760px)").matches;
  elements.detailPanel.classList.toggle("is-empty-mobile", hideOnMobile);
  elements.detailPanel.hidden = hideOnMobile;
}

function applyTelegramTheme() {
  const tg = window.Telegram?.WebApp;
  if (!tg) {
    return;
  }
  tg.ready();
  tg.expand();

  const bgColor = tg.themeParams.secondary_bg_color;
  const textColor = tg.themeParams.text_color;
  if (bgColor) {
    document.documentElement.style.setProperty("--panel", bgColor);
  }
  if (textColor) {
    document.documentElement.style.setProperty("--text", textColor);
  }
}

function filtersToQueryString() {
  const params = new URLSearchParams();
  if (elements.kindFilter.value) {
    params.set("kind", elements.kindFilter.value);
  }
  if (elements.statusFilter.value) {
    params.set("status", elements.statusFilter.value);
  }
  if (elements.feedbackFilter.value) {
    params.set("feedback", elements.feedbackFilter.value);
  }
  if (elements.queryFilter.value.trim()) {
    params.set("query", elements.queryFilter.value.trim());
  }
  params.set("limit", "100");
  return params.toString();
}

function _initDataHeader() {
  const initData = window.Telegram?.WebApp?.initData;
  return initData ? { "X-Telegram-Init-Data": initData } : {};
}

function showRequestError(prefix, error) {
  const message = error?.message || String(error || "unknown_error");
  alert(`${prefix}: ${message}`);
}

function scheduleReelsRefresh(draftId, attempts = 10) {
  if (!draftId || attempts <= 0) {
    return;
  }
  window.clearTimeout(reelRefreshTimer);
  reelRefreshTimer = window.setTimeout(async () => {
    try {
      const reel = await fetchJson(`/api/reels/${draftId}`);
      const readyFrames = Array.isArray(reel.frames)
        ? reel.frames.filter((item) => item.current_asset?.url).length
        : 0;
      state.selectedReels = reel;
      state.reels = state.reels.map((item) =>
        item.draft_id === reel.draft_id ? { ...item, ...reel } : item
      );
      renderReels();
      renderReelsDetail(reel);
      if (readyFrames < (reel.frame_count || 0)) {
        scheduleReelsRefresh(draftId, attempts - 1);
      }
    } catch (_error) {
      scheduleReelsRefresh(draftId, attempts - 1);
    }
  }, 4000);
}

function sendDraftToChat(draftId) {
  const tg = window.Telegram?.WebApp;
  if (!tg?.sendData || !draftId) {
    return;
  }
  tg.sendData(JSON.stringify({
    action: "open_draft",
    draft_id: String(draftId),
  }));
}

function requestDraftReview(draftId) {
  const tg = window.Telegram?.WebApp;
  if (!tg?.sendData || !draftId) {
    return;
  }
  tg.sendData(JSON.stringify({
    action: "request_review",
    draft_id: String(draftId),
  }));
}

function sendPlanToChat(planId) {
  const tg = window.Telegram?.WebApp;
  if (!tg?.sendData || !planId) {
    return;
  }
  tg.sendData(JSON.stringify({
    action: "open_plan",
    plan_id: String(planId),
  }));
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
    } catch (_error) {
      detail = "";
    }
    throw new Error(`${response.status} ${response.statusText}${detail}`);
  }
  return response.json();
}

async function loadDrafts() {
  const data = await fetchJson(`/api/drafts?${filtersToQueryString()}`);
  state.drafts = data.items || [];
  renderDraftList();

  const preferredId = state.draftId || state.drafts[0]?.draft_id || "";
  if (preferredId) {
    await openDraft(preferredId);
  } else {
    renderEmptyDetail();
  }
}

async function loadInbox() {
  const params = new URLSearchParams();
  params.set("limit", "100");
  if (state.inboxKind && state.inboxKind !== "all") {
    params.set("kind", state.inboxKind);
  }
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
  } catch (_error) {
    state.aromaAccess = false;
  }
  if (elements.aromaTabButton) {
    elements.aromaTabButton.hidden = !state.aromaAccess;
  }
}

async function loadAromas() {
  if (!state.aromaAccess) {
    renderAromasLocked();
    return;
  }
  const data = await fetchJson("/api/aromas");
  state.aromas = data.items || [];
  const selectedSlug = state.selectedAroma?.slug || state.aromas[0]?.slug || "";
  if (!selectedSlug) {
    state.selectedAroma = null;
    renderAromas();
    return;
  }
  await openAroma(selectedSlug);
}

async function openAroma(slug) {
  if (!slug) {
    return;
  }
  state.selectedAroma = await fetchJson(`/api/aromas/${encodeURIComponent(slug)}`);
  renderAromas();
}

function renderCreate() {
  elements.listTitle.textContent = "Создание";
  elements.draftCount.textContent = "4 инструмента";
  setEmptyState(true);
  elements.draftList.innerHTML = `
    <div class="create-list">
      <article class="create-card">
        <div class="draft-kind">контент</div>
        <h3 class="draft-topic">Тредс / Инстаграм / Телеграм</h3>
        <div class="draft-preview">Тема + цель + формат -> готовый черновик в истории.</div>
      </article>
        <article class="create-card">
          <div class="draft-kind">рилсы</div>
        <h3 class="draft-topic">Сценарий + раскадровка</h3>
        <div class="draft-preview">Только тема -> сценарий и 4 кадра раскадровки.</div>
      </article>
      <article class="create-card">
        <div class="draft-kind">план</div>
        <h3 class="draft-topic">Недельный контент-план</h3>
        <div class="draft-preview">Собирает тренды и сохраняет недельный план прямо в приложении.</div>
      </article>
      <article class="create-card">
        <div class="draft-kind">карусель</div>
        <h3 class="draft-topic">Карусель Инстаграм</h3>
        <div class="draft-preview">Тема -> 5 слайдов + промпты для картинок, сохраняется в черновики.</div>
      </article>
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>Создать контент</h3>
        <form class="create-form" data-create-content>
          <label>
            Тема
            <textarea name="topic" placeholder="Например: как мягко переключиться после рабочего дня"></textarea>
          </label>
          <div class="field-grid">
            <label>
              Цель
              <select name="goal_key">
                <option value="trust">Доверие</option>
                <option value="authority">Экспертность</option>
                <option value="engagement">Вовлечённость</option>
                <option value="sales">Продажи</option>
              </select>
            </label>
            <label>
              Формат
              <select name="format_key">
                <option value="threads">Тредс</option>
                <option value="instagram">Инстаграм</option>
                <option value="telegram">Телеграм</option>
              </select>
            </label>
          </div>
          <button class="primary-button" type="submit">Создать контент</button>
        </form>
      </section>
      <section class="section">
        <h3>Создать рилс</h3>
        <form class="create-form" data-create-reels>
          <label>
            Тема
            <textarea name="topic" placeholder="Например: вечерний сенсорный ритуал на 30 секунд"></textarea>
          </label>
          <button class="primary-button" type="submit">Создать рилс</button>
        </form>
      </section>
      <section class="section">
        <h3>Создать план</h3>
        <form class="create-form" data-create-plan>
          <div class="detail-preview">Собирает актуальные тренды и сохраняет недельный контент-план в разделе «Планы».</div>
          <button class="primary-button" type="submit">Собрать недельный план</button>
        </form>
      </section>
      <section class="section">
        <h3>Создать карусель</h3>
        <form class="create-form" data-create-carousel>
          <label>
            Тема
            <textarea name="topic" placeholder="Например: вечерний ритуал для перезагрузки нервной системы"></textarea>
          </label>
          <button class="primary-button" type="submit">Создать карусель</button>
        </form>
      </section>
      <section class="section">
        <h3>Создать карусель</h3>
        <form class="create-form" data-create-carousel>
          <label>
            Тема
            <textarea name="topic" placeholder="Например: вечерний ритуал для перезагрузки нервной системы"></textarea>
          </label>
          <button class="primary-button" type="submit">Сгенерировать</button>
        </form>
      </section>
    </div>
  `;
  syncDetailPanelState(false);

  const contentForm = elements.draftDetail.querySelector("[data-create-content]");
  if (contentForm) {
    bindTopicForm(contentForm, {
      pendingText: "Создаю...",
      onSubmit: async (topic) => {
      const goalKey = contentForm.querySelector("select[name='goal_key']").value;
      const formatKey = contentForm.querySelector("select[name='format_key']").value;
      try {
        const draft = await fetchJson("/api/generate/content", {
          method: "POST",
          body: JSON.stringify({ topic, goal_key: goalKey, format_key: formatKey }),
        });
        state.draftId = draft.draft_id;
        setTab("drafts");
        await loadDrafts();
      } catch (err) {
        showRequestError("Ошибка создания контента", err);
      }
      },
    });
  }

  const reelsForm = elements.draftDetail.querySelector("[data-create-reels]");
  if (reelsForm) {
    bindTopicForm(reelsForm, {
      pendingText: "Создаю...",
      onSubmit: async (topic) => {
      try {
        const reel = await fetchJson("/api/generate/reels", {
          method: "POST",
          body: JSON.stringify({ topic }),
        });
        state.selectedReels = reel;
        state.selectedFrameIndex = 0;
        setTab("reels");
        await loadReels();
        renderReelsDetail(reel);
        scheduleReelsRefresh(reel.draft_id);
      } catch (err) {
        showRequestError("Ошибка создания рилса", err);
      }
      },
    });
  }

  const planForm = elements.draftDetail.querySelector("[data-create-plan]");
  if (planForm) {
    planForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const plan = await fetchJson("/api/generate/plan", {
          method: "POST",
          body: JSON.stringify({}),
        });
        state.selectedPlan = plan;
        setTab("plans");
        await loadPlans();
        renderPlanDetail(plan);
      } catch (err) {
        showRequestError("Ошибка создания плана", err);
      }
    });
  }

  const carouselForm = elements.draftDetail.querySelector("[data-create-carousel]");
  if (carouselForm) {
    bindTopicForm(carouselForm, {
      pendingText: "Создаю...",
      onSubmit: async (topic) => {
        try {
          const draft = await fetchJson("/api/generate/carousel", {
            method: "POST",
            body: JSON.stringify({ topic }),
          });
          state.draftId = draft.draft_id;
          setTab("drafts");
          await loadDrafts();
        } catch (err) {
          showRequestError("Ошибка создания карусели", err);
        }
      },
    });
  }
}

function aromaSection(title, content) {
  return `
    <section class="section">
      <h3>${escapeHtml(title)}</h3>
      <div class="detail-preview">${escapeHtml(content || "Нет данных.")}</div>
    </section>
  `;
}

function renderAromasLocked() {
  elements.listTitle.textContent = "Ароматы";
  elements.draftCount.textContent = "";
  setEmptyState(true);
  elements.draftList.innerHTML = `
    <div class="detail-preview">Доступ к ароматическому помощнику открыт только для выбранных Telegram-пользователей.</div>
  `;
  elements.draftDetail.innerHTML = `<div class="detail-empty">Нет доступа к карточкам масел.</div>`;
  syncDetailPanelState(false);
}

function renderAromas() {
  const items = state.aromas || [];
  const query = state.aromaSearch.trim().toLowerCase();
  const filtered = items.filter((item) => {
    const haystack = `${item.name} ${item.description || ""}`.toLowerCase();
    return !query || haystack.includes(query);
  });
  const aroma = state.selectedAroma;
  elements.listTitle.textContent = "Ароматы";
  elements.draftCount.textContent = `${items.length} масел`;
  setEmptyState(filtered.length > 0, "Масла не найдены.");
  elements.draftList.innerHTML = `
    <div class="aroma-search">
      <label>
        Поиск масла
        <input id="aromaSearchInput" type="search" placeholder="Например: лаванда" value="${escapeHtml(state.aromaSearch)}" />
      </label>
    </div>
    <div class="plans-list">
      ${filtered.map((item) => `
        <article class="draft-card${item.slug === aroma?.slug ? " active" : ""}">
          <div class="draft-kind">масло</div>
          <h3 class="draft-topic">${escapeHtml(item.name)}</h3>
          <div class="draft-preview">${escapeHtml(item.description || "")}</div>
          <button type="button" data-aroma-open="${escapeHtml(item.slug)}">Открыть</button>
        </article>
      `).join("")}
    </div>
  `;

  const searchInput = document.getElementById("aromaSearchInput");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      state.aromaSearch = searchInput.value;
      renderAromas();
    });
  }

  elements.draftList.querySelectorAll("[data-aroma-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openAroma(button.dataset.aromaOpen);
    });
  });

  if (!aroma) {
    elements.draftDetail.innerHTML = `<div class="detail-empty">Выберите масло слева.</div>`;
    syncDetailPanelState(false);
    return;
  }

  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section aroma-hero">
        <img class="aroma-image" src="${escapeHtml(aroma.image_url)}" alt="${escapeHtml(aroma.image_alt)}" />
        <div class="aroma-image-caption">${escapeHtml(aroma.image_alt)}</div>
      </section>
      ${aromaSection("Описание действия масла", aroma.description)}
      ${aromaSection("Какие вопросы вызывает масло", aroma.questions)}
      ${aromaSection("Действие на НПС", aroma.nps_effect)}
      ${aromaSection("Терапевтические свойства", aroma.therapeutic_properties)}
      ${aromaSection("Психологические свойства", aroma.psychological_properties)}
      ${aromaSection('Ресурсные значения "+"', aroma.resource_values?.plus)}
      ${aromaSection('Ресурсные значения "-"', aroma.resource_values?.minus)}
      ${aromaSection("Исторические сведения", aroma.history)}
      ${aromaSection("Летучесть", aroma.volatility)}
    </div>
  `;
  syncDetailPanelState(false);
}

function setTab(tab) {
  if (tab === "aromas" && !state.aromaAccess) {
    tab = "drafts";
  }
  state.tab = tab;
  const params = new URLSearchParams(window.location.search);
  params.set("tab", tab);
  if (state.draftId) {
    params.set("draft_id", state.draftId);
  }
  history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
  for (const button of elements.tabButtons) {
    button.classList.toggle("active", button.dataset.tab === tab);
  }
  const isDrafts = tab === "drafts";
  for (const node of [elements.kindFilter, elements.statusFilter, elements.feedbackFilter, elements.queryFilter]) {
    node.closest("label").hidden = !isDrafts;
  }
}

function groupInboxItems(items) {
  return {
    plan: items.filter((item) => item.category === "plan"),
    reels: items.filter((item) => item.category === "reels"),
    content: items.filter((item) => item.category === "content"),
  };
}

function inboxSectionMarkup(title, items) {
  if (!items.length) {
    return "";
  }
  return `
    <section class="inbox-section">
      <h3>${escapeHtml(title)}</h3>
      ${items.map((item) => `
        <article class="draft-card">
          <div class="draft-kind">${escapeHtml(kindLabel(item.kind))}</div>
          <h4 class="draft-topic">${escapeHtml(item.topic)}</h4>
          <div class="draft-preview">${escapeHtml(item.preview || "Без превью")}</div>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(statusLabel(item.status))}</span>
            <span class="tag">${escapeHtml(kindLabel(item.source))}</span>
          </div>
          <div class="meta">${escapeHtml(item.review_reason || "")}</div>
          <div class="actions-row">
            <button type="button" data-inbox-open="${escapeHtml(item.draft_id)}">Открыть</button>
            <button type="button" data-inbox-review="${escapeHtml(item.draft_id)}">На согласование</button>
            <button type="button" data-inbox-approve="${escapeHtml(item.draft_id)}">Согласовать</button>
          </div>
        </article>
      `).join("")}
    </section>
  `;
}

function renderInbox() {
  elements.listTitle.textContent = "Согласование";
  const items = state.inbox || [];
  const grouped = groupInboxItems(items);
  elements.draftCount.textContent = `${items.length} на проверке`;
  setEmptyState(items.length > 0, "В очереди согласования пока пусто.");
  elements.draftList.innerHTML = `
    <div class="inbox-toolbar">
      <label>
        Тип очереди
        <select id="inboxKindFilter">
          <option value="all"${state.inboxKind === "all" ? " selected" : ""}>Все</option>
          <option value="content"${state.inboxKind === "content" ? " selected" : ""}>Контент</option>
          <option value="reels"${state.inboxKind === "reels" ? " selected" : ""}>Рилсы</option>
          <option value="plan"${state.inboxKind === "plan" ? " selected" : ""}>Из плана</option>
        </select>
      </label>
    </div>
    <div class="plans-list">
      ${inboxSectionMarkup("Из плана", grouped.plan)}
      ${inboxSectionMarkup("Рилсы", grouped.reels)}
      ${inboxSectionMarkup("Контент", grouped.content)}
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>Очередь согласования</h3>
        <div class="detail-preview">Здесь видно, что ждёт проверки: новый черновик, материал из плана или рилс-черновик.</div>
      </section>
    </div>
  `;
  syncDetailPanelState(false);

  const inboxKindFilter = document.getElementById("inboxKindFilter");
  if (inboxKindFilter) {
    inboxKindFilter.addEventListener("change", async () => {
      state.inboxKind = inboxKindFilter.value;
      await loadInbox();
    });
  }


  elements.draftList.querySelectorAll("[data-inbox-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      const draftId = button.dataset.inboxOpen;
      state.draftId = draftId;
      setTab("drafts");
      await loadDrafts();
    });
  });

  elements.draftList.querySelectorAll("[data-inbox-review]").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetchJson(`/api/drafts/${button.dataset.inboxReview}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "in_review" }),
      });
      await loadInbox();
    });
  });

  elements.draftList.querySelectorAll("[data-inbox-approve]").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetchJson(`/api/drafts/${button.dataset.inboxApprove}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "approved" }),
      });
      await loadInbox();
    });
  });
}

function renderDraftList() {
  elements.listTitle.textContent = "Черновики";
  elements.draftList.innerHTML = "";
  elements.draftCount.textContent = `${state.drafts.length} шт`;
  setEmptyState(state.drafts.length > 0);

  for (const draft of state.drafts) {
    const article = document.createElement("article");
    article.className = `draft-card${draft.draft_id === state.draftId ? " active" : ""}`;
    article.innerHTML = `
      <div class="draft-kind">${escapeHtml(kindLabel(draft.kind))}</div>
      <h3 class="draft-topic">${escapeHtml(draft.topic)}</h3>
      <div class="draft-preview">${escapeHtml(draft.preview || "Без превью")}</div>
      <div class="draft-meta">
        <span class="tag">${escapeHtml(statusLabel(draft.status))}</span>
        <span class="tag">${escapeHtml(feedbackLabel(draft.feedback))}</span>
        <span class="tag">${escapeHtml(kindLabel(draft.source))}</span>
      </div>
    `;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Открыть";
    button.addEventListener("click", () => openDraft(draft.draft_id));
    article.appendChild(button);
    elements.draftList.appendChild(article);
  }
  syncDetailPanelState(state.drafts.length === 0);
}

function renderStatus() {
  elements.listTitle.textContent = "Статус";
  const status = state.status;
  const items = status?.items || [];
  elements.draftCount.textContent = `${items.length} источников`;
  setEmptyState(items.length > 0, "Источники не найдены.");
  elements.draftList.innerHTML = `
    <div class="status-list">
      ${items.map((item) => `
        <article class="status-card">
          <strong>${escapeHtml(item.source)}</strong>
          <span class="${item.enabled ? "status-good" : "status-bad"}">
            ${item.enabled ? "включён" : "выключен"}
          </span>
        </article>
      `).join("")}
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>Дайджест</h3>
        <div class="detail-preview">Время: ${escapeHtml(status?.digest_time || "")}\nТаймзона: ${escapeHtml(status?.timezone || "")}</div>
      </section>
      <section class="section">
        <h3>Адрес Mini App</h3>
        <div class="detail-preview">${escapeHtml(status?.mini_app_url || "не настроен")}</div>
      </section>
    </div>
  `;
  syncDetailPanelState(false);
}

function renderPlans() {
  elements.listTitle.textContent = "Планы";
  const items = state.plans || [];
  elements.draftCount.textContent = `${items.length} планов`;
  setEmptyState(items.length > 0, "Планы пока не созданы.");
  elements.draftList.innerHTML = `
    <div class="plans-list">
      ${items.map((plan) => `
        <article class="plan-card">
          <div class="draft-kind">недельный план</div>
          <h3 class="draft-topic">${escapeHtml(plan.plan_id)}</h3>
          <div class="draft-preview">${escapeHtml((plan.raw_text || "").slice(0, 220) || "Без текста плана")}</div>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(plan.entries.length)} записей</span>
            <span class="tag">${escapeHtml(plan.related_drafts.length)} черновиков</span>
          </div>
          <button type="button" data-plan-open="${escapeHtml(plan.plan_id)}">Открыть</button>
        </article>
      `).join("")}
    </div>
  `;

  elements.draftList.querySelectorAll("[data-plan-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openPlan(button.dataset.planOpen);
    });
  });

  if (items[0] && !state.selectedPlan) {
    renderPlanDetail(items[0]);
  } else if (!items.length) {
    elements.draftDetail.innerHTML = `<div class="detail-empty">Планы пока не созданы.</div>`;
    syncDetailPanelState(true);
    return;
  }
  syncDetailPanelState(!items.length && !state.selectedPlan);
}

function renderReels() {
  elements.listTitle.textContent = "Рилсы";
  const items = state.reels || [];
  elements.draftCount.textContent = `${items.length} рилсов`;
  setEmptyState(items.length > 0, "Рилсы пока не созданы.");
  elements.draftList.innerHTML = `
    <div class="plans-list">
      ${items.map((reel) => `
        <article class="reels-card">
          <div class="draft-kind">рилс-черновик</div>
          <h3 class="draft-topic">${escapeHtml(reel.topic)}</h3>
          <div class="draft-preview">${escapeHtml(reel.preview || "Без сценария")}</div>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(statusLabel(reel.status))}</span>
            <span class="tag">${escapeHtml(reel.images_ready)} кадров готово</span>
            <span class="tag">${escapeHtml(reel.frame_count)} кадров</span>
          </div>
          <button type="button" data-reels-open="${escapeHtml(reel.draft_id)}">Открыть</button>
        </article>
      `).join("")}
    </div>
  `;

  elements.draftList.querySelectorAll("[data-reels-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openReels(button.dataset.reelsOpen);
    });
  });

  if (items[0] && !state.selectedReels) {
    renderReelsDetail(items[0]);
  } else if (!items.length) {
    elements.draftDetail.innerHTML = `<div class="detail-empty">Рилсы пока не созданы.</div>`;
    syncDetailPanelState(true);
    return;
  }
  syncDetailPanelState(!items.length && !state.selectedReels);
}

async function openReels(draftId) {
  const reel = await fetchJson(`/api/reels/${draftId}`);
  state.selectedReels = reel;
  state.selectedFrameIndex = 0;
  renderReelsDetail(reel);
}

async function saveReelsFrameNote(draftId, frameIndex, note) {
  const reel = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/note`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
  state.selectedReels = reel;
  state.reels = state.reels.map((item) =>
    item.draft_id === reel.draft_id ? { ...item, ...reel } : item
  );
  renderReels();
  renderReelsDetail(reel);
}

async function saveReelsFramePrompt(draftId, frameIndex, prompt) {
  const reel = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/prompt`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
  state.selectedReels = reel;
  state.reels = state.reels.map((item) =>
    item.draft_id === reel.draft_id ? { ...item, ...reel } : item
  );
  renderReels();
  renderReelsDetail(reel);
}

async function regenerateReelsFrame(draftId, frameIndex, button) {
  const originalText = button.innerText;
  button.disabled = true;
  button.innerText = "Генерирую...";
  try {
    const reel = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/regenerate`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.selectedReels = reel;
    state.reels = state.reels.map((item) =>
      item.draft_id === reel.draft_id ? { ...item, ...reel } : item
    );
    renderReels();
    renderReelsDetail(reel);
  } catch (error) {
    showRequestError("Не удалось пересобрать кадр", error);
  } finally {
    button.disabled = false;
    button.innerText = originalText;
  }
}

async function exportReelsProductionPack(draftId) {
  const payload = await fetchJson(`/api/reels/${draftId}/export`);
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${draftId}-production-pack.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderReelsDetail(reel) {
  state.selectedReels = reel;
  const frames = Array.isArray(reel.frames) ? reel.frames : [];
  const frame = frames[state.selectedFrameIndex] || frames[0] || null;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <div class="detail-top">
        <div>
          <p class="eyebrow">рилс • ${escapeHtml(kindLabel(reel.source || ""))}</p>
          <h2 class="detail-title">${escapeHtml(reel.topic)}</h2>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(statusLabel(reel.status))}</span>
            <span class="tag">${escapeHtml(feedbackLabel(reel.feedback))}</span>
            <span class="tag">${escapeHtml(reel.images_ready)} кадров готово</span>
          </div>
          <div class="actions-row">
            <button class="status-button" data-reel-status="draft">Черновик</button>
            <button class="status-button" data-reel-status="in_review">На согласовании</button>
            <button class="status-button" data-reel-status="approved">Согласовано</button>
            <button class="status-button" data-reel-status="published">Опубликовано</button>
          </div>
          <div class="actions-row">
            <button class="feedback-button" data-reel-feedback="worked">Сработало</button>
            <button class="feedback-button" data-reel-feedback="missed">Не сработало</button>
            <button class="feedback-button" data-reel-feedback="">Сбросить</button>
          </div>
          <div class="actions-row">
            <button class="secondary-button" type="button" data-reel-export="${escapeHtml(reel.draft_id)}">Экспорт JSON</button>
          </div>
        </div>
        <div class="actions-row">
          <button class="secondary-button" type="button" data-send-draft-chat="${escapeHtml(reel.draft_id)}">Отправить в чат</button>
          <button class="secondary-button" type="button" data-request-review="${escapeHtml(reel.draft_id)}">Запросить согласование</button>
        </div>
      </div>
      ${payloadSection("Сценарий", reel.payload?.scenario || reel.preview)}
      <section class="section">
        <h3>Кадры</h3>
        <div class="reels-frames">
          ${frames.map((item, index) => `
            <button class="reels-frame${index === state.selectedFrameIndex ? " active" : ""}" type="button" data-frame-open="${index}">
              <strong>${escapeHtml(item.timecode || `Кадр ${index + 1}`)}</strong>
              <div>${escapeHtml(item.scene || "")}</div>
            </button>
          `).join("")}
        </div>
      </section>
      ${frame ? `
        <section class="section">
          <h3>Выбранный кадр</h3>
          <div class="reels-focus">
            <strong>${escapeHtml(frame.timecode || "")}</strong>
            <div>${escapeHtml(frame.scene || "")}</div>
            <div class="meta">${escapeHtml(frame.angle || "")}</div>
            ${payloadSection("Промпт Gemini", frame.gemini_prompt)}
            ${frame.current_asset?.url
              ? `<img class="frame-image" src="${escapeHtml(frame.current_asset.url)}" alt="Кадр ассет" />`
              : `<div class="frame-loading">⏳ Кадр генерируется…</div>`}
            <div class="actions-row">
              <button class="secondary-button" type="button" data-frame-regenerate="${escapeHtml(String(frame.frame_index))}">Пересобрать кадр</button>
            </div>
            <form class="frame-note-form" data-frame-note-form="${escapeHtml(String(frame.frame_index))}">
              <label>
                Замечание
                <textarea name="note" placeholder="Например: темнее, ближе камера, меньше объектов в кадре.">${escapeHtml(frame.review_note || "")}</textarea>
              </label>
              <button class="primary-button" type="submit">Сохранить замечание</button>
            </form>
            <form class="frame-prompt-form" data-frame-prompt-form="${escapeHtml(String(frame.frame_index))}">
              <label>
                Промпт Gemini
                <textarea name="prompt" placeholder="Уточни prompt для следующей версии кадра.">${escapeHtml(frame.gemini_prompt || "")}</textarea>
              </label>
              <button class="primary-button" type="submit">Сохранить промпт</button>
            </form>
            ${(frame.prompt_revisions || []).length ? `
              <div class="revision-list">
                ${(frame.prompt_revisions || []).map((revision, index) => `
                  <div class="revision-item">
                    <strong>Версия ${index + 1}</strong>
                    <div>${escapeHtml(revision)}</div>
                  </div>
                `).join("")}
              </div>
            ` : ""}
            ${(frame.asset_revisions || []).length ? `
              <div class="asset-revisions">
                ${(frame.asset_revisions || []).map((asset, index) => `
                  <div class="asset-revision">
                    <strong>Версия кадра ${index + 1}</strong>
                    <div class="meta">${escapeHtml(asset.generated_at || "")}</div>
                    ${asset.url ? `<img class="frame-image" src="${escapeHtml(asset.url)}" alt="Версия кадра" />` : ""}
                  </div>
                `).join("")}
              </div>
            ` : ""}
          </div>
        </section>
      ` : ""}
      <section class="section">
        <h3>Шот-лист</h3>
        <div class="shot-list">
          ${(reel.shot_list || []).map((shot) => `
            <div class="shot-item">
              <strong>${escapeHtml(shot.title || "")}</strong>
              <div>${escapeHtml(shot.timecode || "")}</div>
              <div>${escapeHtml(shot.action || "")}</div>
              <div class="meta">${escapeHtml(shot.camera || "")}</div>
              <div class="meta">${shot.asset_ready ? "Кадр готов" : "Кадр ещё не готов"}</div>
              ${shot.note ? `<div class="meta">Замечание: ${escapeHtml(shot.note)}</div>` : ""}
            </div>
          `).join("")}
        </div>
      </section>
      <section class="section">
        <h3>Продакшн-заметки</h3>
        <div class="shot-list">
          <div class="shot-item">
            <strong>Обязательно</strong>
            <div>${(reel.production_notes?.required || []).map((item) => escapeHtml(item)).join("<br />") || "Нет"}</div>
          </div>
          <div class="shot-item">
            <strong>Опционально</strong>
            <div>${(reel.production_notes?.optional || []).map((item) => escapeHtml(item)).join("<br />") || "Нет"}</div>
          </div>
        </div>
      </section>
      <section class="section">
        <h3>Готовность к экспорту</h3>
        <div class="shot-list">
          <div class="shot-item">
            <strong>Готово кадров</strong>
            <div>${escapeHtml(String((reel.frames || []).filter((item) => item.current_asset?.url).length))} / ${escapeHtml(String(reel.frame_count || 0))}</div>
          </div>
          <div class="shot-item">
            <strong>Что экспортируется</strong>
            <div>JSON с сценарием, шот-листом, замечаниями, промптами и URL кадров.</div>
          </div>
        </div>
      </section>
      <section class="section">
        <h3>JSON-данные</h3>
        <pre class="json-block">${escapeHtml(JSON.stringify(reel.payload || {}, null, 2))}</pre>
      </section>
    </div>
  `;
  syncDetailPanelState(false);

  elements.draftDetail.querySelectorAll("[data-frame-open]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedFrameIndex = Number(button.dataset.frameOpen);
      renderReelsDetail(reel);
    });
  });

  const exportButton = elements.draftDetail.querySelector("[data-reel-export]");
  if (exportButton) {
    exportButton.addEventListener("click", async () => {
      await exportReelsProductionPack(reel.draft_id);
    });
  }

  const sendDraftButton = elements.draftDetail.querySelector("[data-send-draft-chat]");
  if (sendDraftButton) {
    sendDraftButton.addEventListener("click", () => {
      sendDraftToChat(sendDraftButton.dataset.sendDraftChat);
    });
  }

  const requestReviewButton = elements.draftDetail.querySelector("[data-request-review]");
  if (requestReviewButton) {
    requestReviewButton.addEventListener("click", () => {
      requestDraftReview(requestReviewButton.dataset.requestReview);
    });
  }

  const noteForm = elements.draftDetail.querySelector("[data-frame-note-form]");
  if (noteForm) {
    noteForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const note = noteForm.querySelector("textarea[name='note']").value.trim();
      await saveReelsFrameNote(reel.draft_id, state.selectedFrameIndex, note);
    });
  }

  const promptForm = elements.draftDetail.querySelector("[data-frame-prompt-form]");
  if (promptForm) {
    promptForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const prompt = promptForm.querySelector("textarea[name='prompt']").value.trim();
      await saveReelsFramePrompt(reel.draft_id, state.selectedFrameIndex, prompt);
    });
  }

  const regenButton = elements.draftDetail.querySelector("[data-frame-regenerate]");
  if (regenButton) {
    regenButton.addEventListener("click", async () => {
      await regenerateReelsFrame(reel.draft_id, state.selectedFrameIndex, regenButton);
    });
  }

  elements.draftDetail.querySelectorAll("[data-reel-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      const updated = await fetchJson(`/api/drafts/${reel.draft_id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: button.dataset.reelStatus }),
      });
      state.selectedReels = { ...reel, ...updated };
      state.reels = state.reels.map((item) =>
        item.draft_id === reel.draft_id ? { ...item, ...updated } : item
      );
      renderReels();
      renderReelsDetail(state.selectedReels);
    });
  });

  elements.draftDetail.querySelectorAll("[data-reel-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      const updated = await fetchJson(`/api/drafts/${reel.draft_id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ feedback: button.dataset.reelFeedback }),
      });
      state.selectedReels = { ...reel, ...updated };
      state.reels = state.reels.map((item) =>
        item.draft_id === reel.draft_id ? { ...item, ...updated } : item
      );
      renderReels();
      renderReelsDetail(state.selectedReels);
    });
  });
}

async function openPlan(planId) {
  const plan = await fetchJson(`/api/plans/${planId}`);
  state.selectedPlan = plan;
  renderPlanDetail(plan);
}

async function generateFromPlan(planId, entryIndex) {
  const response = await fetchJson(`/api/plans/${planId}/generate`, {
    method: "POST",
    body: JSON.stringify({ entry_index: entryIndex }),
  });
  const draft = response.draft;
  state.draftId = draft.draft_id;
  setTab("drafts");
  await loadDrafts();
}

function renderPlanDetail(plan) {
  state.selectedPlan = plan;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>ID плана</h3>
        <div class="detail-preview">${escapeHtml(plan.plan_id)}</div>
        <div class="actions-row">
          <button class="secondary-button" type="button" data-send-plan-chat="${escapeHtml(plan.plan_id)}">Отправить в чат</button>
        </div>
      </section>
      <section class="section">
        <h3>Записи</h3>
        <div class="plan-entries">
          ${plan.entries.map((entry, index) => `
            <div class="plan-entry">
              <strong>${escapeHtml(entry.day_label || "")}</strong>
              <div>${escapeHtml(kindLabel(entry.platform || ""))} / ${escapeHtml(entry.format_label || "")}</div>
              <div>${escapeHtml(entry.topic || "")}</div>
              <div class="meta">${escapeHtml(entry.goal || "")}</div>
              <div class="actions-row">
                <button class="secondary-button" type="button" data-plan-generate="${index}">Создать черновик</button>
              </div>
            </div>
          `).join("")}
        </div>
      </section>
      <section class="section">
        <h3>Связанные черновики</h3>
        <div class="related-drafts">
          ${plan.related_drafts.length ? plan.related_drafts.map((draft) => `
            <div class="plan-entry">
              <strong>${escapeHtml(kindLabel(draft.kind))}</strong>
              <div>${escapeHtml(draft.topic)}</div>
              <div class="meta">ID: ${escapeHtml(draft.draft_id)} / ${escapeHtml(statusLabel(draft.status))}</div>
            </div>
          `).join("") : '<div class="detail-preview">По этому плану пока не созданы черновики.</div>'}
        </div>
      </section>
      <section class="section">
        <h3>Исходный план</h3>
        <pre class="json-block">${escapeHtml(plan.raw_text || "")}</pre>
      </section>
    </div>
  `;
  syncDetailPanelState(false);

  elements.draftDetail.querySelectorAll("[data-plan-generate]").forEach((button) => {
    button.addEventListener("click", async () => {
      await generateFromPlan(plan.plan_id, Number(button.dataset.planGenerate));
    });
  });

  const sendPlanButton = elements.draftDetail.querySelector("[data-send-plan-chat]");
  if (sendPlanButton) {
    sendPlanButton.addEventListener("click", () => {
      sendPlanToChat(sendPlanButton.dataset.sendPlanChat);
    });
  }
}

function keywordFieldMarkup(topicIdx, fieldKey, fieldLabel, words) {
  return `
    <div class="keyword-field">
      <strong>${escapeHtml(fieldLabel)}</strong>
      <div class="keyword-items">
        ${words.map((word) => `
          <span class="keyword-chip">
            <span>${escapeHtml(word)}</span>
            <button type="button" data-remove-topic="${topicIdx}" data-remove-field="${fieldKey}" data-remove-word="${escapeHtml(word)}">✕</button>
          </span>
        `).join("")}
      </div>
      <form class="keyword-form" data-add-topic="${topicIdx}" data-add-field="${fieldKey}">
        <input type="text" name="word" placeholder="Добавить слово" />
        <button type="submit">Добавить</button>
      </form>
    </div>
  `;
}

function renderKeywords() {
  elements.listTitle.textContent = "Ключи";
  const items = state.keywords?.items || [];
  const labels = state.keywords?.field_labels || {};
  elements.draftCount.textContent = `${items.length} тем`;
  setEmptyState(items.length > 0, "Словари пока пусты.");
  elements.draftList.innerHTML = `
    <div class="keywords-list">
      ${items.map((topic) => `
        <article class="keyword-topic">
          <h3 class="draft-topic">${escapeHtml(topic.name)}</h3>
          <div class="keyword-fields">
            ${Object.entries(topic.fields).map(([fieldKey, words]) =>
              keywordFieldMarkup(topic.topic_idx, fieldKey, labels[fieldKey] || fieldKey, words)
            ).join("")}
          </div>
        </article>
      `).join("")}
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>Словари</h3>
        <div class="detail-preview">Здесь можно редактировать словари тем и хэштегов без команды /keywords в чате.</div>
      </section>
    </div>
  `;

  elements.draftList.querySelectorAll("[data-remove-topic]").forEach((button) => {
    button.addEventListener("click", async () => {
      await mutateKeyword("/api/keywords/remove", {
        topic_idx: Number(button.dataset.removeTopic),
        field: button.dataset.removeField,
        word: button.dataset.removeWord,
      });
    });
  });

  elements.draftList.querySelectorAll("[data-add-topic]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = form.querySelector("input[name='word']");
      const word = input.value.trim();
      if (!word) {
        return;
      }
      await mutateKeyword("/api/keywords/add", {
        topic_idx: Number(form.dataset.addTopic),
        field: form.dataset.addField,
        word,
      });
      input.value = "";
    });
  });
}

async function mutateKeyword(url, payload) {
  state.keywords = await fetchJson(url, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderKeywords();
}

function storyboardMarkup(items) {
  if (!Array.isArray(items) || !items.length) {
    return "";
  }
  return `
    <section class="section">
      <h3>Раскадровка</h3>
      <div class="storyboard">
        ${items.map((frame) => `
          <div class="storyboard-frame">
            <strong>${escapeHtml(frame.timecode || "Кадр")}</strong>
            <div>${escapeHtml(frame.scene || "")}</div>
            <div class="meta">${escapeHtml(frame.angle || "")}</div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function slidesMarkup(items) {
  if (!Array.isArray(items) || !items.length) {
    return "";
  }
  return `
    <section class="section">
      <h3>Слайды</h3>
      <div class="slides">
        ${items.map((slide, index) => `
          <div class="slide">
            <strong>Слайд ${index + 1}</strong>
            <div>${escapeHtml(slide)}</div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function setSelectedDraft(draft) {
  state.selected = draft;
  state.draftId = draft.draft_id;
  const params = new URLSearchParams(window.location.search);
  params.set("draft_id", draft.draft_id);
  history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
}

function renderEmptyDetail() {
  elements.draftDetail.innerHTML = `
    <div class="detail-empty">
      Выбери черновик слева, чтобы открыть детали, сценарий, слайды и статусы.
    </div>
  `;
  syncDetailPanelState(true);
}

function isContentReviewDraft(draft) {
  return ["threads", "instagram", "telegram"].includes(String(draft.kind || "").toLowerCase());
}

function renderDraftDetail(draft) {
  const payload = draft.payload || {};
  const detailHtml = `
    <div class="detail-grid">
      <div class="detail-top">
        <div>
          <p class="eyebrow">${escapeHtml(kindLabel(draft.kind))} • ${escapeHtml(kindLabel(draft.source))}</p>
          <h2 class="detail-title">${escapeHtml(draft.topic)}</h2>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(statusLabel(draft.status))}</span>
            <span class="tag">${escapeHtml(feedbackLabel(draft.feedback))}</span>
            <span class="tag">${escapeHtml(draft.draft_id)}</span>
          </div>
        </div>
        <div class="actions">
          <div class="actions-row">
            <button class="status-button" data-status="draft">Черновик</button>
            <button class="status-button" data-status="in_review">На согласовании</button>
            <button class="status-button" data-status="approved">Согласовано</button>
            <button class="status-button" data-status="published">Опубликовано</button>
          </div>
          <div class="actions-row">
            <button class="feedback-button" data-feedback="worked">Сработало</button>
            <button class="feedback-button" data-feedback="missed">Не сработало</button>
            <button class="feedback-button" data-feedback="">Сбросить</button>
          </div>
          <div class="actions-row">
            <button class="secondary-button" type="button" data-send-draft-chat="${escapeHtml(draft.draft_id)}">Отправить в чат</button>
            <button class="secondary-button" type="button" data-request-review="${escapeHtml(draft.draft_id)}">Запросить согласование</button>
          </div>
        </div>
      </div>
      ${payloadSection("Превью", draft.preview)}
      ${payloadSection("Угол", payload.angle)}
      ${payloadSection("Хук", payload.hook)}
      ${payloadSection("Подпись", payload.caption)}
      ${payloadSection("Сценарий", payload.scenario)}
      ${payloadSection("Призыв к действию", payload.cta)}
      ${payloadSection("Хэштеги", payload.hashtags)}
      ${payloadSection("Визуальный промпт", payload.visual_prompt)}
      ${isContentReviewDraft(draft) ? `
        <section class="section">
          <h3>Редактирование контента</h3>
          <form class="content-review-form" data-content-review-form>
            <label>
              Тема
              <textarea name="topic">${escapeHtml(draft.topic || "")}</textarea>
            </label>
            <label>
              Угол
              <textarea name="angle">${escapeHtml(payload.angle || "")}</textarea>
            </label>
            <label>
              Хук
              <textarea name="hook">${escapeHtml(payload.hook || "")}</textarea>
            </label>
            <label>
              Подпись
              <textarea name="caption">${escapeHtml(payload.caption || "")}</textarea>
            </label>
            <label>
              Призыв к действию
              <textarea name="cta">${escapeHtml(payload.cta || "")}</textarea>
            </label>
            <label>
              Хэштеги
              <textarea name="hashtags">${escapeHtml(payload.hashtags || "")}</textarea>
            </label>
            <label>
              Визуальный промпт
              <textarea name="visual_prompt">${escapeHtml(payload.visual_prompt || "")}</textarea>
            </label>
            <div class="actions-row">
              <button class="primary-button" type="submit">Сохранить</button>
              <button class="secondary-button" type="button" data-content-polish>Улучшить текст</button>
              <button class="secondary-button" type="button" data-content-approve>Согласовать</button>
            </div>
          </form>
        </section>
      ` : ""}
      ${slidesMarkup(payload.slides)}
      ${storyboardMarkup(payload.storyboard)}
      <section class="section">
        <h3>JSON-данные</h3>
        <pre class="json-block">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
      </section>
    </div>
  `;
  elements.draftDetail.innerHTML = detailHtml;
  syncDetailPanelState(false);

  elements.draftDetail.querySelectorAll("[data-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      await updateDraft("status", { status: button.dataset.status });
    });
  });

  elements.draftDetail.querySelectorAll("[data-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      await updateDraft("feedback", { feedback: button.dataset.feedback });
    });
  });

  const contentForm = elements.draftDetail.querySelector("[data-content-review-form]");
  if (contentForm) {
    contentForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const updatedDraft = await fetchJson(`/api/drafts/${draft.draft_id}/content`, {
        method: "POST",
        body: JSON.stringify({
          topic: contentForm.querySelector("textarea[name='topic']").value.trim(),
          angle: contentForm.querySelector("textarea[name='angle']").value.trim(),
          hook: contentForm.querySelector("textarea[name='hook']").value.trim(),
          caption: contentForm.querySelector("textarea[name='caption']").value.trim(),
          cta: contentForm.querySelector("textarea[name='cta']").value.trim(),
          hashtags: contentForm.querySelector("textarea[name='hashtags']").value.trim(),
          visual_prompt: contentForm.querySelector("textarea[name='visual_prompt']").value.trim(),
        }),
      });
      setSelectedDraft(updatedDraft);
      state.drafts = state.drafts.map((item) =>
        item.draft_id === updatedDraft.draft_id ? { ...item, ...updatedDraft } : item
      );
      renderDraftList();
      renderDraftDetail(updatedDraft);
    });
  }

  const polishButton = elements.draftDetail.querySelector("[data-content-polish]");
  if (polishButton) {
    polishButton.addEventListener("click", async () => {
      const updatedDraft = await fetchJson(`/api/drafts/${draft.draft_id}/content/polish`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setSelectedDraft(updatedDraft);
      state.drafts = state.drafts.map((item) =>
        item.draft_id === updatedDraft.draft_id ? { ...item, ...updatedDraft } : item
      );
      renderDraftList();
      renderDraftDetail(updatedDraft);
    });
  }

  const approveButton = elements.draftDetail.querySelector("[data-content-approve]");
  if (approveButton) {
    approveButton.addEventListener("click", async () => {
      await updateDraft("status", { status: "approved" });
    });
  }

  const sendDraftButton = elements.draftDetail.querySelector("[data-send-draft-chat]");
  if (sendDraftButton) {
    sendDraftButton.addEventListener("click", () => {
      sendDraftToChat(sendDraftButton.dataset.sendDraftChat);
    });
  }

  const requestReviewButton = elements.draftDetail.querySelector("[data-request-review]");
  if (requestReviewButton) {
    requestReviewButton.addEventListener("click", () => {
      requestDraftReview(requestReviewButton.dataset.requestReview);
    });
  }
}

async function openDraft(draftId) {
  const draft = await fetchJson(`/api/drafts/${draftId}`);
  setSelectedDraft(draft);
  renderDraftList();
  renderDraftDetail(draft);
}

async function updateDraft(action, payload) {
  if (!state.draftId) {
    return;
  }
  const draft = await fetchJson(`/api/drafts/${state.draftId}/${action}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setSelectedDraft(draft);
  state.drafts = state.drafts.map((item) =>
    item.draft_id === draft.draft_id ? { ...item, ...draft } : item
  );
  renderDraftList();
  renderDraftDetail(draft);
}

function bindFilters() {
  [elements.kindFilter, elements.statusFilter, elements.feedbackFilter].forEach((node) => {
    node.addEventListener("change", loadDrafts);
  });

  let timer = null;
  elements.queryFilter.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(loadDrafts, 250);
  });

  bindPress(elements.refreshButton, async () => {
    await loadCurrentTab();
  });

  for (const button of elements.tabButtons) {
    bindPress(button, async () => {
      setTab(button.dataset.tab);
      await loadCurrentTab();
    });
  }
}

async function loadCurrentTab() {
  if (state.tab === "create") {
    renderCreate();
    return;
  }
  if (state.tab === "inbox") {
    await loadInbox();
    return;
  }
  if (state.tab === "plans") {
    await loadPlans();
    return;
  }
  if (state.tab === "reels") {
    await loadReels();
    return;
  }
  if (state.tab === "aromas") {
    await loadAromas();
    return;
  }
  if (state.tab === "status") {
    await loadStatus();
    return;
  }
  if (state.tab === "keywords") {
    await loadKeywords();
    return;
  }
  await loadDrafts();
}

async function bootstrap() {
  applyTelegramTheme();
  bindFilters();
  try {
    await loadAromaAccess();
    setTab(state.tab);
    await loadCurrentTab();
  } catch (error) {
    elements.draftDetail.innerHTML = `
      <div class="detail-empty">
        Не удалось загрузить Mini App.<br />
        <span class="status-bad">${escapeHtml(error.message)}</span>
      </div>
    `;
  }
}

bootstrap();
