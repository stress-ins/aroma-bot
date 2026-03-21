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
    fetchJson,
    withButtonFeedback,
    enterDetailView,
    syncMobileNavigation,
  } = deps;

  if (!state.archiveFilter) state.archiveFilter = { platform: "all" };
  if (!state.archiveStats) state.archiveStats = null;
  if (!state.archiveItems) state.archiveItems = [];
  if (state.archiveStatsCollapsed === undefined) state.archiveStatsCollapsed = false;

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
    const map = { text: "✍️", carousel: "🖼", reels: "🎬", stories: "📱", image: "📸" };
    return map[kind] || "📄";
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
        cardsHtml += monthItems.map(renderArchiveCard).join("");
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
    if (window.lucide) lucide.createIcons();
  }

  function renderArchiveCard(item) {
    const score = avgScore(item);
    const scoreBadge = score != null ? `<span class="archive-score-badge">${score}★</span>` : "";

    return `
      <article class="archive-card interactive-card"
        data-action="openArchiveDetail" data-args='["${escapeHtml(item.pub_id)}"]'>
        <div class="archive-card-top">
          <div class="archive-card-left">
            <div class="archive-card-kind">${kindIcon(item.kind)} ${escapeHtml(kindBadge(item.kind))}<span class="archive-card-date">${escapeHtml(formatDate(item.published_at))}</span></div>
            <div class="archive-card-title">${escapeHtml(item.topic || item.caption?.substring(0, 60) || "Без заголовка")}</div>
            <div class="archive-card-metrics">
              ${item.views ? `${uiIcon("eye")} ${fmtNum(item.views)}` : ""}
              ${item.likes ? ` ${uiIcon("heart")} ${fmtNum(item.likes)}` : ""}
              ${item.comments ? ` ${uiIcon("message-circle")} ${fmtNum(item.comments)}` : ""}
              ${scoreBadge}
            </div>
          </div>
        </div>
      </article>
    `;
  }

  // ── Detail ──────────────────────────────────────────────────────────────────

  async function openArchiveDetail(pubId) {
    elements.draftDetail.innerHTML = `${renderBackButton()}<p style="padding:16px">Загрузка...</p>`;
    enterDetailView();

    try {
      const pub = await fetchJson(`/api/archive/${pubId}`);
      renderArchiveDetail(pub);
      enterDetailView();
    } catch (_e) {
      elements.draftDetail.innerHTML = `${renderBackButton()}<p style="padding:16px;color:var(--bad)">Не удалось загрузить</p>`;
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
          <section class="section">
            <h3>МЕТРИКИ</h3>
            <div class="metrics-grid">
              ${pub.views ? `<div class="metric-item">${uiIcon("eye")} <strong>${fmtNum(pub.views)}</strong> просмотров</div>` : ""}
              ${pub.likes ? `<div class="metric-item">${uiIcon("heart")} <strong>${fmtNum(pub.likes)}</strong> лайков</div>` : ""}
              ${pub.comments ? `<div class="metric-item">${uiIcon("message-circle")} <strong>${fmtNum(pub.comments)}</strong> комментариев</div>` : ""}
              ${pub.shares ? `<div class="metric-item">${uiIcon("share-2")} <strong>${fmtNum(pub.shares)}</strong> репостов</div>` : ""}
            </div>
          </section>
        ` : ""}

        <section class="section">
          <h3>ОЦЕНКА</h3>
          ${scoreInputRow("score_engagement", "Вовлечение", "качество реакций", pub.score_engagement)}
          ${scoreInputRow("score_brand_fit", "Бренд", "попадание в голос", pub.score_brand_fit)}
          ${scoreInputRow("score_craft", "Контент", "хук, визуал, CTA", pub.score_craft)}
          ${scoreInputRow("score_goal_hit", "Цель", "достигнута ли цель", pub.score_goal_hit)}
          ${score != null ? `<div class="score-avg">Средняя: ${score} ★</div>` : ""}
        </section>

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

        <div class="actions-row">
          <button class="secondary-button" data-action="openArchiveForm" data-args='["${escapeHtml(pub.pub_id)}"]'>
            ${uiIcon("pencil")} Редактировать
          </button>
          <button class="danger-button" data-action="deletePublication" data-args='["${escapeHtml(pub.pub_id)}", null]'>
            ${uiIcon("trash-2")} Удалить
          </button>
        </div>
      </div>
    `;
    syncMobileNavigation();
    if (window.lucide) lucide.createIcons();

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
    if (window.lucide) lucide.createIcons();

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
    if (!confirm("Удалить публикацию?")) return;
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
  };
}
