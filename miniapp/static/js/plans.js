export function createPlansModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    actionLabel,
    tagMarkup,
    interactiveCardAttrs,
    contentKindIcon,
    kindLabel,
    sourceLabel,
    sourceTone,
    formatPlanDate,
    renderBackButton,
    renderMarkdown,
    renderGuidedState,
    setEmptyState,
    fetchJson,
    withButtonFeedback,
    upsertDraftSummary,
    draftSummaryFromDraft,
    setTab,
    enterDetailView,
    syncMobileNavigation,
    loadPlans: reloadPlans,
    loadDrafts,
    loadReels,
    openDraft,
    openReels,
    openPendingReelsCreation,
    finalizePendingReelsCreation,
    recoverPendingReelsCreation,
    scheduleDraftRefresh,
  } = deps;

  // ── State initialisation ───────────────────────────────────────────────────
  if (!state.plansFeed) state.plansFeed = [];
  if (!state.plansFeedDates) state.plansFeedDates = [];
  if (!state.plansFilter) state.plansFilter = { status: "all", platform: "all", date: null };

  // ── Helpers ────────────────────────────────────────────────────────────────

  function formatTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  function formatDateTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return isoStr;
    return d.toLocaleDateString("ru-RU") + " " + d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  function toDateKey(isoStr) {
    if (!isoStr) return "";
    return isoStr.substring(0, 10);
  }

  function formatDayLabel(dateKey) {
    if (!dateKey) return "";
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const d = new Date(dateKey + "T00:00:00");
    const diff = Math.round((d - today) / 86400000);
    const months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
    const datePart = `${d.getDate()} ${months[d.getMonth()]}`;
    if (diff === 0) return `Сегодня · ${datePart}`;
    if (diff === 1) return `Завтра · ${datePart}`;
    if (diff === -1) return `Вчера · ${datePart}`;
    const days = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
    return `${days[d.getDay()]} · ${datePart}`;
  }

  function groupByDate(items) {
    const map = new Map();
    for (const item of items) {
      const key = toDateKey(item.scheduled_at);
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    }
    return Array.from(map.entries()).map(([date, its]) => ({ date, items: its }));
  }

  function platformIcon(name) {
    const n = String(name || "").toLowerCase();
    const knownIcons = ["threads", "instagram", "tiktok", "youtube", "telegram"];
    if (knownIcons.includes(n)) return uiIcon(n);
    return `<span style="font-size:11px">${escapeHtml(name)}</span>`;
  }

  function slotLabel(slot) {
    const map = { morning: "Утро", day: "День", evening: "Вечер" };
    return map[slot] || slot || "";
  }

  function statusLabel(s) {
    const map = { scheduled: "Запланировано", published: "Опубликовано", error: "Ошибка", cancelled: "Отменено" };
    return map[s] || s;
  }

  function statusTone(s) {
    const map = { scheduled: "warn", published: "good", error: "bad", cancelled: "neutral" };
    return map[s] || "neutral";
  }

  function getSummary(draft, slot) {
    const p = draft.payload || {};
    if (draft.kind === "threads_series") return p.series_summary || draft.topic || "";
    if (p.hook) return String(p.hook).substring(0, 120);
    if (p.caption) return String(p.caption).substring(0, 120);
    return draft.topic || "";
  }

  function getPostText(draft, slot) {
    const p = draft.payload || {};
    if (draft.kind === "threads_series") {
      const posts = p.threads_posts || [];
      const post = posts.find((pt) => pt.slot === slot);
      return post ? (post.text || "") : "";
    }
    if (p.caption) return p.caption;
    if (p.hook) return p.hook;
    return "";
  }

  function findPlanItem(draftId, platform, slot) {
    return (state.plansFeed || []).find((i) => {
      if (i.draft_id !== draftId) return false;
      if (slot && i.slot !== slot) return false;
      if (!slot && i.platform !== platform) return false;
      return true;
    }) || null;
  }

  // -- Metrics cache for published items --
  const _metricsCache = new Map();

  async function _fetchMetricsBadge(draftId) {
    if (_metricsCache.has(draftId)) return _metricsCache.get(draftId);
    try {
      const data = await fetchJson(`/api/drafts/${draftId}/metrics`);
      const items = data.metrics || [];
      if (!items.length) { _metricsCache.set(draftId, ""); return ""; }
      const m = items[0].metrics || {};
      const views = m.views ?? m.impressions ?? null;
      const likes = m.likes ?? null;
      let badge = "";
      if (views !== null) badge += `<i data-lucide="eye" style="width:12px;height:12px"></i> ${Number(views).toLocaleString("ru-RU")}`;
      if (likes !== null) badge += `${badge ? " \u00b7 " : ""}<i data-lucide="heart" style="width:12px;height:12px"></i> ${Number(likes).toLocaleString("ru-RU")}`;
      _metricsCache.set(draftId, badge);
      return badge;
    } catch (_e) {
      _metricsCache.set(draftId, "");
      return "";
    }
  }

  function _injectMetricsBadges() {
    const badges = document.querySelectorAll("[data-metrics-draft]");
    for (const el of badges) {
      const draftId = el.dataset.metricsDraft;
      if (!draftId || el.dataset.loaded) continue;
      el.dataset.loaded = "1";
      _fetchMetricsBadge(draftId).then((html) => {
        if (html) {
          el.innerHTML = html;
          el.hidden = false;
          if (window.lucide) lucide.createIcons();
        }
      });
    }
  }

  // ── Feed loading ───────────────────────────────────────────────────────────

  async function loadPlansFeed() {
    try {
      const data = await fetchJson("/api/plans/feed");
      state.plansFeed = data.items || [];
      state.plansFeedDates = data.dates_with_content || [];
    } catch (_e) {
      state.plansFeed = state.plansFeed || [];
      state.plansFeedDates = state.plansFeedDates || [];
    }
    renderPlans();
  }

  // ── Filter setters (global, called from onclick) ───────────────────────────

  function setPlanStatusFilter(v) {
    state.plansFilter.status = v;
    renderPlans();
  }

  function setPlanPlatformFilter(v) {
    state.plansFilter.platform = v;
    renderPlans();
  }

  function setPlanDateFilter(dateStr) {
    state.plansFilter.date = state.plansFilter.date === dateStr ? null : dateStr;
    renderPlans();
  }

  // ── Calendar strip ─────────────────────────────────────────────────────────

  function renderCalendarStrip(activeDateStr, datesWithContent) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = [];
    const dayNames = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
    const months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
    for (let i = -7; i <= 6; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      const dateKey = d.toISOString().substring(0, 10);
      days.push({
        dateKey,
        label: dayNames[d.getDay()],
        day: d.getDate(),
        month: months[d.getMonth()],
        isToday: i === 0,
        isActive: dateKey === activeDateStr,
        hasContent: (datesWithContent || []).includes(dateKey),
      });
    }
    return `
      <div class="plans-calendar-strip" id="plansCalendarStrip">
        ${days.map((day) => `
          <button class="plans-cal-day${day.isToday ? " is-today" : ""}${day.isActive ? " is-active" : ""}"
            data-action="setPlanDateFilter" data-args='["${day.dateKey}"]'
            title="${day.day} ${day.month}">
            <div class="plans-cal-day-label">${day.label}</div>
            <div class="plans-cal-day-num">${day.day}</div>
            ${day.hasContent && !day.isActive ? `<div class="plans-cal-day-dot"></div>` : ""}
          </button>
        `).join("")}
      </div>
    `;
  }

  // ── Filter chips ───────────────────────────────────────────────────────────

  function renderStatusFilters(active) {
    const chips = [
      { label: "Все", value: "all" },
      { label: "Запланировано", value: "scheduled" },
      { label: "Опубликовано", value: "published" },
      { label: "Ошибка", value: "error" },
    ];
    return `
      <div class="filter-chips-row">
        ${chips.map((c) => `
          <button class="filter-chip${c.value === active ? " active" : ""}"
            data-action="setPlanStatusFilter" data-args='["${c.value}"]'>
            ${escapeHtml(c.label)}
          </button>
        `).join("")}
      </div>
    `;
  }

  function renderPlatformFilters(active) {
    const chips = [
      { label: "Все платформы", value: "all" },
      { label: "Threads", value: "Threads" },
      { label: "Instagram", value: "Instagram" },
      { label: "TikTok", value: "TikTok" },
      { label: "YouTube", value: "YouTube" },
      { label: "Telegram", value: "Telegram" },
    ];
    return `
      <div class="filter-chips-row">
        ${chips.map((c) => `
          <button class="filter-chip${c.value === active ? " active" : ""}"
            data-action="setPlanPlatformFilter" data-args='["${c.value}"]'>
            ${escapeHtml(c.label)}
          </button>
        `).join("")}
      </div>
    `;
  }

  // ── Plan card ──────────────────────────────────────────────────────────────

  function renderPlanCard(item) {
    const kindIcons = { threads: "✍️", threads_series: "✍️", reels: "🎬", carousel: "🖼", instagram: "📸" };
    const kindBadge = {
      threads: "ТРЕДС",
      threads_series: "ТРЕДС",
      reels: "РИЛС",
      carousel: "КАРУСЕЛЬ",
      instagram: "ИНСТАГРАМ",
      telegram: "ТЕЛЕГРАМ",
    };
    const icon = kindIcons[item.kind] || "📄";
    const badge = kindBadge[item.kind] || String(item.kind || "").toUpperCase();
    const slotSuffix = item.slot ? ` · ${slotLabel(item.slot)}` : "";
    const label = statusLabel(item.status);
    const tone = statusTone(item.status);

    return `
      <article class="plan-card plan-card-${escapeHtml(item.status)} interactive-card"
        data-action="openPlanDetail" data-args='${JSON.stringify([item.draft_id, item.platform, item.slot || ""])}'>
        <div class="plan-card-top">
          <div class="plan-card-left">
            <div class="plan-card-kind">${icon} ${escapeHtml(badge)}${escapeHtml(slotSuffix)}</div>
            <div class="plan-card-title">${escapeHtml(item.title)}</div>
            ${item.preview ? `<div class="plan-card-preview">${escapeHtml(item.preview)}</div>` : ""}
            ${item.status === "error" && item.error_message ? `
              <div class="plan-card-error">${escapeHtml(item.error_message)}</div>
            ` : ""}
            ${item.status === "published" ? `<span class="plan-card-metrics-badge" data-metrics-draft="${escapeHtml(item.draft_id)}" hidden></span>` : ""}
          </div>
          <div class="plan-card-right">
            <div class="plan-card-time">${escapeHtml(formatTime(item.scheduled_at))}</div>
            <div class="plan-card-platforms">
              ${(item.platforms || [item.platform]).map((p) => platformIcon(p)).join("")}
            </div>
            ${tagMarkup(label, tone)}
          </div>
        </div>
      </article>
    `;
  }

  // ── Feed empty states ──────────────────────────────────────────────────────

  function renderPlansEmpty(filters) {
    if (filters.status === "error") {
      return renderGuidedState({
        eyebrow: "Ошибки публикации",
        title: "Ошибок нет",
        body: "Публикации с ошибками за последние 30 дней не найдены.",
        actionLabel: "+ Создать контент",
        action: "openCreateTool()",
      });
    }
    if (filters.platform !== "all") {
      return renderGuidedState({
        eyebrow: escapeHtml(filters.platform),
        title: "Нет публикаций",
        body: `Публикаций для ${escapeHtml(filters.platform)} не найдено.`,
        actionLabel: "+ Создать контент",
        action: "openCreateTool()",
      });
    }
    if (filters.date) {
      return renderGuidedState({
        eyebrow: "День",
        title: "Нет публикаций",
        body: "На этот день ничего не запланировано.",
        actionLabel: "+ Создать контент",
        action: "openCreateTool()",
      });
    }
    return renderGuidedState({
      eyebrow: "Лента публикаций",
      title: "Публикаций пока нет",
      body: "Контент-план помогает планировать публикации на неделю вперёд. Создайте план и начните заполнять.",
      actionLabel: "+ Создать контент",
      action: "setTab('create')",
    });
  }

  // ── Feed render ────────────────────────────────────────────────────────────

  function renderPlansFeed(items, filters) {
    let filtered = items.slice();

    if (filters.status && filters.status !== "all") {
      filtered = filtered.filter((i) => i.status === filters.status);
    }
    if (filters.platform && filters.platform !== "all") {
      const pLower = filters.platform.toLowerCase();
      filtered = filtered.filter((i) => (i.platforms || [i.platform]).some((p) => p.toLowerCase() === pLower));
    }
    if (filters.date) {
      filtered = filtered.filter((i) => toDateKey(i.scheduled_at) === filters.date);
    }

    filtered.sort((a, b) => (a.scheduled_at || "") < (b.scheduled_at || "") ? -1 : 1);

    if (filtered.length === 0) return renderPlansEmpty(filters);

    const groups = groupByDate(filtered);
    return groups.map((g) => `
      <div class="plans-day-group">
        <div class="plans-day-label">${escapeHtml(formatDayLabel(g.date))}</div>
        ${g.items.map(renderPlanCard).join("")}
      </div>
    `).join("");
  }

  // ── Detail view ────────────────────────────────────────────────────────────

  function renderPlanDetailView(draft, platform, slot) {
    const item = findPlanItem(draft.draft_id, platform, slot);
    const p = draft.payload || {};

    const kindBadge = {
      threads: "ТРЕДС", threads_series: "ТРЕДС", reels: "РИЛС",
      carousel: "КАРУСЕЛЬ", instagram: "ИНСТАГРАМ", telegram: "ТЕЛЕГРАМ",
    };
    const kindIcons = { threads: "✍️", threads_series: "✍️", reels: "🎬", carousel: "🖼", instagram: "📸" };
    const icon = kindIcons[draft.kind] || "📄";
    const badge = (kindBadge[draft.kind] || String(draft.kind || "").toUpperCase())
      + (slot ? ` · ${slotLabel(slot)}` : "");

    const s = item ? item.status : "scheduled";
    const label = statusLabel(s);
    const tone = statusTone(s);
    const scheduledAt = item ? item.scheduled_at : null;
    const errorMsg = item ? (item.error_message || "") : "";
    const publishedAt = item ? (item.published_at || null) : null;

    const postText = getPostText(draft, slot);
    const summary = getSummary(draft, slot);

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}

        <div class="detail-top">
          <p class="eyebrow">${icon} <span>${escapeHtml(badge)}</span></p>
          <h2 class="detail-title">${escapeHtml(draft.topic || "")}</h2>
          ${summary ? `<p class="detail-summary">${escapeHtml(summary)}</p>` : ""}
          <div class="draft-meta">
            ${tagMarkup(label, tone)}
            ${tagMarkup(escapeHtml(platform), "neutral")}
          </div>
        </div>

        <div class="detail-facts">
          ${deps.detailFactMarkup ? deps.detailFactMarkup("ТИП", badge) : ""}
          ${deps.detailFactMarkup ? deps.detailFactMarkup("ПЛАТФОРМА", platform) : ""}
          ${scheduledAt && deps.detailFactMarkup ? deps.detailFactMarkup("ВРЕМЯ", formatDateTime(scheduledAt)) : ""}
          ${publishedAt && deps.detailFactMarkup ? deps.detailFactMarkup("ОПУБЛИКОВАНО", formatDateTime(publishedAt)) : ""}
          ${deps.detailFactMarkup ? deps.detailFactMarkup("СТАТУС", label) : ""}
        </div>

        ${s === "error" && errorMsg ? `
          <section class="section" style="border-color:rgba(176,58,46,.25);background:rgba(176,58,46,.06)">
            <h3>ОШИБКА ПУБЛИКАЦИИ</h3>
            <p style="font-size:13px;color:var(--bad)">${escapeHtml(errorMsg)}</p>
            <div class="actions-row">
              <button class="primary-button"
                data-action="retryPublication" data-args='${JSON.stringify([draft.draft_id, platform, slot || "", null])}'>
                ↺ Повторить публикацию
              </button>
            </div>
          </section>
        ` : ""}

        ${postText ? `
          <section class="section">
            <h3>ТЕКСТ ПОСТА</h3>
            <div class="detail-preview detail-markdown">${renderMarkdown(postText)}</div>
          </section>
        ` : ""}

        <div class="actions-row">
          ${s === "scheduled" ? `
            <button class="primary-button"
              data-action="publishScheduledNow" data-args='${JSON.stringify([draft.draft_id, draft.kind, slot || "", null])}'>
              ${actionLabel("send", "Опубликовать сейчас")}
            </button>
            <button class="secondary-button"
              data-action="cancelPublishSchedule" data-args='${JSON.stringify([draft.draft_id, null])}'>
              ✗ Отменить
            </button>
          ` : ""}
          <button class="danger-button"
            data-action="deleteDraft" data-args='${JSON.stringify([draft.draft_id, "plans", null])}'>
            🗑 Удалить черновик
          </button>
        </div>
      </div>
    `;
  }

  async function openPlanDetail(draftId, platform, slot) {
    elements.draftDetail.innerHTML = `${renderBackButton()}${deps.renderDetailLoader ? deps.renderDetailLoader("Открываю публикацию") : ""}`;
    enterDetailView();
    try {
      const draft = await fetchJson(`/api/drafts/${draftId}`);
      renderPlanDetailView(draft, platform, slot);
      enterDetailView();
    } catch (_e) {
      elements.draftDetail.innerHTML = `${renderBackButton()}<p style="padding:16px;color:var(--bad)">Не удалось загрузить публикацию</p>`;
    }
  }

  // ── Main render ────────────────────────────────────────────────────────────

  async function loadPlans() {
    const data = await fetchJson("/api/plans?limit=20");
    state.plans = data.items || [];
    renderPlans();
  }

  function renderPlansSwitcher(active) {
    return `<button class="header-tab${active === "publications" ? " active" : ""}" data-action="setPlansSubMode" data-args='["publications"]'>Публикации</button>
      <button class="header-tab${active === "archive" ? " active" : ""}" data-action="setPlansSubMode" data-args='["archive"]'>Архив</button>
      <button class="header-tab${active === "mentions" ? " active" : ""}" data-action="setPlansSubMode" data-args='["mentions"]'>Упоминания</button>`;
  }

  function renderPlans() {
    const subMode = state.plansSubMode || "publications";
    const topbarNavTabs = document.getElementById("topbarNavTabs");
    if (topbarNavTabs) topbarNavTabs.innerHTML = renderPlansSwitcher(subMode);

    if (subMode === "archive") {
      if (window.archiveModule) {
        window.archiveModule.loadArchive();
      }
      return;
    }

    if (subMode === "mentions") {
      elements.listTitle.textContent = "Упоминания";
      elements.draftCount.textContent = "";
      elements.draftList.innerHTML = `<div id="plans-container"></div>`;
      if (window.mentionsModule) {
        window.mentionsModule.loadMentions().then(() => {
          const count = (state.mentions || []).length;
          if (count > 0) elements.draftCount.textContent = `${count} шт`;
        });
      }
      return;
    }

    const feed = state.plansFeed || [];
    const filters = state.plansFilter || { status: "all", platform: "all", date: null };

    // Count for header
    let filtered = feed.slice();
    if (filters.status && filters.status !== "all") filtered = filtered.filter((i) => i.status === filters.status);
    if (filters.platform && filters.platform !== "all") {
      const pLower = filters.platform.toLowerCase();
      filtered = filtered.filter((i) => (i.platforms || [i.platform]).some((p) => p.toLowerCase() === pLower));
    }
    if (filters.date) filtered = filtered.filter((i) => toDateKey(i.scheduled_at) === filters.date);

    elements.listTitle.textContent = "Планы";
    elements.draftCount.textContent = `${filtered.length} публикаций`;

    const plans = state.plans || [];
    elements.draftList.innerHTML = `
      <div class="plans-sticky-header">
        ${renderCalendarStrip(filters.date, state.plansFeedDates || [])}
        ${renderStatusFilters(filters.status)}
        ${renderPlatformFilters(filters.platform)}
      </div>
      <div class="plans-feed-body">
        ${renderPlansFeed(feed, filters)}
      </div>
      ${plans.length > 0 ? `
        <div class="plans-feed-body plans-content-plans">
          <div class="plans-day-label">Контент-планы</div>
          ${plans.map((plan) => `
            <article ${interactiveCardAttrs(`Открыть план ${plan.plan_id}`)} class="plan-card overview-card${plan.plan_id === state.selectedPlan?.plan_id ? " active" : ""} interactive-card" data-action="openPlan" data-args='["${plan.plan_id}"]'>
              <div class="overview-card-top">
                <div class="draft-kind">${contentKindIcon("plan")}<span>План</span></div>
                <span class="overview-card-date">${escapeHtml(formatPlanDate(plan.created_at) || plan.plan_id)}</span>
              </div>
              <h3 class="draft-topic">${escapeHtml(formatPlanDate(plan.created_at) ? `План от ${formatPlanDate(plan.created_at)}` : plan.plan_id)}</h3>
              <div class="draft-preview">${escapeHtml(String(plan.raw_text || "").trim())}</div>
              <div class="draft-meta overview-card-footer">
                ${tagMarkup(`${(plan.entries || []).length} карточек`, "source-plan")}
                ${tagMarkup(`${(plan.related_drafts || []).length} черновиков`, "status-review")}
              </div>
            </article>
          `).join("")}
        </div>
      ` : ""}
    `;

    if (!state.selectedPlan) {
      elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({
        eyebrow: "Публикации",
        title: "Выберите публикацию",
        body: "Нажмите на карточку чтобы просмотреть детали, отредактировать и отправить на публикацию.",
      })}</div>`;
    }
    syncMobileNavigation();
    requestAnimationFrame(() => _injectMetricsBadges());
  }

  // ── Existing plan functions (kept as-is) ───────────────────────────────────

  function planEntryTargetKind(entry = {}) {
    const platform = String(entry.platform || "").trim().toLowerCase();
    const formatLabel = String(entry.format_label || "").trim().toLowerCase();
    if (platform.includes("reels") || formatLabel.includes("reels") || formatLabel.includes("рилс")) return "reels";
    if (formatLabel.includes("карус") || formatLabel.includes("carousel")) return "carousel";
    if (platform.includes("threads")) return "threads";
    if (platform.includes("instagram")) return "instagram";
    if (platform.includes("telegram")) return "telegram";
    return "instagram";
  }

  function planEntryFormatLabel(entry = {}) {
    const target = planEntryTargetKind(entry);
    return kindLabel(target) || "Контент";
  }

  function relatedDraftsForEntry(plan = {}, entry = {}) {
    const topic = String(entry.topic || "").trim();
    const related = Array.isArray(plan.related_drafts) ? plan.related_drafts : [];
    if (!topic) return [];
    return related.filter((draft) => String(draft.topic || "").trim() === topic);
  }

  async function openPlan(id) {
    elements.draftDetail.innerHTML = `${renderBackButton()}${deps.renderDetailLoader ? deps.renderDetailLoader("Открываю план") : ""}`;
    enterDetailView();
    const p = await fetchJson(`/api/plans/${id}`);
    state.selectedPlan = p;
    state.plans = state.plans.map((item) => item.plan_id === p.plan_id ? { ...item, ...p } : item);
    renderPlanDetail(p);
    enterDetailView();
    const params = new URLSearchParams(window.location.search);
    params.set("tab", state.tab);
    params.set("draft_id", id);
    history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
  }

  async function generateDraftFromPlan(planId, entryIndex, button) {
    const plan = state.selectedPlan || state.plans.find((p) => p.plan_id === planId);
    const entries = plan?.entries || [];
    const entry = entries[entryIndex] || {};
    const isReels = planEntryTargetKind(entry) === "reels";

    if (isReels) {
      const topic = String(entry.topic || "").trim();
      const pending = openPendingReelsCreation(topic);
      try {
        const payload = await fetchJson(`/api/plans/${planId}/generate`, {
          method: "POST",
          body: JSON.stringify({ entry_index: entryIndex }),
          timeout: 45000,
        });
        const draft = payload?.draft || null;
        if (draft?.draft_id) {
          finalizePendingReelsCreation(draft);
          await reloadPlans();
          await openReels(draft.draft_id);
        }
      } catch {
        recoverPendingReelsCreation(String(entry.topic || "").trim(), pending.draft_id);
      }
      return;
    }

    const apply = async () => {
      const payload = await fetchJson(`/api/plans/${planId}/generate`, {
        method: "POST",
        body: JSON.stringify({ entry_index: entryIndex }),
        timeout: 15000,
      });
      const draft = payload?.draft || null;
      if (draft?.draft_id) {
        upsertDraftSummary(draftSummaryFromDraft(draft));
        await reloadPlans();
        setTab("drafts");
        await loadDrafts();
        await openDraft(draft.draft_id);
        if (draft.generation_pending) scheduleDraftRefresh(draft.draft_id);
      }
      return draft;
    };
    const draft = button instanceof HTMLElement
      ? await withButtonFeedback(button, "Создаю...", apply, "Создано")
      : await apply();
  }

  async function openPlanRelatedDraft(kind, draftId) {
    if (!draftId) return;
    if (kind === "reels") {
      await loadReels();
      await openReels(draftId);
      return;
    }
    setTab("drafts");
    await loadDrafts();
    await openDraft(draftId);
  }

  function renderPlanDetail(p) {
    const entries = Array.isArray(p.entries) ? p.entries : [];
    const relatedDrafts = Array.isArray(p.related_drafts) ? p.related_drafts : [];
    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("calendar")}<span>План • ${escapeHtml(formatPlanDate(p.created_at) || p.plan_id)}</span></p>
          <h2 class="detail-title">Контент-план</h2>
          <div class="draft-meta">
            ${tagMarkup(`${entries.length} тем`, "progress")}
            ${relatedDrafts.length ? tagMarkup(`${relatedDrafts.length} связанных черновиков`, "status-positive") : tagMarkup("Без связанных черновиков", "status-neutral")}
          </div>
        </div>
        <section class="section">
          <h3>${uiIcon("text")}Исходный план</h3>
          <div class="detail-preview detail-markdown">${renderMarkdown(p.raw_text || "План без исходного текста")}</div>
        </section>
        <section class="section">
          <h3>${uiIcon("slides")}Темы и форматы</h3>
          <div class="plan-entry-list">
            ${entries.map((entry, index) => {
              const related = relatedDraftsForEntry(p, entry);
              return `
                <article class="plan-entry-card">
                  <div class="plan-entry-head">
                    <div>
                      <strong>${escapeHtml(entry.topic || `Тема ${index + 1}`)}</strong>
                      <div class="draft-meta">
                        ${entry.day_label ? tagMarkup(entry.day_label, "status-neutral") : ""}
                        ${entry.platform ? tagMarkup(entry.platform, "source-plan") : ""}
                        ${tagMarkup(planEntryFormatLabel(entry), "source-plan")}
                      </div>
                    </div>
                    <button class="primary-button" type="button" data-action="generateDraftFromPlan" data-args='${JSON.stringify([p.plan_id, index, null])}'>${actionLabel("sparkle", `Создать ${planEntryFormatLabel(entry)}`)}</button>
                  </div>
                  ${entry.angle ? `<div class="detail-preview">${escapeHtml(entry.angle)}</div>` : ""}
                  ${entry.goal ? `<div class="detail-preview"><strong>Цель:</strong> ${escapeHtml(entry.goal)}</div>` : ""}
                  ${related.length ? `
                    <div class="actions-row">
                      ${related.map((draft) => `
                        <button class="secondary-button" type="button" data-action="openPlanRelatedDraft" data-args='${JSON.stringify([draft.kind, draft.draft_id])}'>${actionLabel(draft.kind === "reels" ? "reel" : "eye", `Открыть ${kindLabel(draft.kind)}`)}</button>
                      `).join("")}
                    </div>
                  ` : ""}
                </article>
              `;
            }).join("")}
          </div>
        </section>
        ${(!p.status || p.status === "draft") ? `
          <div class="actions-row">
            <button class="primary-button" type="button" id="activatePlanBtn"
              data-action="activatePlan" data-args='${JSON.stringify([p.plan_id, null])}'>
              ${actionLabel("zap", "Активировать план")}
            </button>
          </div>
        ` : ""}
        ${p.status === "activating" ? `
          <div class="actions-row">
            <p style="color:var(--warn);font-size:13px">${uiIcon("loader")} Активация в процессе...</p>
          </div>
        ` : ""}
        ${p.status === "active" ? `
          <div class="actions-row">
            <p style="color:var(--good);font-size:13px">${uiIcon("check")} План активирован</p>
          </div>
        ` : ""}
        ${p.status === "failed" ? `
          <div class="actions-row">
            <p style="color:var(--bad);font-size:13px">${uiIcon("alert-circle")} Ошибка активации</p>
            <button class="primary-button" type="button"
              data-action="activatePlan" data-args='${JSON.stringify([p.plan_id, null])}'>
              ${actionLabel("zap", "Повторить")}
            </button>
          </div>
        ` : ""}
      </div>
    `;
    syncMobileNavigation();
    if (window.lucide) lucide.createIcons();
  }

  async function activatePlan(planId, button) {
    const apply = async () => {
      await fetchJson(`/api/plans/${planId}/activate`, { method: "POST" });
      let attempts = 0;
      const maxAttempts = 24;
      while (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 5000));
        attempts++;
        const status = await fetchJson(`/api/plans/${planId}/activation-status`);
        if (status.status === "active") return status;
        if (status.status === "failed") throw new Error("Activation failed");
      }
      throw new Error("Activation timed out");
    };
    try {
      const result = button instanceof HTMLElement
        ? await withButtonFeedback(button, "Активирую...", apply, "Активировано")
        : await apply();
      await openPlan(planId);
      await loadPlansFeed();
    } catch (_e) {
      await openPlan(planId);
    }
  }

  return {
    loadPlans,
    loadPlansFeed,
    setPlanStatusFilter,
    setPlanPlatformFilter,
    setPlanDateFilter,
    openPlanDetail,
    planEntryTargetKind,
    planEntryFormatLabel,
    relatedDraftsForEntry,
    openPlan,
    generateDraftFromPlan,
    openPlanRelatedDraft,
    renderPlans,
    renderPlanDetail,
    activatePlan,
  };
}
