const state = {
  draftId: new URLSearchParams(window.location.search).get("draft_id") || "",
  drafts: [],
  selected: null,
};

const elements = {
  draftList: document.getElementById("draftList"),
  draftDetail: document.getElementById("draftDetail"),
  draftCount: document.getElementById("draftCount"),
  emptyState: document.getElementById("emptyState"),
  kindFilter: document.getElementById("kindFilter"),
  statusFilter: document.getElementById("statusFilter"),
  feedbackFilter: document.getElementById("feedbackFilter"),
  queryFilter: document.getElementById("queryFilter"),
  refreshButton: document.getElementById("refreshButton"),
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

function renderDraftList() {
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
}

async function bootstrap() {
  applyTelegramTheme();
  bindFilters();
  try {
    await loadDrafts();
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
