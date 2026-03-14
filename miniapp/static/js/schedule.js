/**
 * Schedule view — shows scheduled and recently published drafts.
 */
export function createScheduleModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    tagMarkup,
    kindLabel,
    contentKindIcon,
    formatPlanDate,
    statusLabel,
    statusTone,
    fetchJson,
    withButtonFeedback,
    setEmptyState,
    syncMobileNavigation,
    renderBackButton,
    interactiveCardAttrs,
  } = deps;

  async function loadSchedule() {
    const [scheduled, history] = await Promise.all([
      fetchJson("/api/publish/scheduled"),
      fetchJson("/api/publish/history?limit=20"),
    ]);
    state._scheduleData = {
      scheduled: scheduled?.items || [],
      history: history?.items || [],
    };
  }

  function renderScheduleList() {
    elements.listTitle.textContent = "Расписание";
    elements.draftCount.textContent = "";
    const data = state._scheduleData || { scheduled: [], history: [] };
    const hasItems = data.scheduled.length > 0 || data.history.length > 0;
    setEmptyState(hasItems, {
      eyebrow: "Расписание",
      title: "Нет запланированных публикаций",
      body: "Запланируйте публикацию из карточки согласованного материала.",
    });
    if (!hasItems) return;

    let html = "";
    if (data.scheduled.length) {
      html += `<div class="schedule-group"><h3 class="schedule-group-title">Запланировано</h3>`;
      html += data.scheduled.map(item => `
        <article ${interactiveCardAttrs(`Открыть ${item.topic}`)} class="draft-card overview-card interactive-card" onclick="openDraft('${item.draft_id}')">
          <div class="overview-card-top">
            <div class="draft-kind">${contentKindIcon(item.kind)}<span>${escapeHtml(kindLabel(item.kind))}</span></div>
            <span class="overview-card-date">${escapeHtml(formatPlanDate(item.scheduled_at) || "")}</span>
          </div>
          <h3 class="draft-topic">${escapeHtml(item.topic)}</h3>
          <div class="draft-meta overview-card-footer">
            ${(item.publish_platforms || []).map(p => tagMarkup(p, "status-neutral")).join("")}
            <button class="tag tag-negative" type="button" onclick="event.stopPropagation(); cancelPublishSchedule('${item.draft_id}', this)">Отмена</button>
          </div>
        </article>
      `).join("");
      html += `</div>`;
    }

    if (data.history.length) {
      html += `<div class="schedule-group"><h3 class="schedule-group-title">Опубликовано</h3>`;
      const grouped = {};
      for (const log of data.history) {
        if (!grouped[log.draft_id]) grouped[log.draft_id] = [];
        grouped[log.draft_id].push(log);
      }
      for (const [draftId, logs] of Object.entries(grouped)) {
        const first = logs[0];
        html += `
          <article class="draft-card overview-card">
            <div class="overview-card-top">
              <span class="overview-card-date">${escapeHtml(formatPlanDate(first.created_at) || "")}</span>
            </div>
            <div class="draft-meta overview-card-footer">
              ${logs.map(l => tagMarkup(`${l.platform}: ${l.status}`, l.status === "success" ? "status-positive" : "status-negative")).join("")}
            </div>
          </article>
        `;
      }
      html += `</div>`;
    }

    elements.draftList.innerHTML = html;
    syncMobileNavigation();
  }

  function renderScheduleDetail() {
    elements.draftDetail.innerHTML = `
      ${renderBackButton()}
      <div class="detail-empty">
        <p class="eyebrow">Расписание</p>
        <p>Выберите запланированный пост слева для подробностей.</p>
      </div>
    `;
    syncMobileNavigation();
  }

  return {
    loadSchedule,
    renderScheduleList,
    renderScheduleDetail,
  };
}
