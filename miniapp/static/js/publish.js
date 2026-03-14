/**
 * Publish panel — shown for approved drafts.
 * Platforms: threads, instagram, telegram.
 * Supports immediate publish and scheduling.
 */
export function createPublishModule(deps) {
  const { fetchJson, withButtonFeedback, escapeHtml, tagMarkup, uiIcon } = deps;

  let _pollTimer = null;

  function renderPublishPanel(draftId, status) {
    if (status !== "approved" && status !== "published" && status !== "scheduled") return "";
    const isPublished = status === "published";
    const isScheduled = status === "scheduled";
    return `
      <section class="section section-primary">
        <div class="section-heading">
          <h3>${uiIcon("chat")}Публикация</h3>
          <p>${isPublished ? "Материал опубликован." : isScheduled ? "Материал запланирован." : "Выберите платформы и опубликуйте или запланируйте."}</p>
        </div>
        <div class="publish-panel" id="publishPanel" data-draft-id="${draftId}">
          <div class="publish-platforms">
            <label class="publish-platform-toggle"><input type="checkbox" id="pubThreads" value="threads" ${isPublished ? "disabled" : ""} checked><span>Threads</span></label>
            <label class="publish-platform-toggle"><input type="checkbox" id="pubInstagram" value="instagram" ${isPublished ? "disabled" : ""}><span>Instagram</span></label>
            <label class="publish-platform-toggle"><input type="checkbox" id="pubTelegram" value="telegram" ${isPublished ? "disabled" : ""}><span>Telegram</span></label>
          </div>
          ${!isPublished ? `
            <div class="publish-schedule-row">
              <label class="publish-schedule-label"><span>Запланировать на</span>
                <input type="datetime-local" id="pubScheduleAt" class="publish-datetime">
              </label>
            </div>
            <div class="actions-row">
              <button class="primary-button" type="button" onclick="publishDraft('${draftId}', false, this)">Опубликовать сейчас</button>
              <button class="secondary-button" type="button" onclick="publishDraft('${draftId}', true, this)">Запланировать</button>
            </div>
          ` : ""}
          ${isScheduled ? `
            <div class="actions-row">
              <button class="danger-button" type="button" onclick="cancelPublishSchedule('${draftId}', this)">Отменить публикацию</button>
            </div>
          ` : ""}
          <div id="publishStatusContainer"></div>
        </div>
      </section>
    `;
  }

  function _getSelectedPlatforms() {
    const platforms = [];
    if (document.getElementById("pubThreads")?.checked) platforms.push("threads");
    if (document.getElementById("pubInstagram")?.checked) platforms.push("instagram");
    if (document.getElementById("pubTelegram")?.checked) platforms.push("telegram");
    return platforms;
  }

  async function publishDraft(draftId, withSchedule, button) {
    const platforms = _getSelectedPlatforms();
    if (!platforms.length) {
      alert("Выберите хотя бы одну платформу");
      return;
    }
    const body = { platforms };
    if (withSchedule) {
      const dt = document.getElementById("pubScheduleAt")?.value;
      if (!dt) {
        alert("Укажите дату и время");
        return;
      }
      body.scheduled_at = new Date(dt).toISOString();
    }
    await withButtonFeedback(button, withSchedule ? "Планирую..." : "Публикую...", async () => {
      await fetchJson(`/api/drafts/${draftId}/publish`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      _startStatusPoll(draftId);
    }, withSchedule ? "Запланировано" : "Отправлено");
  }

  async function cancelPublishSchedule(draftId, button) {
    await withButtonFeedback(button, "Отменяю...", async () => {
      await fetchJson(`/api/drafts/${draftId}/publish-schedule`, { method: "DELETE" });
    }, "Отменено");
  }

  async function loadPublishStatus(draftId) {
    const data = await fetchJson(`/api/drafts/${draftId}/publish-status`);
    _renderStatusLogs(data?.logs || []);
  }

  function _renderStatusLogs(logs) {
    const container = document.getElementById("publishStatusContainer");
    if (!container || !logs.length) return;
    const PLATFORM_ICONS = { threads: "T", instagram: "IG", telegram: "TG" };
    const STATUS_ICONS = { success: "done", failed: "error", pending: "pending" };
    container.innerHTML = `
      <div class="publish-status-list">
        ${logs.map(l => `
          <div class="publish-status-item publish-status-${l.status}">
            <span class="publish-status-platform">${PLATFORM_ICONS[l.platform] || l.platform}</span>
            <span class="publish-status-action">${l.action}</span>
            ${tagMarkup(l.status, l.status === "success" ? "status-positive" : l.status === "failed" ? "status-negative" : "pending")}
            ${l.error_message ? `<span class="publish-status-error">${escapeHtml(l.error_message)}</span>` : ""}
          </div>
        `).join("")}
      </div>
    `;
  }

  function _startStatusPoll(draftId) {
    if (_pollTimer) clearInterval(_pollTimer);
    loadPublishStatus(draftId);
    _pollTimer = setInterval(() => loadPublishStatus(draftId), 5000);
    setTimeout(() => { if (_pollTimer) clearInterval(_pollTimer); }, 60000);
  }

  return {
    renderPublishPanel,
    publishDraft,
    cancelPublishSchedule,
    loadPublishStatus,
  };
}
