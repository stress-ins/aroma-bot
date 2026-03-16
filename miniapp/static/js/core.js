export function createCoreModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    renderBackButton,
    renderMarkdown,
    getInitDataHeaders,
    getCurrentDraftId,
    timers,
    callbacks,
  } = deps;

  function interactiveCardAttrs(label) {
    return `role="button" tabindex="0" aria-label="${escapeHtml(label)}"`;
  }

  function renderDetailLoader(label = "Открываю карточку", subtitle = "Подгружаю данные и собираю экран.", extraClass = "") {
    return `
      <div class="detail-loader-card${extraClass ? ` ${escapeHtml(extraClass)}` : ""}" aria-live="polite">
        <div class="brand-loader" aria-hidden="true">
          <span class="brand-loader-ring"></span>
          <span class="brand-loader-letter">A</span>
        </div>
        <div class="detail-loader-copy">
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(subtitle)}</span>
        </div>
      </div>
    `;
  }

  function renderPanelLoader(label = "Загружаю данные") {
    return `
      <div class="detail-loader-card panel-loader-card" aria-live="polite">
        <div class="brand-loader" aria-hidden="true">
          <span class="brand-loader-ring"></span>
          <span class="brand-loader-letter">A</span>
        </div>
        <div class="detail-loader-copy">
          <strong>${escapeHtml(label)}</strong>
          <span>Собираю и обновляю содержимое раздела.</span>
        </div>
      </div>
    `;
  }

  function renderPanelError(title, message) {
    return `
      <div class="boot-fallback boot-fallback-inline is-error">
        <div class="boot-fallback-copy">
          <p class="eyebrow">Нужна повторная попытка</p>
          <h2>${escapeHtml(title)}</h2>
          <p>${escapeHtml(message)}</p>
        </div>
        <button class="secondary-button" type="button" onclick="retryCurrentTab()">Повторить</button>
      </div>
    `;
  }

  function renderGuidedState({
    eyebrow = "Следующий шаг",
    title,
    body = "",
    actionLabel = "",
    action = "",
    tone = "soft",
  } = {}) {
    return `
      <div class="guided-state tone-${escapeHtml(tone)}">
        <div class="guided-state-copy">
          <p class="eyebrow">${escapeHtml(eyebrow)}</p>
          <h3>${escapeHtml(title || "Пока ничего не выбрано")}</h3>
          ${body ? `<p>${escapeHtml(body)}</p>` : ""}
        </div>
        ${actionLabel && action ? `<div class="guided-state-actions"><button class="secondary-button" type="button" onclick="${action}">${escapeHtml(actionLabel)}</button></div>` : ""}
      </div>
    `;
  }

  function showUiNotice(message, tone = "info") {
    let notice = document.getElementById("uiNotice");
    if (!notice) {
      notice = document.createElement("div");
      notice.id = "uiNotice";
      notice.className = "ui-notice";
      document.body.appendChild(notice);
    }
    notice.textContent = String(message || "");
    notice.className = `ui-notice is-visible tone-${tone}`;
    window.clearTimeout(timers.getUiNotice());
    timers.setUiNotice(window.setTimeout(() => {
      notice.classList.remove("is-visible");
    }, 2400));
  }

  function renderDetailError(title, message, retryAction = "retryCurrentTab()") {
    return `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="boot-fallback boot-fallback-inline is-error">
          <div class="boot-fallback-copy">
            <p class="eyebrow">Нужна повторная попытка</p>
            <h2>${escapeHtml(title)}</h2>
            <p>${escapeHtml(message)}</p>
          </div>
          <button class="secondary-button" type="button" onclick="${retryAction}">Повторить</button>
        </div>
      </div>
    `;
  }

  function draftSummaryFromDraft(draft) {
    if (!draft) return null;
    return {
      draft_id: draft.draft_id,
      kind: draft.kind,
      topic: draft.topic,
      source: draft.source,
      created_at: draft.created_at,
      status: draft.status,
      feedback: draft.feedback || "",
      preview: draft.preview || "",
      slides_count: draft.slides_count || 0,
      storyboard_count: draft.storyboard_count || 0,
      images_ready: draft.images_ready || 0,
      generation_pending: Boolean(draft.generation_pending),
    };
  }

  function upsertDraftSummary(summary) {
    if (!summary?.draft_id) return;
    state.drafts = [
      summary,
      ...state.drafts.filter((item) => item.draft_id !== summary.draft_id),
    ];
  }

  function draftGenerationLabel(draft) {
    if (!draft?.generation_pending) return "";
    if (draft.kind === "carousel") {
      const stage = String(draft.generation_stage || "").trim();
      const total = Number(draft.slides_count || 0);
      const ready = Number(draft.images_ready || 0);
      if (total && ready >= total) return "";
      if (stage === "images" && total) return "Генерируем картинки";
      return total ? `Ещё генерируется ${ready}/${total}` : "Ещё генерируется";
    }
    if (draft.kind === "reels") {
      const total = Number(draft.storyboard_count || 0);
      const ready = Number(draft.images_ready || 0);
      if (total && ready >= total) return "";
      return total ? `Ещё генерируется ${ready}/${total}` : "Ещё генерируется";
    }
    return "Ещё генерируется";
  }

  function generationStateMarkup(item, kind = "draft") {
    if (!item?.generation_pending) return "";
    const stage = String(item.generation_stage || "").trim();
    if (kind === "draft" && stage === "images") return "";
    if (kind === "draft" && item.kind === "carousel") {
      const payload = item.payload || {};
      if (Array.isArray(payload.slides) && payload.slides.length > 0) return "";
    }
    const message = String(item.generation_message || "").trim();
    const title = kind === "reels"
      ? (stage === "scenario" ? "Собираю сценарий и раскадровку" : stage === "images" ? "Генерирую кадры" : "Собираю рилс")
      : (stage === "slides" ? "Собираю структуру карусели" : stage === "images" ? "Генерирую картинки" : "Собираю карточку");
    return `
      <section class="section section-accent">
        <div class="section-heading">
          <h3>${uiIcon("sparkle")}${escapeHtml(title)}</h3>
          <p>${escapeHtml(message || "Подождите ещё немного, мы обновим карточку автоматически.")}</p>
        </div>
        ${renderDetailLoader(title, message || "Подождите ещё немного, данные догружаются.", "detail-loader-card-compact")}
      </section>
    `;
  }

  function isPendingDraftId(value) {
    return String(value || "").startsWith("pending-");
  }

  function buildPendingDraft(kind, topic) {
    const draftId = `pending-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    return {
      draft_id: draftId,
      kind,
      topic,
      source: "/miniapp",
      created_at: new Date().toISOString(),
      status: "draft",
      feedback: "",
      preview: "Генерируем черновик...",
      slides_count: kind === "carousel" ? 5 : 0,
      storyboard_count: kind === "reels" ? 4 : 0,
      images_ready: 0,
      generation_pending: true,
      payload: {},
    };
  }

  function openPendingDraftCreation(kind, topic) {
    const draft = buildPendingDraft(kind, topic);
    state.pendingCreateRecovery = {
      draft_id: draft.draft_id,
      kind,
      topic,
      started_at: Date.now(),
    };
    state.draftId = draft.draft_id;
    state.selected = draft;
    callbacks.setTab("drafts");
    upsertDraftSummary(draftSummaryFromDraft(draft));
    callbacks.renderDraftList();
    callbacks.renderDraftDetail(draft);
    callbacks.enterDetailView();
    return draft;
  }

  function finalizePendingDraftCreation(draft) {
    if (!draft?.draft_id) return;
    state.pendingCreateRecovery = null;
    state.draftId = draft.draft_id;
    state.selected = draft;
    state.drafts = state.drafts.filter((item) => !isPendingDraftId(item.draft_id));
    upsertDraftSummary(draftSummaryFromDraft(draft));
    callbacks.renderDraftList();
    callbacks.renderDraftDetail(draft);
    callbacks.enterDetailView();
    void callbacks.loadDrafts();
  }

  async function recoverPendingDraftCreation(kind, topic, pendingDraftId) {
    const startedAt = Date.now();
    state.pendingCreateRecovery = {
      draft_id: pendingDraftId,
      kind,
      topic,
      started_at: startedAt,
    };
    for (let attempt = 0; attempt < 8; attempt += 1) {
      try {
        const params = new URLSearchParams();
        params.set("limit", "20");
        params.set("kind", kind);
        const data = await fetchJson(`/api/drafts?${params.toString()}`, { timeout: 20000 });
        state.drafts = (data.items || []).filter((item) => item.draft_id !== pendingDraftId);
        const recovered = state.drafts.find((item) => {
          const createdAt = new Date(item.created_at || 0).getTime();
          return item.kind === kind
            && item.topic === topic
            && item.source === "/miniapp"
            && (Number.isNaN(createdAt) || createdAt >= startedAt - 10_000);
        });
        if (recovered?.draft_id) {
          state.pendingCreateRecovery = null;
          state.draftId = recovered.draft_id;
          callbacks.renderDraftList();
          await callbacks.openDraft(recovered.draft_id);
          return true;
        }
        callbacks.renderDraftList();
      } catch (_error) {
        // Keep pending UI visible while the backend finishes creating the draft.
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    elements.draftDetail.innerHTML = renderDetailError(
      "Черновик создаётся дольше обычного",
      "Мы продолжаем ждать создание карточки. Откройте Черновики ещё раз или повторите позже.",
      "retryCurrentTab()",
    );
    callbacks.syncMobileNavigation();
    return false;
  }

  function mergeDraftIntoState(draft) {
    if (!draft?.draft_id) return;
    state.selected = draft;
    state.draftId = draft.draft_id;
    state.drafts = state.drafts.map((item) => item.draft_id === draft.draft_id ? { ...item, ...draft } : item);
  }

  function mergeReelsIntoState(draft) {
    if (!draft?.draft_id) return;
    state.selectedReels = draft;
    state.reels = state.reels.map((item) => item.draft_id === draft.draft_id ? { ...item, ...draft } : item);
  }

  function setEmptyState(hidden, text = "Ничего не найдено.") {
    elements.emptyState.hidden = hidden;
    if (hidden) {
      elements.emptyState.textContent = "";
    } else if (typeof text === "string") {
      elements.emptyState.textContent = text;
    } else {
      elements.emptyState.innerHTML = renderGuidedState(text || {});
    }
    elements.emptyState.style.display = hidden ? "none" : "block";
  }

  function showBootFallback(title, text, isError = false) {
    if (!elements.bootFallback) return;
    elements.bootFallback.hidden = false;
    elements.bootFallback.classList.toggle("is-error", isError);
    if (elements.bootFallbackTitle) elements.bootFallbackTitle.textContent = title;
    if (elements.bootFallbackText) elements.bootFallbackText.textContent = text;
  }

  function hideBootFallback() {
    if (!elements.bootFallback) return;
    elements.bootFallback.hidden = true;
    elements.bootFallback.classList.remove("is-error");
    document.body.classList.add("app-ready");
    const splash = document.getElementById("splash");
    if (splash) {
      splash.addEventListener("transitionend", () => splash.remove(), { once: true });
    }
  }

  function humanizeRequestMessage(message) {
    if (message === "request_timeout") {
      return "Сервер отвечает слишком долго. Действие могло уже запуститься, проверьте карточку ещё раз.";
    }
    if (message === "Load failed" || message === "Failed to fetch") {
      return "Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.";
    }
    return message;
  }

  function showRequestError(prefix, error) {
    const message = error?.message || String(error || "unknown_error");
    showUiNotice(`${prefix}: ${humanizeRequestMessage(message)}`, "error");
  }

  function showRuntimeWarning(prefix, error) {
    const message = error?.message || String(error || "unknown_error");
    const humanMessage = humanizeRequestMessage(message);
    if (!callbacks.isBootstrapped()) {
      showBootFallback(prefix, humanMessage, true);
      return;
    }
    hideBootFallback();
    setEmptyState(true);
    elements.listTitle.textContent = "Загрузка";
    elements.draftCount.textContent = "";
    elements.draftList.innerHTML = renderPanelError(prefix, humanMessage);
    if (!elements.draftDetail.innerHTML.trim()) {
      elements.draftDetail.innerHTML = renderDetailLoader("Подождите ещё немного");
    }
  }

  async function copyText(value) {
    const text = String(value || "").trim();
    if (!text) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const field = document.createElement("textarea");
        field.value = text;
        field.setAttribute("readonly", "readonly");
        field.style.position = "absolute";
        field.style.left = "-9999px";
        document.body.appendChild(field);
        field.select();
        document.execCommand("copy");
        document.body.removeChild(field);
      }
    } catch (error) {
      showRequestError("Не удалось скопировать промпт", error);
      return;
    }
    const tg = window.Telegram?.WebApp;
    if (tg?.showAlert) tg.showAlert("Промпт скопирован");
    else showUiNotice("Промпт скопирован", "success");
  }

  function showPaywall(tierRequired) {
    const tierLabel = tierRequired === "expert" ? "Эксперт" : "Студент";
    const existing = document.getElementById("paywallModal");
    if (existing) existing.remove();
    const modal = document.createElement("div");
    modal.id = "paywallModal";
    modal.className = "paywall-modal-backdrop";
    modal.innerHTML = `
      <div class="paywall-modal" role="dialog" aria-modal="true" aria-label="Нужен тариф ${escapeHtml(tierLabel)}">
        <div class="paywall-modal-header">
          <span class="paywall-lock">${uiIcon("lock")}</span>
          <h3>Функция доступна с тарифом <strong>${escapeHtml(tierLabel)}</strong></h3>
        </div>
        <div class="paywall-modal-body">
          <p>Введите промокод для активации:</p>
          <div class="paywall-input-row">
            <input id="paywallCodeInput" class="paywall-code-input" type="text" placeholder="AROMA-XXXXX" autocomplete="off" />
            <button id="paywallActivateBtn" class="primary-button" type="button">Активировать</button>
          </div>
          <div id="paywallError" class="paywall-error" hidden></div>
        </div>
        <div class="paywall-modal-footer">
          <button class="secondary-button" type="button" id="paywallCloseBtn">Закрыть</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    const input = modal.querySelector("#paywallCodeInput");
    const activateBtn = modal.querySelector("#paywallActivateBtn");
    const closeBtn = modal.querySelector("#paywallCloseBtn");
    const errorEl = modal.querySelector("#paywallError");

    closeBtn.addEventListener("click", () => modal.remove());
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });

    activateBtn.addEventListener("click", async () => {
      const code = input.value.trim().toUpperCase();
      if (!code) return;
      activateBtn.disabled = true;
      activateBtn.textContent = "Активирую...";
      errorEl.hidden = true;
      try {
        const res = await fetch("/api/promo/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getInitDataHeaders() },
          body: JSON.stringify({ code }),
        });
        if (res.ok) {
          const data = await res.json();
          state.userPlan = { ...state.userPlan, effective_tier: data.tier, trial_ends_at: data.ends_at };
          modal.remove();
          showUiNotice(`Тариф активирован: ${data.tier}`, "success");
        } else {
          const body = await res.json().catch(() => ({}));
          errorEl.textContent = body?.detail === "promo_not_found_or_expired"
            ? "Промокод не найден или уже использован."
            : "Не удалось активировать промокод.";
          errorEl.hidden = false;
          activateBtn.disabled = false;
          activateBtn.textContent = "Активировать";
        }
      } catch (_err) {
        errorEl.textContent = "Ошибка соединения. Попробуйте ещё раз.";
        errorEl.hidden = false;
        activateBtn.disabled = false;
        activateBtn.textContent = "Активировать";
      }
    });

    setTimeout(() => input.focus(), 100);
  }

  function showDailyLimitBanner(used, max) {
    showUiNotice(`Дневной лимит: ${used}/${max} карточек. Попробуйте завтра или активируйте промокод.`, "error");
  }

  async function fetchJson(url, options = {}) {
    const { timeout = 12000, ...fetchOptions } = options;
    const extraHeaders = url.startsWith("/api/") ? getInitDataHeaders() : {};
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    let response;
    try {
      response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...extraHeaders },
        signal: controller.signal,
        ...fetchOptions,
      });
    } catch (error) {
      clearTimeout(timer);
      if (error?.name === "AbortError") throw new Error("request_timeout");
      throw error;
    }
    clearTimeout(timer);
    if (!response.ok) {
      let body = null;
      try { body = await response.json(); } catch (_e) { /* ignore */ }
      if (response.status === 402) {
        const tierRequired = (typeof body?.detail === "object" ? body.detail?.tier_required : null) || "expert";
        showPaywall(tierRequired);
        throw new Error("paywall");
      }
      if (response.status === 429) {
        const detail = typeof body?.detail === "object" ? body.detail : {};
        showDailyLimitBanner(detail?.used ?? 0, detail?.max ?? 10);
        throw new Error("daily_limit");
      }
      const detail = body?.detail ? (typeof body.detail === "string" ? ` (${body.detail})` : "") : "";
      throw new Error(`${response.status} ${response.statusText}${detail}`);
    }
    return response.json();
  }

  async function withButtonFeedback(button, pendingLabel, handler, doneLabel = "Готово") {
    const target = button instanceof HTMLElement ? button : null;
    const originalHtml = target?.innerHTML || "";
    if (target) {
      target.disabled = true;
      target.classList.remove("did-complete", "did-error");
      target.classList.add("is-busy");
      target.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${escapeHtml(pendingLabel)}</span>`;
    }
    try {
      const result = await handler();
      if (target) {
        target.disabled = false;
        target.classList.remove("is-busy");
        target.classList.add("did-complete");
        target.innerHTML = `<span>${escapeHtml(doneLabel)}</span>`;
        window.setTimeout(() => {
          target.classList.remove("did-complete");
          target.innerHTML = originalHtml;
        }, 900);
      }
      return result;
    } catch (error) {
      if (target) {
        target.disabled = false;
        target.classList.remove("is-busy");
        target.classList.add("did-error");
        target.innerHTML = "<span>Ошибка</span>";
        window.setTimeout(() => {
          target.classList.remove("did-error");
          target.innerHTML = originalHtml;
        }, 1200);
      }
      throw error;
    }
  }

  async function updateCurrentDraft(action, payload, button) {
    const currentDraftId = getCurrentDraftId();
    if (!currentDraftId) return;
    const request = async () => fetchJson(`/api/drafts/${currentDraftId}/${action}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const draft = button instanceof HTMLElement
      ? await withButtonFeedback(button, "Сохраняю...", request, "Готово")
      : await request();
    if (state.tab === "reels" || draft.kind === "reels") {
      mergeReelsIntoState(draft);
      callbacks.renderReels();
      callbacks.renderReelsDetail(draft);
      return;
    }
    mergeDraftIntoState(draft);
    callbacks.renderDraftDetail(draft);
    callbacks.renderDraftList();
  }

  function aromaSection(title, content) {
    if (!content) return "";
    const str = String(content);
    if (str.includes("Нет данных") || str.includes("Стоит дополнить")) return "";
    return `<section class="section"><h3>${deps.sectionHeadingIcon(title)}${escapeHtml(title)}</h3><div class="detail-preview detail-markdown">${renderMarkdown(str)}</div></section>`;
  }

  function aromaHtmlSection(title, htmlContent) {
    if (!htmlContent) return "";
    return `<section class="section"><h3>${deps.sectionHeadingIcon(title)}${escapeHtml(title)}</h3><div class="detail-preview passport-preview">${htmlContent}</div></section>`;
  }

  return {
    interactiveCardAttrs,
    renderDetailLoader,
    renderPanelLoader,
    renderPanelError,
    renderGuidedState,
    showUiNotice,
    showPaywall,
    showDailyLimitBanner,
    renderDetailError,
    draftSummaryFromDraft,
    upsertDraftSummary,
    draftGenerationLabel,
    generationStateMarkup,
    isPendingDraftId,
    openPendingDraftCreation,
    finalizePendingDraftCreation,
    recoverPendingDraftCreation,
    mergeDraftIntoState,
    mergeReelsIntoState,
    setEmptyState,
    showBootFallback,
    hideBootFallback,
    showRuntimeWarning,
    copyText,
    fetchJson,
    withButtonFeedback,
    updateCurrentDraft,
    aromaSection,
    aromaHtmlSection,
  };
}
