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
      renderMentionDetail(container);
      return;
    }

    const { platform, status } = state.mentionsFilter;
    const platforms = ["all", "telegram", "threads", "instagram"];
    const statuses = ["pending", "replied", "ignored", "all"];

    const filterBar = `
      <div class="plans-filter-bar" style="margin-bottom:12px">
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          ${platforms.map(p => `
            <button class="filter-chip${platform === p ? " active" : ""}"
              onclick="setMentionsFilter('platform','${p}')">
              ${p === "all" ? "Все платформы" : platformLabel(p)}
            </button>`).join("")}
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
          ${statuses.map(s => `
            <button class="filter-chip${status === s ? " active" : ""}"
              onclick="setMentionsFilter('status','${s}')">
              ${statusLabel(s)}
            </button>`).join("")}
        </div>
      </div>`;

    if (!state.mentions.length) {
      container.innerHTML = filterBar + `<div class="empty-state"><p>Нет упоминаний</p></div>`;
      return;
    }

    const cards = state.mentions.map(m => `
      <div class="mention-card" onclick="openMentionDetail('${m.mention_id}')">
        <div class="mention-meta">
          <span class="mention-platform-badge">
            <i data-lucide="${platformIcon(m.platform)}"></i> ${platformLabel(m.platform)}
          </span>
          <span class="mention-time">${formatTime(m.received_at)}</span>
          <span class="tag-status-${m.status === "pending" ? "warn" : "ok"}">${statusLabel(m.status)}</span>
        </div>
        <div class="mention-author">@${escapeHtml(m.author_username || m.author_name || "аноним")}</div>
        <div class="mention-preview">${escapeHtml(m.content.substring(0, 120))}${m.content.length > 120 ? "…" : ""}</div>
      </div>`).join("");

    container.innerHTML = filterBar + `<div class="mention-list">${cards}</div>`;
    if (window.lucide) lucide.createIcons();
  }

  // ── Detail view ────────────────────────────────────────────────────────────

  function openMentionDetail(mentionId) {
    const m = state.mentions.find(x => x.mention_id === mentionId);
    if (!m) return;
    state.selectedMention = m;
    renderMentionDetail(
      elements.plansContainer || document.getElementById("plans-container")
    );
  }

  function closeMentionDetail() {
    state.selectedMention = null;
    renderMentions();
  }

  function renderMentionDetail(container) {
    const m = state.selectedMention;
    if (!m) return;

    const repliesHtml = m.replies && m.replies.length
      ? m.replies.map(r => `
          <div class="reply-option${r.selected ? " is-selected" : ""}">
            <div class="reply-tone-badge">${toneLabel(r.tone)}</div>
            <div class="reply-text">${escapeHtml(r.content)}</div>
            <div class="reply-length">${r.content.length} символов</div>
            ${!r.published_at ? `
              <button class="btn btn-sm btn-primary"
                onclick="publishReply('${m.mention_id}','${r.reply_id}',this)">
                Опубликовать
              </button>` : `<span class="tag-status-ok">Опубликовано</span>`}
            ${r.publish_error ? `<div class="error-text">${escapeHtml(r.publish_error)}</div>` : ""}
          </div>`).join("")
      : `<p class="hint-text">Ещё нет ответов. Нажми «Сгенерировать».</p>`;

    container.innerHTML = `
      <button class="btn btn-ghost btn-back" onclick="closeMentionDetail()">
        ← Назад
      </button>
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
      <div class="mention-actions" style="display:flex;gap:8px;margin:12px 0">
        <button class="btn btn-primary" onclick="generateReplies('${m.mention_id}',this)">
          <i data-lucide="sparkles"></i> Сгенерировать ответы
        </button>
        ${m.status === "pending" ? `
          <button class="btn btn-ghost" onclick="ignoreMentionAction('${m.mention_id}',this)">
            <i data-lucide="eye-off"></i> Игнорировать
          </button>` : ""}
      </div>
      <div class="reply-list" id="reply-list-${m.mention_id}">
        ${repliesHtml}
      </div>`;

    if (window.lucide) lucide.createIcons();
  }

  // ── Actions ────────────────────────────────────────────────────────────────

  async function generateReplies(mentionId, btn) {
    await withButtonFeedback(btn, "Генерирую…", async () => {
      const data = await fetchJson(`/api/mentions/${mentionId}/generate-replies`, { method: "POST" });
      // Update in state
      const m = state.mentions.find(x => x.mention_id === mentionId);
      if (m) m.replies = data.replies || [];
      if (state.selectedMention?.mention_id === mentionId) {
        state.selectedMention.replies = data.replies || [];
      }
      renderMentionDetail(
        elements.plansContainer || document.getElementById("plans-container")
      );
    });
  }

  async function publishReply(mentionId, replyId, btn) {
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
      }
      renderMentionDetail(
        elements.plansContainer || document.getElementById("plans-container")
      );
    });
  }

  async function ignoreMentionAction(mentionId, btn) {
    await withButtonFeedback(btn, "…", async () => {
      await fetchJson(`/api/mentions/${mentionId}/ignore`, { method: "PATCH" });
      const m = state.mentions.find(x => x.mention_id === mentionId);
      if (m) m.status = "ignored";
      if (state.selectedMention?.mention_id === mentionId) {
        state.selectedMention.status = "ignored";
      }
      state.selectedMention = null;
      renderMentions();
    });
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
