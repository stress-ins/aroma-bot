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
  let intelligenceData = null;
  let digestData = null;
  let analyticsSourceFilter = null; // null = all, string = specific source key
  let monitoredAccounts = { instagram: [], threads: [], connected_usernames: {} };
  let trackedHashtags = [];
  let accountStats = [];
  let healthData = null;
  let healthExpanded = false;
  let cooldownUntil = 0; // unix ms when cooldown expires
  let _cooldownTimer = null;

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
          : trendsPlatform === "analytics"
            ? fetchJson("/api/trends/intelligence")
            : fetchJson(`/api/trends/${trendsPlatform}?period=${trendsPeriod}`),
        fetchJson("/api/social/monitored-accounts"),
        fetchJson("/api/social/tracked-hashtags"),
        fetchJson("/api/trends/account-stats"),
        fetchJson("/api/trends/health"),
      ];
      if (trendsPlatform === "analytics") {
        promises.push(fetchJson("/api/trends/cards?limit=10"));
        promises.push(fetchJson("/api/trends/digest"));
      } else if (trendsPlatform !== "compare") {
        promises.push(fetchJson(`/api/trends/suggestions?platform=${trendsPlatform}`));
      }
      const results = await Promise.allSettled(promises);
      const [trendsResult, accountsResult, hashtagsResult, statsResult, healthResult] = results;

      if (trendsPlatform === "analytics") {
        intelligenceData = trendsResult.status === "fulfilled" ? trendsResult.value : null;
        const cardsResult = results[5];
        const digestResult = results[6];
        trendCards = cardsResult && cardsResult.status === "fulfilled" ? (cardsResult.value?.cards || []) : null;
        digestData = digestResult && digestResult.status === "fulfilled" ? digestResult.value : null;
        trendsData = null;
        trendsCompare = null;
        analyticsSourceFilter = null;
      } else if (trendsPlatform === "compare") {
        trendsCompare = trendsResult.status === "fulfilled" ? trendsResult.value : null;
        trendsData = null;
        intelligenceData = null;
      } else {
        trendsData = trendsResult.status === "fulfilled" ? trendsResult.value : null;
        trendsCompare = null;
        intelligenceData = null;
        const suggestionsResult = results[5];
        if (suggestionsResult && suggestionsResult.status === "fulfilled") {
          suggestionsData = suggestionsResult.value;
        } else {
          suggestionsData = null;
        }
      }

      if (accountsResult.status === "fulfilled") {
        monitoredAccounts = accountsResult.value || { instagram: [], threads: [] };
      }
      if (hashtagsResult.status === "fulfilled") {
        trackedHashtags = (hashtagsResult.value || {}).items || [];
      }
      if (statsResult && statsResult.status === "fulfilled") {
        accountStats = (statsResult.value || {}).accounts || [];
      }
      if (healthResult && healthResult.status === "fulfilled") {
        healthData = healthResult.value || [];
      }
    } catch (err) {
      trendsData = null;
      trendsCompare = null;
      intelligenceData = null;
      suggestionsData = null;
      healthData = null;
      digestData = null;
    }

    elements.listTitle.textContent = "Тренды";
    elements.draftList.innerHTML = renderTrendsListPanel();
    elements.draftDetail.innerHTML = renderTrendsDetail();
    syncMobileNavigation();
  }

  // ── Health indicator ──────────────────────────────────────────────────

  function _collectorStatus(c) {
    const now = new Date();
    const lastSuccess = c.last_success ? new Date(c.last_success) : null;
    const circuitUntil = c.circuit_open_until ? new Date(c.circuit_open_until) : null;
    const hoursSince = lastSuccess ? (now - lastSuccess) / 3600000 : Infinity;
    const failures = c.consecutive_failures || 0;

    if (circuitUntil && circuitUntil > now) return "red";
    if (hoursSince > 24) return "red";
    if (hoursSince > 12 || failures > 0) return "yellow";
    return "green";
  }

  function _collectorDisplayName(key) {
    const names = {
      google_trends: "Google",
      threads: "Threads",
      instagram: "Instagram",
      youtube: "YouTube",
    };
    return names[key] || key;
  }

  function _formatHealthTimestamp() {
    if (!healthData || !healthData.length) return null;
    let latest = null;
    for (const c of healthData) {
      if (c.last_success) {
        const d = new Date(c.last_success);
        if (!latest || d > latest) latest = d;
      }
    }
    if (!latest) return null;
    const hh = String(latest.getHours()).padStart(2, "0");
    const mm = String(latest.getMinutes()).padStart(2, "0");
    const dd = String(latest.getDate()).padStart(2, "0");
    const mo = String(latest.getMonth() + 1).padStart(2, "0");
    return `${hh}:${mm} ${dd}.${mo}`;
  }

  function renderHealthIndicator() {
    if (!healthData || !healthData.length) return "";

    const ts = _formatHealthTimestamp();
    const tsLabel = ts ? `Данные от: ${ts}` : "Нет данных";

    const dots = healthData.map((c) => {
      const status = _collectorStatus(c);
      const name = _collectorDisplayName(c.source_key);
      return `<span class="health-dot-item"><span class="health-dot health-dot--${status}"></span>${escapeHtml(name)}</span>`;
    }).join("");

    let details = "";
    if (healthExpanded) {
      const rows = healthData.map((c) => {
        const status = _collectorStatus(c);
        const name = _collectorDisplayName(c.source_key);
        const failures = c.consecutive_failures || 0;
        const lastOk = c.last_success
          ? new Date(c.last_success).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
          : "никогда";
        const circuitUntil = c.circuit_open_until ? new Date(c.circuit_open_until) : null;
        const circuitActive = circuitUntil && circuitUntil > new Date();

        let statusText = "Работает";
        if (status === "red") statusText = circuitActive ? "Приостановлен" : "Нет данных >24ч";
        else if (status === "yellow") statusText = failures > 0 ? `Ошибки: ${failures}` : "Данные устаревают";

        return `
          <div class="health-detail-row">
            <span class="health-dot health-dot--${status}"></span>
            <span class="health-detail-name">${escapeHtml(name)}</span>
            <span class="health-detail-status">${statusText}</span>
            <span class="health-detail-time">${escapeHtml(lastOk)}</span>
          </div>`;
      }).join("");

      details = `<div class="health-details">${rows}</div>`;
    }

    const expandIcon = healthExpanded ? "caret-up" : "caret-down";

    return `
      <div class="health-indicator" data-action="toggleHealthDetails">
        <div class="health-summary">
          <span class="health-ts">${escapeHtml(tsLabel)}</span>
          <span class="health-dots">${dots}</span>
          <i class="ph ph-${expandIcon} health-chevron"></i>
        </div>
        ${details}
      </div>`;
  }

  function toggleHealthDetails() {
    healthExpanded = !healthExpanded;
    const container = document.querySelector(".health-indicator");
    if (container) {
      container.outerHTML = renderHealthIndicator();
    }
  }

  // ── List Panel (platform selector + filters) ─────────────────────────

  function renderTrendsListPanel() {
    const platforms = [
      { id: "instagram", label: "Instagram", icon: "instagram" },
      { id: "threads", label: "Threads", icon: "at-sign" },
      { id: "compare", label: "Сравнение", icon: "columns-2" },
      { id: "analytics", label: "Аналитика", icon: "chart-line" },
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

    const now = Date.now();
    const inCooldown = cooldownUntil > now;
    const cooldownRemainSec = inCooldown ? Math.ceil((cooldownUntil - now) / 1000) : 0;
    const cooldownLabel = inCooldown
      ? `${uiIcon("clock", 14)} Обновление через ${_formatCooldown(cooldownRemainSec)}`
      : `${uiIcon("refresh-cw", 14)} Обновить`;
    const refreshBtn = `<button class="trends-refresh-btn ${inCooldown ? "trends-refresh-btn--cooldown" : ""}" id="trendsRefreshBtn"
                                ${inCooldown ? "disabled" : ""}
                                data-action="refreshTrends" data-args='[null]'>
      ${cooldownLabel}
    </button>`;

    let summary = "";
    if (trendsPlatform === "analytics") {
      summary = renderAnalyticsSummaryList();
    } else if (trendsPlatform === "compare" && trendsCompare) {
      summary = renderCompareSummaryList();
    } else if (trendsData) {
      summary = renderPlatformSummaryList();
    }

    const settingsLink = `
      <div class="trends-settings-link">
        <button class="secondary-button" type="button" data-action="openSettingsSection" data-args='["monitored"]'>
          ${uiIcon("settings", 14)} <span>Аккаунты и хештеги</span>
        </button>
      </div>`;

    // On mobile, detail panel is hidden — show dashboard inline before posts
    let inlineDashboard = "";
    if (document.body.classList.contains("is-mobile-layout")) {
      const dashHtml = renderTrendsDetail();
      if (dashHtml && !dashHtml.includes("detail-empty")) {
        inlineDashboard = `<div class="trends-dashboard-inline">${dashHtml}</div>`;
      }
    }

    const healthBar = renderHealthIndicator();

    return `
      <div class="trends-controls">
        <div class="trends-platform-tabs">${platformTabs}</div>
        ${healthBar}
        <div class="trends-period-row">
          <div class="trends-period-btns">${periodBtns}</div>
          ${refreshBtn}
        </div>
      </div>
      ${inlineDashboard}
      ${summary}
      ${settingsLink}
    `;
  }

  const MEDIA_LABELS = { IMAGE: "Фото", VIDEO: "Видео", CAROUSEL_ALBUM: "Карусель", TEXT_POST: "Текст", REEL: "Reels" };

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

    const connected = monitoredAccounts.connected_usernames || {};
    const ownUsernames = new Set(
      Object.values(connected).map(u => u.replace(/^@/, "").toLowerCase()),
    );

    const isIg = trendsPlatform === "instagram";
    const platformClass = isIg ? "ig" : "th";
    const posts = topPosts.slice(0, 10);

    // Compute totals for summary bar
    const totalLikes = posts.reduce((s, p) => s + (p.like_count || 0), 0);
    const totalViews = posts.reduce((s, p) => s + (p.view_count || 0), 0);
    const totalComments = posts.reduce((s, p) => s + (p.comment_count || 0) + (p.reply_count || 0), 0);
    const maxLikes = Math.max(...posts.map(p => p.like_count || 0), 1);

    // Find top post index (most likes)
    let topIdx = 0;
    posts.forEach((p, i) => { if ((p.like_count || 0) > (posts[topIdx].like_count || 0)) topIdx = i; });

    const summaryBar = `
      <div class="posts-summary-bar">
        <span class="psb-item">${posts.length} постов</span>
        <span class="psb-dot">·</span>
        <span class="psb-item psb-highlight">♡ ${totalLikes} всего</span>
        <span class="psb-dot">·</span>
        <span class="psb-item">${totalViews ? `◉ ${totalViews} просм.` : `💬 ${totalComments} комм.`}</span>
      </div>`;

    const cards = posts
      .map((p, i) => {
        const preview = escapeHtml((p.text || "").substring(0, 80));
        const author = (p.author_username || "").toLowerCase();
        const isOwn = ownUsernames.has(author);
        const isTop = i === topIdx && (p.like_count || 0) > 0;
        const relPct = Math.round(((p.like_count || 0) / maxLikes) * 100);
        const engRate = totalViews > 0
          ? ((p.like_count || 0) / Math.max(p.view_count || 1, 1) * 100).toFixed(1)
          : ((p.like_count || 0) / maxLikes * 10).toFixed(1);

        return `
        <div class="post-card-v2 ${isTop ? "is-top" : ""} ${isIg ? "pc-ig" : ""}" data-action="openTrendsPost" data-args='[${i}]'>
          <div class="pc-v2-top">
            <span class="pc-v2-account">@${escapeHtml(p.author_username || "—")}</span>
            ${isOwn ? `<span class="pc-v2-own-badge">Свой</span>` : `<span class="pc-v2-competitor-badge">Чужой</span>`}
            ${p.media_type ? `<span class="pc-v2-type">${MEDIA_LABELS[p.media_type] || p.media_type}</span>` : ""}
            <span class="pc-v2-time">${_relDate(p.posted_at)}</span>
          </div>
          <div class="pc-v2-text">${preview}${p.text && p.text.length > 80 ? "…" : ""}</div>
          <div class="pc-v2-metrics">
            <div class="pc-v2-metric ${isTop ? "pc-highlight" : ""}">♡ ${p.like_count || 0}</div>
            ${(p.reply_count || 0) ? `<div class="pc-v2-metric">◎ ${p.reply_count}</div>` : ""}
            ${(p.comment_count || 0) ? `<div class="pc-v2-metric">💬 ${p.comment_count}</div>` : ""}
            ${(p.view_count || 0) ? `<div class="pc-v2-metric">◉ ${p.view_count}</div>` : ""}
            ${(p.share_count || 0) ? `<div class="pc-v2-metric">↺ ${p.share_count}</div>` : ""}
            ${isTop ? `<div class="pc-v2-top-badge">топ</div>` : ""}
          </div>
          <div class="pc-v2-rel-bar">
            <div class="pcr-v2-bg"><div class="pcr-v2-fill ${platformClass}" style="width:${relPct}%"></div></div>
            <span class="pcr-v2-val">${engRate}%</span>
          </div>
        </div>`;
      })
      .join("");

    return `${summaryBar}<div class="draft-list-content">${cards}</div>`;
  }

  function _relDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    const diffH = Math.round((now - d) / 3600000);
    if (diffH < 1) return "только что";
    if (diffH < 24) return `${diffH}ч назад`;
    const diffD = Math.round(diffH / 24);
    return `${diffD}д назад`;
  }

  function renderCompareSummaryList() {
    if (!trendsCompare) return "";
    const ig = trendsCompare.instagram || {};
    const th = trendsCompare.threads || {};
    const totals = trendsCompare.totals || {};
    const bestPost = trendsCompare.best_post;
    const periodDays = trendsCompare.period_days || trendsPeriod;

    // Engagement bar relative percentage (max = larger of the two)
    const maxEng = Math.max(ig.avg_engagement || 0, th.avg_engagement || 0, 1);
    const igEngPct = Math.round(((ig.avg_engagement || 0) / maxEng) * 100);
    const thEngPct = Math.round(((th.avg_engagement || 0) / maxEng) * 100);

    const summarySection = `
      <div class="analytics-summary">
        <div class="analytics-summary-label">Всего за ${periodDays} дней</div>
        <div class="analytics-summary-metrics">
          <div class="asm-item">
            <span class="asm-val">${totals.posts || 0}</span>
            <span class="asm-label">постов</span>
          </div>
          <div class="asm-divider"></div>
          <div class="asm-item">
            <span class="asm-val">${totals.likes || 0}</span>
            <span class="asm-label">лайков</span>
          </div>
          <div class="asm-divider"></div>
          <div class="asm-item">
            <span class="asm-val">${totals.comments || 0}</span>
            <span class="asm-label">комментов</span>
          </div>
          <div class="asm-divider"></div>
          <div class="asm-item">
            <span class="asm-val">${totals.views || 0}</span>
            <span class="asm-label">просмотров</span>
          </div>
        </div>
      </div>`;

    const platformCards = `
      <div class="analytics-stats-grid">
        <div class="analytics-platform-card">
          <div class="apc-header">
            <div class="apc-dot apc-dot-ig"></div>
            <span class="apc-platform">Instagram</span>
          </div>
          <div class="apc-metric">
            <span class="apc-m-val">${ig.avg_engagement || 0}</span>
            <span class="apc-m-label">ср. вовлечение</span>
            <div class="apc-eng-bar">
              <div class="apc-eng-bar-bg"><div class="apc-eng-bar-fill ig" style="width:${igEngPct}%"></div></div>
            </div>
          </div>
          <div class="apc-divider"></div>
          <div class="apc-metric">
            <span class="apc-m-val-sm">${ig.best_hour != null ? ig.best_hour + ":00" : "—"}</span>
            <span class="apc-m-label">лучшее время</span>
          </div>
          <div class="apc-divider"></div>
          <div class="apc-metric">
            <span class="apc-m-val-sm">${ig.post_count || 0} постов</span>
            <span class="apc-m-label">за период</span>
          </div>
        </div>
        <div class="analytics-platform-card">
          <div class="apc-header">
            <div class="apc-dot apc-dot-th"></div>
            <span class="apc-platform">Threads</span>
          </div>
          <div class="apc-metric">
            <span class="apc-m-val">${th.avg_engagement || 0}</span>
            <span class="apc-m-label">ср. вовлечение</span>
            <div class="apc-eng-bar">
              <div class="apc-eng-bar-bg"><div class="apc-eng-bar-fill th" style="width:${thEngPct}%"></div></div>
            </div>
          </div>
          <div class="apc-divider"></div>
          <div class="apc-metric">
            <span class="apc-m-val-sm">${th.best_hour != null ? th.best_hour + ":00" : "—"}</span>
            <span class="apc-m-label">лучшее время</span>
          </div>
          <div class="apc-divider"></div>
          <div class="apc-metric">
            <span class="apc-m-val-sm">${th.post_count || 0} постов</span>
            <span class="apc-m-label">за период</span>
          </div>
        </div>
      </div>`;

    let bestPostHtml = "";
    if (bestPost) {
      const isIg = bestPost.platform === "instagram";
      bestPostHtml = `
        <div class="analytics-best-post" style="border-left-color: ${isIg ? "#e1306c" : "#9580ff"}">
          <div class="abp-label">
            <div class="apc-dot ${isIg ? "apc-dot-ig" : "apc-dot-th"}"></div>
            Лучший пост за период
          </div>
          <div class="abp-text">${escapeHtml(bestPost.text)}</div>
          <div class="abp-metrics">
            <span class="abp-val">♡ ${bestPost.likes}</span>
            ${bestPost.shares ? `<span class="abp-secondary">↺ ${bestPost.shares}</span>` : ""}
            <span class="abp-time">${_relDate(bestPost.posted_at)}</span>
          </div>
        </div>`;
    }

    return `<div class="draft-list-content" style="display:flex;flex-direction:column;gap:8px;padding:0 0 8px">
      ${summarySection}${platformCards}${bestPostHtml}
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
                <p>Перейдите в <button class="link-button" data-action="openSettingsSection" data-args='["monitored"]'>настройки аккаунтов</button> и укажите конкурентов или источники вдохновения.</p>
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
    if (trendsPlatform === "analytics") return renderAnalyticsDetail();
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

    // Repost leaders (Threads)
    const repostLeaders = trendsData.repost_leaders || [];
    if (repostLeaders.length > 0) {
      sections.push(renderRepostLeaders(repostLeaders));
    }

    // Content lengths (Threads)
    const lengths = trendsData.content_lengths;
    if (lengths) {
      sections.push(renderContentLengths(lengths));
    }

    if (sections.length === 0) {
      return `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Аналитика",
        title: "Данные ещё собираются",
        body: "Мониторинг настроен. Данные появятся после следующего цикла обновления (каждые 6 часов) или нажмите «Обновить» вручную.",
        actionLabel: "Обновить",
        action: "refreshTrends",
      })}</div>`;
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
      <div class="insight-card">
        <div class="insight-card-topic">${escapeHtml(h)}</div>
        <div class="insight-card-footer">
          <span class="insight-card-format">${uiIcon("zap", 14)} Хук</span>
          <button class="secondary-button" type="button" data-action="createFromInsight" data-args='${JSON.stringify([h, [], "threads_series"])}'>
            ${uiIcon("plus", 14)} Создать контент
          </button>
        </div>
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

  function renderRepostLeaders(leaders) {
    const items = leaders
      .filter((p) => (p.share_count || 0) > 0)
      .map(
        (p) => `
      <div class="trends-repost-row">
        <span class="trends-repost-author">@${escapeHtml(p.author_username || "—")}</span>
        <span class="trends-repost-count">${actionLabel("repeat", p.share_count || 0)} репостов</span>
        <span class="trends-repost-preview">${escapeHtml((p.text || "").substring(0, 60))}${(p.text || "").length > 60 ? "…" : ""}</span>
      </div>`
      )
      .join("");

    if (!items) return "";

    return `
      <div class="detail-section">
        <div class="detail-section-title">${uiIcon("repeat", 16)} Лидеры репостов</div>
        ${items}
      </div>`;
  }

  function renderDetailLoader() {
    return `<div class="detail-loader"><div class="loader"></div> Загрузка трендов…</div>`;
  }

  // ── Monitored accounts section ─────────────────────────────────────────

  function renderMonitoredAccountsSection() {
    const igAccounts = monitoredAccounts.instagram || [];
    const thAccounts = monitoredAccounts.threads || [];

    const _formatRelative = (isoStr) => {
      if (!isoStr) return "";
      const d = new Date(isoStr);
      const now = new Date();
      const diffMs = now - d;
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 60) return `${diffMin} мин назад`;
      const diffH = Math.floor(diffMin / 60);
      if (diffH < 24) return `${diffH} ч назад`;
      const diffD = Math.floor(diffH / 24);
      return `${diffD} д назад`;
    };

    const renderAccountChips = (accounts, platform) => {
      if (accounts.length === 0) return `<span class="plan-entry-hint">Нет аккаунтов</span>`;
      return accounts.map((a) => {
        const username = a.username || a;
        const stat = accountStats.find((s) => s.platform === platform && s.source_value === `@${username}`);
        const statHtml = stat
          ? `<span class="account-stat">${stat.post_count} пост. · ${_formatRelative(stat.last_collected)}</span>`
          : `<span class="account-stat account-stat--pending">ожидает сбора</span>`;
        return `<span class="keyword-chip keyword-chip--with-stat">
          <span>@${escapeHtml(username)}</span>
          ${statHtml}
          <button type="button" aria-label="Удалить" data-action="removeMonitoredAccount" data-args='${JSON.stringify([platform, username])}'><i class="ph ph-x" style="font-size:14px" aria-hidden="true"></i></button>
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
            <button type="button" aria-label="Удалить" data-action="removeTrackedHashtag" data-args='${JSON.stringify([tag])}'><i class="ph ph-x" style="font-size:14px" aria-hidden="true"></i></button>
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

  function _formatCooldown(totalSec) {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return m > 0 ? `${m} мин ${s > 0 ? s + " сек" : ""}`.trim() : `${s} сек`;
  }

  function _startCooldownTimer() {
    if (_cooldownTimer) clearInterval(_cooldownTimer);
    _cooldownTimer = setInterval(() => {
      const now = Date.now();
      if (cooldownUntil <= now) {
        clearInterval(_cooldownTimer);
        _cooldownTimer = null;
        // Re-render button to unlock it
        const btn = document.getElementById("trendsRefreshBtn");
        if (btn) {
          btn.disabled = false;
          btn.classList.remove("trends-refresh-btn--cooldown");
          btn.innerHTML = `${uiIcon("refresh-cw", 14)} Обновить`;
        }
        return;
      }
      const remainSec = Math.ceil((cooldownUntil - now) / 1000);
      const btn = document.getElementById("trendsRefreshBtn");
      if (btn) {
        btn.innerHTML = `${uiIcon("clock", 14)} Обновление через ${_formatCooldown(remainSec)}`;
      }
    }, 1000);
  }

  async function refreshTrends(btn) {
    // Already in cooldown — ignore click
    if (cooldownUntil > Date.now()) return;

    if (btn) {
      await withButtonFeedback(btn, "Обновление…", async () => {
        try {
          await fetchJson("/api/trends/refresh", { method: "POST" });
          // Set 1-hour cooldown
          cooldownUntil = Date.now() + 60 * 60 * 1000;
          _startCooldownTimer();
          showUiNotice("Сбор данных запущен. Данные обновятся через пару минут.", "success");
          // Re-render button with cooldown state
          const refreshBtn = document.getElementById("trendsRefreshBtn");
          if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.classList.add("trends-refresh-btn--cooldown");
            const remainSec = Math.ceil((cooldownUntil - Date.now()) / 1000);
            refreshBtn.innerHTML = `${uiIcon("clock", 14)} Обновление через ${_formatCooldown(remainSec)}`;
          }
        } catch (err) {
          const msg = err?.message || "";
          // fetchJson throws Error("cooldown") on 429 with cooldown detail
          if (msg === "cooldown" || msg.includes("cooldown")) {
            // Parse retry_after from the original 429 body — we need to fetch it
            // The generic 429 handler already shows a notice, just set cooldown
            cooldownUntil = Date.now() + 60 * 60 * 1000; // assume 1 hour
            _startCooldownTimer();
            const refreshBtn = document.getElementById("trendsRefreshBtn");
            if (refreshBtn) {
              refreshBtn.disabled = true;
              refreshBtn.classList.add("trends-refresh-btn--cooldown");
              const remainSec = Math.ceil((cooldownUntil - Date.now()) / 1000);
              refreshBtn.innerHTML = `${uiIcon("clock", 14)} Обновление через ${_formatCooldown(remainSec)}`;
            }
          } else {
            showUiNotice("Не удалось запустить обновление.", "error");
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
    const connected = monitoredAccounts.connected_usernames || {};
    const ownUsernames = new Set(
      Object.values(connected).map(u => u.replace(/^@/, "").toLowerCase()),
    );
    const detailAuthor = (post.author_username || "").toLowerCase();
    const isOwnPost = ownUsernames.has(detailAuthor);
    const _mediaLbl = (mt) => ({ IMAGE: "Фото", VIDEO: "Видео", CAROUSEL_ALBUM: "Карусель", TEXT_POST: "Текст", REEL: "Reels" }[mt] || mt || "");

    elements.draftDetail.innerHTML = `
      ${renderBackButton("К трендам", () => { void loadTrends(); })}
      <div class="detail-section">
        <div class="detail-section-title">
          @${escapeHtml(post.author_username || "Пост")}
          ${isOwnPost ? `<span class="meta-chip meta-chip--own">Свой</span>` : `<span class="meta-chip meta-chip--competitor">Чужой</span>`}
          ${post.media_type ? `<span class="meta-chip">${_mediaLbl(post.media_type)}</span>` : ""}
        </div>
        <div class="detail-text">${escapeHtml(post.text || "").replace(/\n/g, "<br>")}</div>
        <div class="detail-meta" style="margin-top: 12px;">
          ${(post.like_count || 0) ? actionLabel("heart", post.like_count) : ""}
          ${(post.reply_count || 0) ? actionLabel("message-circle", post.reply_count) : ""}
          ${(post.share_count || 0) ? actionLabel("repeat", post.share_count) : ""}
          ${(post.view_count || 0) ? actionLabel("eye", post.view_count) : ""}
          ${(post.comment_count || 0) ? actionLabel("copy", post.comment_count) : ""}
        </div>
        ${post.permalink ? `<a href="${escapeHtml(post.permalink)}" target="_blank" class="btn btn-secondary" style="margin-top: 12px;">Открыть оригинал</a>` : ""}
        ${post.posted_at ? `<div class="detail-meta" style="margin-top: 8px; opacity: 0.6;">${escapeHtml(new Date(post.posted_at).toLocaleString("ru"))}</div>` : ""}
      </div>
      ${post.hashtags && post.hashtags.length > 0 ? `<div class="detail-section"><div class="detail-section-title">Хэштеги</div><div class="trends-tagcloud">${post.hashtags.map((t) => `<span class="trends-tagcloud-chip" style="font-size: 0.85rem">#${escapeHtml(t)}</span>`).join("")}</div></div>` : ""}
    `;
    enterDetailView();
    syncMobileNavigation();
  }

  // ── Analytics tab (consolidated: Digest + Intelligence + AI cards) ──

  const SOURCE_ICONS = {
    youtube: "youtube", youtube_ru: "youtube", instagram: "instagram",
    threads: "at-sign", tiktok: "music", reddit: "message-circle",
    telegram: "send", google_trends: "trending-up",
  };
  const SOURCE_DISPLAY = {
    youtube: "YouTube", youtube_ru: "YouTube RU", instagram: "Instagram",
    threads: "Threads", tiktok: "TikTok", reddit: "Reddit",
    telegram: "Telegram", google_trends: "Google",
  };

  function _deduplicateSignals(topOpps, emerging) {
    // Build a set of keywords from top_opportunities
    const oppKeywords = new Set(topOpps.map(o => (o.keyword || "").toLowerCase().trim()));
    // Mark emerging signals that also appear in top_opportunities
    const deduped = [];
    const alsoInTop = new Set();
    for (const s of emerging) {
      const kw = (s.keyword || "").toLowerCase().trim();
      if (oppKeywords.has(kw)) {
        alsoInTop.add(kw);
      } else {
        deduped.push(s);
      }
    }
    // Add "also_emerging" flag to matching top opportunities
    const enrichedOpps = topOpps.map(o => {
      const kw = (o.keyword || "").toLowerCase().trim();
      return alsoInTop.has(kw) ? { ...o, _alsoEmerging: true } : o;
    });
    return { enrichedOpps, dedupedEmerging: deduped };
  }

  function setAnalyticsSourceFilter(source) {
    analyticsSourceFilter = analyticsSourceFilter === source ? null : source;
    // Re-render list panel
    elements.draftList.innerHTML = renderTrendsListPanel();
  }

  function renderAnalyticsSummaryList() {
    const sections = [];

    // ─── Section 1: Дайджест ───
    sections.push(_renderDigestSection());

    // ─── Section 2: Trend Intelligence ───
    sections.push(_renderIntelligenceSection());

    // ─── Section 3: AI-карточки ───
    sections.push(_renderAiCardsSection());

    return `<div class="analytics-tab-content">${sections.join("")}</div>`;
  }

  function _renderDigestSection() {
    if (!digestData || digestData.status === "not_available") {
      return `
        <div class="analytics-section">
          <div class="analytics-section-header">
            <span class="analytics-section-icon">${uiIcon("clipboard", 16)}</span>
            <span class="analytics-section-title">Дайджест</span>
          </div>
          <div class="analytics-section-empty">Дайджест ещё не сформирован. Данные появятся после следующего цикла сбора.</div>
        </div>`;
    }

    const report = digestData.ru_report || "";
    const generatedAt = digestData.generated_at
      ? new Date(digestData.generated_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
      : "";

    // Convert markdown-like report to simple HTML
    const htmlReport = escapeHtml(report)
      .replace(/\n/g, "<br>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    return `
      <div class="analytics-section">
        <div class="analytics-section-header">
          <span class="analytics-section-icon">${uiIcon("clipboard", 16)}</span>
          <span class="analytics-section-title">Дайджест</span>
          ${generatedAt ? `<span class="analytics-section-ts">${escapeHtml(generatedAt)}</span>` : ""}
        </div>
        <div class="analytics-digest-body">${htmlReport}</div>
      </div>`;
  }

  function _renderIntelligenceSection() {
    if (!intelligenceData) {
      return `
        <div class="analytics-section">
          <div class="analytics-section-header">
            <span class="analytics-section-icon">${uiIcon("radar", 16)}</span>
            <span class="analytics-section-title">Trend Intelligence</span>
          </div>
          <div class="analytics-section-empty">Данные разведки ещё не собраны. Отчёт обновляется ежедневно.</div>
        </div>`;
    }

    const rawOpps = intelligenceData.top_opportunities || [];
    const rawEmerging = intelligenceData.emerging_signals || [];
    const declining = intelligenceData.declining_topics || [];
    const total = intelligenceData.total_signals_analyzed || 0;

    const { enrichedOpps, dedupedEmerging } = _deduplicateSignals(rawOpps, rawEmerging);

    // Source filter pills (show all unique sources from data)
    const allSources = new Set();
    [...enrichedOpps, ...dedupedEmerging, ...declining].forEach(item => {
      (item.sources || []).forEach(s => allSources.add(s));
    });
    const sourceFilterHtml = allSources.size > 0 ? `
      <div class="analytics-source-filters">
        <button class="analytics-source-pill ${!analyticsSourceFilter ? "active" : ""}"
                data-action="setAnalyticsSourceFilter" data-args='[null]'>
          Все
        </button>
        ${[...allSources].map(s => `
          <button class="analytics-source-pill ${analyticsSourceFilter === s ? "active" : ""}"
                  data-action="setAnalyticsSourceFilter" data-args='${JSON.stringify([s])}'>
            ${uiIcon(SOURCE_ICONS[s] || "globe", 14)} ${escapeHtml(SOURCE_DISPLAY[s] || s)}
          </button>
        `).join("")}
      </div>` : "";

    // Filter by source if active
    const filterBySource = (items) => {
      if (!analyticsSourceFilter) return items;
      return items.filter(item => (item.sources || []).includes(analyticsSourceFilter));
    };

    const filteredOpps = filterBySource(enrichedOpps);
    const filteredEmerging = filterBySource(dedupedEmerging);
    const filteredDeclining = filterBySource(declining);

    const statsRow = `<div class="trends-stats-row">
      ${uiIcon("activity", 12)}
      ${total} сигналов · ${enrichedOpps.length} возможностей · ${dedupedEmerging.length} новых · ${declining.length} спадающих
    </div>`;

    // Top opportunities
    const oppCards = filteredOpps.slice(0, 10).map((o, i) => {
      const kw = (o.keyword || "").length > 60 ? o.keyword.substring(0, 60) + "\u2026" : o.keyword;
      const score = Math.round((o.score || 0) * 100);
      const lc = o.lifecycle || "emerging";
      const cls = LIFECYCLE_CSS[lc] || "tc-early";
      const velocity = o.velocity ? o.velocity.toFixed(1) : "0.0";
      const sources = o.sources || [];

      const sourcePills = sources.length ? `
        <div class="tc-source-pills">
          ${sources.map(s => `
            <span class="tc-source-pill ${analyticsSourceFilter === s ? "tc-source-pill--active" : ""}"
                  data-action="setAnalyticsSourceFilter" data-args='${JSON.stringify([s])}'>
              ${uiIcon(SOURCE_ICONS[s] || "globe", 12)} ${escapeHtml(SOURCE_DISPLAY[s] || s)}
            </span>`).join("")}
        </div>` : "";

      const emergingBadge = o._alsoEmerging
        ? `<span class="tc-badge tc-badge-secondary">Нарастающий</span>`
        : "";

      return `
        <div class="trend-card-v2 ${cls}" data-action="openIntelligenceOpp" data-args='[${i}]'>
          <div class="tc-v2-top">
            <div class="tc-v2-title">${escapeHtml(kw)}</div>
            <span class="tc-badge ${cls}">${LIFECYCLE_LABELS[lc] || lc}</span>
            ${emergingBadge}
          </div>
          <div class="tc-v2-metrics">
            <div class="tc-metric-big">
              <span class="tc-metric-val">${velocity}\u00d7</span>
              <span class="tc-metric-label">скорость</span>
            </div>
            <div class="tc-metric-divider"></div>
            <div class="tc-metric-small">
              <span class="tc-ms-val">${sources.length} ист.</span>
              <span class="tc-ms-label">источника</span>
            </div>
            <div class="tc-metric-small" style="margin-left:auto">
              ${_sentimentHtml(o.sentiment)}
            </div>
          </div>
          ${sourcePills}
          <div class="tc-rel-bar-wrap">
            <div class="tc-rel-bar-bg"><div class="tc-rel-bar-fill tc-bar-${cls.replace("tc-", "")}" style="width:${score}%"></div></div>
            <span class="tc-rel-pct">${score}%</span>
          </div>
        </div>`;
    }).join("");

    // Emerging signals (deduplicated)
    let emergingHtml = "";
    if (filteredEmerging.length > 0) {
      const items = filteredEmerging.slice(0, 8).map(s => {
        const lc = s.lifecycle || "emerging";
        const cls = LIFECYCLE_CSS[lc] || "tc-hot";
        const velocity = s.velocity ? s.velocity.toFixed(1) : "0.0";
        const sources = s.sources || [];
        return `
          <div class="analytics-emerging-item" data-action="createFromIntelligence" data-args='${JSON.stringify([s.keyword || "", "content"])}'>
            <span class="analytics-emerging-kw">${escapeHtml((s.keyword || "").substring(0, 50))}</span>
            <span class="tc-badge ${cls}" style="font-size:10px;padding:1px 6px">${LIFECYCLE_LABELS[lc] || "Новый"}</span>
            <span class="analytics-emerging-vel">${velocity}\u00d7</span>
            ${sources.length ? `<span class="analytics-emerging-src">${sources.map(src => `<span class="tc-source-pill-sm" data-action="setAnalyticsSourceFilter" data-args='${JSON.stringify([src])}'>${escapeHtml(SOURCE_DISPLAY[src] || src)}</span>`).join("")}</span>` : ""}
          </div>`;
      }).join("");
      emergingHtml = `
        <div class="analytics-subsection">
          <div class="analytics-subsection-title">${uiIcon("zap", 14)} Нарастающие</div>
          ${items}
        </div>`;
    }

    // Declining signals
    let decliningHtml = "";
    if (filteredDeclining.length > 0) {
      const items = filteredDeclining.slice(0, 5).map(s => {
        const score = Math.round((s.score || 0) * 100);
        return `
          <div class="analytics-emerging-item analytics-declining-item" data-action="createFromIntelligence" data-args='${JSON.stringify([s.keyword || "", "content"])}'>
            <span class="analytics-emerging-kw">${escapeHtml((s.keyword || "").substring(0, 50))}</span>
            <span class="tc-badge tc-declining" style="font-size:10px;padding:1px 6px">Спадает</span>
            <span class="analytics-emerging-vel">${score}%</span>
          </div>`;
      }).join("");
      decliningHtml = `
        <div class="analytics-subsection">
          <div class="analytics-subsection-title">${uiIcon("trending-down", 14)} Спадающие</div>
          ${items}
        </div>`;
    }

    return `
      <div class="analytics-section">
        <div class="analytics-section-header">
          <span class="analytics-section-icon">${uiIcon("radar", 16)}</span>
          <span class="analytics-section-title">Trend Intelligence</span>
        </div>
        ${statsRow}
        ${sourceFilterHtml}
        <div class="analytics-subsection">
          <div class="analytics-subsection-title">${uiIcon("trending-up", 14)} Топ возможности</div>
          ${oppCards || `<p class="analytics-section-empty">Нет данных</p>`}
        </div>
        ${emergingHtml}
        ${decliningHtml}
      </div>`;
  }

  function _renderAiCardsSection() {
    if (!trendCards) {
      return `
        <div class="analytics-section">
          <div class="analytics-section-header">
            <span class="analytics-section-icon">${uiIcon("sparkles", 16)}</span>
            <span class="analytics-section-title">AI-карточки</span>
          </div>
          <div class="analytics-section-empty">
            Нет AI-карточек. Нажмите кнопку ниже для создания.
            <button class="primary-button" type="button" data-action="generateTrendCards" style="margin-top:8px">
              ${uiIcon("sparkles", 14)}<span>Сгенерировать карточки</span>
            </button>
          </div>
        </div>`;
    }

    if (trendCards.length === 0) {
      return `
        <div class="analytics-section">
          <div class="analytics-section-header">
            <span class="analytics-section-icon">${uiIcon("sparkles", 16)}</span>
            <span class="analytics-section-title">AI-карточки</span>
          </div>
          <div class="analytics-section-empty">
            Нет AI-карточек.
            <button class="primary-button" type="button" data-action="generateTrendCards" style="margin-top:8px">
              ${uiIcon("sparkles", 14)}<span>Сгенерировать карточки</span>
            </button>
          </div>
        </div>`;
    }

    const cards = trendCards.slice(0, 8).map(c => {
      const lc = c.lifecycle || "emerging";
      const cls = _lifecycleClass(lc);
      const pct = Math.round((c.strength || 0) * 100);
      const vel = (c.velocity || 0).toFixed(1);
      const srcCount = (c.source_signals || []).length || "\u2014";
      return `
      <div class="trend-card-v2 ${cls} interactive-card" data-card-id="${escapeHtml(c.card_id)}">
        <div class="tc-v2-top">
          <div class="tc-v2-title">${escapeHtml(c.title || c.keyword)}</div>
          <span class="tc-badge ${cls}">${STATUS_LABELS[lc] || lc}</span>
        </div>
        <div class="tc-v2-metrics">
          <div class="tc-metric-big">
            <span class="tc-metric-val">${vel}\u00d7</span>
            <span class="tc-metric-label">скорость</span>
          </div>
          <div class="tc-metric-divider"></div>
          <div class="tc-metric-small">
            <span class="tc-ms-val">${srcCount} ист.</span>
            <span class="tc-ms-label">источника</span>
          </div>
          <div class="tc-metric-small" style="margin-left:auto;">
            ${_sentimentHtml(c.sentiment)}
          </div>
        </div>
        <div class="tc-rel-bar-wrap">
          <div class="tc-rel-bar-bg"><div class="tc-rel-bar-fill tc-bar-${lc === "peaking" ? "hot" : lc === "evergreen" ? "stable" : lc === "emerging" ? "early" : lc}" style="width:${pct}%;"></div></div>
          <span class="tc-rel-pct">${pct}%</span>
        </div>
      </div>`;
    }).join("");

    return `
      <div class="analytics-section">
        <div class="analytics-section-header">
          <span class="analytics-section-icon">${uiIcon("sparkles", 16)}</span>
          <span class="analytics-section-title">AI-карточки</span>
        </div>
        ${cards}
        <button class="secondary-button" type="button" data-action="generateTrendCards" style="margin-top:0.5rem">
          ${uiIcon("refresh-cw", 14)}<span>Обновить карточки</span>
        </button>
      </div>`;
  }

  function renderAnalyticsDetail() {
    if (!intelligenceData && !digestData && !trendCards) {
      return `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Аналитика",
        title: "Данные собираются ежедневно",
        body: "Отчёт включает анализ из 10+ источников: Google Trends, YouTube, TikTok, Reddit, Telegram и др.",
        actionLabel: "Обновить",
        action: "refreshTrends",
      })}</div>`;
    }

    const sections = [];

    // Sources breakdown from intelligence
    if (intelligenceData) {
      const breakdown = intelligenceData.sources_breakdown || {};
      if (Object.keys(breakdown).length > 0) {
        const rows = Object.entries(breakdown).map(([src, count]) => `
          <div class="analytics-breakdown-row">
            <span class="analytics-breakdown-src">${uiIcon(SOURCE_ICONS[src] || "globe", 14)} ${escapeHtml(SOURCE_DISPLAY[src] || src)}</span>
            <span class="analytics-breakdown-count">${count} сигналов</span>
          </div>`).join("");
        sections.push(`
          <div class="detail-section">
            <div class="detail-section-title">${uiIcon("bar-chart-3", 16)} Источники сигналов</div>
            ${rows}
          </div>`);
      }

      // Emerging signals detail
      const emerging = intelligenceData.emerging_signals || [];
      if (emerging.length > 0) {
        const items = emerging.map(s => {
          const lc = s.lifecycle || "emerging";
          const cls = LIFECYCLE_CSS[lc] || "tc-hot";
          const velocity = s.velocity ? s.velocity.toFixed(1) : "0.0";
          return `
            <div class="trend-card-v2 ${cls}" data-action="createFromIntelligence" data-args='${JSON.stringify([s.keyword || "", "content"])}'>
              <div class="tc-v2-top">
                <div class="tc-v2-title">${escapeHtml((s.keyword || "").substring(0, 60))}</div>
                <span class="tc-badge ${cls}">${LIFECYCLE_LABELS[lc] || "Новый"}</span>
              </div>
              ${s.content_angle ? `<div class="tc-v2-angle">${escapeHtml(s.content_angle.substring(0, 120))}</div>` : ""}
              <div class="tc-v2-metrics">
                <div class="tc-metric-big">
                  <span class="tc-metric-val">${velocity}\u00d7</span>
                  <span class="tc-metric-label">скорость</span>
                </div>
              </div>
            </div>`;
        }).join("");
        sections.push(`<div class="detail-section"><div class="detail-section-title">${uiIcon("zap", 16)} Новые сигналы</div>${items}</div>`);
      }

      // Declining
      const declining = intelligenceData.declining_topics || [];
      if (declining.length > 0) {
        const items = declining.map(s => {
          const score = Math.round((s.score || 0) * 100);
          return `
            <div class="trend-card-v2 tc-declining" data-action="createFromIntelligence" data-args='${JSON.stringify([s.keyword || "", "content"])}'>
              <div class="tc-v2-top">
                <div class="tc-v2-title">${escapeHtml((s.keyword || "").substring(0, 60))}</div>
                <span class="tc-badge tc-declining">Спадает</span>
              </div>
              ${s.content_angle ? `<div class="tc-v2-angle">${escapeHtml(s.content_angle.substring(0, 120))}</div>` : ""}
              <div class="tc-rel-bar-wrap">
                <div class="tc-rel-bar-bg"><div class="tc-rel-bar-fill tc-bar-declining" style="width:${score}%"></div></div>
                <span class="tc-rel-pct">${score}%</span>
              </div>
            </div>`;
        }).join("");
        sections.push(`<div class="detail-section"><div class="detail-section-title">${uiIcon("trending-down", 16)} Спадающие темы</div>${items}</div>`);
      }
    }

    if (sections.length === 0) {
      return `<div class="detail-empty"><p>Выберите тренд слева для деталей</p></div>`;
    }

    return `<div class="trends-detail-content">${sections.join("")}</div>`;
  }

  // ── Intelligence (trend report from aggregator) ──────────────────

  const LIFECYCLE_CSS = {
    emerging: "tc-hot", growing: "tc-growing", peaking: "tc-hot",
    declining: "tc-declining", evergreen: "tc-stable",
  };
  const LIFECYCLE_LABELS = {
    emerging: "Набирает", growing: "Растёт", peaking: "На пике",
    declining: "Спадает", evergreen: "Стабильный",
  };

  function _sentimentHtml(sentiment) {
    const s = (sentiment || "neutral").toLowerCase();
    if (s === "positive") return `<span class="tc-ms-sentiment tc-ms-positive">↗ позитивный</span>`;
    if (s === "negative") return `<span class="tc-ms-sentiment tc-ms-negative">↘ негативный</span>`;
    return `<span class="tc-ms-sentiment tc-ms-neutral">— нейтральный</span>`;
  }

  function renderIntelligenceSummaryList() {
    if (!intelligenceData) {
      return `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Разведка",
        title: "Загрузка данных",
        body: "Отчёт собирается ежедневно из Google Trends, YouTube, TikTok, Reddit, Telegram и других источников.",
        actionLabel: "Обновить",
        action: "refreshTrends",
      })}</div>`;
    }

    const opps = intelligenceData.top_opportunities || [];
    const emerging = intelligenceData.emerging_signals || [];
    const declining = intelligenceData.declining_topics || [];
    const total = intelligenceData.total_signals_analyzed || 0;

    const oppCards = opps.slice(0, 10).map((o, i) => {
      const kw = (o.keyword || "").length > 60 ? o.keyword.substring(0, 60) + "…" : o.keyword;
      const score = Math.round((o.score || 0) * 100);
      const lc = o.lifecycle || "emerging";
      const cls = LIFECYCLE_CSS[lc] || "tc-early";
      const velocity = o.velocity ? o.velocity.toFixed(1) : "0.0";
      const srcCount = o.sources ? o.sources.length : 0;

      return `
        <div class="trend-card-v2 ${cls}" data-action="openIntelligenceOpp" data-args='[${i}]'>
          <div class="tc-v2-top">
            <div class="tc-v2-title">${escapeHtml(kw)}</div>
            <span class="tc-badge ${cls}">${LIFECYCLE_LABELS[lc] || lc}</span>
          </div>
          <div class="tc-v2-metrics">
            <div class="tc-metric-big">
              <span class="tc-metric-val">${velocity}×</span>
              <span class="tc-metric-label">скорость</span>
            </div>
            <div class="tc-metric-divider"></div>
            <div class="tc-metric-small">
              <span class="tc-ms-val">${srcCount} ист.</span>
              <span class="tc-ms-label">источника</span>
            </div>
            <div class="tc-metric-small" style="margin-left:auto">
              ${_sentimentHtml(o.sentiment)}
            </div>
          </div>
          <div class="tc-rel-bar-wrap">
            <div class="tc-rel-bar-bg"><div class="tc-rel-bar-fill tc-bar-${cls.replace("tc-", "")}" style="width:${score}%"></div></div>
            <span class="tc-rel-pct">${score}%</span>
          </div>
        </div>`;
    }).join("");

    const statsRow = `<div class="trends-stats-row">
      ${uiIcon("activity", 12)}
      ${total} сигналов · ${opps.length} возможностей · ${emerging.length} новых · ${declining.length} спадающих
    </div>`;

    return `${statsRow}<div class="draft-list-content">${oppCards || `<p style="padding:1rem;opacity:0.6">Нет данных — запустите сбор трендов</p>`}</div>`;
  }

  function renderIntelligenceDetail() {
    if (!intelligenceData) {
      return `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Разведка",
        title: "Данные собираются ежедневно",
        body: "Отчёт включает анализ из 10+ источников: Google Trends, YouTube, TikTok, Reddit, Telegram и др.",
        actionLabel: "Обновить",
        action: "refreshTrends",
      })}</div>`;
    }

    const sections = [];
    const emerging = intelligenceData.emerging_signals || [];
    const declining = intelligenceData.declining_topics || [];

    if (emerging.length > 0) {
      const items = emerging.map((s, i) => {
        const score = Math.round((s.score || 0) * 100);
        const velocity = s.velocity ? s.velocity.toFixed(1) : "0.0";
        const srcCount = s.sources ? s.sources.length : 0;
        const lc = s.lifecycle || "emerging";
        const cls = LIFECYCLE_CSS[lc] || "tc-hot";
        return `
        <div class="trend-card-v2 ${cls}" data-action="createFromIntelligence" data-args='${JSON.stringify([s.keyword || "", "content"])}'>
          <div class="tc-v2-top">
            <div class="tc-v2-title">${escapeHtml((s.keyword || "").substring(0, 60))}</div>
            <span class="tc-badge ${cls}">${LIFECYCLE_LABELS[lc] || "Новый"}</span>
          </div>
          ${s.content_angle ? `<div class="tc-v2-angle">${escapeHtml(s.content_angle.substring(0, 120))}</div>` : ""}
          <div class="tc-v2-metrics">
            <div class="tc-metric-big">
              <span class="tc-metric-val">${velocity}×</span>
              <span class="tc-metric-label">скорость</span>
            </div>
            <div class="tc-metric-divider"></div>
            <div class="tc-metric-small">
              <span class="tc-ms-val">${srcCount} ист.</span>
              <span class="tc-ms-label">источника</span>
            </div>
            <div class="tc-metric-small" style="margin-left:auto">
              ${_sentimentHtml(s.sentiment)}
            </div>
          </div>
          <div class="tc-rel-bar-wrap">
            <div class="tc-rel-bar-bg"><div class="tc-rel-bar-fill tc-bar-${cls.replace("tc-", "")}" style="width:${score}%"></div></div>
            <span class="tc-rel-pct">${score}%</span>
          </div>
        </div>`;
      }).join("");
      sections.push(`<div class="detail-section"><div class="detail-section-title">${uiIcon("zap", 16)} Новые сигналы</div>${items}</div>`);
    }

    if (declining.length > 0) {
      const items = declining.map(s => {
        const score = Math.round((s.score || 0) * 100);
        const velocity = s.velocity ? s.velocity.toFixed(1) : "0.0";
        return `
        <div class="trend-card-v2 tc-declining" data-action="createFromIntelligence" data-args='${JSON.stringify([s.keyword || "", "content"])}'>
          <div class="tc-v2-top">
            <div class="tc-v2-title">${escapeHtml((s.keyword || "").substring(0, 60))}</div>
            <span class="tc-badge tc-declining">Спадает</span>
          </div>
          ${s.content_angle ? `<div class="tc-v2-angle">${escapeHtml(s.content_angle.substring(0, 120))}</div>` : ""}
          <div class="tc-rel-bar-wrap">
            <div class="tc-rel-bar-bg"><div class="tc-rel-bar-fill tc-bar-declining" style="width:${score}%"></div></div>
            <span class="tc-rel-pct">${score}%</span>
          </div>
        </div>`;
      }).join("");
      sections.push(`<div class="detail-section"><div class="detail-section-title">${uiIcon("trending-down", 16)} Спадающие темы</div>${items}</div>`);
    }

    if (sections.length === 0) {
      return `<div class="detail-empty"><p>Выберите тренд слева для деталей</p></div>`;
    }

    return `<div class="trends-detail-content">${sections.join("")}</div>`;
  }

  function openIntelligenceOpp(idx) {
    if (!intelligenceData || !intelligenceData.top_opportunities) return;
    const opp = intelligenceData.top_opportunities[idx];
    if (!opp) return;

    const FORMAT_LABELS = { "in-depth post": "Подробный пост", "carousel": "Карусель", "reels": "Рилс", "live session": "Прямой эфир", "thread": "Тред", "threads_series": "Серия Threads", "expert commentary": "Экспертный комментарий", "tutorial": "Туториал", "content": "Пост" };
    const lc = opp.lifecycle || "emerging";
    const cls = LIFECYCLE_CSS[lc] || "tc-early";
    const velocity = (opp.velocity || 0).toFixed(1);
    const score = Math.round((opp.score || 0) * 100);
    const sentiment = opp.sentiment || "neutral";
    const hashtags = (opp.hashtags || []).map(t => `#${escapeHtml(t)}`).join(" ");
    const formats = opp.suggested_formats || [];
    const sources = opp.sources || [];

    const formatPills = formats.length
      ? formats.map(f => `<span class="ds-format-pill">${escapeHtml(FORMAT_LABELS[f] || f)}</span>`).join("")
      : "";

    const sourceChips = sources.length
      ? sources.map(s => `<span class="ds-source-chip">${uiIcon(SOURCE_ICONS[s] || "globe", 14)} ${escapeHtml(SOURCE_DISPLAY[s] || s)}</span>`).join("")
      : "";

    elements.draftDetail.innerHTML = `
      ${renderBackButton("К аналитике", () => { void loadTrends(); })}
      <div class="trends-detail-v2">
        <div class="detail-hero">
          <div class="detail-status-row">
            <span class="tc-badge ${cls}">${LIFECYCLE_LABELS[lc] || lc}</span>
            ${hashtags ? `<span class="detail-hashtags">${hashtags}</span>` : ""}
          </div>
          <h2 class="detail-hero-title">${escapeHtml(opp.keyword || "Тренд")}</h2>
          <div class="detail-chips">
            <div class="detail-chip detail-chip-speed">
              ${uiIcon("trending-up", 12)} ${velocity}× скорость
            </div>
            <div class="detail-chip detail-chip-rel">
              ${uiIcon("check-circle", 12)} ${score}% релевантность
            </div>
            <div class="detail-chip detail-chip-sentiment">
              ${uiIcon(sentiment === "positive" ? "smile" : sentiment === "negative" ? "frown" : "meh", 12)} ${sentiment}
            </div>
          </div>
        </div>

        ${opp.content_angle ? `
        <div class="ds-section">
          <div class="ds-label">О тренде</div>
          <div class="ds-text">${escapeHtml(opp.content_angle)}</div>
        </div>` : ""}

        ${formatPills ? `
        <div class="ds-section">
          <div class="ds-label">Рекомендуемые форматы</div>
          <div class="ds-formats-pills">${formatPills}</div>
        </div>` : ""}

        ${sourceChips ? `
        <div class="ds-section">
          <div class="ds-label">Источники</div>
          <div class="ds-sources-row">${sourceChips}</div>
        </div>` : ""}

        <button class="trend-cta-btn" type="button" data-action="createFromIntelligence" data-args='${JSON.stringify([opp.keyword, formats[0] || "content"])}'>
          ${uiIcon("plus", 16)} Создать контент по тренду
        </button>
      </div>`;
    enterDetailView();
    syncMobileNavigation();
  }

  async function createFromIntelligence(keyword, format) {
    const formatMap = { "carousel": "carousel", "reels": "reels", "threads_series": "threads_series" };
    const endpoint = format === "carousel" ? "/api/generate/carousel"
      : format === "reels" ? "/api/generate/reels"
      : format === "threads_series" ? "/api/generate/threads-series"
      : "/api/generate/content";
    const body = { topic: keyword };
    if (endpoint === "/api/generate/content") {
      body.format_key = "instagram";
      body.goal_key = "trust";
    }
    try {
      const draft = await fetchJson(endpoint, {
        method: "POST",
        timeout: 45000,
        body: JSON.stringify(body),
      });
      showUiNotice("Черновик создан из тренда", "success");
      if (draft?.draft_id && deps.openDraft) {
        await deps.openDraft(draft.draft_id);
      }
    } catch (e) {
      if (e?.message === "paywall") return;
      showUiNotice("Ошибка создания черновика", "error");
    }
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
        } catch (_e) { /* optional */ }
      })();
      return `<div class="trends-cards-container"><div class="suggest-topics-loading"><span class="button-spinner"></span> Загрузка карточек...</div></div>`;
    }
    return `<div class="trends-cards-container">${_renderCardsInner()}</div>`;
  }

  const STATUS_LABELS = {
    growing:   "Набирает",
    emerging:  "Ранний",
    hot:       "Горячий",
    peaking:   "Горячий",
    stable:    "Стабильный",
    declining: "Спадает",
    evergreen: "Стабильный",
  };

  function _lifecycleClass(lc) {
    if (lc === "peaking") return "tc-hot";
    if (lc === "evergreen") return "tc-stable";
    if (lc === "emerging") return "tc-early";
    return "tc-" + (lc || "early");
  }

  function _renderCardsInner() {
    if (!trendCards || !trendCards.length) {
      return `<div class="detail-empty"><p>Нет AI-карточек. Нажмите «Сгенерировать» для создания.</p>
        <button class="primary-button" type="button" data-action="generateTrendCards">${uiIcon("sparkles", 14)}<span>Сгенерировать карточки</span></button></div>`;
    }

    const total = trendCards.length;
    const opportunities = trendCards.filter(c => (c.strength || 0) >= 0.5).length;
    const growing = trendCards.filter(c => c.lifecycle === "growing" || c.lifecycle === "emerging").length;

    const statsRow = `<div class="trends-stats-row">
      ${uiIcon("chart-line", 12)}
      ${total} сигналов · ${opportunities} возможностей · ${growing} новых
    </div>`;

    const cards = trendCards.map(c => {
      const lc = c.lifecycle || "emerging";
      const cls = _lifecycleClass(lc);
      const pct = Math.round((c.strength || 0) * 100);
      const vel = (c.velocity || 0).toFixed(1);
      const srcCount = (c.source_signals || []).length || "—";
      return `
      <div class="trend-card-v2 ${cls} interactive-card" data-card-id="${escapeHtml(c.card_id)}">
        <div class="tc-v2-top">
          <div class="tc-v2-title">${escapeHtml(c.title || c.keyword)}</div>
          <span class="tc-badge ${cls}">${STATUS_LABELS[lc] || lc}</span>
        </div>
        <div class="tc-v2-metrics">
          <div class="tc-metric-big">
            <span class="tc-metric-val">${vel}×</span>
            <span class="tc-metric-label">скорость</span>
          </div>
          <div class="tc-metric-divider"></div>
          <div class="tc-metric-small">
            <span class="tc-ms-val">${srcCount} ист.</span>
            <span class="tc-ms-label">источника</span>
          </div>
          <div class="tc-metric-small" style="margin-left:auto;">
            ${_sentimentHtml(c.sentiment)}
          </div>
        </div>
        <div class="tc-rel-bar-wrap">
          <div class="tc-rel-bar-bg"><div class="tc-rel-bar-fill tc-bar-${lc === "peaking" ? "hot" : lc === "evergreen" ? "stable" : lc === "emerging" ? "early" : lc}" style="width:${pct}%;"></div></div>
          <span class="tc-rel-pct">${pct}%</span>
        </div>
      </div>`;
    }).join("");

    return statsRow + cards + `<button class="secondary-button" type="button" data-action="generateTrendCards" style="margin-top:0.5rem">${uiIcon("refresh-cw", 14)}<span>Обновить карточки</span></button>`;
  }

  async function generateTrendCards() {
    try {
      await fetchJson("/api/trends/cards/generate", { method: "POST", timeout: 60000 });
      showUiNotice("Генерация карточек запущена", "info");
      trendCards = null;
      renderTrendsListPanel();
    } catch (e) {
      if (e?.message === "paywall") return; // paywall already shown by fetchJson
      showUiNotice(`Ошибка генерации: ${e?.message || "неизвестная ошибка"}`, "error");
    }
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
    openIntelligenceOpp,
    createFromIntelligence,
    toggleHealthDetails,
    setAnalyticsSourceFilter,
  };
}
