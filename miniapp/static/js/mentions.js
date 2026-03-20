/**
 * Mentions module — view and respond to mentions from Threads/Instagram/Telegram.
 * Pattern: createMentionsModule(deps) matching createPlansModule.
 */
export function createMentionsModule(deps) {
  const {
    state,
    elements,
    fetchJson,
    escapeHtml,
    withButtonFeedback,
    showUiNotice,
    enterDetailView,
    syncMobileNavigation,
    renderBackButton,
  } = deps;

  // ── State ──────────────────────────────────────────────────────────────────
  if (!state.mentions) state.mentions = [];
  if (!state.mentionsFilter) state.mentionsFilter = { platform: "all", status: "pending" };
  if (!state.selectedMention) state.selectedMention = null;

  // ── Helpers ────────────────────────────────────────────────────────────────

  function platformIcon(platform) {
    const icons = { threads: "at-sign", instagram: "instagram", telegram: "send" };
    return icons[platform] || "message-circle";
  }

  function platformLabel(platform) {
    return { telegram: "Telegram", threads: "Threads", instagram: "Instagram" }[platform] || platform;
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function toneLabel(tone) {
    return { official: "Официальный", warm: "Тёплый", provocative: "Провокационный" }[tone] || tone;
  }

  function statusLabel(status) {
    return { pending: "Ожидает", replied: "Отвечено", ignored: "Игнорируется", all: "Все" }[status] || status;
  }

  // ── Load ───────────────────────────────────────────────────────────────────

  async function loadMentions() {
    const { platform, status } = state.mentionsFilter;
    try {
      const data = await fetchJson(
        `/api/mentions?platform=${platform}&status=${status}&limit=50`
      );
      state.mentions = data.items || [];
    } catch (e) {
      state.mentions = [];
    }
    renderMentions();
  }

  // ── Render list ────────────────────────────────────────────────────────────

  function renderMentions() {
    const container = elements.plansContainer || document.getElementById("plans-container");
    if (!container) return;

    if (state.selectedMention) {
      renderMentionDetail();
      return;
    }

    const { platform, status } = state.mentionsFilter;
    const platforms = ["all", "telegram", "threads", "instagram"];
    const statuses = ["pending", "replied", "ignored", "all"];

    const filterBar = `
      <div class="plans-filter-bar" style="margin-bottom:12px">
        <div style="display:flex;gap:6px;overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none;-webkit-overflow-scrolling:touch">
          ${platforms.map(p => `
            <button class="filter-chip${platform === p ? " active" : ""}" style="flex-shrink:0"
              data-action="setMentionsFilter" data-args='["platform","${p}"]'>
              ${p === "all" ? "Все платформы" : platformLabel(p)}
            </button>`).join("")}
        </div>
        <div style="display:flex;gap:6px;overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none;-webkit-overflow-scrolling:touch;margin-top:6px">
          ${statuses.map(s => `
            <button class="filter-chip${status === s ? " active" : ""}"
              data-action="setMentionsFilter" data-args='["status","${s}"]'>
              ${statusLabel(s)}
            </button>`).join("")}
        </div>
      </div>`;

    if (!state.mentions.length) {
      container.innerHTML = filterBar + `<div class="empty-state"><p>Нет упоминаний</p></div>`;
      return;
    }

    const cards = state.mentions.map(m => {
      const statusClass = m.status === "pending" ? "tag-status-warn"
        : m.status === "replied" ? "tag-status-ok"
        : "tag-status-neutral";
      const dimClass = m.status !== "pending" ? " mention-card--dim" : "";
      const checkIcon = m.status === "replied" ? `<i data-lucide="check" style="width:12px;height:12px"></i> ` : "";
      return `
      <div class="mention-card${dimClass}" data-action="openMentionDetail" data-args='["${m.mention_id}"]'>
        <div class="mention-meta">
          <span class="mention-platform-badge">
            <i data-lucide="${platformIcon(m.platform)}"></i> ${platformLabel(m.platform)}
          </span>
          <span class="mention-time">${formatTime(m.received_at)}</span>
          <span class="${statusClass}">${checkIcon}${statusLabel(m.status)}</span>
        </div>
        <div class="mention-author">@${escapeHtml(m.author_username || m.author_name || "аноним")}</div>
        <div class="mention-preview">${escapeHtml(m.content.substring(0, 120))}${m.content.length > 120 ? "…" : ""}</div>
      </div>`;
    }).join("");

    container.innerHTML = filterBar + `<div class="mention-list">${cards}</div>`;
    if (window.lucide) lucide.createIcons();
  }

  // ── Detail view ────────────────────────────────────────────────────────────

  async function openMentionDetail(mentionId) {
    try {
      const detail = await fetchJson(`/api/mentions/${mentionId}`);
      // Merge fresh detail (with replies) into list state
      const idx = state.mentions.findIndex(x => x.mention_id === mentionId);
      if (idx !== -1) state.mentions[idx] = detail;
      state.selectedMention = detail;
    } catch (_e) {
      // Fallback to cached list data
      const m = state.mentions.find(x => x.mention_id === mentionId);
      if (!m) return;
      state.selectedMention = m;
    }
    enterDetailView();
    renderMentionDetail();
  }

  function closeMentionDetail() {
    state.selectedMention = null;
    renderMentions();
  }

  function renderMentionDetail() {
    const m = state.selectedMention;
    if (!m) return;
    const container = elements.draftDetail || document.getElementById("draftDetail");

    const hasPublished = m.replies && m.replies.some(r => r.published_at && !r.publish_error);
    const repliesHtml = m.replies && m.replies.length
      ? m.replies.map(r => {
          const isPublished = r.published_at && !r.publish_error;
          const hasError = !!r.publish_error;
          let statusHtml = "";
          if (isPublished) {
            statusHtml = `<span class="tag-status-ok"><i data-lucide="check"></i> Опубликовано · ${toneLabel(r.tone)}</span>`;
          } else if (hasError) {
            statusHtml = `
              <div class="reply-publish-error">
                <span class="tag-status-warn"><i data-lucide="alert-triangle" style="width:12px;height:12px"></i> Ошибка публикации</span>
                <div style="color:var(--danger);font-size:12px;margin-top:4px">${escapeHtml(r.publish_error)}</div>
                <button class="secondary-button compact" style="margin-top:6px"
                  data-action="publishReply" data-args='${JSON.stringify([m.mention_id, r.reply_id, null])}'>
                  <i data-lucide="refresh-cw"></i> Повторить
                </button>
              </div>`;
          } else if (!hasPublished) {
            statusHtml = `
              <button class="primary-button compact"
                data-action="publishReply" data-args='${JSON.stringify([m.mention_id, r.reply_id, null])}'>
                Опубликовать
              </button>`;
          }
          return `
          <div class="reply-option${r.selected ? " is-selected" : ""}">
            <div class="reply-tone-badge">${toneLabel(r.tone)}</div>
            <div class="reply-text">${escapeHtml(r.content)}</div>
            <div class="reply-length">${r.content.length} символов</div>
            ${statusHtml}
          </div>`;
        }).join("")
      : `<p class="field-help">Ещё нет ответов. Нажми «Сгенерировать».</p>`;

    container.innerHTML = `
      ${renderBackButton()}
      <div class="mention-content">
        <div class="mention-meta">
          <span class="mention-platform-badge">
            <i data-lucide="${platformIcon(m.platform)}"></i> ${platformLabel(m.platform)}
          </span>
          <span class="mention-time">${formatTime(m.received_at)}</span>
          <span class="tag-status-${m.status === "pending" ? "warn" : "ok"}">${statusLabel(m.status)}</span>
        </div>
        <div class="mention-author">@${escapeHtml(m.author_username || m.author_name || "аноним")}</div>
        ${m.context_post ? `<div class="mention-context">${escapeHtml(m.context_post)}</div>` : ""}
        <div class="mention-content-text">${escapeHtml(m.content)}</div>
        ${m.url ? `<a href="${escapeHtml(m.url)}" class="mention-link" target="_blank">Открыть оригинал</a>` : ""}
      </div>
      ${m.status !== "ignored" ? `
      <div class="mention-actions" style="display:flex;gap:8px;margin:12px 0">
        <button class="primary-button" data-action="generateReplies" data-args='${JSON.stringify([m.mention_id, null])}'
          ${m.status === "replied" ? "disabled" : ""}>
          <i data-lucide="sparkles"></i> Сгенерировать ответы
        </button>
        <button class="secondary-button" data-action="ignoreMentionAction" data-args='${JSON.stringify([m.mention_id, null])}'
          ${m.status === "replied" ? "disabled" : ""}>
          <i data-lucide="eye-off"></i> Игнорировать
        </button>
      </div>` : ""}
      <div class="reply-list" id="reply-list-${m.mention_id}">
        ${repliesHtml}
      </div>`;

    if (window.lucide) lucide.createIcons();
  }

  // ── Actions ────────────────────────────────────────────────────────────────

  async function generateReplies(mentionId, btn) {
    try {
      await withButtonFeedback(btn, "Генерирую…", async () => {
        const data = await fetchJson(`/api/mentions/${mentionId}/generate-replies`, { method: "POST" });
        const m = state.mentions.find(x => x.mention_id === mentionId);
        if (m) m.replies = data.replies || [];
        if (state.selectedMention?.mention_id === mentionId) {
          state.selectedMention.replies = data.replies || [];
        }
        showUiNotice("Ответы сгенерированы", "success");
        renderMentionDetail();
      });
    } catch (_e) {
      // withButtonFeedback already showed error via showUiNotice
    }
  }

  async function publishReply(mentionId, replyId, btn) {
    try {
      await withButtonFeedback(btn, "Публикую…", async () => {
        const data = await fetchJson(`/api/mentions/${mentionId}/publish-reply`, {
          method: "POST",
          body: JSON.stringify({ reply_id: replyId }),
        });
        if (data.published) {
          const m = state.mentions.find(x => x.mention_id === mentionId);
          if (m) {
            m.status = "replied";
            const r = (m.replies || []).find(x => x.reply_id === replyId);
            if (r) r.published_at = new Date().toISOString();
          }
          if (state.selectedMention?.mention_id === mentionId) {
            state.selectedMention.status = "replied";
          }
          showUiNotice("Ответ опубликован", "success");
        }
        renderMentionDetail();
      });
    } catch (_e) {
      // withButtonFeedback already showed error via showUiNotice
    }
  }

  async function ignoreMentionAction(mentionId, btn) {
    try {
      await withButtonFeedback(btn, "…", async () => {
        await fetchJson(`/api/mentions/${mentionId}/ignore`, { method: "PATCH" });
        const m = state.mentions.find(x => x.mention_id === mentionId);
        if (m) m.status = "ignored";
        if (state.selectedMention?.mention_id === mentionId) {
          state.selectedMention.status = "ignored";
        }
        state.selectedMention = null;
        loadMentions();
      });
    } catch (_e) {
      // withButtonFeedback already showed error via showUiNotice
    }
  }

  // ── Filter bridge ──────────────────────────────────────────────────────────

  function setMentionsFilter(key, value) {
    state.mentionsFilter[key] = value;
    loadMentions();
  }

  return {
    loadMentions,
    renderMentions,
    openMentionDetail,
    closeMentionDetail,
    generateReplies,
    publishReply,
    ignoreMentionAction,
    setMentionsFilter,
  };
}
