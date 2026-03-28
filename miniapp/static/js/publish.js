/**
 * Publish panel — shown for approved drafts.
 * Platforms: threads, instagram, telegram.
 * Supports immediate publish and scheduling.
 */
import { sseQueryString } from "./sse-auth.js";
import { PLATFORM_SVG } from "./platform-icons.js";

export function createPublishModule(deps) {
  const { fetchJson, withButtonFeedback, escapeHtml, tagMarkup, uiIcon, showUiNotice, confirmAction, mergeDraftIntoState, renderDraftList, renderDraftDetail } = deps;

  let _pollTimer = null;
  let _publishEventSource = null;

  function _authQs() {
    const d = window.Telegram?.WebApp?.initData;
    return d ? `?init_data=${encodeURIComponent(d)}` : "";
  }

  function renderPublishPanel(draftId, status, opts) {
    if (status !== "approved" && status !== "published" && status !== "scheduled") return "";
    const isPublished = status === "published";
    const isScheduled = status === "scheduled";
    const hasMedia = opts?.hasMedia ?? true;
    const hasVideo = opts?.hasVideo ?? false;
    const igDisabled = isPublished || !hasMedia;
    const ttDisabled = isPublished || !hasVideo;
    return `
      <section class="section section-primary">
        <div class="section-heading">
          <h3>${uiIcon("chat")}Публикация</h3>
          <p>${isPublished ? "Материал опубликован." : isScheduled ? "Материал запланирован." : "Выберите платформы и опубликуйте или запланируйте."}</p>
        </div>
        <div class="publish-panel" id="publishPanel" data-draft-id="${draftId}">
          <div class="publish-platforms">
            <label class="publish-platform-toggle"><input type="checkbox" id="pubThreads" value="threads" ${isPublished ? "disabled" : ""} checked>${PLATFORM_SVG.threads}<span>Threads</span></label>
            <label class="publish-platform-toggle ${!hasMedia ? "publish-platform-disabled" : ""}"><input type="checkbox" id="pubInstagram" value="instagram" ${igDisabled ? "disabled" : ""}>${PLATFORM_SVG.instagram}<span>Instagram</span>${!hasMedia ? '<span class="publish-platform-hint">нужна картинка</span>' : ""}</label>
            <label class="publish-platform-toggle"><input type="checkbox" id="pubTelegram" value="telegram" ${isPublished ? "disabled" : ""}>${PLATFORM_SVG.telegram}<span>Telegram</span></label>
            <label class="publish-platform-toggle ${!hasVideo ? "publish-platform-disabled" : ""}"><input type="checkbox" id="pubTiktok" value="tiktok" ${ttDisabled ? "disabled" : ""}>${PLATFORM_SVG.tiktok}<span>TikTok</span>${!hasVideo ? '<span class="publish-platform-hint">нужно видео</span>' : ""}</label>
          </div>
          ${!isPublished ? `
            <div class="publish-schedule-row">
              <label class="publish-schedule-label"><span>Запланировать на</span>
                <input type="datetime-local" id="pubScheduleAt" class="publish-datetime">
              </label>
            </div>
            <div class="actions-row">
              <button class="primary-button" type="button" data-action="publishDraft" data-args='${JSON.stringify([draftId, false, null])}'>Опубликовать сейчас</button>
              <button class="secondary-button" type="button" data-action="publishDraft" data-args='${JSON.stringify([draftId, true, null])}'>Запланировать</button>
            </div>
          ` : ""}
          ${isScheduled ? `
            <div class="actions-row">
              <button class="danger-button" type="button" data-action="cancelPublishSchedule" data-args='${JSON.stringify([draftId, null])}'>Отменить публикацию</button>
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
    if (document.getElementById("pubTiktok")?.checked) platforms.push("tiktok");
    return platforms;
  }

  async function publishDraft(draftId, withSchedule, button) {
    const platforms = _getSelectedPlatforms();
    if (!platforms.length) {
      showUiNotice("Выберите хотя бы одну платформу", "error");
      return;
    }
    if (!withSchedule) {
      const ok = confirm("Опубликовать сейчас?");
      if (!ok) return;
    }
    const body = { platforms };
    if (withSchedule) {
      const dt = document.getElementById("pubScheduleAt")?.value;
      if (!dt) {
        showUiNotice("Укажите дату и время", "error");
        return;
      }
      body.scheduled_at = new Date(dt).toISOString();
    }
    await withButtonFeedback(button, withSchedule ? "Планирую..." : "Публикую...", async () => {
      await fetchJson(`/api/drafts/${draftId}/publish`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const draft = await fetchJson(`/api/drafts/${draftId}`);
      if (draft && mergeDraftIntoState) {
        mergeDraftIntoState(draft);
        if (renderDraftList) renderDraftList();
        if (renderDraftDetail) renderDraftDetail(draft);
      }
      _startStatusPoll(draftId);
    }, withSchedule ? "Запланировано" : "Отправлено");
  }

  async function cancelPublishSchedule(draftId, button) {
    const _confirm = confirmAction || ((msg) => Promise.resolve(window.confirm(msg)));
    const ok = await _confirm("Отменить запланированную публикацию?");
    if (!ok) return;
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
    const PLATFORM_ICONS = { threads: PLATFORM_SVG.threads, instagram: PLATFORM_SVG.instagram, telegram: PLATFORM_SVG.telegram, tiktok: PLATFORM_SVG.tiktok };
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

  async function _startStatusPoll(draftId) {
    if (_pollTimer) clearInterval(_pollTimer);
    if (_publishEventSource) { _publishEventSource.close(); _publishEventSource = null; }
    loadPublishStatus(draftId);
    if (typeof EventSource !== "undefined") {
      const qs = await sseQueryString();
      const es = new EventSource(`/api/drafts/${draftId}/publish-stream${qs}`);
      _publishEventSource = es;
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.error === "not_found" || data.done) {
            _renderStatusLogs(data.logs || []);
            es.close(); _publishEventSource = null;
            return;
          }
          _renderStatusLogs(data.logs || []);
        } catch (_e) { /* ignore */ }
      };
      es.onerror = () => { es.close(); _publishEventSource = null; _fallbackStatusPoll(draftId); };
    } else {
      _fallbackStatusPoll(draftId);
    }
  }

  function _fallbackStatusPoll(draftId) {
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
