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
    renderGuidedState,
    renderPanelError,
  } = deps;

  // ── State ──────────────────────────────────────────────────────────────────
  if (!state.mentions) state.mentions = [];
  if (!state.mentionsFilter) state.mentionsFilter = { platform: "all", status: "pending" };
  if (!state.selectedMention) state.selectedMention = null;

  // ── Helpers ────────────────────────────────────────────────────────────────

  function platformIcon(platform) {
    const icons = { threads: "at", instagram: "instagram-logo", telegram: "paper-plane-tilt" };
    return icons[platform] || "chat-circle";
  }

  function platformLabel(platform) {
    return { telegram: "Telegram", threads: "Threads", instagram: "Instagram", youtube: "YouTube" }[platform] || platform;
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
      const container = elements.plansContainer || document.getElementById("plans-container");
      if (container) {
        container.innerHTML = renderPanelError("Не удалось загрузить упоминания", "Проверьте соединение и попробуйте ещё раз.");
      }
      return;
    }
    renderMentions();
  }

  // ── Render list ────────────────────────────────────────────────────────────

  function renderMentions() {
    const container = elements.plansContainer || document.getElementById("plans-container");
    if (!container) return;

    // Update mentions count in header
    const count = (state.mentions || []).length;
    if (elements.draftCount) {
      elements.draftCount.textContent = count > 0 ? `${count} шт` : "";
    }

    if (state.selectedMention) {
      renderMentionDetail();
      return;
    }

    const { platform, status } = state.mentionsFilter;
    const platforms = ["all", "telegram", "threads", "instagram", "youtube"];
    const statuses = ["pending", "replied", "ignored", "all"];

    const pendingCount = state.mentions.filter(m => m.status === "pending").length;
    const summaryRow = `
      <div class="mentions-summary">
        <span><strong>${count}</strong> упоминаний</span>
        ${pendingCount > 0 ? `<span class="ms-waiting">${pendingCount} ожидают ответа</span>` : ""}
      </div>`;

    const filterBar = `
      <div class="plans-filter-bar" style="margin-bottom:12px">
        <div style="display:flex;gap:6px;overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none;-webkit-overflow-scrolling:touch">
          ${platforms.map(p => `
            <button class="mf-pill${platform === p ? " active" : ""}"
              data-action="setMentionsFilter" data-args='["platform","${p}"]'>
              ${p === "all" ? "Все платформы" : platformLabel(p)}
            </button>`).join("")}
        </div>
        <div style="display:flex;gap:6px;overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none;-webkit-overflow-scrolling:touch;margin-top:6px">
          ${statuses.map(s => `
            <button class="mf-pill${status === s ? " active" : ""}"
              data-action="setMentionsFilter" data-args='["status","${s}"]'>
              ${statusLabel(s)}
            </button>`).join("")}
        </div>
      </div>`;

    if (!state.mentions.length) {
      const emptyPollBtn = `
        <div style="margin-top:12px;text-align:center">
          <button class="secondary-button compact" data-action="pollMentionsNow">
            <i class="ph ph-arrow-clockwise"></i> Загрузить сейчас
          </button>
        </div>`;
      container.innerHTML = filterBar + renderGuidedState({
        eyebrow: "Упоминания",
        title: "Упоминаний пока нет",
        body: "Здесь появятся упоминания вашего бренда в социальных сетях. Убедитесь что аккаунты для мониторинга настроены.",
        actionLabel: "Настроить мониторинг",
        action: "openSettingsSection",
      }) + emptyPollBtn;
      return;
    }

    const cards = state.mentions.map(m => {
      const statusClass = m.status === "pending" ? "tag-status-warn"
        : m.status === "replied" ? "tag-status-ok"
        : "tag-status-neutral";
      const dimClass = m.status !== "pending" ? " mention-card--dim" : "";
      const checkIcon = m.status === "replied" ? `<i class="ph ph-check" style="font-size:12px"></i> ` : "";
      return `
      <div class="mention-card${dimClass}" data-status="${escapeHtml(m.status)}" data-action="openMentionDetail" data-args='${JSON.stringify([m.mention_id])}'>
        <div class="mention-meta">
          <span class="mention-platform-badge">
            <i class="ph ph-${platformIcon(m.platform)}"></i> ${escapeHtml(platformLabel(m.platform))}
          </span>
          <span class="mention-time">${formatTime(m.received_at)}</span>
          <span class="${statusClass}">${checkIcon}${escapeHtml(statusLabel(m.status))}</span>
        </div>
        <div class="mention-author">@${escapeHtml(m.author_username || m.author_name || "аноним")}</div>
        <div class="mention-preview">${escapeHtml(m.content.substring(0, 120))}${m.content.length > 120 ? "…" : ""}</div>
      </div>`;
    }).join("");

    const pollBtn = `
      <div style="margin-bottom:12px">
        <button class="secondary-button compact" data-action="pollMentionsNow">
          <i class="ph ph-arrow-clockwise"></i> Загрузить сейчас
        </button>
      </div>`;

    container.innerHTML = summaryRow + filterBar + pollBtn + `<div class="mention-list">${cards}</div>`;
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
            statusHtml = `<span class="tag-status-ok"><i class="ph ph-check"></i> Опубликовано · ${toneLabel(r.tone)}</span>`;
          } else if (hasError) {
            statusHtml = `
              <div class="reply-publish-error">
                <span class="tag-status-warn"><i class="ph ph-warning" style="font-size:12px"></i> Ошибка публикации</span>
                <div style="color:var(--danger);font-size:12px;margin-top:4px">${escapeHtml(r.publish_error)}</div>
                <button class="secondary-button compact" style="margin-top:6px"
                  data-action="publishReply" data-args='${JSON.stringify([m.mention_id, r.reply_id, null])}'>
                  <i class="ph ph-arrow-clockwise"></i> Повторить
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
            <i class="ph ph-${platformIcon(m.platform)}"></i> ${escapeHtml(platformLabel(m.platform))}
          </span>
          <span class="mention-time">${formatTime(m.received_at)}</span>
          <span class="tag-status-${m.status === "pending" ? "warn" : "ok"}">${escapeHtml(statusLabel(m.status))}</span>
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
          <i class="ph ph-sparkle"></i> Сгенерировать ответы
        </button>
        <button class="secondary-button" data-action="ignoreMentionAction" data-args='${JSON.stringify([m.mention_id, null])}'
          ${m.status === "replied" ? "disabled" : ""}>
          <i class="ph ph-eye-slash"></i> Игнорировать
        </button>
      </div>` : ""}
      <div class="reply-list" id="reply-list-${m.mention_id}">
        ${repliesHtml}
      </div>`;

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

  // ── Poll now ───────────────────────────────────────────────────────────────

  async function pollMentionsNow(btn) {
    try {
      await withButtonFeedback(btn, "Загрузка…", async () => {
        const data = await fetchJson("/api/mentions/poll-threads", { method: "POST" });
        const count = data.new_count ?? data.count ?? 0;
        showUiNotice(count > 0 ? `Загружено ${count} новых упоминаний` : "Новых упоминаний нет", count > 0 ? "success" : "info");
        await loadMentions();
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
    pollMentionsNow,
  };
}
