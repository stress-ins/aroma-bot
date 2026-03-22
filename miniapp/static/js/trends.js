/**
 * Trends module — Instagram & Threads social trend analytics.
 * Platform tabs, period filter, heatmap, tag cloud, format breakdown.
 */
export function createTrendsModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    actionLabel,
    renderBackButton,
    renderGuidedState,
    withButtonFeedback,
    fetchJson,
    confirmAction,
    showUiNotice,
    setEmptyState,
    syncMobileNavigation,
    enterDetailView,
  } = deps;

  function _extractUsername(input) {
    const trimmed = input.trim();
    const urlPatterns = [
      /(?:instagram\.com|instagr\.am)\/([a-zA-Z0-9_.]+)/,
      /(?:threads\.net|threads\.com)\/@?([a-zA-Z0-9_.]+)/,
    ];
    for (const pat of urlPatterns) {
      const m = trimmed.match(pat);
      if (m) return m[1];
    }
    return trimmed.replace(/^@/, "");
  }

  let trendsPlatform = "instagram";
  let trendsPeriod = 7;
  let trendsData = null;
  let trendsCompare = null;
  let monitoredAccounts = { instagram: [], threads: [] };
  let trackedHashtags = [];

  const WEEKDAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

  // ── Loaders ──────────────────────────────────────────────────────────

  async function loadTrends() {
    elements.draftList.innerHTML = renderTrendsListPanel();
    elements.draftDetail.innerHTML = renderDetailLoader();
    syncMobileNavigation();

    try {
      const promises = [
        trendsPlatform === "compare"
          ? fetchJson(`/api/trends/compare?period=${trendsPeriod}`)
          : fetchJson(`/api/trends/${trendsPlatform}?period=${trendsPeriod}`),
        fetchJson("/api/social/monitored-accounts"),
        fetchJson("/api/social/tracked-hashtags"),
      ];
      if (trendsPlatform !== "compare") {
        promises.push(fetchJson(`/api/trends/suggestions?platform=${trendsPlatform}`));
      }
      const [trendsResult, accountsResult, hashtagsResult, suggestionsResult] = await Promise.allSettled(promises);

      if (trendsPlatform === "compare") {
        trendsCompare = trendsResult.status === "fulfilled" ? trendsResult.value : null;
        trendsData = null;
      } else {
        trendsData = trendsResult.status === "fulfilled" ? trendsResult.value : null;
        trendsCompare = null;
      }

      if (accountsResult.status === "fulfilled") {
        monitoredAccounts = accountsResult.value || { instagram: [], threads: [] };
      }
      if (hashtagsResult.status === "fulfilled") {
        trackedHashtags = (hashtagsResult.value || {}).items || [];
      }
      if (suggestionsResult && suggestionsResult.status === "fulfilled") {
        suggestionsData = suggestionsResult.value;
      } else {
        suggestionsData = null;
      }
    } catch (err) {
      trendsData = null;
      trendsCompare = null;
      suggestionsData = null;
    }

    elements.draftList.innerHTML = renderTrendsListPanel();
    elements.draftDetail.innerHTML = renderTrendsDetail();
    syncMobileNavigation();
    if (window.lucide) lucide.createIcons();
  }

  // ── List Panel (platform selector + filters) ─────────────────────────

  function renderTrendsListPanel() {
    const platforms = [
      { id: "instagram", label: "Instagram", icon: "instagram" },
      { id: "threads", label: "Threads", icon: "at-sign" },
      { id: "compare", label: "Сравнение", icon: "columns-2" },
      { id: "cards", label: "AI-карточки", icon: "sparkles" },
    ];

    const platformTabs = platforms
      .map(
        (p) => `
      <button class="trends-platform-btn ${p.id === trendsPlatform ? "active" : ""}"
              data-action="selectTrendsPlatform" data-args='["${p.id}"]'>
        ${uiIcon(p.icon, 16)} ${escapeHtml(p.label)}
      </button>`
      )
      .join("");

    const periods = [7, 14, 30];
    const periodBtns = periods
      .map(
        (d) => `
      <button class="trends-period-btn ${d === trendsPeriod ? "active" : ""}"
              data-action="selectTrendsPeriod" data-args='[${d}]'>
        ${d}д
      </button>`
      )
      .join("");

    const refreshBtn = `<button class="trends-refresh-btn" id="trendsRefreshBtn"
                                data-action="refreshTrends" data-args='[null]'>
      ${uiIcon("refresh-cw", 14)} Обновить
    </button>`;

    let summary = "";
    if (trendsPlatform === "cards") {
      summary = renderTrendCardsList();
    } else if (trendsPlatform === "compare" && trendsCompare) {
      summary = renderCompareSummaryList();
    } else if (trendsData) {
      summary = renderPlatformSummaryList();
    }

    return `
      <div class="trends-controls">
        <div class="trends-platform-tabs">${platformTabs}</div>
        <div class="trends-period-row">
          <div class="trends-period-btns">${periodBtns}</div>
          ${refreshBtn}
        </div>
      </div>
      ${summary}
      ${renderMonitoredAccountsSection()}
      ${renderTrackedHashtagsSection()}
    `;
  }

  function renderPlatformSummaryList() {
    if (!trendsData) return "";
    const topPosts = trendsData.top_posts || [];
    if (topPosts.length === 0) {
      return `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Тренды",
        title: "Нет данных",
        body: "Добавьте аккаунты для мониторинга и дождитесь сбора данных.",
        actionLabel: "Обновить",
        action: "refreshTrends",
      })}</div>`;
    }

    const cards = topPosts
      .slice(0, 10)
      .map((p, i) => {
        const eng = (p.like_count || 0) + (p.comment_count || 0) + (p.share_count || 0) + (p.reply_count || 0);
        const preview = escapeHtml((p.text || "").substring(0, 80));
        return `
        <div class="draft-card" data-action="openTrendsPost" data-args='[${i}]'>
          <div class="draft-card-header">
            <span class="draft-card-topic">${escapeHtml(p.author_username || "")}</span>
            <span class="draft-card-date">${actionLabel("heart", eng)}</span>
          </div>
          <div class="draft-card-preview">${preview}${p.text && p.text.length > 80 ? "…" : ""}</div>
          <div class="draft-card-meta">
            <span>${actionLabel("thumbs-up", p.like_count || 0)}</span>
            <span>${actionLabel("message-circle", p.comment_count || 0)}</span>
            ${p.share_count ? `<span>${actionLabel("repeat", p.share_count)}</span>` : ""}
            ${p.reply_count ? `<span>${actionLabel("corner-down-right", p.reply_count)}</span>` : ""}
          </div>
        </div>`;
      })
      .join("");

    return `<div class="draft-list-content">${cards}</div>`;
  }

  function renderCompareSummaryList() {
    if (!trendsCompare) return "";
    const ig = trendsCompare.instagram || {};
    const th = trendsCompare.threads || {};

    return `
      <div class="trends-compare-cards">
        <div class="trends-compare-card">
          <div class="trends-compare-card-title">${uiIcon("instagram", 16)} Instagram</div>
          <div class="trends-compare-metric">${actionLabel("heart", ig.avg_engagement || 0)} ср. вовлечение</div>
          <div class="trends-compare-metric">${actionLabel("clock", ig.best_hour != null ? ig.best_hour + ":00" : "—")} лучшее время</div>
          <div class="trends-compare-metric">${actionLabel("file-text", ig.post_count || 0)} постов</div>
        </div>
        <div class="trends-compare-card">
          <div class="trends-compare-card-title">${uiIcon("at-sign", 16)} Threads</div>
          <div class="trends-compare-metric">${actionLabel("heart", th.avg_engagement || 0)} ср. вовлечение</div>
          <div class="trends-compare-metric">${actionLabel("clock", th.best_hour != null ? th.best_hour + ":00" : "—")} лучшее время</div>
          <div class="trends-compare-metric">${actionLabel("file-text", th.post_count || 0)} постов</div>
        </div>
      </div>`;
  }

  // ── Insight cards from suggestions ────────────────────────────────

  let suggestionsData = null;

  async function loadSuggestions() {
    try {
      suggestionsData = await fetchJson(`/api/trends/suggestions?platform=${trendsPlatform}`);
    } catch (_) {
      suggestionsData = null;
    }
  }

  function renderInsightCards() {
    if (!suggestionsData || !suggestionsData.insights || !suggestionsData.insights.length) return "";
    const FORMAT_ICONS = { carousel: "layout-grid", reels: "video", threads_series: "at-sign", content: "file-text" };
    const FORMAT_LABELS = { carousel: "Карусель", reels: "Рилс", threads_series: "Серия Threads", content: "Пост" };

    const cards = suggestionsData.insights.map((ins, i) => `
      <div class="insight-card">
        <div class="insight-card-header">
          <span class="insight-card-author">@${escapeHtml(ins.author_username || "—")}</span>
          <span class="insight-card-engagement">${actionLabel("heart", ins.engagement_score)}</span>
        </div>
        <div class="insight-card-topic">${escapeHtml(ins.topic)}</div>
        ${ins.hashtags.length ? `<div class="insight-card-tags">${ins.hashtags.map(t => `<span class="trends-tagcloud-chip" style="font-size:0.75rem">#${escapeHtml(t)}</span>`).join(" ")}</div>` : ""}
        <div class="insight-card-footer">
          <span class="insight-card-format">${uiIcon(FORMAT_ICONS[ins.suggested_format] || "file-text", 14)} ${escapeHtml(FORMAT_LABELS[ins.suggested_format] || "Пост")}</span>
          <button class="secondary-button" type="button" data-action="createFromInsight" data-args='${JSON.stringify([ins.topic, ins.hashtags, ins.suggested_format])}'>
            ${uiIcon("plus", 14)} Создать контент
          </button>
        </div>
      </div>
    `).join("");

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("lightbulb", 16)} Идеи из трендов</div>
        ${cards}
      </div>`;
  }

  function createFromInsight(topic, hashtags, format) {
    sessionStorage.setItem("trend_create_context", JSON.stringify({ topic, hashtags, source: "trends" }));
    if (typeof window.openCreateTool === "function") {
      window.openCreateTool(format || "content");
    }
    // Pre-fill topic after form renders
    setTimeout(() => {
      const topicField = document.querySelector(".create-form textarea[name='topic']");
      if (topicField && topic) {
        topicField.value = topic;
        topicField.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }, 100);
  }

  function renderEmptyGuide() {
    return `
      <div class="trends-empty-guide">
        <div class="detail-section">
          <div class="detail-section-title">${uiIcon("compass", 16)} Как начать</div>
          <p class="trends-guide-intro">Тренды помогут понять, какой контент работает у конкурентов, и создавать свой на основе данных.</p>
          <div class="trends-guide-steps">
            <div class="trends-guide-step">
              <span class="trends-guide-step-num">1</span>
              <div>
                <strong>Добавьте аккаунты для мониторинга</strong>
                <p>Укажите конкурентов или источники вдохновения ниже в секции «Отслеживаемые аккаунты».</p>
              </div>
            </div>
            <div class="trends-guide-step">
              <span class="trends-guide-step-num">2</span>
              <div>
                <strong>Подключите Instagram/Threads API</strong>
                <p>Перейдите в <button class="link-button" data-action="openSettingsSection" data-args='["tokens"]'>настройки токенов</button> для авторизации.</p>
              </div>
            </div>
            <div class="trends-guide-step">
              <span class="trends-guide-step-num">3</span>
              <div>
                <strong>Данные обновляются каждые 6 часов</strong>
                <p>Или нажмите «Обновить» вручную.</p>
              </div>
            </div>
          </div>
          <div class="trends-guide-cta">
            <button class="primary-button" type="button" data-action="openSettingsSection" data-args='["monitored"]'>
              ${uiIcon("settings", 14)} Настроить источники
            </button>
            <button class="secondary-button" type="button" data-action="refreshTrends" data-args='[null]'>
              ${uiIcon("refresh-cw", 14)} Обновить сейчас
            </button>
          </div>
        </div>
      </div>`;
  }

  // ── Detail Panel ────────────────────────────────────────────────────

  function renderTrendsDetail() {
    if (trendsPlatform === "compare") return renderCompareDetail();
    if (!trendsData) {
      return `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Аналитика",
        title: "Данные собираются ежедневно",
        body: "Выберите пост слева для подробной аналитики. Если постов нет — добавьте аккаунты для мониторинга и нажмите «Обновить».",
        actionLabel: "Обновить",
        action: "refreshTrends",
      })}</div>`;
    }

    const sections = [];

    // Hashtag cloud
    const cloud = trendsData.hashtag_cloud || trendsData.trending_keywords || [];
    if (cloud.length > 0) {
      sections.push(renderHashtagCloud(cloud));
    }

    // Heatmap
    const heatmap = trendsData.heatmap;
    if (heatmap && Object.keys(heatmap).length > 0) {
      sections.push(renderHeatmap(heatmap));
    }

    // Format breakdown
    const formats = trendsData.format_breakdown || {};
    if (Object.keys(formats).length > 0) {
      sections.push(renderFormatBreakdown(formats));
    }

    // Thread hooks (Threads only)
    const hooks = trendsData.thread_hooks || [];
    if (hooks.length > 0) {
      sections.push(renderThreadHooks(hooks));
    }

    // Best times
    const times = trendsData.best_times || [];
    if (times.length > 0) {
      sections.push(renderBestTimes(times));
    }

    // Content lengths (Threads)
    const lengths = trendsData.content_lengths;
    if (lengths) {
      sections.push(renderContentLengths(lengths));
    }

    if (sections.length === 0) {
      return renderEmptyGuide();
    }

    // Prepend insight cards before analytics
    const insightsHtml = renderInsightCards();
    return `<div class="trends-detail-content">${insightsHtml}${sections.join("")}</div>`;
  }

  function renderCompareDetail() {
    if (!trendsCompare) {
      return `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Сравнение",
        title: "Загрузка данных",
        body: "Сравнение платформ загружается. Если данных пока нет — добавьте аккаунты и обновите.",
        actionLabel: "Обновить",
        action: "refreshTrends",
      })}</div>`;
    }
    const ig = trendsCompare.instagram || {};
    const th = trendsCompare.threads || {};

    return `
      <div class="trends-detail-content">
        <div class="detail-section">
          <div class="detail-section-title">${uiIcon("bar-chart-3", 16)} Сравнение платформ за ${trendsPeriod} дн.</div>
          <table class="trends-comparison-table">
            <thead><tr><th></th><th>Instagram</th><th>Threads</th></tr></thead>
            <tbody>
              <tr><td>Ср. вовлечение</td><td>${ig.avg_engagement || 0}</td><td>${th.avg_engagement || 0}</td></tr>
              <tr><td>Лучший час</td><td>${ig.best_hour != null ? ig.best_hour + ":00" : "—"}</td><td>${th.best_hour != null ? th.best_hour + ":00" : "—"}</td></tr>
              <tr><td>Постов</td><td>${ig.post_count || 0}</td><td>${th.post_count || 0}</td></tr>
            </tbody>
          </table>
        </div>
      </div>`;
  }

  // ── Visualization Components ─────────────────────────────────────────

  function renderHashtagCloud(tags) {
    const maxCount = Math.max(...tags.map((t) => t.count), 1);
    const chips = tags
      .map((t) => {
        const size = 0.75 + (t.count / maxCount) * 0.75;
        return `<span class="trends-tagcloud-chip" style="font-size: ${size}rem"
                      title="${escapeHtml(t.tag)}: ${t.count}">#${escapeHtml(t.tag)}</span>`;
      })
      .join("");

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("hash", 16)} Хэштеги</div>
        <div class="trends-tagcloud">${chips}</div>
      </div>`;
  }

  function renderHeatmap(data) {
    let maxVal = 0;
    for (const day of Object.values(data)) {
      for (const count of Object.values(day)) {
        if (count > maxVal) maxVal = count;
      }
    }
    if (maxVal === 0) maxVal = 1;

    // Build 7×24 grid
    let rows = "";
    for (let d = 0; d < 7; d++) {
      let cells = `<div class="trends-heatmap-label">${WEEKDAY_LABELS[d]}</div>`;
      const dayData = data[d] || {};
      for (let h = 0; h < 24; h++) {
        const count = dayData[h] || 0;
        const opacity = count > 0 ? 0.15 + (count / maxVal) * 0.85 : 0.04;
        const isTop = count === maxVal && count > 0;
        cells += `<div class="trends-heatmap-cell ${isTop ? "top" : ""}"
                       style="background: rgba(var(--brand-rgb), ${opacity})"
                       title="${WEEKDAY_LABELS[d]} ${h}:00 — ${count} пост."></div>`;
      }
      rows += `<div class="trends-heatmap-row">${cells}</div>`;
    }

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("calendar", 16)} Активность по дням/часам</div>
        <div class="trends-heatmap">
          <div class="trends-heatmap-header">
            <div class="trends-heatmap-label"></div>
            ${Array.from({ length: 24 }, (_, h) => `<div class="trends-heatmap-hour">${h % 6 === 0 ? h : ""}</div>`).join("")}
          </div>
          ${rows}
        </div>
      </div>`;
  }

  function renderFormatBreakdown(formats) {
    const total = Object.values(formats).reduce((s, v) => s + v, 0) || 1;
    const formatLabels = {
      IMAGE: "Фото",
      VIDEO: "Видео",
      CAROUSEL_ALBUM: "Карусель",
      TEXT_POST: "Текст",
      unknown: "Другое",
    };
    const formatColors = {
      IMAGE: "var(--brand)",
      VIDEO: "#4a90d9",
      CAROUSEL_ALBUM: "#6bb86e",
      TEXT_POST: "#d4845e",
      unknown: "#999",
    };

    const segments = Object.entries(formats)
      .sort(([, a], [, b]) => b - a)
      .map(
        ([type, count]) => `
        <div class="trends-format-segment"
             style="flex-grow: ${count}; background: ${formatColors[type] || formatColors.unknown}">
        </div>`
      )
      .join("");

    const labels = Object.entries(formats)
      .sort(([, a], [, b]) => b - a)
      .map(
        ([type, count]) => `
        <span class="trends-format-label">
          <span class="trends-format-dot" style="background: ${formatColors[type] || formatColors.unknown}"></span>
          ${escapeHtml(formatLabels[type] || type)} ${Math.round((count / total) * 100)}%
        </span>`
      )
      .join("");

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("layout-grid", 16)} Форматы</div>
        <div class="trends-format-bar">${segments}</div>
        <div class="trends-format-labels">${labels}</div>
      </div>`;
  }

  function renderThreadHooks(hooks) {
    const items = hooks
      .map(
        (h) => `
      <div class="trends-hook-card">
        <span class="trends-hook-quote">"${escapeHtml(h)}"</span>
      </div>`
      )
      .join("");

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("zap", 16)} Зацепки (хуки)</div>
        ${items}
      </div>`;
  }

  function renderBestTimes(times) {
    const items = times
      .slice(0, 5)
      .map(
        (t) => `
      <div class="trends-time-row">
        <span class="trends-time-hour">${t.hour}:00</span>
        <span class="trends-time-eng">${actionLabel("heart", t.avg_engagement)} ср. вовлечение</span>
        <span class="trends-time-count">${t.post_count} пост.</span>
      </div>`
      )
      .join("");

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("clock", 16)} Лучшее время для публикации</div>
        ${items}
      </div>`;
  }

  function renderContentLengths(lengths) {
    const total = (lengths.short || 0) + (lengths.medium || 0) + (lengths.long || 0) || 1;
    const bars = [
      { label: "Короткие (<100)", count: lengths.short || 0, color: "#6bb86e" },
      { label: "Средние (100-300)", count: lengths.medium || 0, color: "var(--brand)" },
      { label: "Длинные (>300)", count: lengths.long || 0, color: "#4a90d9" },
    ];

    const segments = bars
      .map((b) => `<div class="trends-format-segment" style="flex-grow: ${b.count || 0.1}; background: ${b.color}"></div>`)
      .join("");
    const labels = bars
      .map(
        (b) => `<span class="trends-format-label">
          <span class="trends-format-dot" style="background: ${b.color}"></span>
          ${escapeHtml(b.label)} ${Math.round((b.count / total) * 100)}%
        </span>`
      )
      .join("");

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("align-left", 16)} Длина контента</div>
        <div class="trends-format-bar">${segments}</div>
        <div class="trends-format-labels">${labels}</div>
      </div>`;
  }

  function renderDetailLoader() {
    return `<div class="detail-loader"><div class="loader"></div> Загрузка трендов…</div>`;
  }

  // ── Monitored accounts section ─────────────────────────────────────────

  function renderMonitoredAccountsSection() {
    const igAccounts = monitoredAccounts.instagram || [];
    const thAccounts = monitoredAccounts.threads || [];

    const renderAccountChips = (accounts, platform) => {
      if (accounts.length === 0) return `<span class="plan-entry-hint">Нет аккаунтов</span>`;
      return accounts.map((a) => {
        const username = a.username || a;
        return `<span class="keyword-chip">
          <span>@${escapeHtml(username)}</span>
          <button type="button" aria-label="Удалить" data-action="removeMonitoredAccount" data-args='${JSON.stringify([platform, username])}'><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
        </span>`;
      }).join("");
    };

    return `
      <div class="trends-monitored-section">
        <div class="detail-section-title" style="margin-top:16px">${uiIcon("at-sign", 16)} Отслеживаемые аккаунты</div>
        <div class="trends-monitored-group">
          <strong class="trends-monitored-label">${uiIcon("instagram", 14)} Instagram</strong>
          <div class="keyword-items">${renderAccountChips(igAccounts, "instagram")}</div>
        </div>
        <div class="trends-monitored-group">
          <strong class="trends-monitored-label">${uiIcon("at-sign", 14)} Threads</strong>
          <div class="keyword-items">${renderAccountChips(thAccounts, "threads")}</div>
        </div>
        <div class="keyword-form keyword-add-row" style="margin-top:8px">
          <select id="monitoredPlatformSelect" class="trends-platform-select">
            <option value="instagram">Instagram</option>
            <option value="threads">Threads</option>
          </select>
          <input id="monitoredUsernameInput" type="text" placeholder="@username">
          <button class="secondary-button" type="button" data-action="addMonitoredAccount">Добавить</button>
        </div>
      </div>
    `;
  }

  function renderTrackedHashtagsSection() {
    const chips = trackedHashtags.length === 0
      ? `<span class="plan-entry-hint">Нет хештегов</span>`
      : trackedHashtags.map((tag) => `
          <span class="keyword-chip">
            <span>#${escapeHtml(tag)}</span>
            <button type="button" aria-label="Удалить" data-action="removeTrackedHashtag" data-args='${JSON.stringify([tag])}'><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
          </span>`).join("");

    return `
      <div class="trends-monitored-section" style="margin-top:12px">
        <div class="detail-section-title">${uiIcon("hash", 16)} Отслеживаемые хештеги и ключевые слова</div>
        <div class="keyword-items">${chips}</div>
        <div class="keyword-form keyword-add-row" style="margin-top:8px">
          <input id="trackedHashtagInput" type="text" placeholder="#хештег или ключевое слово">
          <button class="secondary-button" type="button" data-action="addTrackedHashtag">Добавить</button>
        </div>
      </div>`;
  }

  async function addTrackedHashtag() {
    const inputEl = document.getElementById("trackedHashtagInput");
    const raw = String(inputEl?.value || "").trim().replace(/^#/, "");
    if (!raw) { inputEl?.focus(); return; }
    try {
      await fetchJson("/api/social/tracked-hashtags", {
        method: "POST",
        body: JSON.stringify({ tag: raw }),
      });
      if (inputEl) inputEl.value = "";
      showUiNotice("Хештег добавлен", "success");
      try {
        const res = await fetchJson("/api/social/tracked-hashtags");
        trackedHashtags = (res || {}).items || [];
      } catch (_) { /* ignore */ }
      elements.draftList.innerHTML = renderTrendsListPanel();
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      const detail = err?.detail || "";
      if (detail === "already_tracked") showUiNotice("Хештег уже добавлен", "warning");
      else showUiNotice("Не удалось добавить хештег", "error");
    }
  }

  async function removeTrackedHashtag(tag) {
    const _confirm = confirmAction || ((msg) => Promise.resolve(window.confirm(msg)));
    const ok = await _confirm(`Удалить хештег #${tag}?`);
    if (!ok) return;
    try {
      await fetchJson(`/api/social/tracked-hashtags/${encodeURIComponent(tag)}`, {
        method: "DELETE",
      });
      showUiNotice("Хештег удалён", "success");
      try {
        const res = await fetchJson("/api/social/tracked-hashtags");
        trackedHashtags = (res || {}).items || [];
      } catch (_) { /* ignore */ }
      elements.draftList.innerHTML = renderTrendsListPanel();
      if (window.lucide) lucide.createIcons();
    } catch (_err) {
      showUiNotice("Не удалось удалить хештег", "error");
    }
  }

  async function addMonitoredAccount() {
    const platformEl = document.getElementById("monitoredPlatformSelect");
    const usernameEl = document.getElementById("monitoredUsernameInput");
    const platform = platformEl?.value || "instagram";
    const raw = String(usernameEl?.value || "").trim();
    const username = _extractUsername(raw);
    if (!username) { usernameEl?.focus(); return; }
    try {
      await fetchJson("/api/social/monitored-accounts", {
        method: "POST",
        body: JSON.stringify({ platform, username }),
      });
      if (usernameEl) usernameEl.value = "";
      showUiNotice("Аккаунт добавлен", "success");
      // Reload accounts
      try {
        monitoredAccounts = await fetchJson("/api/social/monitored-accounts");
      } catch (_) { /* ignore */ }
      elements.draftList.innerHTML = renderTrendsListPanel();
      if (window.lucide) lucide.createIcons();
    } catch (err) {
      const detail = err?.detail || "";
      if (detail === "already_monitored") showUiNotice("Аккаунт уже добавлен", "warning");
      else if (detail === "max_accounts_reached") showUiNotice("Достигнут лимит аккаунтов", "error");
      else showUiNotice("Не удалось добавить аккаунт", "error");
    }
  }

  async function removeMonitoredAccount(platform, username) {
    const _confirm = confirmAction || ((msg) => Promise.resolve(window.confirm(msg)));
    const ok = await _confirm(`Удалить аккаунт @${username}?`);
    if (!ok) return;
    try {
      await fetchJson(`/api/social/monitored-accounts/${platform}/${encodeURIComponent(username)}`, {
        method: "DELETE",
      });
      showUiNotice("Аккаунт удалён", "success");
      try {
        monitoredAccounts = await fetchJson("/api/social/monitored-accounts");
      } catch (_) { /* ignore */ }
      elements.draftList.innerHTML = renderTrendsListPanel();
      if (window.lucide) lucide.createIcons();
    } catch (_err) {
      showUiNotice("Не удалось удалить аккаунт", "error");
    }
  }

  // ── Actions ──────────────────────────────────────────────────────────

  function selectTrendsPlatform(platform) {
    trendsPlatform = platform;
    void loadTrends();
  }

  function selectTrendsPeriod(period) {
    trendsPeriod = period;
    void loadTrends();
  }

  async function refreshTrends(btn) {
    if (btn) {
      await withButtonFeedback(btn, "Обновление…", async () => {
        try {
          await fetchJson("/api/trends/refresh", { method: "POST" });
          showUiNotice("Сбор данных запущен. Обновите через пару минут.");
        } catch (err) {
          const detail = err?.detail || {};
          if (detail.error === "cooldown") {
            showUiNotice(`Повторите через ${Math.ceil(detail.retry_after_seconds / 60)} мин.`);
          } else {
            showUiNotice("Не удалось запустить обновление.");
          }
        }
      }, "Готово");
    }
  }

  function openTrendsPost(idx) {
    if (!trendsData || !trendsData.top_posts) return;
    const post = trendsData.top_posts[idx];
    if (!post) return;

    const eng = (post.like_count || 0) + (post.comment_count || 0) + (post.share_count || 0) + (post.reply_count || 0);

    elements.draftDetail.innerHTML = `
      ${renderBackButton("К трендам", () => { void loadTrends(); })}
      <div class="detail-section">
        <div class="detail-section-title">${escapeHtml(post.author_username || "Пост")}</div>
        <div class="detail-text">${escapeHtml(post.text || "").replace(/\n/g, "<br>")}</div>
        <div class="detail-meta" style="margin-top: 12px;">
          ${actionLabel("heart", post.like_count || 0)}
          ${actionLabel("message-circle", post.comment_count || 0)}
          ${post.share_count ? actionLabel("repeat", post.share_count) : ""}
          ${post.reply_count ? actionLabel("corner-down-right", post.reply_count) : ""}
          ${post.view_count ? actionLabel("eye", post.view_count) : ""}
        </div>
        ${post.permalink ? `<a href="${escapeHtml(post.permalink)}" target="_blank" class="btn btn-secondary" style="margin-top: 12px;">Открыть оригинал</a>` : ""}
        ${post.posted_at ? `<div class="detail-meta" style="margin-top: 8px; opacity: 0.6;">${escapeHtml(new Date(post.posted_at).toLocaleString("ru"))}</div>` : ""}
      </div>
      ${post.hashtags && post.hashtags.length > 0 ? `<div class="detail-section"><div class="detail-section-title">Хэштеги</div><div class="trends-tagcloud">${post.hashtags.map((t) => `<span class="trends-tagcloud-chip" style="font-size: 0.85rem">#${escapeHtml(t)}</span>`).join("")}</div></div>` : ""}
    `;
    enterDetailView();
    syncMobileNavigation();
    if (window.lucide) lucide.createIcons();
  }

  // ── Trend Cards (AI-generated) ────────────────────────────────────
  let trendCards = null;

  function renderTrendCardsList() {
    if (!trendCards) {
      (async () => {
        try {
          const data = await fetchJson("/api/trends/cards?limit=10");
          trendCards = data.cards || [];
          const container = elements.draftList.querySelector(".trends-cards-container");
          if (container) container.innerHTML = _renderCardsInner();
          if (window.lucide) lucide.createIcons();
        } catch (_e) { /* optional */ }
      })();
      return `<div class="trends-cards-container"><div class="suggest-topics-loading"><span class="button-spinner"></span> Загрузка карточек...</div></div>`;
    }
    return `<div class="trends-cards-container">${_renderCardsInner()}</div>`;
  }

  function _renderCardsInner() {
    if (!trendCards || !trendCards.length) {
      return `<div class="detail-empty"><p>Нет AI-карточек. Нажмите "Сгенерировать" для создания.</p>
        <button class="primary-button" type="button" data-action="generateTrendCards">${uiIcon("sparkles", 14)}<span>Сгенерировать карточки</span></button></div>`;
    }
    const lifecycleColors = { emerging: "#4CAF50", growing: "#2196F3", peaking: "#FF9800", declining: "#9E9E9E" };
    return trendCards.map(c => `
      <div class="trend-card interactive-card" data-card-id="${escapeHtml(c.card_id)}">
        <div class="trend-card-header">
          <span class="keyword-chip" style="background:${lifecycleColors[c.lifecycle] || "var(--muted)"};color:#fff;font-size:0.7rem">${escapeHtml(c.lifecycle || "?")}</span>
          <strong>${escapeHtml(c.title || c.keyword)}</strong>
          <span class="trend-strength" style="color:${c.strength >= 0.7 ? "var(--success, green)" : "var(--muted)"}">${(c.strength * 100).toFixed(0)}%</span>
        </div>
        <div class="trend-card-summary">${escapeHtml((c.summary || "").substring(0, 120))}</div>
        ${c.recommendation ? `<div class="trend-card-rec">${uiIcon("lightbulb", 12)} ${escapeHtml(c.recommendation.substring(0, 100))}</div>` : ""}
        <div class="trend-card-actions">
          <button class="secondary-button" type="button" data-action="createFromTrendCard" data-args='${JSON.stringify([c.card_id, c.title])}'>${uiIcon("plus", 14)}<span>Создать контент</span></button>
        </div>
      </div>
    `).join("") + `<button class="secondary-button" type="button" data-action="generateTrendCards" style="margin-top:0.5rem">${uiIcon("refresh-cw", 14)}<span>Обновить карточки</span></button>`;
  }

  async function generateTrendCards() {
    try {
      await fetchJson("/api/trends/cards/generate", { method: "POST", timeout: 60000 });
      showUiNotice("Генерация карточек запущена", "info");
      trendCards = null;
      renderTrendsListPanel();
    } catch (e) { showUiNotice("Произошла ошибка", "error"); }
  }

  async function createFromTrendCard(cardId, title) {
    try {
      const draft = await fetchJson("/api/trends/create-from-trend", {
        method: "POST", timeout: 45000,
        body: JSON.stringify({ card_id: cardId, format_key: "instagram", goal_key: "trust" }),
      });
      showUiNotice("Черновик создан из тренда", "success");
      if (draft?.draft_id && deps.openDraft) {
        await deps.openDraft(draft.draft_id);
      }
    } catch (e) { showUiNotice("Произошла ошибка", "error"); }
  }

  return {
    loadTrends,
    renderTrendsListPanel,
    renderTrendsDetail,
    selectTrendsPlatform,
    selectTrendsPeriod,
    refreshTrends,
    openTrendsPost,
    addMonitoredAccount,
    removeMonitoredAccount,
    addTrackedHashtag,
    removeTrackedHashtag,
    createFromInsight,
    generateTrendCards,
    createFromTrendCard,
  };
}
