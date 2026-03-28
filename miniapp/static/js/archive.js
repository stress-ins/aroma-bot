export function createArchiveModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    tagMarkup,
    renderBackButton,
    renderMarkdown,
    renderGuidedState,
    renderDetailLoader,
    renderPanelError,
    fetchJson,
    withButtonFeedback,
    confirmAction,
    enterDetailView,
    syncMobileNavigation,
  } = deps;

  if (!state.archiveFilter) state.archiveFilter = { platform: "all" };
  if (!state.archiveStats) state.archiveStats = null;
  if (!state.archiveItems) state.archiveItems = [];
  if (state.archiveStatsCollapsed === undefined) state.archiveStatsCollapsed = false;
  if (state.coachingSummaryOpen === undefined) state.coachingSummaryOpen = false;
  if (!state.coachingSummaryData) state.coachingSummaryData = null;
  if (!state.coachingCache) state.coachingCache = {};

  // ── Helpers ────────────────────────────────────────────────────────────────

  function formatDate(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
  }

  function formatMonthGroup(isoStr) {
    if (!isoStr) return "Без даты";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return "Без даты";
    const months = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
      "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
    return `${months[d.getMonth()]} ${d.getFullYear()}`;
  }

  function kindIcon(kind) {
    const map = { text: "note", carousel: "layers", reels: "reel", stories: "smartphone", image: "image" };
    return uiIcon(map[kind] || "file-text");
  }

  function kindBadge(kind) {
    const map = { text: "ТРЕДС", carousel: "КАРУСЕЛЬ", reels: "РИЛС", stories: "СТОРИС", image: "ФОТО" };
    return map[kind] || String(kind || "").toUpperCase();
  }

  function platformLabel(p) {
    const map = { threads: "Threads", instagram: "Instagram", telegram: "Telegram", tiktok: "TikTok" };
    return map[p] || p;
  }

  function fmtNum(n) {
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    return String(n || 0);
  }

  function avgScore(item) {
    return item.avg_score != null ? item.avg_score.toFixed(1) : null;
  }

  function starRow(score, max = 5) {
    let html = "";
    for (let i = 1; i <= max; i++) {
      html += `<span class="score-star${i <= (score || 0) ? " score-star--filled" : ""}">${uiIcon("star")}</span>`;
    }
    return html;
  }

  function scoreInputRow(name, label, hint, value) {
    return `
      <div class="score-stars-row">
        <div class="score-label">
          <span class="score-label-name">${escapeHtml(label)}</span>
          <span class="score-label-hint">${escapeHtml(hint)}</span>
        </div>
        <div class="score-stars" data-score-name="${escapeHtml(name)}" data-score-value="${value || 0}">
          ${[1, 2, 3, 4, 5].map(i => `
            <button type="button" class="score-star-btn${i <= (value || 0) ? " score-star--filled" : ""}"
              data-action="setArchiveScore" data-args='["${escapeHtml(name)}", ${i}]'>
              ${uiIcon("star")}
            </button>
          `).join("")}
        </div>
      </div>
    `;
  }

  // ── Load ────────────────────────────────────────────────────────────────────

  async function loadArchive() {
    try {
      const filter = state.archiveFilter || {};
      const params = new URLSearchParams();
      if (filter.platform && filter.platform !== "all") params.set("platform", filter.platform);
      const data = await fetchJson(`/api/archive?${params.toString()}`);
      state.archiveItems = data.items || [];
    } catch (_e) {
      state.archiveItems = [];
    }

    try {
      state.archiveStats = await fetchJson("/api/archive/stats");
    } catch (_e) {
      state.archiveStats = null;
    }

    renderArchiveList();
  }

  // ── Filters ─────────────────────────────────────────────────────────────────

  function setArchivePlatformFilter(value) {
    state.archiveFilter.platform = value;
    loadArchive();
  }

  // ── Stats toggle ────────────────────────────────────────────────────────────

  function toggleArchiveStats() {
    state.archiveStatsCollapsed = !state.archiveStatsCollapsed;
    renderArchiveList();
  }

  // ── List render ─────────────────────────────────────────────────────────────

  function renderArchiveList() {
    const items = state.archiveItems || [];
    const stats = state.archiveStats;
    const filter = state.archiveFilter || {};

    elements.listTitle.textContent = "Архив";
    elements.draftCount.textContent = `${items.length} публикаций`;

    // Platform filters
    const platforms = [
      { label: "Все", value: "all" },
      { label: "Threads", value: "threads" },
      { label: "Instagram", value: "instagram" },
      { label: "Telegram", value: "telegram" },
      { label: "TikTok", value: "tiktok" },
    ];
    const filtersHtml = `
      <div class="filter-chips-row">
        ${platforms.map(c => `
          <button class="filter-chip${c.value === (filter.platform || "all") ? " active" : ""}"
            data-action="setArchivePlatformFilter" data-args='["${c.value}"]'>
            ${escapeHtml(c.label)}
          </button>
        `).join("")}
      </div>
    `;

    // Stats section
    let statsHtml = "";
    if (stats && stats.total > 0) {
      const collapsed = state.archiveStatsCollapsed;
      statsHtml = `
        <div class="archive-stats">
          <div class="archive-stats-header" data-action="toggleArchiveStats" data-args='[]'>
            <span>СТАТИСТИКА</span>
            <span>${collapsed ? "▼" : "▲"}</span>
          </div>
          ${!collapsed ? `
            <div class="archive-stats-body">
              <div class="archive-stat-row">
                <span>${stats.total} публикаций</span>
                <span>·</span>
                <span>${stats.rated || 0} оценено</span>
                ${stats.avg_score != null ? `<span>· ø ${stats.avg_score}★</span>` : ""}
              </div>
            </div>
          ` : ""}
        </div>
      `;
    }

    // Group by month
    const groups = new Map();
    for (const item of items) {
      const key = formatMonthGroup(item.published_at);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    }

    // Compute summary & relative metrics
    let summaryHtml = "";
    let maxPrimary = 1;
    if (items.length > 0) {
      let maxReach = 0, topLikes = 0;
      for (const it of items) {
        const pm = it.likes || it.views || 0;
        if (pm > maxPrimary) maxPrimary = pm;
        if ((it.views || 0) > maxReach) maxReach = it.views || 0;
        if ((it.likes || 0) > topLikes) topLikes = it.likes || 0;
      }
      summaryHtml = `
        <div class="archive-summary">
          <span class="as-item"><strong>${items.length}</strong> постов</span>
          <span class="as-dot">·</span>
          <span class="as-item"><strong>${fmtNum(maxReach)}</strong> макс. охват</span>
          <span class="as-dot">·</span>
          <span class="as-item"><strong>${fmtNum(topLikes)}</strong> топ лайков</span>
        </div>
      `;
    }

    // Sort items by primary metric for isTop detection
    const sortedByMetric = [...items].sort((a, b) => (b.likes || b.views || 0) - (a.likes || a.views || 0));
    const topPubId = sortedByMetric.length > 0 ? sortedByMetric[0].pub_id : null;

    let cardsHtml = "";
    if (items.length === 0) {
      cardsHtml = renderGuidedState({
        eyebrow: "Архив публикаций",
        title: "Пока пусто",
        body: "Добавьте свои опубликованные посты, чтобы оценить их и получить рекомендации.",
        actionLabel: "+ Добавить публикацию",
        action: "openArchiveForm()",
      });
    } else {
      for (const [month, monthItems] of groups) {
        cardsHtml += `<div class="plans-day-label">${escapeHtml(month)}</div>`;
        cardsHtml += monthItems.map(it => {
          const pm = it.likes || it.views || 0;
          const pct = Math.round((pm / maxPrimary) * 100);
          return renderArchiveCard(it, it.pub_id === topPubId, pct);
        }).join("");
      }
    }

    elements.draftList.innerHTML = `
      <div class="plans-sticky-header">
        ${filtersHtml}
      </div>
      <div class="plans-feed-body">
        <div style="padding:0 12px 8px">
          <button class="secondary-button" style="width:100%"
            data-action="openArchiveForm" data-args='[]'>
            ${uiIcon("plus")} Добавить публикацию
          </button>
        </div>
        ${summaryHtml}
        ${items.length > 0 ? renderCoachingSummaryHeader() : ""}
        ${statsHtml}
        ${cardsHtml}
      </div>
    `;

    // Reset detail
    elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({
      eyebrow: "Архив",
      title: "Выберите публикацию",
      body: "Нажмите на карточку для просмотра деталей и оценки.",
    })}</div>`;

    syncMobileNavigation();
  }

  function renderArchiveCard(item, isTop, relativePct) {
    const score = avgScore(item);
    const scoreBadge = score != null ? `<span class="archive-score-badge">${score}★</span>` : "";
    const typeClass = `type-${item.kind || "text"}`;
    const badgeClass = `ac-badge-${item.kind || "text"}`;
    const primaryMetric = item.likes || item.views || 0;
    const fillClass = `fill-${item.platform || "threads"}`;

    return `
      <article class="archive-card ${typeClass} interactive-card"
        data-action="openArchiveDetail" data-args='["${escapeHtml(item.pub_id)}"]'>
        <div class="archive-card-top">
          <div class="archive-card-kind ${badgeClass}">${kindIcon(item.kind)} ${escapeHtml(kindBadge(item.kind))}</div>
          <span class="archive-card-date">${escapeHtml(formatDate(item.published_at))}</span>
        </div>
        <div class="archive-card-title">${escapeHtml(item.topic || item.caption?.substring(0, 60) || "Без заголовка")}</div>
        <div class="archive-card-metrics">
          ${item.likes ? `<span>${uiIcon("heart")} ${fmtNum(item.likes)}</span>` : ""}
          ${item.comments ? `<span>${uiIcon("message-circle")} ${fmtNum(item.comments)}</span>` : ""}
          ${item.views ? `<span>${uiIcon("eye")} ${fmtNum(item.views)}</span>` : ""}
          ${isTop ? `<span class="ac-top-badge">топ</span>` : ""}
          ${scoreBadge}
        </div>
        ${primaryMetric > 0 ? `
        <div class="ac-metric-bar">
          <div class="acmb-bg"><div class="acmb-fill ${fillClass}" style="width:${relativePct || 0}%"></div></div>
          <span class="acmb-val">${fmtNum(primaryMetric)}</span>
        </div>
        ` : ""}
      </article>
    `;
  }

  // ── Detail ──────────────────────────────────────────────────────────────────

  async function openArchiveDetail(pubId) {
    elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Загружаю публикацию")}`;
    enterDetailView();

    try {
      const pub = await fetchJson(`/api/archive/${pubId}`);
      renderArchiveDetail(pub);
      enterDetailView();
    } catch (_e) {
      elements.draftDetail.innerHTML = `${renderBackButton()}${renderPanelError("Не удалось загрузить", "Произошла ошибка при загрузке публикации")}`;
    }
  }

  function renderArchiveDetail(pub) {
    const score = avgScore(pub);

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">${kindIcon(pub.kind)} <span>${escapeHtml(kindBadge(pub.kind))}</span></p>
          <h2 class="detail-title">${escapeHtml(pub.topic || "Публикация")}</h2>
          <div class="draft-meta">
            ${tagMarkup("Архив", "archive")}
            ${tagMarkup(platformLabel(pub.platform), "neutral")}
            ${pub.kind ? tagMarkup(kindBadge(pub.kind), "neutral") : ""}
          </div>
        </div>

        <div class="detail-facts">
          ${pub.published_at ? `<div class="detail-fact"><div class="detail-fact-label">ДАТА</div><div class="detail-fact-value">${escapeHtml(formatDate(pub.published_at))}</div></div>` : ""}
          <div class="detail-fact"><div class="detail-fact-label">ПЛАТФОРМА</div><div class="detail-fact-value">${escapeHtml(platformLabel(pub.platform))}</div></div>
          <div class="detail-fact"><div class="detail-fact-label">ФОРМАТ</div><div class="detail-fact-value">${escapeHtml(kindBadge(pub.kind))}</div></div>
          ${pub.external_url ? `<div class="detail-fact"><div class="detail-fact-label">ССЫЛКА</div><div class="detail-fact-value"><a href="${escapeHtml(pub.external_url)}" target="_blank" rel="noopener">${escapeHtml(pub.external_url.substring(0, 40))}… ↗</a></div></div>` : ""}
        </div>

        ${(pub.views || pub.likes || pub.comments || pub.shares) ? `
          <div class="metrics-block">
            ${pub.likes ? `<div class="mb-item"><span class="mb-val">${fmtNum(pub.likes)}</span><span class="mb-key">лайков</span></div>` : ""}
            ${pub.likes && pub.views ? `<div class="mb-divider"></div>` : ""}
            ${pub.views ? `<div class="mb-item"><span class="mb-val">${fmtNum(pub.views)}</span><span class="mb-key">просмотров</span></div>` : ""}
            ${(pub.likes || pub.views) && pub.comments ? `<div class="mb-divider"></div>` : ""}
            ${pub.comments ? `<div class="mb-item"><span class="mb-val">${fmtNum(pub.comments)}</span><span class="mb-key">комментариев</span></div>` : ""}
            ${(pub.likes || pub.views || pub.comments) && pub.shares ? `<div class="mb-divider"></div>` : ""}
            ${pub.shares ? `<div class="mb-item"><span class="mb-val">${fmtNum(pub.shares)}</span><span class="mb-key">репостов</span></div>` : ""}
          </div>
        ` : ""}

        <div class="rating-card">
          <div class="rc-label">Оценка</div>
          ${scoreInputRow("score_engagement", "Вовлечение", "качество реакций", pub.score_engagement)}
          ${scoreInputRow("score_brand_fit", "Бренд", "попадание в голос", pub.score_brand_fit)}
          ${scoreInputRow("score_craft", "Контент", "хук, визуал, CTA", pub.score_craft)}
          ${scoreInputRow("score_goal_hit", "Цель", "достигнута ли цель", pub.score_goal_hit)}
          ${score != null ? `<div class="score-avg">Средняя: ${score} ★</div>` : ""}
        </div>

        ${pub.content_pillar || pub.funnel_stage ? `
          <div class="draft-meta" style="padding:0 0 8px">
            ${pub.content_pillar ? tagMarkup(pub.content_pillar, "source-plan") : ""}
            ${pub.funnel_stage ? tagMarkup(pub.funnel_stage, "status-neutral") : ""}
          </div>
        ` : ""}

        ${pub.caption ? `
          <section class="section">
            <h3>ТЕКСТ ПОСТА</h3>
            <div class="detail-preview detail-markdown">${renderMarkdown(pub.caption)}</div>
          </section>
        ` : ""}

        ${pub.notes ? `
          <section class="section">
            <h3>ЗАМЕТКИ</h3>
            <div class="detail-preview">${escapeHtml(pub.notes)}</div>
          </section>
        ` : ""}

        <div class="archive-actions">
          <button class="archive-action-btn archive-action-secondary" data-action="loadPostCoaching" data-args='["${escapeHtml(pub.pub_id)}"]'>
            ${uiIcon("brain")} Анализ AI
          </button>
          <button class="archive-action-btn archive-action-secondary" data-action="openArchiveForm" data-args='["${escapeHtml(pub.pub_id)}"]'>
            ${uiIcon("pencil")} Редактировать
          </button>
          <button class="archive-action-btn archive-action-danger" data-action="deletePublication" data-args='["${escapeHtml(pub.pub_id)}", null]'>
            ${uiIcon("trash-2")} Удалить
          </button>
        </div>
        <div id="coachPanelContainer"></div>
      </div>
    `;
    syncMobileNavigation();

    // Store current pubId for score saving
    state._currentArchivePubId = pub.pub_id;
  }

  // ── Score setting ────────────────────────────────────────────────────────

  async function setArchiveScore(name, value) {
    const pubId = state._currentArchivePubId;
    if (!pubId) return;

    try {
      const updated = await fetchJson(`/api/archive/${pubId}`, {
        method: "PUT",
        body: JSON.stringify({ [name]: value }),
      });
      renderArchiveDetail(updated);
    } catch (_e) { /* ignore */ }
  }

  // ── Form ────────────────────────────────────────────────────────────────────

  async function openArchiveForm(pubId) {
    let pub = null;
    if (pubId) {
      try {
        pub = await fetchJson(`/api/archive/${pubId}`);
      } catch (_e) { /* new */ }
    }

    const isEdit = !!pub;
    const title = isEdit ? "Редактировать" : "Добавить публикацию";

    const platforms = ["threads", "instagram", "telegram", "tiktok"];
    const kinds = [
      { value: "text", label: "Текст" },
      { value: "carousel", label: "Карусель" },
      { value: "reels", label: "Рилс" },
      { value: "stories", label: "Сторис" },
    ];
    const funnelStages = [
      { value: "", label: "—" },
      { value: "awareness", label: "Осведомлённость" },
      { value: "consideration", label: "Интерес" },
      { value: "conversion", label: "Конверсия" },
      { value: "retention", label: "Удержание" },
    ];

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("archive")} <span>${escapeHtml(title)}</span></p>
        </div>

        ${!isEdit ? `
          <section class="section">
            <h3>ИМПОРТ ПО URL</h3>
            <div style="display:flex;gap:8px">
              <input type="url" id="archiveImportUrl" class="form-input" placeholder="https://threads.net/..." style="flex:1">
              <button class="primary-button" data-action="importFromUrl" data-args='[null]'>Загрузить</button>
            </div>
            <div class="divider-label">или заполните вручную</div>
          </section>
        ` : ""}

        <section class="section">
          <h3>ПЛАТФОРМА</h3>
          <div class="filter-chips-row">
            ${platforms.map(p => `
              <button type="button" class="filter-chip${(pub?.platform || "threads") === p ? " active" : ""}"
                data-chip-group="archivePlatform" data-chip-value="${p}">
                ${escapeHtml(platformLabel(p))}
              </button>
            `).join("")}
          </div>
        </section>

        <section class="section">
          <h3>ФОРМАТ</h3>
          <div class="filter-chips-row">
            ${kinds.map(k => `
              <button type="button" class="filter-chip${(pub?.kind || "text") === k.value ? " active" : ""}"
                data-chip-group="archiveKind" data-chip-value="${k.value}">
                ${escapeHtml(k.label)}
              </button>
            `).join("")}
          </div>
        </section>

        <section class="section">
          <label class="form-label">Дата публикации</label>
          <input type="date" id="archiveDate" class="form-input" value="${pub?.published_at ? pub.published_at.substring(0, 10) : ""}">

          <label class="form-label" style="margin-top:12px">Тема / заголовок</label>
          <input type="text" id="archiveTopic" class="form-input" value="${escapeHtml(pub?.topic || "")}" placeholder="О чём пост">

          <label class="form-label" style="margin-top:12px">Текст поста</label>
          <textarea id="archiveCaption" class="form-input" rows="4" placeholder="Текст публикации">${escapeHtml(pub?.caption || "")}</textarea>
        </section>

        <section class="section">
          <h3>МЕТРИКИ</h3>
          <div class="metrics-grid">
            <div class="metric-input-item"><label>Просмотры</label><input type="number" id="archiveViews" class="form-input" value="${pub?.views || 0}" min="0"></div>
            <div class="metric-input-item"><label>Лайки</label><input type="number" id="archiveLikes" class="form-input" value="${pub?.likes || 0}" min="0"></div>
            <div class="metric-input-item"><label>Комментарии</label><input type="number" id="archiveComments" class="form-input" value="${pub?.comments || 0}" min="0"></div>
            <div class="metric-input-item"><label>Репосты</label><input type="number" id="archiveShares" class="form-input" value="${pub?.shares || 0}" min="0"></div>
          </div>
        </section>

        <section class="section">
          <h3>ВОРОНКА</h3>
          <div class="filter-chips-row">
            ${funnelStages.map(f => `
              <button type="button" class="filter-chip${(pub?.funnel_stage || "") === f.value ? " active" : ""}"
                data-chip-group="archiveFunnel" data-chip-value="${f.value}">
                ${escapeHtml(f.label)}
              </button>
            `).join("")}
          </div>
        </section>

        <section class="section">
          <label class="form-label">Заметки</label>
          <textarea id="archiveNotes" class="form-input" rows="2" placeholder="Что сработало, что нет...">${escapeHtml(pub?.notes || "")}</textarea>
        </section>

        <div class="actions-row">
          <button class="primary-button" data-action="savePublication" data-args='["${pub?.pub_id || ""}", null]'>
            ${uiIcon("save")} Сохранить
          </button>
        </div>
      </div>
    `;

    enterDetailView();
    syncMobileNavigation();

    // Chip selection handler
    elements.draftDetail.querySelectorAll("[data-chip-group]").forEach(btn => {
      btn.addEventListener("click", () => {
        const group = btn.dataset.chipGroup;
        elements.draftDetail.querySelectorAll(`[data-chip-group="${group}"]`).forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
      });
    });
  }

  // ── Save ────────────────────────────────────────────────────────────────────

  async function savePublication(pubId, button) {
    const getChipValue = (group) => {
      const active = elements.draftDetail.querySelector(`[data-chip-group="${group}"].active`);
      return active ? active.dataset.chipValue : "";
    };

    const body = {
      platform: getChipValue("archivePlatform") || "threads",
      kind: getChipValue("archiveKind") || "text",
      topic: document.getElementById("archiveTopic")?.value || "",
      caption: document.getElementById("archiveCaption")?.value || "",
      published_at: document.getElementById("archiveDate")?.value ? new Date(document.getElementById("archiveDate").value).toISOString() : null,
      views: parseInt(document.getElementById("archiveViews")?.value || "0", 10),
      likes: parseInt(document.getElementById("archiveLikes")?.value || "0", 10),
      comments: parseInt(document.getElementById("archiveComments")?.value || "0", 10),
      shares: parseInt(document.getElementById("archiveShares")?.value || "0", 10),
      funnel_stage: getChipValue("archiveFunnel") || "",
      notes: document.getElementById("archiveNotes")?.value || "",
    };

    const apply = async () => {
      if (pubId) {
        await fetchJson(`/api/archive/${pubId}`, { method: "PUT", body: JSON.stringify(body) });
      } else {
        await fetchJson("/api/archive", { method: "POST", body: JSON.stringify(body) });
      }
      await loadArchive();
    };

    if (button instanceof HTMLElement) {
      await withButtonFeedback(button, "Сохраняю...", apply, "Сохранено");
    } else {
      await apply();
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────

  async function deletePublication(pubId, button) {
    const _confirm = confirmAction || ((msg) => Promise.resolve(window.confirm(msg)));
    const confirmed = await _confirm("Удалить публикацию?");
    if (!confirmed) return;
    const apply = async () => {
      await fetchJson(`/api/archive/${pubId}`, { method: "DELETE" });
      await loadArchive();
    };
    if (button instanceof HTMLElement) {
      await withButtonFeedback(button, "Удаляю...", apply, "Удалено");
    } else {
      await apply();
    }
  }

  // ── Import from URL ─────────────────────────────────────────────────────────

  async function importFromUrl(button) {
    const urlInput = document.getElementById("archiveImportUrl");
    const url = urlInput?.value?.trim();
    if (!url) return;

    const apply = async () => {
      const pub = await fetchJson("/api/archive/import-url", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      // Open form pre-filled with fetched data
      openArchiveForm(pub.pub_id);
    };

    if (button instanceof HTMLElement) {
      await withButtonFeedback(button, "Импортирую...", apply, "Загружено");
    } else {
      await apply();
    }
  }

  // ── Bulk import ─────────────────────────────────────────────────────────────

  async function bulkImportFromAccount(platform, button) {
    const apply = async () => {
      const result = await fetchJson("/api/archive/bulk-import", {
        method: "POST",
        body: JSON.stringify({ platform, days: 14 }),
      });
      return result;
    };

    try {
      let result;
      if (button instanceof HTMLElement) {
        result = await withButtonFeedback(button, "Импортирую...", apply, "Готово");
      } else {
        result = await apply();
      }
      if (result && result.imported !== undefined) {
        alert(`Импортировано ${result.imported} публикаций (пропущено: ${result.skipped})`);
      }
    } catch (e) {
      alert("Ошибка импорта: " + (e.message || "неизвестная ошибка"));
    }
  }

  // ── Coaching: Summary ─────────────────────────────────────────────────────

  function renderCoachingSummaryHeader() {
    return `
      <div class="coach-summary-header disabled">
        ${uiIcon("brain")} Coaching Summary
        <span class="coach-summary-soon">скоро</span>
      </div>
    `;
  }

  function renderCoachingSummaryPanel() {
    const data = state.coachingSummaryData;
    if (!data) {
      return `<div class="coach-summary-panel"><div class="coach-loading">${uiIcon("loader")} Анализирую публикации...</div></div>`;
    }

    let formatRecsHtml = "";
    if (data.format_recommendations && data.format_recommendations.length) {
      formatRecsHtml = `
        <div class="coach-section">
          <h4>Форматы</h4>
          ${data.format_recommendations.map(r => `
            <div class="coach-rec-item">
              <span class="coach-rec-format">${escapeHtml(r.format || "")}</span>
              <span class="coach-rec-verdict coach-rec-verdict--${escapeHtml(r.verdict || "keep")}">${escapeHtml(r.verdict || "")}</span>
              <span class="coach-rec-note">${escapeHtml(r.note || "")}</span>
            </div>
          `).join("")}
        </div>
      `;
    }

    let pillarRecsHtml = "";
    if (data.pillar_recommendations && data.pillar_recommendations.length) {
      pillarRecsHtml = `
        <div class="coach-section">
          <h4>Столпы контента</h4>
          ${data.pillar_recommendations.map(r => `
            <div class="coach-rec-item">
              <span class="coach-rec-format">${escapeHtml(r.pillar || "")}</span>
              <span class="coach-rec-verdict coach-rec-verdict--${escapeHtml(r.verdict || "keep")}">${escapeHtml(r.verdict || "")}</span>
              <span class="coach-rec-note">${escapeHtml(r.note || "")}</span>
            </div>
          `).join("")}
        </div>
      `;
    }

    let gapsHtml = "";
    if (data.content_gaps && data.content_gaps.length) {
      gapsHtml = `
        <div class="coach-section">
          <h4>Пробелы в контенте</h4>
          <ul>${data.content_gaps.map(g => `<li>${escapeHtml(g)}</li>`).join("")}</ul>
        </div>
      `;
    }

    let weeklyHtml = "";
    if (data.weekly_plan_suggestion) {
      weeklyHtml = `
        <div class="coach-weekly">
          <div class="coach-weekly-label">План на неделю</div>
          ${escapeHtml(data.weekly_plan_suggestion)}
        </div>
      `;
    }

    return `
      <div class="coach-summary-panel">
        <div class="coach-summary-insight">${escapeHtml(data.top_insight || "")}</div>
        ${formatRecsHtml}
        ${pillarRecsHtml}
        ${gapsHtml}
        ${weeklyHtml}
      </div>
    `;
  }

  async function toggleCoachingSummary() {
    state.coachingSummaryOpen = !state.coachingSummaryOpen;
    renderArchiveList();

    if (state.coachingSummaryOpen && !state.coachingSummaryData) {
      try {
        const data = await fetchJson("/api/archive/coaching/summary");
        state.coachingSummaryData = data;
      } catch (_e) {
        state.coachingSummaryData = {
          top_insight: "Не удалось загрузить анализ. Попробуйте позже.",
          format_recommendations: [],
          pillar_recommendations: [],
          content_gaps: [],
          weekly_plan_suggestion: "",
        };
      }
      renderArchiveList();
    }
  }

  // ── Coaching: Per-post ──────────────────────────────────────────────────

  function renderCoachPanel(data) {
    const verdictIcons = { success: "trophy", average: "minus", underperformed: "alert-triangle" };
    const verdictLabels = { success: "Успех", average: "Средне", underperformed: "Ниже среднего" };
    const icon = verdictIcons[data.verdict] || "minus";
    const label = verdictLabels[data.verdict] || "Анализ";
    const delta = data.score_vs_average != null ? (data.score_vs_average > 0 ? "+" : "") + data.score_vs_average.toFixed(1) + "%" : "";

    let strengthsHtml = "";
    if (data.strengths && data.strengths.length) {
      strengthsHtml = `
        <div class="coach-section">
          <h4>Сильные стороны</h4>
          <ul>${data.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
        </div>
      `;
    }

    let weaknessesHtml = "";
    if (data.weaknesses && data.weaknesses.length) {
      weaknessesHtml = `
        <div class="coach-section">
          <h4>Что улучшить</h4>
          <ul>${data.weaknesses.map(w => `<li>${escapeHtml(w)}</li>`).join("")}</ul>
        </div>
      `;
    }

    let recsHtml = "";
    if (data.recommendations && data.recommendations.length) {
      recsHtml = `
        <div class="coach-section">
          <h4>Рекомендации</h4>
          <ul>${data.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
        </div>
      `;
    }

    let scoresHtml = "";
    if (data.score_explanation) {
      const scoreLabels = {
        engagement: "Вовлечение",
        brand_fit: "Бренд",
        craft: "Контент",
        goal_hit: "Цель",
      };
      scoresHtml = `
        <div class="coach-section">
          <h4>Оценки</h4>
          <div class="coach-scores">
            ${Object.entries(data.score_explanation).map(([key, text]) => `
              <div class="coach-score-card">
                <div class="coach-score-card-label">${escapeHtml(scoreLabels[key] || key)}</div>
                <div class="coach-score-card-text">${escapeHtml(text || "")}</div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    let patternsHtml = "";
    if (data.patterns_detected && data.patterns_detected.length) {
      patternsHtml = `
        <div class="coach-section">
          <h4>Паттерны</h4>
          <ul>${data.patterns_detected.map(p => `<li>${escapeHtml(p)}</li>`).join("")}</ul>
        </div>
      `;
    }

    let improvementsHtml = "";
    if (data.suggested_improvements) {
      improvementsHtml = `
        <div class="coach-section">
          <h4>Улучшенный вариант</h4>
          <div class="coach-improvements">${escapeHtml(data.suggested_improvements)}</div>
        </div>
      `;
    }

    return `
      <div class="coach-panel">
        <div class="coach-verdict coach-verdict--${escapeHtml(data.verdict || "average")}">
          ${uiIcon(icon)}
          <span>${escapeHtml(label)}</span>
          <span class="coach-delta">${escapeHtml(delta)}</span>
        </div>
        ${strengthsHtml}
        ${weaknessesHtml}
        ${recsHtml}
        ${scoresHtml}
        ${patternsHtml}
        ${improvementsHtml}
      </div>
    `;
  }

  async function loadPostCoaching(pubId, button) {
    const container = document.getElementById("coachPanelContainer");
    if (!container) return;

    // Check cache
    if (state.coachingCache[pubId]) {
      container.innerHTML = renderCoachPanel(state.coachingCache[pubId]);
      if (window.lucide) lucide.createIcons();
      return;
    }

    container.innerHTML = `<div class="coach-panel"><div class="coach-loading">${uiIcon("loader")} Анализирую пост...</div></div>`;
    if (window.lucide) lucide.createIcons();

    try {
      const data = await fetchJson(`/api/archive/${pubId}/coaching`);
      state.coachingCache[pubId] = data;
      container.innerHTML = renderCoachPanel(data);
    } catch (_e) {
      container.innerHTML = `<div class="coach-panel"><p style="color:var(--bad);padding:12px">Не удалось загрузить анализ. Попробуйте позже.</p></div>`;
    }

    if (window.lucide) lucide.createIcons();
  }

  return {
    loadArchive,
    openArchiveDetail,
    openArchiveForm,
    savePublication,
    deletePublication,
    importFromUrl,
    toggleArchiveStats,
    setArchivePlatformFilter,
    setArchiveScore,
    bulkImportFromAccount,
    toggleCoachingSummary,
    loadPostCoaching,
  };
}
