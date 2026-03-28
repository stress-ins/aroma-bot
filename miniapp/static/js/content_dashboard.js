export function createContentDashboardModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    fetchJson,
    renderGuidedState,
  } = deps;

  if (!state.dashboardData) state.dashboardData = null;
  if (!state.dashboardRecommendations) state.dashboardRecommendations = null;
  if (!state.dashboardPeriod) state.dashboardPeriod = 30;
  if (!state.dashboardLoading) state.dashboardLoading = false;

  const KIND_LABELS = {
    carousel: "Карусели",
    reels: "Рилсы",
    text: "Тексты",
    stories: "Сторис",
    image: "Фото",
    threads_series: "Серии",
    content: "Контент",
  };

  const KIND_ICONS = {
    carousel: "layers",
    reels: "clapperboard",
    text: "type",
    stories: "smartphone",
    image: "image",
    threads_series: "list",
    content: "file-text",
  };

  async function loadDashboard() {
    state.dashboardLoading = true;
    renderDashboard();
    try {
      const [dash, recs] = await Promise.all([
        fetchJson(`/api/analytics/dashboard?days=${state.dashboardPeriod}`),
        fetchJson("/api/analytics/recommendations"),
      ]);
      state.dashboardData = dash;
      state.dashboardRecommendations = recs;
    } catch (err) {
      state.dashboardData = null;
      state.dashboardRecommendations = null;
    }
    state.dashboardLoading = false;
    renderDashboard();
  }

  function renderDashboard() {
    const container = elements.draftList;
    if (!container) return;

    elements.listTitle.textContent = "Аналитика";
    elements.draftCount.textContent = "";

    if (state.dashboardLoading) {
      container.innerHTML = `
        <div class="detail-loader-card panel-loader-card" aria-live="polite">
          <div class="brand-loader" aria-hidden="true">
            <span class="brand-loader-ring"></span>
            <span class="brand-loader-letter">\u0410</span>
          </div>
          <div class="detail-loader-copy">
            <strong>Загружаю аналитику</strong>
            <span>Собираю данные о публикациях.</span>
          </div>
        </div>`;
      return;
    }

    const data = state.dashboardData;
    const recs = state.dashboardRecommendations;

    if (!data) {
      container.innerHTML = renderGuidedState({
        eyebrow: "Аналитика",
        title: "Нет данных",
        body: "Опубликуйте контент и оцените его в Архиве, чтобы увидеть статистику.",
      });
      return;
    }

    const sections = [];

    // Period selector
    sections.push(renderPeriodSelector());

    // Summary cards
    sections.push(renderSummaryCards(data, recs));

    // Format performance bar chart
    if (data.format_performance && data.format_performance.length > 0) {
      sections.push(renderFormatChart(data.format_performance));
    }

    // Pillar performance
    if (data.pillar_performance && data.pillar_performance.length > 0) {
      sections.push(renderPillarList(data.pillar_performance));
    }

    // Best publish time
    if (data.time_performance && (data.time_performance.best_day || data.time_performance.best_hour)) {
      sections.push(renderTimePerformance(data.time_performance));
    }

    // Top posts
    if (data.top_posts && data.top_posts.length > 0) {
      sections.push(renderTopPosts(data.top_posts));
    }

    // Recommendations
    if (recs && recs.suggestions && recs.suggestions.length > 0) {
      sections.push(renderRecommendations(recs));
    }

    container.innerHTML = `<div class="dashboard-container">${sections.join("")}</div>`;

    // Attach period selector listeners
    container.querySelectorAll(".dashboard-period-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const days = parseInt(btn.dataset.days, 10);
        if (days && days !== state.dashboardPeriod) {
          state.dashboardPeriod = days;
          loadDashboard();
        }
      });
    });

    // Phosphor icons are CSS-based, no init needed
  }

  function renderPeriodSelector() {
    const periods = [
      { days: 7, label: "7 дней" },
      { days: 30, label: "30 дней" },
      { days: 90, label: "90 дней" },
    ];
    return `
      <div class="dashboard-period-selector">
        ${periods.map(p => `
          <button class="dashboard-period-btn${state.dashboardPeriod === p.days ? " active" : ""}"
                  data-days="${p.days}" type="button">${escapeHtml(p.label)}</button>
        `).join("")}
      </div>`;
  }

  function renderSummaryCards(data, recs) {
    const totalPub = data.total_published || 0;

    // Calculate average engagement across all formats
    let avgEng = 0;
    if (data.format_performance && data.format_performance.length > 0) {
      const total = data.format_performance.reduce((s, f) => s + f.avg_score * f.count, 0);
      const count = data.format_performance.reduce((s, f) => s + f.count, 0);
      avgEng = count > 0 ? (total / count).toFixed(1) : 0;
    }

    const bestFmt = recs?.best_format;
    const bestFmtLabel = bestFmt ? (KIND_LABELS[bestFmt.kind] || bestFmt.kind) : "---";

    return `
      <div class="dashboard-summary-cards">
        <div class="dashboard-summary-card">
          <div class="dashboard-summary-icon">${uiIcon("send")}</div>
          <div class="dashboard-summary-value">${totalPub}</div>
          <div class="dashboard-summary-label">Опубликовано</div>
        </div>
        <div class="dashboard-summary-card">
          <div class="dashboard-summary-icon">${uiIcon("star")}</div>
          <div class="dashboard-summary-value">${avgEng}</div>
          <div class="dashboard-summary-label">Средний балл</div>
        </div>
        <div class="dashboard-summary-card">
          <div class="dashboard-summary-icon">${uiIcon("trophy")}</div>
          <div class="dashboard-summary-value">${escapeHtml(bestFmtLabel)}</div>
          <div class="dashboard-summary-label">Лучший формат</div>
        </div>
      </div>`;
  }

  function renderFormatChart(formats) {
    const maxScore = Math.max(...formats.map(f => f.avg_score), 1);

    const bars = formats.map(f => {
      const pct = Math.round((f.avg_score / maxScore) * 100);
      const label = KIND_LABELS[f.kind] || f.kind;
      const iconName = KIND_ICONS[f.kind] || "file-text";
      return `
        <div class="dashboard-bar-row">
          <div class="dashboard-bar-label">
            <span class="dashboard-bar-icon">${uiIcon(iconName)}</span>
            <span>${escapeHtml(label)}</span>
            <span class="dashboard-bar-count">${f.count} шт</span>
          </div>
          <div class="dashboard-bar-track">
            <div class="dashboard-bar-fill" style="width:${pct}%"></div>
          </div>
          <div class="dashboard-bar-value">${f.avg_score.toFixed(1)}</div>
        </div>`;
    }).join("");

    return `
      <div class="dashboard-section">
        <h3 class="dashboard-section-title">${uiIcon("bar-chart-3")} Форматы</h3>
        <div class="dashboard-bar-chart">${bars}</div>
      </div>`;
  }

  function renderPillarList(pillars) {
    const sorted = [...pillars].sort((a, b) => b.avg_score - a.avg_score);
    const items = sorted.map((p, i) => {
      const medal = i === 0 ? `<span class="dashboard-medal">${uiIcon("award")}</span>` : "";
      return `
        <div class="dashboard-pillar-item">
          <div class="dashboard-pillar-name">${medal} ${escapeHtml(p.pillar || "Без столпа")}</div>
          <div class="dashboard-pillar-stats">
            <span class="dashboard-pillar-score">${p.avg_score.toFixed(1)}</span>
            <span class="dashboard-pillar-count">${p.count} публ.</span>
          </div>
        </div>`;
    }).join("");

    return `
      <div class="dashboard-section">
        <h3 class="dashboard-section-title">${uiIcon("compass")} Столпы контента</h3>
        <div class="dashboard-pillar-list">${items}</div>
      </div>`;
  }

  function renderTimePerformance(time) {
    const parts = [];
    if (time.best_day) {
      parts.push(`
        <div class="dashboard-time-card">
          <div class="dashboard-time-icon">${uiIcon("calendar")}</div>
          <div class="dashboard-time-info">
            <div class="dashboard-time-value">${escapeHtml(time.best_day.day)}</div>
            <div class="dashboard-time-label">Лучший день</div>
            <div class="dashboard-time-detail">${time.best_day.avg_engagement.toFixed(1)} средний балл</div>
          </div>
        </div>`);
    }
    if (time.best_hour) {
      parts.push(`
        <div class="dashboard-time-card">
          <div class="dashboard-time-icon">${uiIcon("clock")}</div>
          <div class="dashboard-time-info">
            <div class="dashboard-time-value">${escapeHtml(time.best_hour.label)}</div>
            <div class="dashboard-time-label">Лучшее время</div>
            <div class="dashboard-time-detail">${time.best_hour.avg_engagement.toFixed(1)} средний балл</div>
          </div>
        </div>`);
    }

    return `
      <div class="dashboard-section">
        <h3 class="dashboard-section-title">${uiIcon("clock")} Лучшее время публикации</h3>
        <div class="dashboard-time-cards">${parts.join("")}</div>
      </div>`;
  }

  function renderTopPosts(posts) {
    const items = posts.map((p, i) => {
      const rank = i + 1;
      return `
        <div class="dashboard-top-item">
          <span class="dashboard-top-rank">${rank}</span>
          <div class="dashboard-top-info">
            <div class="dashboard-top-topic">${escapeHtml(p.topic || "Без темы")}</div>
            <div class="dashboard-top-meta">
              ${escapeHtml(KIND_LABELS[p.kind] || p.kind)} · ${escapeHtml(p.platform || "")}
            </div>
          </div>
          <div class="dashboard-top-score">${p.avg_score.toFixed(1)}</div>
        </div>`;
    }).join("");

    return `
      <div class="dashboard-section">
        <h3 class="dashboard-section-title">${uiIcon("trending-up")} Топ публикации</h3>
        <div class="dashboard-top-list">${items}</div>
      </div>`;
  }

  function renderRecommendations(recs) {
    const items = recs.suggestions.map(s => `
      <div class="dashboard-rec-item">
        <span class="dashboard-rec-icon">${uiIcon("lightbulb")}</span>
        <span class="dashboard-rec-text">${escapeHtml(s)}</span>
      </div>`).join("");

    return `
      <div class="dashboard-section dashboard-section--recs">
        <h3 class="dashboard-section-title">${uiIcon("sparkles")} Рекомендации</h3>
        <div class="dashboard-rec-list">${items}</div>
      </div>`;
  }

  return { loadDashboard, renderDashboard };
}
