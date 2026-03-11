const state = {
  tab: new URLSearchParams(window.location.search).get("tab") || "drafts",
  draftId: new URLSearchParams(window.location.search).get("draft_id") || "",
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

function _initDataHeader() {
  const initData = window.Telegram?.WebApp?.initData;
  return initData ? { "X-Telegram-Init-Data": initData } : {};
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
  const extraHeaders = options.method === "POST" ? _initDataHeader() : {};
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...extraHeaders },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
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

function renderCreate() {
  elements.listTitle.textContent = "Create";
  elements.draftCount.textContent = "3 tools";
  elements.emptyState.hidden = true;
  elements.draftList.innerHTML = `
    <div class="create-list">
      <article class="create-card">
        <div class="draft-kind">content</div>
        <h3 class="draft-topic">Threads / Instagram / Telegram</h3>
        <div class="draft-preview">Тема + цель + формат -> готовый draft в истории.</div>
      </article>
      <article class="create-card">
        <div class="draft-kind">reels</div>
        <h3 class="draft-topic">Scenario + storyboard</h3>
        <div class="draft-preview">Только тема -> сценарий и 4 кадра раскадровки.</div>
      </article>
      <article class="create-card">
        <div class="draft-kind">plan</div>
        <h3 class="draft-topic">Weekly content plan</h3>
        <div class="draft-preview">Собирает тренды и сохраняет недельный план прямо в приложении.</div>
      </article>
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>Create Content</h3>
        <form class="create-form" data-create-content>
          <label>
            Topic
            <textarea name="topic" placeholder="Например: как мягко переключиться после рабочего дня"></textarea>
          </label>
          <div class="field-grid">
            <label>
              Goal
              <select name="goal_key">
                <option value="trust">trust</option>
                <option value="authority">authority</option>
                <option value="engagement">engagement</option>
                <option value="sales">sales</option>
              </select>
            </label>
            <label>
              Format
              <select name="format_key">
                <option value="threads">threads</option>
                <option value="instagram">instagram</option>
                <option value="telegram">telegram</option>
              </select>
            </label>
          </div>
          <button class="primary-button" type="submit">Generate content</button>
        </form>
      </section>
      <section class="section">
        <h3>Create Reels</h3>
        <form class="create-form" data-create-reels>
          <label>
            Topic
            <textarea name="topic" placeholder="Например: вечерний сенсорный ритуал на 30 секунд"></textarea>
          </label>
          <button class="primary-button" type="submit">Generate reels</button>
        </form>
      </section>
      <section class="section">
        <h3>Create Plan</h3>
        <form class="create-form" data-create-plan>
          <div class="detail-preview">Собирает актуальные тренды и сохраняет недельный контент-план в Plan workspace.</div>
          <button class="primary-button" type="submit">Generate weekly plan</button>
        </form>
      </section>
    </div>
  `;

  const contentForm = elements.draftDetail.querySelector("[data-create-content]");
  if (contentForm) {
    contentForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const topic = contentForm.querySelector("textarea[name='topic']").value.trim();
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
        alert("Ошибка генерации: " + (err.message || err));
      }
    });
  }

  const reelsForm = elements.draftDetail.querySelector("[data-create-reels]");
  if (reelsForm) {
    reelsForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const topic = reelsForm.querySelector("textarea[name='topic']").value.trim();
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
      } catch (err) {
        alert("Ошибка генерации: " + (err.message || err));
      }
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
        alert("Ошибка генерации: " + (err.message || err));
      }
    });
  }
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
          <div class="draft-kind">${escapeHtml(item.kind)}</div>
          <h4 class="draft-topic">${escapeHtml(item.topic)}</h4>
          <div class="draft-preview">${escapeHtml(item.preview || "Без превью")}</div>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(item.status)}</span>
            <span class="tag">${escapeHtml(item.source)}</span>
          </div>
          <div class="meta">${escapeHtml(item.review_reason || "")}</div>
          <div class="actions-row">
            <button type="button" data-inbox-open="${escapeHtml(item.draft_id)}">Open</button>
            <button type="button" data-inbox-review="${escapeHtml(item.draft_id)}">In review</button>
            <button type="button" data-inbox-approve="${escapeHtml(item.draft_id)}">Approve</button>
          </div>
        </article>
      `).join("")}
    </section>
  `;
}

function renderInbox() {
  elements.listTitle.textContent = "Approval Inbox";
  const items = state.inbox || [];
  const grouped = groupInboxItems(items);
  elements.draftCount.textContent = `${items.length} review`;
  elements.emptyState.hidden = items.length > 0;
  elements.draftList.innerHTML = `
    <div class="inbox-toolbar">
      <label>
        Queue type
        <select id="inboxKindFilter">
          <option value="all"${state.inboxKind === "all" ? " selected" : ""}>All</option>
          <option value="content"${state.inboxKind === "content" ? " selected" : ""}>Content</option>
          <option value="reels"${state.inboxKind === "reels" ? " selected" : ""}>Reels</option>
          <option value="plan"${state.inboxKind === "plan" ? " selected" : ""}>Plan-derived</option>
        </select>
      </label>
    </div>
    <div class="plans-list">
      ${inboxSectionMarkup("Plan-derived", grouped.plan)}
      ${inboxSectionMarkup("Reels", grouped.reels)}
      ${inboxSectionMarkup("Content", grouped.content)}
    </div>
  `;
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      <section class="section">
        <h3>Approval Pipeline</h3>
        <div class="detail-preview">Inbox показывает, что именно ждёт review, и почему: новый draft, item из плана или reels-черновик.</div>
      </section>
    </div>
  `;

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

function renderPlans() {
  elements.listTitle.textContent = "Plans";
  const items = state.plans || [];
  elements.draftCount.textContent = `${items.length} plans`;
  elements.emptyState.hidden = items.length > 0;
  elements.draftList.innerHTML = `
    <div class="plans-list">
      ${items.map((plan) => `
        <article class="plan-card">
          <div class="draft-kind">weekly plan</div>
          <h3 class="draft-topic">${escapeHtml(plan.plan_id)}</h3>
          <div class="draft-preview">${escapeHtml((plan.raw_text || "").slice(0, 220) || "Без текста плана")}</div>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(plan.entries.length)} entries</span>
            <span class="tag">${escapeHtml(plan.related_drafts.length)} drafts</span>
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
    elements.draftDetail.innerHTML = `<div class="detail-empty">Планы пока не сгенерированы через /plan.</div>`;
  }
}

function renderReels() {
  elements.listTitle.textContent = "Reels";
  const items = state.reels || [];
  elements.draftCount.textContent = `${items.length} reels`;
  elements.emptyState.hidden = items.length > 0;
  elements.draftList.innerHTML = `
    <div class="plans-list">
      ${items.map((reel) => `
        <article class="reels-card">
          <div class="draft-kind">reels draft</div>
          <h3 class="draft-topic">${escapeHtml(reel.topic)}</h3>
          <div class="draft-preview">${escapeHtml(reel.preview || "Без сценария")}</div>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(reel.status)}</span>
            <span class="tag">${escapeHtml(reel.images_ready)} images</span>
            <span class="tag">${escapeHtml(reel.frame_count)} frames</span>
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
    elements.draftDetail.innerHTML = `<div class="detail-empty">Reels-черновики пока не сгенерированы.</div>`;
  }
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

async function regenerateReelsFrame(draftId, frameIndex) {
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
          <p class="eyebrow">reels • ${escapeHtml(reel.source || "")}</p>
          <h2 class="detail-title">${escapeHtml(reel.topic)}</h2>
          <div class="draft-meta">
            <span class="tag">${escapeHtml(reel.status)}</span>
            <span class="tag">${escapeHtml(reel.feedback || "no feedback")}</span>
            <span class="tag">${escapeHtml(reel.images_ready)} images</span>
          </div>
          <div class="actions-row">
            <button class="secondary-button" type="button" data-reel-export="${escapeHtml(reel.draft_id)}">Export production pack</button>
          </div>
        </div>
        <div class="actions-row">
          <button class="secondary-button" type="button" data-send-draft-chat="${escapeHtml(reel.draft_id)}">Send to chat</button>
          <button class="secondary-button" type="button" data-request-review="${escapeHtml(reel.draft_id)}">Request review</button>
        </div>
      </div>
      ${payloadSection("Scenario", reel.payload?.scenario || reel.preview)}
      <section class="section">
        <h3>Storyboard Frames</h3>
        <div class="reels-frames">
          ${frames.map((item, index) => `
            <button class="reels-frame${index === state.selectedFrameIndex ? " active" : ""}" type="button" data-frame-open="${index}">
              <strong>${escapeHtml(item.timecode || `Frame ${index + 1}`)}</strong>
              <div>${escapeHtml(item.scene || "")}</div>
            </button>
          `).join("")}
        </div>
      </section>
      ${frame ? `
        <section class="section">
          <h3>Focused Frame</h3>
          <div class="reels-focus">
            <strong>${escapeHtml(frame.timecode || "")}</strong>
            <div>${escapeHtml(frame.scene || "")}</div>
            <div class="meta">${escapeHtml(frame.angle || "")}</div>
            ${payloadSection("Gemini Prompt", frame.gemini_prompt)}
            ${frame.current_asset?.url ? `<img class="frame-image" src="${escapeHtml(frame.current_asset.url)}" alt="Frame asset" />` : ""}
            <div class="actions-row">
              <button class="secondary-button" type="button" data-frame-regenerate="${escapeHtml(String(frame.frame_index))}">Regenerate frame</button>
            </div>
            <form class="frame-note-form" data-frame-note-form="${escapeHtml(String(frame.frame_index))}">
              <label>
                Review note
                <textarea name="note" placeholder="Например: темнее, ближе камера, меньше объектов в кадре.">${escapeHtml(frame.review_note || "")}</textarea>
              </label>
              <button class="primary-button" type="submit">Сохранить замечание</button>
            </form>
            <form class="frame-prompt-form" data-frame-prompt-form="${escapeHtml(String(frame.frame_index))}">
              <label>
                Gemini prompt
                <textarea name="prompt" placeholder="Уточни prompt для следующей версии кадра.">${escapeHtml(frame.gemini_prompt || "")}</textarea>
              </label>
              <button class="primary-button" type="submit">Сохранить prompt</button>
            </form>
            ${(frame.prompt_revisions || []).length ? `
              <div class="revision-list">
                ${(frame.prompt_revisions || []).map((revision, index) => `
                  <div class="revision-item">
                    <strong>Revision ${index + 1}</strong>
                    <div>${escapeHtml(revision)}</div>
                  </div>
                `).join("")}
              </div>
            ` : ""}
            ${(frame.asset_revisions || []).length ? `
              <div class="asset-revisions">
                ${(frame.asset_revisions || []).map((asset, index) => `
                  <div class="asset-revision">
                    <strong>Asset revision ${index + 1}</strong>
                    <div class="meta">${escapeHtml(asset.generated_at || "")}</div>
                    ${asset.url ? `<img class="frame-image" src="${escapeHtml(asset.url)}" alt="Frame revision" />` : ""}
                  </div>
                `).join("")}
              </div>
            ` : ""}
          </div>
        </section>
      ` : ""}
      <section class="section">
        <h3>Shot List</h3>
        <div class="shot-list">
          ${(reel.shot_list || []).map((shot) => `
            <div class="shot-item">
              <strong>${escapeHtml(shot.title || "")}</strong>
              <div>${escapeHtml(shot.timecode || "")}</div>
              <div>${escapeHtml(shot.action || "")}</div>
              <div class="meta">${escapeHtml(shot.camera || "")}</div>
              <div class="meta">${shot.asset_ready ? "Asset ready" : "Asset missing"}</div>
              ${shot.note ? `<div class="meta">Note: ${escapeHtml(shot.note)}</div>` : ""}
            </div>
          `).join("")}
        </div>
      </section>
      <section class="section">
        <h3>Production Notes</h3>
        <div class="shot-list">
          <div class="shot-item">
            <strong>Required</strong>
            <div>${(reel.production_notes?.required || []).map((item) => escapeHtml(item)).join("<br />") || "Нет"}</div>
          </div>
          <div class="shot-item">
            <strong>Optional</strong>
            <div>${(reel.production_notes?.optional || []).map((item) => escapeHtml(item)).join("<br />") || "Нет"}</div>
          </div>
        </div>
      </section>
      <section class="section">
        <h3>Export Readiness</h3>
        <div class="shot-list">
          <div class="shot-item">
            <strong>Frames ready</strong>
            <div>${escapeHtml(String((reel.frames || []).filter((item) => item.current_asset?.url).length))} / ${escapeHtml(String(reel.frame_count || 0))}</div>
          </div>
          <div class="shot-item">
            <strong>Current export</strong>
            <div>JSON production pack with scenario, shot list, notes, prompts and asset URLs.</div>
          </div>
        </div>
      </section>
      <section class="section">
        <h3>Payload JSON</h3>
        <pre class="json-block">${escapeHtml(JSON.stringify(reel.payload || {}, null, 2))}</pre>
      </section>
    </div>
  `;

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
      await regenerateReelsFrame(reel.draft_id, state.selectedFrameIndex);
    });
  }
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
        <h3>Plan ID</h3>
        <div class="detail-preview">${escapeHtml(plan.plan_id)}</div>
        <div class="actions-row">
          <button class="secondary-button" type="button" data-send-plan-chat="${escapeHtml(plan.plan_id)}">Send plan to chat</button>
        </div>
      </section>
      <section class="section">
        <h3>Entries</h3>
        <div class="plan-entries">
          ${plan.entries.map((entry, index) => `
            <div class="plan-entry">
              <strong>${escapeHtml(entry.day_label || "")}</strong>
              <div>${escapeHtml(entry.platform || "")} / ${escapeHtml(entry.format_label || "")}</div>
              <div>${escapeHtml(entry.topic || "")}</div>
              <div class="meta">${escapeHtml(entry.goal || "")}</div>
              <div class="actions-row">
                <button class="secondary-button" type="button" data-plan-generate="${index}">Generate draft</button>
              </div>
            </div>
          `).join("")}
        </div>
      </section>
      <section class="section">
        <h3>Related Drafts</h3>
        <div class="related-drafts">
          ${plan.related_drafts.length ? plan.related_drafts.map((draft) => `
            <div class="plan-entry">
              <strong>${escapeHtml(draft.kind)}</strong>
              <div>${escapeHtml(draft.topic)}</div>
              <div class="meta">Draft ID: ${escapeHtml(draft.draft_id)} / ${escapeHtml(draft.status)}</div>
            </div>
          `).join("") : '<div class="detail-preview">По этому плану пока не созданы draft’ы.</div>'}
        </div>
      </section>
      <section class="section">
        <h3>Raw Plan</h3>
        <pre class="json-block">${escapeHtml(plan.raw_text || "")}</pre>
      </section>
    </div>
  `;

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

function isContentReviewDraft(draft) {
  return ["threads", "instagram", "telegram"].includes(String(draft.kind || "").toLowerCase());
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
          <div class="actions-row">
            <button class="secondary-button" type="button" data-send-draft-chat="${escapeHtml(draft.draft_id)}">Send to chat</button>
            <button class="secondary-button" type="button" data-request-review="${escapeHtml(draft.draft_id)}">Request review</button>
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
      ${isContentReviewDraft(draft) ? `
        <section class="section">
          <h3>Content Review</h3>
          <form class="content-review-form" data-content-review-form>
            <label>
              Topic
              <textarea name="topic">${escapeHtml(draft.topic || "")}</textarea>
            </label>
            <label>
              Angle
              <textarea name="angle">${escapeHtml(payload.angle || "")}</textarea>
            </label>
            <label>
              Hook
              <textarea name="hook">${escapeHtml(payload.hook || "")}</textarea>
            </label>
            <label>
              Caption
              <textarea name="caption">${escapeHtml(payload.caption || "")}</textarea>
            </label>
            <label>
              CTA
              <textarea name="cta">${escapeHtml(payload.cta || "")}</textarea>
            </label>
            <label>
              Hashtags
              <textarea name="hashtags">${escapeHtml(payload.hashtags || "")}</textarea>
            </label>
            <label>
              Visual Prompt
              <textarea name="visual_prompt">${escapeHtml(payload.visual_prompt || "")}</textarea>
            </label>
            <div class="actions-row">
              <button class="primary-button" type="submit">Save content</button>
              <button class="secondary-button" type="button" data-content-polish>Polish text</button>
              <button class="secondary-button" type="button" data-content-approve>Approve</button>
            </div>
          </form>
        </section>
      ` : ""}
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

  elements.refreshButton.addEventListener("click", async () => {
    await loadCurrentTab();
  });
  for (const button of elements.tabButtons) {
    button.addEventListener("click", async () => {
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
