export function createSettingsModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    actionLabel,
    interactiveCardAttrs,
    renderBackButton,
    renderGuidedState,
    withButtonFeedback,
    fetchJson,
    confirmAction,
    showUiNotice,
    setEmptyState,
    syncMobileNavigation,
    enterDetailView,
  } = deps;

  function keywordFieldEntries(topic) {
    const labels = state.keywords?.field_labels || {};
    const fields = topic?.fields || {};
    return Object.entries(fields).map(([field, items]) => ({
      field,
      label: labels[field] || field,
      items: Array.isArray(items) ? items : [],
    }));
  }

  function renderSettingsSwitcher(activeSection) {
    return `
      <section class="settings-switcher">
        <button class="tab-button${activeSection === "status" ? " active" : ""}" type="button" onclick="openSettingsSection('status')">${uiIcon("gear")}<span>Статус</span></button>
        <button class="tab-button${activeSection === "keywords" ? " active" : ""}" type="button" onclick="openSettingsSection('keywords')">${uiIcon("text")}<span>Ключи</span></button>
        <button class="tab-button${activeSection === "brand" ? " active" : ""}" type="button" onclick="openSettingsSection('brand')">${uiIcon("card")}<span>Бренд</span></button>
        <button class="tab-button${activeSection === "accounts" ? " active" : ""}" type="button" onclick="openSettingsSection('accounts')">${uiIcon("link")}<span>Аккаунты</span></button>
      </section>
    `;
  }

  // ── Brand Voice (Policy Engine) ──────────────────────────────────────────

  async function loadImageModels() {
    try {
      const cfg = await fetchJson("/api/preferences/image-models");
      const carouselSelect = document.getElementById("imageModelCarousel");
      const img2imgSelect = document.getElementById("imageModelImg2img");
      const reelsSelect = document.getElementById("imageModelReels");
      const autoCheckbox = document.getElementById("reelsAutoImages");
      if (carouselSelect) carouselSelect.value = cfg.image_model_carousel;
      if (img2imgSelect) img2imgSelect.value = cfg.image_model_img2img;
      if (reelsSelect) reelsSelect.value = cfg.image_model_reels;
      if (autoCheckbox) autoCheckbox.checked = cfg.reels_auto_images;
    } catch (_err) { /* ignore */ }
  }

  async function saveImageModels() {
    const carouselSelect = document.getElementById("imageModelCarousel");
    const reelsSelect = document.getElementById("imageModelReels");
    const autoCheckbox = document.getElementById("reelsAutoImages");
    try {
      await fetchJson("/api/preferences/image-models", {
        method: "PUT",
        body: JSON.stringify({
          image_model_carousel: carouselSelect?.value || null,
          image_model_reels: reelsSelect?.value || null,
          reels_auto_images: autoCheckbox?.checked ?? false,
        }),
      });
      showUiNotice("Настройки моделей сохранены", "success");
    } catch (_err) {
      showUiNotice("Не удалось сохранить настройки моделей", "error");
    }
  }

  async function loadPolicy() {
    try {
      const cfg = await fetchJson("/api/preferences/policy");
      renderForbiddenPhrases(cfg.forbidden_phrases || []);
      renderRewrites(cfg.soft_rewrites || []);
      renderPlatformTone(cfg.per_platform_tone || {});
    } catch (_err) {
      // fallback: load legacy forbidden phrases
      try {
        const payload = await fetchJson("/api/preferences/forbidden-phrases");
        renderForbiddenPhrases(payload.items || []);
      } catch (_e2) { /* silently ignore */ }
    }
  }

  function renderRewrites(rewrites) {
    const container = document.getElementById("rewritesList");
    if (!container) return;
    const ARROW_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
    const CLOSE_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>`;
    container.innerHTML = (rewrites || []).map((r) => {
      const [pattern, replacement] = r;
      return `<span class="keyword-chip rewrite-chip">
        <span>${escapeHtml(pattern)} ${ARROW_SVG} ${escapeHtml(replacement)}</span>
        <button type="button" aria-label="Удалить замену" onclick='removeRewrite(${JSON.stringify(String(pattern))})'>${CLOSE_SVG}</button>
      </span>`;
    }).join("") || `<span class="plan-entry-hint">Нет авто-замен.</span>`;
  }

  function renderPlatformTone(tone) {
    for (const platform of ["instagram", "telegram", "threads"]) {
      const el = document.getElementById(`tone-${platform}`);
      if (el) el.value = tone[platform] || "";
    }
  }

  async function addRewrite() {
    const patternEl = document.getElementById("rewritePatternInput");
    const replacementEl = document.getElementById("rewriteReplacementInput");
    const pattern = String(patternEl?.value || "").trim();
    const replacement = String(replacementEl?.value || "").trim();
    if (!pattern) { patternEl?.focus(); return; }
    try {
      const cfg = await fetchJson("/api/preferences/policy/rewrites/add", {
        method: "POST",
        body: JSON.stringify({ pattern, replacement }),
      });
      if (patternEl) patternEl.value = "";
      if (replacementEl) replacementEl.value = "";
      renderRewrites(cfg.soft_rewrites || []);
      showUiNotice("Замена добавлена", "success");
    } catch (_err) {
      showUiNotice("Не удалось добавить замену", "error");
    }
  }

  async function removeRewrite(pattern) {
    try {
      const cfg = await fetchJson("/api/preferences/policy/rewrites/remove", {
        method: "POST",
        body: JSON.stringify({ pattern }),
      });
      renderRewrites(cfg.soft_rewrites || []);
      showUiNotice("Замена удалена", "success");
    } catch (_err) {
      showUiNotice("Не удалось удалить замену", "error");
    }
  }

  async function loadUploadPostPrefs() {
    try {
      const data = await fetchJson("/api/preferences/upload-post");
      const userEl = document.getElementById("uploadPostUser");
      const statusEl = document.getElementById("uploadPostKeyStatus");
      if (userEl) userEl.value = data.user || "";
      if (statusEl) statusEl.innerHTML = data.has_key ? `${uiIcon("approve")} Ключ сохранён` : "Ключ не задан";
    } catch (_err) { /* silently ignore */ }
  }

  async function saveUploadPostPrefs() {
    const apiKey = document.getElementById("uploadPostApiKey")?.value || "";
    const user = document.getElementById("uploadPostUser")?.value || "";
    const body = { user };
    if (apiKey) body.api_key = apiKey;
    try {
      const data = await fetchJson("/api/preferences/upload-post", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      const keyEl = document.getElementById("uploadPostApiKey");
      if (keyEl) keyEl.value = "";
      const statusEl = document.getElementById("uploadPostKeyStatus");
      if (statusEl) statusEl.innerHTML = data.has_key ? `${uiIcon("approve")} Ключ сохранён` : "Ключ не задан";
      showUiNotice("Upload-Post настройки сохранены", "success");
    } catch (_err) {
      showUiNotice("Не удалось сохранить настройки", "error");
    }
  }

  async function savePlatformTone(platform) {
    const el = document.getElementById(`tone-${platform}`);
    const value = String(el?.value || "").trim();
    try {
      const cfg = await fetchJson("/api/preferences/policy");
      const tone = { ...(cfg.per_platform_tone || {}), [platform]: value };
      await fetchJson("/api/preferences/policy", {
        method: "PUT",
        body: JSON.stringify({ per_platform_tone: tone }),
      });
      showUiNotice("Тон сохранён", "success");
    } catch (_err) {
      showUiNotice("Не удалось сохранить тон", "error");
    }
  }

  async function loadForbiddenPhrases() {
    try {
      const payload = await fetchJson("/api/preferences/forbidden-phrases");
      renderForbiddenPhrases(payload.items || []);
    } catch (_err) {
      // silently ignore if endpoint not yet available
    }
  }

  function renderForbiddenPhrases(phrases) {
    const container = document.getElementById("forbiddenPhrasesList");
    if (!container) return;
    const closeSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>`;
    container.innerHTML = (phrases || []).map((phrase) => `
      <span class="keyword-chip">
        <span>${escapeHtml(phrase)}</span>
        <button type="button" aria-label="Удалить ${escapeHtml(phrase)}" onclick='removeForbiddenPhrase(${JSON.stringify(String(phrase))})'>${closeSvg}</button>
      </span>
    `).join("") || `<span class="plan-entry-hint">Нет запрещённых фраз.</span>`;
  }

  async function addForbiddenPhrase() {
    const input = document.getElementById("forbiddenPhraseInput");
    const phrase = String(input?.value || "").trim();
    if (!phrase) { input?.focus(); return; }
    try {
      const payload = await fetchJson("/api/preferences/forbidden-phrases/add", {
        method: "POST",
        body: JSON.stringify({ phrase }),
      });
      if (input) input.value = "";
      renderForbiddenPhrases(payload.items || []);
      showUiNotice("Фраза добавлена", "success");
    } catch (err) {
      showUiNotice("Не удалось добавить фразу", "error");
    }
  }

  async function removeForbiddenPhrase(phrase) {
    try {
      const payload = await fetchJson("/api/preferences/forbidden-phrases/remove", {
        method: "POST",
        body: JSON.stringify({ phrase }),
      });
      renderForbiddenPhrases(payload.items || []);
      showUiNotice("Фраза удалена", "success");
    } catch (err) {
      showUiNotice("Не удалось удалить фразу", "error");
    }
  }

  async function addKeywordItem(topicIdx, field, form, button) {
    const input = form?.querySelector("input[name='word']");
    const word = String(input?.value || "").trim();
    if (!word) {
      input?.focus();
      return;
    }
    await withButtonFeedback(button, "Добавляю...", async () => {
      const payload = await fetchJson("/api/keywords/add", {
        method: "POST",
        body: JSON.stringify({ topic_idx: topicIdx, field, word }),
      });
      state.keywords = payload;
      renderKeywords();
    }, "Добавлено");
    showUiNotice("Ключ добавлен", "success");
  }

  async function removeKeywordItem(topicIdx, field, word, button) {
    const confirmed = await confirmAction(`Удалить ключ "${word}"?`);
    if (!confirmed) return;
    await withButtonFeedback(button, "Удаляю...", async () => {
      const payload = await fetchJson("/api/keywords/remove", {
        method: "POST",
        body: JSON.stringify({ topic_idx: topicIdx, field, word }),
      });
      state.keywords = payload;
      renderKeywords();
    }, "Удалено");
    showUiNotice("Ключ удален", "success");
  }

  function openKeywordTopic(topicIdx) {
    state.selectedKeywordTopicIdx = Number(topicIdx);
    renderKeywords();
    enterDetailView();
  }

  async function loadKeywords() {
    state.keywords = await fetchJson("/api/keywords");
    renderKeywords();
  }

  async function loadSettings() {
    if (state.settingsSection === "keywords") {
      if (!state.keywords) {
        state.keywords = await fetchJson("/api/keywords");
      }
      renderKeywords();
      return;
    }
    if (state.settingsSection === "brand") {
      renderBrand();
      return;
    }
    if (state.settingsSection === "accounts") {
      renderAccounts();
      return;
    }
    if (!state.status) {
      state.status = await fetchJson("/api/status");
    }
    renderStatus();
  }

  function renderBrand() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Голос бренда";
    elements.draftList.innerHTML = renderSettingsSwitcher("brand");
    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("card")}<span>Настройки</span></p>
          <h2 class="detail-title">Голос бренда</h2>
        </div>
        <section class="section settings-section">
          <h3>Запрещённые фразы</h3>
          <p class="settings-hint">Эти фразы будут исключены из всех сгенерированных текстов.</p>
          <div id="forbiddenPhrasesList" class="chips-list keyword-items"></div>
          <div class="keyword-form keyword-add-row">
            <input id="forbiddenPhraseInput" type="text" placeholder="Добавить фразу…">
            <button class="secondary-button" type="button" onclick="addForbiddenPhrase()">Добавить</button>
          </div>
        </section>
        <section class="section settings-section">
          <h3>Авто-замены</h3>
          <p class="settings-hint">При генерации текст «было» автоматически заменяется на «стало».</p>
          <div id="rewritesList" class="chips-list keyword-items"></div>
          <div class="keyword-form settings-form-col">
            <div class="keyword-add-row">
              <input id="rewritePatternInput" type="text" placeholder="Было (regex или слово)">
              <input id="rewriteReplacementInput" type="text" placeholder="Стало">
            </div>
            <button class="secondary-button btn-align-start" type="button" onclick="addRewrite()">Добавить замену</button>
          </div>
        </section>
        <section class="section settings-section">
          <h3>Публикация (Upload-Post)</h3>
          <p class="settings-hint">Credentials для публикации через upload-post.com. API-ключ не отображается после сохранения.</p>
          <div class="keyword-field" class="field-mb">
            <strong>API Key</strong>
            <input id="uploadPostApiKey" type="password" placeholder="Введите API-ключ…" class="draft-textarea" class="field-compact">
            <span id="uploadPostKeyStatus" class="plan-entry-hint"></span>
          </div>
          <div class="keyword-field" class="field-mb">
            <strong>Username</strong>
            <input id="uploadPostUser" type="text" placeholder="Имя пользователя upload-post" class="draft-textarea" class="field-compact">
          </div>
          <button class="secondary-button" type="button" onclick="saveUploadPostPrefs()">Сохранить</button>
        </section>
        <section class="section settings-section">
          <h3>Тон по платформам</h3>
          <p class="settings-hint">Описание стиля для AI-редактора. Сохраняется при потере фокуса.</p>
          ${[
            { key: "instagram", label: "Instagram" },
            { key: "telegram",  label: "Telegram"  },
            { key: "threads",   label: "Threads"   },
          ].map(({ key, label }) => `
            <div class="keyword-field" class="field-mb">
              <strong class="platform-label">${uiIcon(key)}<span>${label}</span></strong>
              <textarea id="tone-${key}" class="draft-textarea" rows="2"
                placeholder="Например: personal, visual, emotional"
                onblur='savePlatformTone("${key}")'></textarea>
            </div>
          `).join("")}
        </section>
        <section class="section settings-section">
          <h3>Модели генерации изображений</h3>
          <p class="settings-hint">Выберите AI-модели для генерации изображений в каруселях и рилсах.</p>
          <div class="keyword-field">
            <strong>Карусели (text-to-image)</strong>
            <select id="imageModelCarousel" class="draft-textarea" onchange="saveImageModels()">
              <option value="gpt-image/1.5-text-to-image">GPT Image 1.5</option>
              <option value="google/nano-banana">Nano Banana</option>
            </select>
          </div>
          <div class="keyword-field">
            <strong>Редактирование (image-to-image)</strong>
            <select id="imageModelImg2img" class="draft-textarea" disabled>
              <option value="google/nano-banana-edit">Nano Banana Edit</option>
            </select>
          </div>
          <div class="keyword-field">
            <strong>Рилсы (text-to-image)</strong>
            <select id="imageModelReels" class="draft-textarea" onchange="saveImageModels()">
              <option value="gpt-image/1.5-text-to-image">GPT Image 1.5</option>
              <option value="flux-2/pro-text-to-image">Flux 2 Pro</option>
              <option value="google/nano-banana">Nano Banana</option>
            </select>
          </div>
          <div class="keyword-field">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
              <input type="checkbox" id="reelsAutoImages" onchange="saveImageModels()">
              <span>Автогенерация картинок при создании рилса</span>
            </label>
            <p class="settings-hint" style="margin-top:4px">Если выключено, картинки для кадров генерируются по кнопке вручную.</p>
          </div>
        </section>
      </div>
    `;
    void loadPolicy();
    void loadUploadPostPrefs();
    void loadImageModels();
    enterDetailView();
  }

  function renderStatus() {
    const items = state.status?.items || [];
    const inSettings = state.tab === "settings";
    elements.listTitle.textContent = inSettings ? "Настройки" : "Статус";
    elements.draftCount.textContent = `${items.length} источников`;
    elements.draftList.innerHTML = `
      ${inSettings ? renderSettingsSwitcher("status") : ""}
      ${items.map((item) => `
      <article class="status-card"><strong>${escapeHtml(item.source)}</strong> <span class="${item.enabled ? "status-good" : "status-bad"}">${item.enabled ? "вкл" : "выкл"}</span></article>
    `).join("")}
    `;
    elements.draftDetail.innerHTML = renderBackButton() + (inSettings ? `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("gear")}<span>Настройки</span></p>
          <h2 class="detail-title">Дополнительные параметры</h2>
        </div>
      </div>
    ` : `<div class="detail-empty">${renderGuidedState({
      eyebrow: "Статус",
      title: "Проверьте состояние источников",
      body: "Слева собраны все подключенные источники и их текущее состояние.",
    })}</div>`);
    syncMobileNavigation();
  }

  function renderKeywords() {
    const inSettings = state.tab === "settings";
    const topics = state.keywords?.items || [];
    const selectedTopic = topics.find((topic) => topic.topic_idx === state.selectedKeywordTopicIdx) || null;
    elements.listTitle.textContent = inSettings ? "Настройки" : "Ключи";
    elements.draftCount.textContent = `${topics.length} тем`;
    setEmptyState(topics.length > 0, {
      eyebrow: "Ключи",
      title: "Темы еще не появились",
      body: "Когда словарь загрузится, здесь можно будет редактировать RU/EN ключи и теги.",
    });
    elements.draftList.innerHTML = `
      ${inSettings ? renderSettingsSwitcher("keywords") : ""}
      ${topics.map((topic) => `
      <article ${interactiveCardAttrs(`Открыть тему ${topic.name}`)} class="keyword-topic${topic.topic_idx === state.selectedKeywordTopicIdx ? " active" : ""} interactive-card" onclick="openKeywordTopic(${topic.topic_idx})">
        <h3>${escapeHtml(topic.name)}</h3>
        <div class="draft-meta">
          <span class="tag">${escapeHtml(`${Object.values(topic.fields || {}).reduce((sum, items) => sum + (Array.isArray(items) ? items.length : 0), 0)} ключей`)}</span>
        </div>
      </article>
    `).join("")}
    `;
    if (!selectedTopic) {
      elements.draftDetail.innerHTML = renderBackButton() + `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Ключи",
        title: "Откройте тему для редактирования",
        body: "Внутри темы можно добавлять и удалять RU/EN ключи и теги без выхода из mini app.",
      })}</div>`;
      syncMobileNavigation();
      return;
    }
    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("text")}<span>Ключи</span></p>
          <h2 class="detail-title">${escapeHtml(selectedTopic.name)}</h2>
        </div>
        <section class="section">
          <h3>${uiIcon("card")}Редактор ключей</h3>
          <div class="keyword-fields">
            ${keywordFieldEntries(selectedTopic).map(({ field, label, items }) => `
              <div class="keyword-field">
                <strong>${escapeHtml(label)}</strong>
                <div class="keyword-items">
                  ${items.map((item) => `
                    <span class="keyword-chip">
                      <span>${escapeHtml(item)}</span>
                      <button type="button" aria-label="Удалить ${escapeHtml(item)}" onclick='removeKeywordItem(${selectedTopic.topic_idx}, ${JSON.stringify(String(field))}, ${JSON.stringify(String(item))}, this)'><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
                    </span>
                  `).join("") || `<span class="plan-entry-hint">Пока пусто.</span>`}
                </div>
                <form class="keyword-form" onsubmit='event.preventDefault(); addKeywordItem(${selectedTopic.topic_idx}, ${JSON.stringify(String(field))}, this, this.querySelector("button"));'>
                  <input name="word" type="text" placeholder="Добавить значение" />
                  <button class="secondary-button" type="submit">${actionLabel("plus", "Добавить")}</button>
                </form>
              </div>
            `).join("")}
          </div>
        </section>
      </div>
    `;
    syncMobileNavigation();
  }


  function formatExpiry(isoDate) {
    if (!isoDate) return null;
    try {
      const d = new Date(isoDate);
      return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
    } catch (_) { return null; }
  }

  function accountCardHtml(acc) {
    const icon = uiIcon(acc.platform === "threads" ? "message-circle" : "camera");
    const label = acc.platform === "threads" ? "Threads" : "Instagram";
    const connected = acc.connected;
    const expiry = formatExpiry(acc.expires_at);
    const subtitle = connected
      ? (acc.username ? `ID: ${escapeHtml(acc.username)}` : "Аккаунт подключён") + (expiry ? ` · до ${expiry}` : "")
      : "Не подключено";
    const btn = connected
      ? `<span class="account-badge connected">${uiIcon("check-circle")}<span>Подключено</span></span>`
      : `<button class="primary-button compact connect-btn" type="button" onclick="connectPlatform('${acc.platform}')">${uiIcon("external-link")}<span>Подключить</span></button>`;
    return `
      <article class="account-card">
        <div class="account-card-header">
          <span class="account-platform-icon">${icon}</span>
          <div class="account-card-info">
            <strong>${label}</strong>
            <span class="account-subtitle">${subtitle}</span>
          </div>
          <div class="account-card-action">${btn}</div>
        </div>
      </article>
    `;
  }

  async function renderAccounts() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Аккаунты";
    elements.draftList.innerHTML = renderSettingsSwitcher("accounts");
    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("link")}<span>Настройки</span></p>
          <h2 class="detail-title">Подключённые аккаунты</h2>
        </div>
        <div id="accountsList" class="accounts-list">
          <div class="account-card skeleton"><div class="skeleton-line"></div></div>
        </div>
        <p class="settings-hint" class="settings-hint-text">
          Подключите аккаунты для автоматической публикации контента.
        </p>
      </div>
    `;
    enterDetailView();
    try {
      const data = await fetchJson("/api/social/status");
      const container = document.getElementById("accountsList");
      if (container) {
        container.innerHTML = (data.accounts || []).map(accountCardHtml).join("");
      }
    } catch (_err) {
      const container = document.getElementById("accountsList");
      if (container) container.innerHTML = `<p class="plan-entry-hint">Не удалось загрузить статус аккаунтов.</p>`;
    }
  }

  async function connectPlatform(platform) {
    try {
      const data = await fetchJson(`/api/social/connect-url?platform=${platform}`);
      if (data.url) {
        const tg = window.Telegram?.WebApp;
        if (tg?.openLink) {
          tg.openLink(data.url);
        } else {
          window.open(data.url, "_blank");
        }
      }
    } catch (err) {
      showUiNotice(`Не удалось получить ссылку для ${platform}`, "error");
    }
  }

  return {
    addKeywordItem,
    removeKeywordItem,
    openKeywordTopic,
    loadKeywords,
    loadSettings,
    renderSettingsSwitcher,
    renderStatus,
    renderKeywords,
    renderBrand,
    loadForbiddenPhrases,
    addForbiddenPhrase,
    removeForbiddenPhrase,
    loadPolicy,
    addRewrite,
    removeRewrite,
    savePlatformTone,
    loadUploadPostPrefs,
    saveUploadPostPrefs,
    saveImageModels,
    loadImageModels,
    renderAccounts,
    connectPlatform,
  };
}
