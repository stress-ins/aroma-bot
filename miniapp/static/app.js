const state = {
  tab: new URLSearchParams(window.location.search).get("tab") || "drafts",
  draftId: new URLSearchParams(window.location.search).get("draft_id") || "",
  drafts: [],
  selected: null,
  status: null,
  keywords: null,
};

const elements = {
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
  tabButtons: Array.from(document.querySelectorAll("[data-tab]")),
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

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadDrafts() {
  const data = await fetchJson(`/miniapp/api/drafts?${filtersToQueryString()}`);
  state.drafts = data.items || [];
  renderDraftList();

  const preferredId = state.draftId || state.drafts[0]?.draft_id || "";
  if (preferredId) {
    await openDraft(preferredId);
  } else {
    renderEmptyDetail();
  }
}

async function loadStatus() {
  state.status = await fetchJson("/miniapp/api/status");
  renderStatus();
}

async function loadKeywords() {
  state.keywords = await fetchJson("/miniapp/api/keywords");
  renderKeywords();
}

function setTab(tab) {
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

function renderDraftList() {
  elements.listTitle.textContent = "Drafts";
  elements.draftList.innerHTML = "";
  elements.draftCount.textContent = `${state.drafts.length} шт`;
  elements.emptyState.hidden = state.drafts.length > 0;

  for (const draft of state.drafts) {
    const article = document.createElement("article");
    article.className = `draft-card${draft.draft_id === state.draftId ? " active" : ""}`;
    article.innerHTML = `
      <div class="draft-kind">${escapeHtml(draft.kind)}</div>
      <h3 class="draft-topic">${escapeHtml(draft.topic)}</h3>
      <div class="draft-preview">${escapeHtml(draft.preview || "Без превью")}</div>
      <div class="draft-meta">
        <span class="tag">${escapeHtml(draft.status)}</span>
        <span class="tag">${escapeHtml(draft.feedback || "no feedback")}</span>
        <span class="tag">${escapeHtml(draft.source)}</span>
      </div>
    `;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Открыть";
    button.addEventListener("click", () => openDraft(draft.draft_id));
    article.appendChild(button);
    elements.draftList.appendChild(article);
  }
}

function renderStatus() {
  elements.listTitle.textContent = "Status";
  const status = state.status;
  const items = status?.items || [];
  elements.draftCount.textContent = `${items.length} sources`;
  elements.emptyState.hidden = items.length > 0;
  elements.draftList.innerHTML = `
    <div class="status-list">
      ${items.map((item) => `
        <article class="status-card">
          <strong>${escapeHtml(item.source)}</strong>
          <span class="${item.enabled ? "status-good" : "status-bad"}">
            ${item.enabled ? "enabled" : "disabled"}
          </span>
        </article>
      `).join("")}
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>Digest</h3>
        <div class="detail-preview">Время: ${escapeHtml(status?.digest_time || "")}\nТаймзона: ${escapeHtml(status?.timezone || "")}</div>
      </section>
      <section class="section">
        <h3>Mini App URL</h3>
        <div class="detail-preview">${escapeHtml(status?.mini_app_url || "не настроен")}</div>
      </section>
    </div>
  `;
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
  elements.listTitle.textContent = "Keywords";
  const items = state.keywords?.items || [];
  const labels = state.keywords?.field_labels || {};
  elements.draftCount.textContent = `${items.length} topics`;
  elements.emptyState.hidden = items.length > 0;
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
        <h3>Keywords Workspace</h3>
        <div class="detail-preview">Здесь можно редактировать словари тем и хэштегов без команды /keywords в чате.</div>
      </section>
    </div>
  `;

  elements.draftList.querySelectorAll("[data-remove-topic]").forEach((button) => {
    button.addEventListener("click", async () => {
      await mutateKeyword("/miniapp/api/keywords/remove", {
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
      await mutateKeyword("/miniapp/api/keywords/add", {
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
      <h3>Storyboard</h3>
      <div class="storyboard">
        ${items.map((frame) => `
          <div class="storyboard-frame">
            <strong>${escapeHtml(frame.timecode || "Frame")}</strong>
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
      <h3>Slides</h3>
      <div class="slides">
        ${items.map((slide, index) => `
          <div class="slide">
            <strong>Slide ${index + 1}</strong>
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
      Выбери draft слева, чтобы открыть детали, сценарий, слайды и статусы.
    </div>
  `;
}

function renderDraftDetail(draft) {
  const payload = draft.payload || {};
  const detailHtml = `
    <div class="detail-grid">
      <div class="detail-top">
        <div>
          <p class="eyebrow">${escapeHtml(draft.kind)} • ${escapeHtml(draft.source)}</p>
          <h2 class="detail-title">${escapeHtml(draft.topic)}</h2>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(draft.status)}</span>
            <span class="tag">${escapeHtml(draft.feedback || "no feedback")}</span>
            <span class="tag">${escapeHtml(draft.draft_id)}</span>
          </div>
        </div>
        <div class="actions">
          <div class="actions-row">
            <button class="status-button" data-status="draft">draft</button>
            <button class="status-button" data-status="in_review">in_review</button>
            <button class="status-button" data-status="approved">approved</button>
            <button class="status-button" data-status="published">published</button>
          </div>
          <div class="actions-row">
            <button class="feedback-button" data-feedback="worked">worked</button>
            <button class="feedback-button" data-feedback="missed">missed</button>
            <button class="feedback-button" data-feedback="">clear</button>
          </div>
        </div>
      </div>
      ${payloadSection("Preview", draft.preview)}
      ${payloadSection("Angle", payload.angle)}
      ${payloadSection("Hook", payload.hook)}
      ${payloadSection("Caption", payload.caption)}
      ${payloadSection("Scenario", payload.scenario)}
      ${payloadSection("CTA", payload.cta)}
      ${payloadSection("Hashtags", payload.hashtags)}
      ${payloadSection("Visual Prompt", payload.visual_prompt)}
      ${slidesMarkup(payload.slides)}
      ${storyboardMarkup(payload.storyboard)}
      <section class="section">
        <h3>Payload JSON</h3>
        <pre class="json-block">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
      </section>
    </div>
  `;
  elements.draftDetail.innerHTML = detailHtml;

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
}

async function openDraft(draftId) {
  const draft = await fetchJson(`/miniapp/api/drafts/${draftId}`);
  setSelectedDraft(draft);
  renderDraftList();
  renderDraftDetail(draft);
}

async function updateDraft(action, payload) {
  if (!state.draftId) {
    return;
  }
  const draft = await fetchJson(`/miniapp/api/drafts/${state.draftId}/${action}`, {
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

  elements.refreshButton.addEventListener("click", loadDrafts);
  for (const button of elements.tabButtons) {
    button.addEventListener("click", async () => {
      setTab(button.dataset.tab);
      await loadCurrentTab();
    });
  }
}

async function loadCurrentTab() {
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
