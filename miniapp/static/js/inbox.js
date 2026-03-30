/**
 * Inbox module — Instagram DM conversations and chat-style messages.
 * Pattern: createInboxModule(deps) matching createMentionsModule.
 */
export function createInboxModule(deps) {
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
  if (!state.inboxConversations) state.inboxConversations = [];
  if (!state.inboxFilter) state.inboxFilter = { status: "active" };
  if (!state.selectedConversation) state.selectedConversation = null;

  // ── Helpers ────────────────────────────────────────────────────────────────

  function avatarHtml(url, size, iconSize) {
    if (url) {
      return '<img src="' + escapeHtml(url) + '" alt="" style="width:100%;height:100%;border-radius:50%;object-fit:cover">';
    }
    return '<i class="ph ph-user" style="font-size:' + iconSize + 'px;color:var(--muted)"></i>';
  }


  function formatTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "";
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return "только что";
    if (diff < 3600000) return `${Math.floor(diff / 60000)} мин`;
    if (diff < 86400000) return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
  }

  function formatMessageTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  function toneLabel(tone) {
    return { official: "Официальный", warm: "Тёплый", provocative: "Провокационный" }[tone] || tone;
  }

  // ── Load ───────────────────────────────────────────────────────────────────

  let _initialPollDone = false;

  async function loadInbox() {
    const { status } = state.inboxFilter;
    try {
      const data = await fetchJson(`/api/inbox?status=${status}&limit=50`);
      state.inboxConversations = data.items || [];
    } catch (e) {
      state.inboxConversations = [];
      const container = elements.plansContainer || document.getElementById("plans-container");
      if (container) {
        container.innerHTML = renderPanelError("Не удалось загрузить входящие", "Проверьте соединение и попробуйте ещё раз.");
      }
      return;
    }
    renderInbox();

    // Auto-poll on first load if inbox is empty
    if (!_initialPollDone && state.inboxConversations.length === 0) {
      _initialPollDone = true;
      try {
        await fetchJson("/api/inbox/poll", { method: "POST" });
        const fresh = await fetchJson(`/api/inbox?status=${status}&limit=50`);
        state.inboxConversations = fresh.items || [];
        renderInbox();
      } catch (_) { /* poll failed silently */ }
    }
    _initialPollDone = true;
  }

  // ── Render conversation list ───────────────────────────────────────────────

  function renderInbox() {
    const container = elements.plansContainer || document.getElementById("plans-container");
    if (!container) return;

    const count = (state.inboxConversations || []).length;
    if (elements.draftCount) {
      elements.draftCount.textContent = count > 0 ? `${count} шт` : "";
    }

    if (state.selectedConversation) {
      renderConversationDetail();
      return;
    }

    const { status } = state.inboxFilter;
    const statuses = ["active", "archived", "all"];

    const unreadCount = state.inboxConversations.filter(c => c.unread_count > 0).length;
    const summaryRow = `
      <div class="inbox-summary">
        <span><strong>${count}</strong> диалогов</span>
        ${unreadCount > 0 ? `<span class="ms-waiting">${unreadCount} непрочитанных</span>` : ""}
      </div>`;

    const filterBar = `
      <div class="plans-filter-bar" style="margin-bottom:12px">
        <div style="display:flex;gap:6px;align-items:center">
          ${statuses.map(s => `
            <button class="mf-pill${status === s ? " active" : ""}"
              data-action="setInboxFilter" data-args='["status","${s}"]'>
              ${s === "active" ? "Активные" : s === "archived" ? "Архив" : "Все"}
            </button>`).join("")}
          <button class="secondary-button compact" style="margin-left:auto"
            data-action="pollInbox" data-args='[null]'>
            <i class="ph ph-arrows-clockwise"></i> Обновить
          </button>
        </div>
      </div>`;

    if (!state.inboxConversations.length) {
      container.innerHTML = filterBar + renderGuidedState({
        eyebrow: "Входящие",
        title: "Входящих пока нет",
        body: "Здесь появятся DM-сообщения из Instagram. Убедитесь что Instagram-аккаунт подключён.",
        actionLabel: "Настроить аккаунт",
        action: "openSettingsSection",
      });
      return;
    }

    const cards = state.inboxConversations.map(c => {
      const unreadBadge = c.unread_count > 0
        ? `<span class="inbox-unread-badge">${c.unread_count}</span>`
        : "";
      const dimClass = c.status === "archived" ? " inbox-card--dim" : "";
      return `
      <div class="inbox-card${dimClass}" data-action="openConversation" data-args='["${c.conversation_id}"]'>
        <div class="inbox-card-avatar">
          ${avatarHtml(c.profile_picture_url, 40, 20)}
        </div>
        <div class="inbox-card-body">
          <div class="inbox-card-header">
            <span class="inbox-card-name">${escapeHtml(c.participant_name || c.participant_username || "Пользователь")}</span>
            <span class="inbox-card-time">${formatTime(c.last_message_at)}</span>
          </div>
          <div class="inbox-card-preview">
            ${escapeHtml((c.last_message_preview || "").substring(0, 100))}${(c.last_message_preview || "").length > 100 ? "..." : ""}
          </div>
        </div>
        ${unreadBadge}
      </div>`;
    }).join("");

    container.innerHTML = summaryRow + filterBar + `<div class="inbox-list">${cards}</div>`;
  }

  // ── Conversation detail (chat view) ────────────────────────────────────────

  async function openConversation(conversationId) {
    try {
      const detail = await fetchJson(`/api/inbox/${conversationId}`);
      state.selectedConversation = detail;
    } catch (_e) {
      const c = state.inboxConversations.find(x => x.conversation_id === conversationId);
      if (!c) return;
      state.selectedConversation = { ...c, messages: [] };
    }
    enterDetailView();
    renderConversationDetail();
  }

  function closeConversation() {
    state.selectedConversation = null;
    loadInbox();
  }

  function renderConversationDetail() {
    const c = state.selectedConversation;
    if (!c) return;
    const container = elements.draftDetail || document.getElementById("draftDetail");
    if (!container) return;

    const messages = c.messages || [];
    const messagesHtml = messages.length
      ? messages.map(m => {
          const isOutgoing = m.sender_type === "business";
          const bubbleClass = isOutgoing ? "inbox-bubble--outgoing" : "inbox-bubble--incoming";
          return `
          <div class="inbox-bubble ${bubbleClass}">
            <div class="inbox-bubble-content">${escapeHtml(m.content)}</div>
            <div class="inbox-bubble-time">${formatMessageTime(m.sent_at)}</div>
          </div>`;
        }).join("")
      : `<p class="field-help" style="text-align:center;padding:24px">Нет сообщений</p>`;

    const aiRepliesHtml = c._aiReplies
      ? `<div class="inbox-ai-replies">
          <div style="font-size:12px;font-weight:600;color:var(--muted);margin-bottom:8px">Варианты ответа:</div>
          ${c._aiReplies.map((r, i) => `
            <div class="reply-option">
              <div class="reply-tone-badge">${toneLabel(r.tone)}</div>
              <div class="reply-text">${escapeHtml(r.content)}</div>
              <button class="primary-button compact" data-action="useAiReply" data-args='${JSON.stringify([c.conversation_id, i, null])}'>
                Использовать
              </button>
            </div>
          `).join("")}
        </div>`
      : "";

    container.innerHTML = `
      ${renderBackButton()}
      <div class="inbox-chat-header">
        <div class="inbox-chat-avatar">
          ${avatarHtml(c.profile_picture_url, 36, 18)}
        </div>
        <div>
          <div class="inbox-chat-name">${escapeHtml(c.participant_name || c.participant_username || "Пользователь")}</div>
          <div class="inbox-chat-username">@${escapeHtml(c.participant_username || "")}</div>
        </div>
        <div style="margin-left:auto;display:flex;gap:6px">
          <button class="secondary-button compact" data-action="archiveConversation" data-args='${JSON.stringify([c.conversation_id, null])}'>
            <i class="ph ph-archive"></i>
          </button>
        </div>
      </div>

      <div class="inbox-messages" id="inbox-messages-container">
        ${messagesHtml}
      </div>

      ${aiRepliesHtml}

      <div class="inbox-compose">
        <div class="inbox-compose-row">
          <textarea class="inbox-compose-input" id="inbox-reply-input" rows="2"
            placeholder="Написать ответ..." data-on-keydown="sendInboxReplyOnEnter"
            data-keydown-guard="Enter"></textarea>
        </div>
        <div class="inbox-compose-actions">
          <button class="secondary-button compact" data-action="generateInboxReply" data-args='${JSON.stringify([c.conversation_id, null])}'>
            <i class="ph ph-sparkle"></i> AI-ответ
          </button>
          <button class="primary-button compact" data-action="sendInboxReply" data-args='${JSON.stringify([c.conversation_id, null])}'>
            <i class="ph ph-paper-plane-right"></i> Отправить
          </button>
        </div>
      </div>`;

    // Scroll to bottom of messages
    requestAnimationFrame(() => {
      const msgContainer = document.getElementById("inbox-messages-container");
      if (msgContainer) msgContainer.scrollTop = msgContainer.scrollHeight;
    });
  }

  // ── Actions ────────────────────────────────────────────────────────────────

  async function sendInboxReply(conversationId, btn) {
    const input = document.getElementById("inbox-reply-input");
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    try {
      await withButtonFeedback(btn, "Отправка...", async () => {
        const data = await fetchJson(`/api/inbox/${conversationId}/reply`, {
          method: "POST",
          body: JSON.stringify({ text }),
        });
        if (data.sent) {
          input.value = "";
          // Add message to local state
          if (state.selectedConversation) {
            if (!state.selectedConversation.messages) state.selectedConversation.messages = [];
            state.selectedConversation.messages.push({
              message_id: data.message_id,
              conversation_id: conversationId,
              sender_type: "business",
              content: text,
              sent_at: new Date().toISOString(),
            });
            state.selectedConversation._aiReplies = null;
          }
          showUiNotice("Сообщение отправлено", "success");
          renderConversationDetail();
        } else {
          showUiNotice(`Ошибка отправки: ${data.error}`, "error");
        }
      });
    } catch (_e) { /* handled */ }
  }

  function sendInboxReplyOnEnter(value, el) {
    if (!el) return;
    const conversationId = state.selectedConversation?.conversation_id;
    if (!conversationId) return;
    // Find the send button
    const sendBtn = el.closest(".inbox-compose")?.querySelector("[data-action='sendInboxReply']");
    sendInboxReply(conversationId, sendBtn);
  }

  async function generateInboxReply(conversationId, btn) {
    try {
      await withButtonFeedback(btn, "Генерирую...", async () => {
        const data = await fetchJson(`/api/inbox/${conversationId}/generate-reply`, {
          method: "POST",
        });
        if (state.selectedConversation?.conversation_id === conversationId) {
          state.selectedConversation._aiReplies = data.replies || [];
        }
        showUiNotice("Варианты ответа готовы", "success");
        renderConversationDetail();
      });
    } catch (_e) { /* handled */ }
  }

  function useAiReply(conversationId, replyIndex) {
    const replies = state.selectedConversation?._aiReplies;
    if (!replies || !replies[replyIndex]) return;
    const input = document.getElementById("inbox-reply-input");
    if (input) {
      input.value = replies[replyIndex].content;
      input.focus();
    }
  }

  async function archiveConversation(conversationId, btn) {
    try {
      await withButtonFeedback(btn, "...", async () => {
        await fetchJson(`/api/inbox/${conversationId}/archive`, { method: "POST" });
        showUiNotice("Диалог архивирован", "success");
        state.selectedConversation = null;
        loadInbox();
      });
    } catch (_e) { /* handled */ }
  }

  async function pollInbox(btn) {
    try {
      await withButtonFeedback(btn, "Обновление...", async () => {
        const data = await fetchJson("/api/inbox/poll", { method: "POST" });
        showUiNotice(
          `Найдено ${data.conversations_polled} диалогов, ${data.messages_saved} новых сообщений`,
          "success"
        );
        await loadInbox();
      });
    } catch (_e) { /* handled */ }
  }

  // ── Filter ─────────────────────────────────────────────────────────────────

  function setInboxFilter(key, value) {
    state.inboxFilter[key] = value;
    loadInbox();
  }

  return {
    loadInbox,
    renderInbox,
    openConversation,
    closeConversation,
    sendInboxReply,
    sendInboxReplyOnEnter,
    generateInboxReply,
    useAiReply,
    archiveConversation,
    pollInbox,
    setInboxFilter,
  };
}
