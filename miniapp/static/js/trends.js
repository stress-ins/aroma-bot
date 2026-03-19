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
    showUiNotice,
    setEmptyState,
    syncMobileNavigation,
    enterDetailView,
  } = deps;

  function _extractUsername(input) {
    const trimmed = input.trim();
    const urlPatterns = [
      /(?:instagram\.com|instagr\.am)\/([a-zA-Z0-9_.]+)/,
      /threads\.net\/@?([a-zA-Z0-9_.]+)/,
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

  const WEEKDAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

  // ── Loaders ──────────────────────────────────────────────────────────

  async function loadTrends() {
    elements.draftList.innerHTML = renderTrendsListPanel();
    elements.draftDetail.innerHTML = renderDetailLoader();
    syncMobileNavigation();

    try {
      const [trendsResult, accountsResult] = await Promise.allSettled([
        trendsPlatform === "compare"
          ? fetchJson(`/api/trends/compare?period=${trendsPeriod}`)
          : fetchJson(`/api/trends/${trendsPlatform}?period=${trendsPeriod}`),
        fetchJson("/api/social/monitored-accounts"),
      ]);

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
    } catch (err) {
      trendsData = null;
      trendsCompare = null;
    }

    elements.draftList.innerHTML = renderTrendsListPanel();
    elements.draftDetail.innerHTML = renderTrendsDetail();
    syncMobileNavigation();
    if (window.lucide) lucide.createIcons();
  }

  // ── Content sub-switcher ────────────────────────────────────────────

  function renderContentSwitcher(active) {
    return `<div class="content-sub-switcher">
      <button class="tab-button${active === "drafts" ? " active" : ""}" data-action="setContentSubMode" data-args='["drafts"]'>Черновики</button>
      <button class="tab-button${active === "trends" ? " active" : ""}" data-action="setContentSubMode" data-args='["trends"]'>Тренды</button>
    </div>`;
  }

  // ── List Panel (platform selector + filters) ─────────────────────────

  function renderTrendsListPanel() {
    const platforms = [
      { id: "instagram", label: "Instagram", icon: "instagram" },
      { id: "threads", label: "Threads", icon: "at-sign" },
      { id: "compare", label: "Сравнение", icon: "columns-2" },
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
    if (trendsPlatform === "compare" && trendsCompare) {
      summary = renderCompareSummaryList();
    } else if (trendsData) {
      summary = renderPlatformSummaryList();
    }

    return `
      ${renderContentSwitcher("trends")}
      <div class="trends-controls">
        <div class="trends-platform-tabs">${platformTabs}</div>
        <div class="trends-period-row">
          <div class="trends-period-btns">${periodBtns}</div>
          ${refreshBtn}
        </div>
      </div>
      ${summary}
      ${renderMonitoredAccountsSection()}
    `;
  }

  function renderPlatformSummaryList() {
    if (!trendsData) return "";
    const topPosts = trendsData.top_posts || [];
    if (topPosts.length === 0) {
      return renderGuidedState(
        "bar-chart-3",
        "Нет данных",
        "Добавьте конкурентов в настройках бренда и дождитесь сбора данных.",
        `<button class="btn btn-secondary" data-action="openSettingsSection" data-args='["accounts"]'>
          ${uiIcon("plus", 16)} Добавить аккаунты
        </button>`
      );
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

  // ── Detail Panel ────────────────────────────────────────────────────

  function renderTrendsDetail() {
    if (trendsPlatform === "compare") return renderCompareDetail();
    if (!trendsData) return renderGuidedState("bar-chart-3", "Загрузка", "Выберите платформу и период.");

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
      return renderGuidedState("bar-chart-3", "Нет данных", "Данные появятся после первого сбора.");
    }

    return `<div class="trends-detail-content">${sections.join("")}</div>`;
  }

  function renderCompareDetail() {
    if (!trendsCompare) return renderGuidedState("columns-2", "Загрузка", "Сравнение платформ.");
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
  };
}
