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
    applyTheme,
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
    // Legacy — kept for backward compat but unused
    return "";
  }

  function settingsMenuRow(icon, color, title, section, badge) {
    const badgeHtml = badge != null ? `<span class="settings-menu-badge">${escapeHtml(String(badge))}</span>` : "";
    return `<div class="settings-menu-row" data-action="openSettingsSection" data-args='${JSON.stringify([section])}'>
      <span class="settings-menu-icon" style="background:${color}"><i class="ph ph-${icon}"></i></span>
      <span class="settings-menu-text">${escapeHtml(title)}</span>
      ${badgeHtml}
      <span class="settings-menu-chevron"><i class="ph ph-caret-right"></i></span>
    </div>`;
  }

  async function renderSettingsMenu() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "";

    let planRes, teamsRes, socialRes, statusRes, adminRes, hashtagsRes, monitoredRes;
    try {
      [planRes, teamsRes, socialRes, statusRes, adminRes, hashtagsRes, monitoredRes] = await Promise.allSettled([
        fetchJson("/api/user/plan"),
        fetchJson("/api/teams"),
        fetchJson("/api/social/status"),
        fetchJson("/api/status"),
        fetchJson("/api/admin/promos"),
        fetchJson("/api/social/tracked-hashtags"),
        fetchJson("/api/social/monitored-accounts"),
      ]);
    } catch (_err) {
      elements.draftList.innerHTML = `<div class="detail-empty">${renderGuidedState({
        eyebrow: "",
        title: "Не удалось загрузить настройки",
        body: "Проверьте подключение к интернету и попробуйте ещё раз.",
      })}</div>`;
      return;
    }

    const teamCount = teamsRes.status === "fulfilled" ? (teamsRes.value?.items || []).reduce((n, t) => n + (t.member_count || 1), 0) : null;
    const connectedCount = socialRes.status === "fulfilled" ? (socialRes.value?.accounts || []).filter((a) => a.connected).length : null;
    const enabledCount = statusRes.status === "fulfilled" ? (statusRes.value?.items || []).filter((i) => i.enabled).length : null;
    const isAdmin = adminRes.status === "fulfilled";
    const hashtagCount = hashtagsRes.status === "fulfilled" ? (hashtagsRes.value?.items || []).length : null;
    const monitoredCount = monitoredRes.status === "fulfilled"
      ? ((monitoredRes.value?.instagram || []).length + (monitoredRes.value?.threads || []).length) || null
      : null;

    let html = `<div class="settings-menu">`;

    // Group: Подписка
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Подписка</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("ticket", "#AF52DE", "Подписка", "promo", isAdmin ? "admin" : null)}
      </div>
    </div>`;

    // Group: Управление
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Управление</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("users", "#007AFF", "Команда", "team", teamCount)}
      </div>
    </div>`;

    // Group: Контент
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Контент</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("palette", "#FF9500", "Бренд и ключи", "brand", null)}
        ${settingsMenuRow("link", "#34C759", "Аккаунты", "accounts", connectedCount)}
        ${settingsMenuRow("hash", "#5856D6", "Теги для мониторинга", "hashtags", hashtagCount)}
        ${settingsMenuRow("eye", "#00C7BE", "Аккаунты на мониторинг", "monitored", monitoredCount)}
      </div>
    </div>`;

    // Group: Система
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Система</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("paint-brush", "#FF9500", "Цветовая тема", "theme", null)}
        ${settingsMenuRow("map-pin", "#FF6B6B", "Город", "city", null)}
        ${settingsMenuRow("activity", "#FF3B30", "Источники данных", "status", enabledCount)}
        ${settingsMenuRow("gauge", "#8E8E93", "Очереди", "admin_dashboard", null)}
      </div>
    </div>`;

    html += `</div>`;
    elements.draftList.innerHTML = html;

    elements.draftDetail.innerHTML = `<div class="detail-empty">${renderGuidedState({
      eyebrow: "",
      title: "Выберите раздел",
      body: "Нажмите на пункт меню слева, чтобы перейти к настройкам.",
    })}</div>`;

    syncMobileNavigation();
  }

  function goBackToSettings() {
    state.settingsInDetail = false;
    state.settingsSection = null;
    state.selectedKeywordTopicIdx = null;
    state.mobileView = "list";
    loadSettings();
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
    const ARROW_SVG = `<i class="ph ph-arrow-right" style="font-size:12px"></i>`;
    const CLOSE_SVG = `<i class="ph ph-x" style="font-size:14px"></i>`;
    container.innerHTML = (rewrites || []).map((r) => {
      const [pattern, replacement] = r;
      return `<span class="keyword-chip rewrite-chip">
        <span>${escapeHtml(pattern)} ${ARROW_SVG} ${escapeHtml(replacement)}</span>
        <button type="button" aria-label="Удалить замену" data-action="removeRewrite" data-args='${JSON.stringify([String(pattern)])}'>${CLOSE_SVG}</button>
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

  // NOTE: GET → PUT has a theoretical race if two platforms are saved
  // concurrently, but blur-triggered saves are sequential in practice.
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
        <button type="button" aria-label="Удалить ${escapeHtml(phrase)}" data-action="removeForbiddenPhrase" data-args='${JSON.stringify([String(phrase)])}'>${closeSvg}</button>
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
    if (state.settingsInDetail && state.settingsSection) {
      if (state.settingsSection === "keywords" || state.settingsSection === "brand") {
        if (!state.keywords) {
          state.keywords = await fetchJson("/api/keywords");
        }
        renderBrandAndKeywords();
        return;
      }
      if (state.settingsSection === "team") {
        renderTeam();
        return;
      }
      if (state.settingsSection === "promo") {
        renderPromo();
        return;
      }
      if (state.settingsSection === "accounts") {
        renderAccounts();
        return;
      }
      if (state.settingsSection === "hashtags") {
        renderTrackedHashtags();
        return;
      }
      if (state.settingsSection === "monitored") {
        renderMonitoredAccounts();
        return;
      }
      if (state.settingsSection === "status") {
        if (!state.status) {
          state.status = await fetchJson("/api/status");
        }
        renderStatus();
        return;
      }
      if (state.settingsSection === "theme") {
        await renderTheme();
        return;
      }
      if (state.settingsSection === "city") {
        await renderCity();
        return;
      }
      if (state.settingsSection === "admin_dashboard") {
        await renderAdminDashboard();
        return;
      }
    }
    // Default: render the menu
    state.settingsInDetail = false;
    await renderSettingsMenu();
  }

  function renderBrand() {
    // Redirect to merged brand+keywords view
    renderBrandAndKeywords();
  }

  function renderBrandAndKeywords() {
    const topics = state.keywords?.items || [];
    const selectedTopic = topics.find((t) => t.topic_idx === state.selectedKeywordTopicIdx) || null;

    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Бренд и ключи";

    // Left panel: keyword topics list
    elements.draftList.innerHTML = `
      <button class="back-button" type="button" data-action="goBackToSettings">${uiIcon("arrow-left")}<span>Назад</span></button>
      ${topics.map((topic) => `
      <article ${interactiveCardAttrs(`Открыть тему ${topic.name}`)} class="keyword-topic${topic.topic_idx === state.selectedKeywordTopicIdx ? " active" : ""} interactive-card" data-action="openKeywordTopic" data-args='${JSON.stringify([topic.topic_idx])}'>
        <h3>${escapeHtml(topic.name)}</h3>
        <div class="draft-meta">
          <span class="tag">${escapeHtml(`${Object.values(topic.fields || {}).reduce((sum, items) => sum + (Array.isArray(items) ? items.length : 0), 0)} ключей`)}</span>
        </div>
      </article>
    `).join("")}
    `;

    // Right panel: brand settings + selected keyword topic
    let keywordsDetailHtml = "";
    if (selectedTopic) {
      keywordsDetailHtml = `
        <section class="section settings-section">
          <h3>${uiIcon("text")}<span>Ключи: ${escapeHtml(selectedTopic.name)}</span></h3>
          <div class="keyword-fields">
            ${keywordFieldEntries(selectedTopic).map(({ field, label, items }) => `
              <div class="keyword-field">
                <strong>${escapeHtml(label)}</strong>
                <div class="keyword-items">
                  ${items.map((item) => `
                    <span class="keyword-chip">
                      <span>${escapeHtml(item)}</span>
                      <button type="button" aria-label="Удалить ${escapeHtml(item)}" data-action="removeKeywordItem" data-args='${JSON.stringify([selectedTopic.topic_idx, String(field), String(item), null])}'><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
                    </span>
                  `).join("") || `<span class="plan-entry-hint">Пока пусто.</span>`}
                </div>
                <form class="keyword-form" data-on-submit="addKeywordItem" data-args='${JSON.stringify([selectedTopic.topic_idx, String(field)])}'>
                  <input name="word" type="text" placeholder="Добавить значение" />
                  <button class="secondary-button" type="submit">${actionLabel("plus", "Добавить")}</button>
                </form>
              </div>
            `).join("")}
          </div>
        </section>
      `;
    }

    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("palette")}<span>Настройки</span></p>
          <h2 class="detail-title">Бренд и ключи</h2>
        </div>
        <section class="section settings-section">
          <h3>Запрещённые фразы</h3>
          <p class="settings-hint">Эти фразы будут исключены из всех сгенерированных текстов.</p>
          <div id="forbiddenPhrasesList" class="chips-list keyword-items"></div>
          <div class="keyword-form keyword-add-row">
            <input id="forbiddenPhraseInput" type="text" placeholder="Добавить фразу…">
            <button class="secondary-button" type="button" data-action="addForbiddenPhrase">Добавить</button>
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
            <button class="secondary-button btn-align-start" type="button" data-action="addRewrite">Добавить замену</button>
          </div>
        </section>
        <section class="section settings-section">
          <h3>Тон по платформам</h3>
          <p class="settings-hint">Описание стиля для AI-редактора. Сохраняется при потере фокуса.</p>
          ${[
            { key: "instagram", label: "Instagram" },
            { key: "telegram",  label: "Telegram"  },
            { key: "threads",   label: "Threads"   },
          ].map(({ key, label }) => `
            <div class="keyword-field">
              <strong class="platform-label">${uiIcon(key)}<span>${label}</span></strong>
              <textarea id="tone-${key}" class="draft-textarea" rows="2"
                placeholder="Например: personal, visual, emotional"
                data-on-blur="savePlatformTone" data-args='${JSON.stringify([key])}'></textarea>
            </div>
          `).join("")}
        </section>
        <section class="section settings-section">
          <h3>Модели генерации изображений</h3>
          <p class="settings-hint">Выберите AI-модели для генерации изображений в каруселях и рилсах.</p>
          <div class="keyword-field">
            <strong>Карусели (text-to-image)</strong>
            <select id="imageModelCarousel" class="draft-textarea" data-on-change="saveImageModels">
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
            <select id="imageModelReels" class="draft-textarea" data-on-change="saveImageModels">
              <option value="gpt-image/1.5-text-to-image">GPT Image 1.5</option>
              <option value="flux-2/pro-text-to-image">Flux 2 Pro</option>
              <option value="google/nano-banana">Nano Banana</option>
            </select>
          </div>
          <div class="keyword-field">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
              <input type="checkbox" id="reelsAutoImages" data-on-change="saveImageModels">
              <span>Автогенерация картинок при создании рилса</span>
            </label>
            <p class="settings-hint" style="margin-top:4px">Если выключено, картинки для кадров генерируются по кнопке вручную.</p>
          </div>
        </section>
        ${keywordsDetailHtml}
      </div>
    `;
    void loadPolicy();
    void loadImageModels();
    enterDetailView();
  }

  const SOURCE_LABELS = {
    google_trends_ru: "Google Trends (RU)",
    google_trends_en: "Google Trends (EN)",
    youtube: "YouTube",
    reddit: "Reddit",
    telegram_channels: "Telegram-каналы",
    twitter: "X (Twitter)",
    instagram: "Instagram",
    vk: "ВКонтакте",
    wordstat: "Яндекс Wordstat",
    tiktok: "TikTok (Global)",
    tiktok_ru: "TikTok (RU)",
    threads: "Threads",
    ai_recommendations: "AI-рекомендации",
  };
  function _sourceLabel(key) { return SOURCE_LABELS[key] || key; }

  function renderStatus() {
    const items = state.status?.items || [];
    const inSettings = state.tab === "settings";
    elements.listTitle.textContent = inSettings ? "Настройки" : "Статус";
    elements.draftCount.textContent = `${items.length} источников`;
    const backAction = inSettings ? "goBackToSettings()" : "goBackToList()";
    elements.draftList.innerHTML = `
      <button class="back-button" type="button" data-action="${backAction}">${uiIcon("arrow-left")}<span>Назад</span></button>
      ${items.map((item) => `
      <article class="status-card"><strong>${escapeHtml(_sourceLabel(item.source))}</strong> <span class="${item.enabled ? "status-good" : "status-bad"}">${item.enabled ? "ВКЛ" : "ВЫКЛ"}</span></article>
    `).join("")}
    `;
    elements.draftDetail.innerHTML = renderBackButton() + (inSettings ? `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("activity")}<span>Настройки</span></p>
          <h2 class="detail-title">Источники данных</h2>
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
    if (inSettings) {
      // In settings tab, keywords are merged into brand view
      renderBrandAndKeywords();
      return;
    }
    const topics = state.keywords?.items || [];
    const selectedTopic = topics.find((topic) => topic.topic_idx === state.selectedKeywordTopicIdx) || null;
    elements.listTitle.textContent = "Ключи";
    elements.draftCount.textContent = `${topics.length} тем`;
    setEmptyState(topics.length > 0, {
      eyebrow: "Ключи",
      title: "Темы еще не появились",
      body: "Когда словарь загрузится, здесь можно будет редактировать RU/EN ключи и теги.",
    });
    elements.draftList.innerHTML = `
      ${topics.map((topic) => `
      <article ${interactiveCardAttrs(`Открыть тему ${topic.name}`)} class="keyword-topic${topic.topic_idx === state.selectedKeywordTopicIdx ? " active" : ""} interactive-card" data-action="openKeywordTopic" data-args='${JSON.stringify([topic.topic_idx])}'>
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
                      <button type="button" aria-label="Удалить ${escapeHtml(item)}" data-action="removeKeywordItem" data-args='${JSON.stringify([selectedTopic.topic_idx, String(field), String(item), null])}'><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
                    </span>
                  `).join("") || `<span class="plan-entry-hint">Пока пусто.</span>`}
                </div>
                <form class="keyword-form" data-on-submit="addKeywordItem" data-args='${JSON.stringify([selectedTopic.topic_idx, String(field)])}'>
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

  function accountCardHtml(acc, opts = {}) {
    const platformIcons = { threads: "message-circle", instagram: "camera", canva: "pen-tool", youtube: "video" };
    const platformLabels = { threads: "Threads", instagram: "Instagram", canva: "Canva", youtube: "YouTube" };
    const icon = uiIcon(platformIcons[acc.platform] || "link");
    const label = platformLabels[acc.platform] || acc.platform;
    const connected = acc.connected;
    const expiry = formatExpiry(acc.expires_at);
    const readOnly = opts.readOnly || false;

    const now = new Date();
    const expiryDate = acc.expires_at ? new Date(acc.expires_at) : null;
    const daysLeft = expiryDate ? Math.ceil((expiryDate - now) / 86400000) : null;
    const expiryBadge = daysLeft === null ? ""
      : daysLeft <= 0 ? ` <span class="tag-status-error">Истёк</span>`
      : daysLeft <= 7 ? ` <span class="tag-status-warn">Через ${daysLeft} дн</span>`
      : "";

    const scopes = acc.scopes || [];
    const scopesBlock = scopes.length > 0 ? (() => {
      const scopeItems = scopes.map((s) =>
        `<li class="${connected ? "granted" : "needed"}">${uiIcon(connected ? "check-circle" : "lock")}<span>${escapeHtml(s)}</span></li>`
      ).join("");
      const summary = connected
        ? `Разрешения (${scopes.length}) ${uiIcon("check-circle")}`
        : `Необходимые разрешения (${scopes.length})`;
      return `<details class="account-scopes"><summary>${summary}</summary><ul class="account-scopes-list">${scopeItems}</ul></details>`;
    })() : "";

    if (connected) {
      const usernameRow = acc.username ? `<span class="account-username">@${escapeHtml(acc.username)}</span>` : "";
      const statusMeta = `<span class="account-meta">${uiIcon("check-circle")}<span>Подключено</span>${expiry ? `<span class="account-expiry"> · до ${expiry}</span>` : ""}${expiryBadge}</span>`;
      const btn = readOnly
        ? ""
        : `<button class="secondary-button account-full-btn" type="button" data-action="connectPlatform" data-args='${JSON.stringify([acc.platform])}'>${uiIcon("regenerate")}<span>Переподключить</span></button>`;
      const importBtn = (!readOnly && (acc.platform === "threads" || acc.platform === "instagram"))
        ? `<button class="secondary-button account-full-btn" type="button" data-action="bulkImportFromAccount" data-args='${JSON.stringify([acc.platform, null])}'>${uiIcon("archive")}<span>Выкачать за 14 дней</span></button>`
        : "";
      return `
        <article class="account-card account-card--vertical">
          <div class="account-card-title">${icon}<strong>${label}</strong></div>
          ${usernameRow}
          ${statusMeta}
          ${scopesBlock}
          <div class="account-card-actions">${btn}${importBtn}</div>
        </article>
      `;
    }

    const btn = readOnly
      ? `<span class="account-meta">Не подключено</span>`
      : `<button class="primary-button account-full-btn" type="button" data-action="connectPlatform" data-args='${JSON.stringify([acc.platform])}'>${uiIcon("link")}<span>Подключить ${label}</span></button>`;
    return `
      <article class="account-card account-card--vertical">
        <div class="account-card-title">${icon}<strong>${label}</strong></div>
        <span class="account-meta">Не подключено</span>
        ${scopesBlock}
        ${readOnly ? "" : btn}
      </article>
    `;
  }

  async function renderAccounts() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Аккаунты";
    elements.draftList.innerHTML = `<button class="back-button" type="button" data-action="goBackToSettings">${uiIcon("arrow-left")}<span>Назад</span></button>`;
    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("link")}<span>Настройки</span></p>
          <h2 class="detail-title">Подключённые аккаунты</h2>
        </div>
        <div id="accountsTeamSwitcher"></div>
        <div id="accountsList" class="accounts-list">
          <div class="account-card skeleton"><div class="skeleton-line"></div></div>
        </div>
        <p class="settings-hint">
          Подключите аккаунты для автоматической публикации контента.
        </p>
      </div>
    `;
    enterDetailView();

    // Load teams for switcher
    try {
      const teamsData = await fetchJson("/api/teams");
      const teams = teamsData?.items || [];
      const switcherEl = document.getElementById("accountsTeamSwitcher");
      if (switcherEl && teams.length > 1) {
        const currentTeamId = state.accountsTeamId || (teams[0] && teams[0].team_id);
        state.accountsTeamId = currentTeamId;
        switcherEl.innerHTML = `
          <div class="accounts-team-switcher">
            ${teams.map((t) => `<button class="team-switcher-chip${t.team_id === currentTeamId ? " active" : ""}" type="button" data-action="switchAccountsTeam" data-args='${JSON.stringify([t.team_id])}'>${uiIcon("users")}<span>${escapeHtml(t.name)}</span></button>`).join("")}
          </div>
        `;
      } else if (switcherEl && teams.length === 1) {
        state.accountsTeamId = teams[0].team_id;
        switcherEl.innerHTML = `<p class="settings-hint" style="margin:0">${uiIcon("users")} ${escapeHtml(teams[0].name)}</p>`;
      }
    } catch (_err) { /* ignore */ }

    try {
      const data = await fetchJson("/api/social/status");
      const container = document.getElementById("accountsList");
      if (container) {
        container.innerHTML = (data.accounts || []).map((a) => accountCardHtml(a)).join("");
      }
    } catch (_err) {
      const container = document.getElementById("accountsList");
      if (container) container.innerHTML = `<p class="plan-entry-hint">Не удалось загрузить статус аккаунтов.</p>`;
    }
  }

  function switchAccountsTeam(teamId) {
    state.accountsTeamId = teamId;
    renderAccounts();
  }

  async function connectPlatform(platform) {
    try {
      const data = await fetchJson(`/api/social/connect-url?platform=${platform}`);
      if (!data.url) return;

      if (platform === "instagram") {
        _showInstagramCopyPanel(data.url);
        return;
      }

      const tg = window.Telegram?.WebApp;
      if (tg?.openLink) {
        tg.openLink(data.url);
      } else {
        window.open(data.url, "_blank");
      }
    } catch (err) {
      const detail = err?.detail || "";
      if (detail.includes("not_configured")) {
        const label = platform === "instagram" ? "Instagram" : "Threads";
        showUiNotice(`${label} ещё не настроен. Обратитесь к администратору.`, "error");
      } else {
        showUiNotice(`Не удалось получить ссылку для ${platform}`, "error");
      }
    }
  }

  function _showInstagramCopyPanel(url) {
    elements.draftDetail.innerHTML = `
      ${renderBackButton()}
      <div class="detail-grid">
        <div class="detail-top" style="text-align:center">
          <p class="eyebrow">${uiIcon("camera")}<span>Instagram</span></p>
          <h2 class="detail-title">Подключение Instagram</h2>
        </div>
        <section class="section" style="text-align:center">
          <p style="margin-bottom:16px;color:var(--hint)">
            На iPhone приложение Instagram перехватывает ссылку авторизации.
          </p>
          <ol style="text-align:left;padding-left:20px;color:var(--text-secondary);line-height:1.8;margin-bottom:20px">
            <li>Нажмите <b>Скопировать ссылку</b></li>
            <li>Откройте <b>Safari</b></li>
            <li>Вставьте в адресную строку и нажмите Enter</li>
            <li>Пройдите авторизацию в Instagram</li>
          </ol>
          <button class="primary-button account-full-btn" type="button" id="igCopyBtn"
            data-action="__copyIgUrl">${uiIcon("link")}<span>Скопировать ссылку</span></button>
          <p id="igCopyStatus" style="font-size:13px;color:var(--good);margin-top:12px;min-height:20px"></p>
        </section>
      </div>
    `;
    enterDetailView();
    window.__copyIgUrl = () => {
      navigator.clipboard.writeText(url).then(() => {
        document.getElementById("igCopyStatus").textContent = "Скопировано! Вставьте в Safari.";
        const btn = document.getElementById("igCopyBtn");
        if (btn) btn.innerHTML = `${uiIcon("approve")}<span>Скопировано</span>`;
      }).catch(() => {
        prompt("Скопируйте ссылку:", url);
      });
    };
  }

  // ── Tracked hashtags ─────────────────────────────────────────────────────

  async function renderTrackedHashtags() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Теги";
    elements.draftList.innerHTML = `<button class="back-button" type="button" data-action="goBackToSettings">${uiIcon("arrow-left")}<span>Назад</span></button>`;
    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("hash")}<span>Настройки</span></p>
          <h2 class="detail-title">Теги для мониторинга</h2>
        </div>
        <section class="section">
          <div id="trackedTagsList" class="keyword-chips">
            <span class="plan-entry-hint">Загрузка…</span>
          </div>
          <div class="keyword-add-row" style="margin-top:12px">
            <input id="trackedTagInput" type="text" placeholder="#хештег" class="keyword-input">
            <button class="primary-button" type="button" data-action="addTrackedHashtag">${uiIcon("plus")}<span>Добавить</span></button>
          </div>
        </section>
        <p class="settings-hint">
          Укажите хештеги, по которым будет отслеживаться активность конкурентов и тренды. Лимит: 30 тегов.
        </p>
      </div>
    `;
    enterDetailView();

    try {
      const data = await fetchJson("/api/social/tracked-hashtags");
      _renderTagChips(data.items || []);
    } catch (_err) {
      const el = document.getElementById("trackedTagsList");
      if (el) el.innerHTML = `<span class="plan-entry-hint">Не удалось загрузить теги.</span>`;
    }
  }

  function _renderTagChips(tags) {
    const container = document.getElementById("trackedTagsList");
    if (!container) return;
    if (!tags.length) {
      container.innerHTML = `<span class="plan-entry-hint">Нет отслеживаемых тегов.</span>`;
      return;
    }
    container.innerHTML = tags.map((t) =>
      `<span class="keyword-chip">#${escapeHtml(t)}<button type="button" aria-label="Удалить тег" data-action="removeTrackedHashtag" data-args='${JSON.stringify([t])}'>${uiIcon("x", 14)}</button></span>`
    ).join("");
  }

  async function addTrackedHashtag() {
    const input = document.getElementById("trackedTagInput") || document.getElementById("trackedHashtagInput");
    const tag = (input?.value || "").trim().replace(/^#/, "");
    if (!tag) { input?.focus(); return; }
    try {
      const data = await fetchJson("/api/social/tracked-hashtags", {
        method: "POST",
        body: JSON.stringify({ tag }),
      });
      if (input) input.value = "";
      _renderTagChips(data.items || []);
      showUiNotice(`#${tag} добавлен`, "success");
      if (state.tab === "trends" && typeof window._currentTabRefresh === "function") window._currentTabRefresh();
    } catch (err) {
      const detail = err?.detail || err?.message || "";
      if (detail === "already_tracked") showUiNotice("Тег уже отслеживается", "error");
      else if (detail === "max_tags_reached") showUiNotice("Достигнут лимит тегов (30)", "error");
      else showUiNotice("Не удалось добавить тег", "error");
    }
  }

  async function removeTrackedHashtag(tag) {
    const confirmed = await confirmAction(`Удалить тег #${tag}?`);
    if (!confirmed) return;
    try {
      const data = await fetchJson(`/api/social/tracked-hashtags/${encodeURIComponent(tag)}`, { method: "DELETE" });
      _renderTagChips(data.items || []);
      showUiNotice(`#${tag} удалён`, "success");
      if (state.tab === "trends" && typeof window._currentTabRefresh === "function") window._currentTabRefresh();
    } catch (_err) {
      showUiNotice("Не удалось удалить тег", "error");
    }
  }

  // ── Monitored accounts ──────────────────────────────────────────────────

  function extractUsername(input) {
    const trimmed = input.trim();
    const urlPatterns = [
      /(?:instagram\.com|instagr\.am)\/([a-zA-Z0-9_.]+)/,
      /(?:threads\.net|threads\.com)\/@?([a-zA-Z0-9_.]+)/,
    ];
    for (const pat of urlPatterns) {
      const m = trimmed.match(pat);
      if (m) return m[1];
    }
    return trimmed.replace(/^@/, "");
  }

  async function renderMonitoredAccounts() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Мониторинг";
    elements.draftList.innerHTML = `<button class="back-button" type="button" data-action="goBackToSettings">${uiIcon("arrow-left")}<span>Назад</span></button>`;
    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("eye")}<span>Настройки</span></p>
          <h2 class="detail-title">Аккаунты на мониторинг</h2>
        </div>
        <section class="section">
          <h3>${uiIcon("camera")}<span>Instagram</span></h3>
          <div id="monitoredInstagramList" class="keyword-chips">
            <span class="plan-entry-hint">Загрузка…</span>
          </div>
          <div class="keyword-add-row" style="margin-top:12px">
            <input id="monitoredInstagramInput" type="text" placeholder="@username или ссылка" class="keyword-input">
            <button class="primary-button" type="button" data-action="addMonitoredAccountFromSettings" data-args='["instagram"]'>${uiIcon("plus")}<span>Добавить</span></button>
          </div>
        </section>
        <section class="section">
          <h3>${uiIcon("message-circle")}<span>Threads</span></h3>
          <div id="monitoredThreadsList" class="keyword-chips">
            <span class="plan-entry-hint">Загрузка…</span>
          </div>
          <div class="keyword-add-row" style="margin-top:12px">
            <input id="monitoredThreadsInput" type="text" placeholder="@username или ссылка" class="keyword-input">
            <button class="primary-button" type="button" data-action="addMonitoredAccountFromSettings" data-args='["threads"]'>${uiIcon("plus")}<span>Добавить</span></button>
          </div>
        </section>
        <p class="settings-hint">
          Укажите аккаунты конкурентов для отслеживания трендов. Лимит: 20 аккаунтов на платформу.
          Можно вставить ссылку на профиль — username будет извлечён автоматически.
        </p>
      </div>
    `;
    enterDetailView();

    try {
      const data = await fetchJson("/api/social/monitored-accounts");
      _renderMonitoredChips("instagram", data.instagram || []);
      _renderMonitoredChips("threads", data.threads || []);
    } catch (_err) {
      for (const id of ["monitoredInstagramList", "monitoredThreadsList"]) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = `<span class="plan-entry-hint">Не удалось загрузить аккаунты.</span>`;
      }
    }
  }

  function _renderMonitoredChips(platform, accounts) {
    const containerId = platform === "instagram" ? "monitoredInstagramList" : "monitoredThreadsList";
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!accounts.length) {
      container.innerHTML = `<span class="plan-entry-hint">Нет отслеживаемых аккаунтов.</span>`;
      return;
    }
    container.innerHTML = accounts.map((a) => {
      const username = a.username || a;
      return `<span class="keyword-chip">@${escapeHtml(username)}<button type="button" aria-label="Удалить" data-action="removeMonitoredAccountFromSettings" data-args='${JSON.stringify([platform, username])}'>${uiIcon("x", 14)}</button></span>`;
    }).join("");
  }

  async function addMonitoredAccountFromSettings(platform) {
    const inputId = platform === "instagram" ? "monitoredInstagramInput" : "monitoredThreadsInput";
    const input = document.getElementById(inputId);
    const raw = String(input?.value || "").trim();
    if (!raw) { input?.focus(); return; }
    const username = extractUsername(raw);
    if (!username) { input?.focus(); return; }
    try {
      await fetchJson("/api/social/monitored-accounts", {
        method: "POST",
        body: JSON.stringify({ platform, username }),
      });
      if (input) input.value = "";
      showUiNotice(`@${username} добавлен`, "success");
      const data = await fetchJson("/api/social/monitored-accounts");
      _renderMonitoredChips("instagram", data.instagram || []);
      _renderMonitoredChips("threads", data.threads || []);
    } catch (err) {
      const detail = err?.detail || "";
      if (detail === "already_tracked") showUiNotice("Аккаунт уже отслеживается", "error");
      else if (detail === "max_accounts_reached") showUiNotice("Достигнут лимит аккаунтов (20)", "error");
      else showUiNotice("Не удалось добавить аккаунт", "error");
    }
  }

  async function removeMonitoredAccountFromSettings(platform, username) {
    const confirmed = await confirmAction(`Удалить аккаунт @${username}?`);
    if (!confirmed) return;
    try {
      await fetchJson(`/api/social/monitored-accounts/${platform}?username=${encodeURIComponent(username)}`, { method: "DELETE" });
      showUiNotice(`@${username} удалён`, "success");
      const data = await fetchJson("/api/social/monitored-accounts");
      _renderMonitoredChips("instagram", data.instagram || []);
      _renderMonitoredChips("threads", data.threads || []);
    } catch (_err) {
      showUiNotice("Не удалось удалить аккаунт", "error");
    }
  }

  // ── City settings ──────────────────────────────────────────────────────

  const CITY_PRESETS = [
    { name: "Москва", lat: 55.7558, lon: 37.6173 },
    { name: "Санкт-Петербург", lat: 59.9343, lon: 30.3351 },
    { name: "Сочи", lat: 43.5855, lon: 39.7231 },
    { name: "Казань", lat: 55.7887, lon: 49.1221 },
    { name: "Екатеринбург", lat: 56.8389, lon: 60.6057 },
    { name: "Новосибирск", lat: 55.0084, lon: 82.9357 },
    { name: "Краснодар", lat: 45.0353, lon: 38.9753 },
    { name: "Нижний Новгород", lat: 56.2965, lon: 43.9361 },
  ];

  async function renderCity() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Город";
    elements.draftList.innerHTML = `<button class="back-button" type="button" data-action="goBackToSettings">${uiIcon("arrow-left")}<span>Назад</span></button>`;

    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("map-pin")}<span>Настройки</span></p>
          <h2 class="detail-title">Город</h2>
        </div>
        <div id="cityContent" class="section">
          <div class="account-card skeleton"><div class="skeleton-line"></div></div>
        </div>
      </div>
    `;
    enterDetailView();

    try {
      const data = await fetchJson("/api/user/city");
      const container = document.getElementById("cityContent");
      if (!container) return;

      const currentCity = data.city_name || "Москва";

      container.innerHTML = `
        <p class="settings-hint">Город используется для подбора масла дня с учётом погоды и геомагнитной обстановки.</p>
        <div class="city-presets">
          ${CITY_PRESETS.map((c) => `<button class="chip${c.name === currentCity ? " chip--active" : ""}" type="button" data-action="selectCity" data-args='${JSON.stringify([c.name, c.lat, c.lon])}'>${escapeHtml(c.name)}</button>`).join("")}
        </div>
        <p class="settings-hint" style="margin-top: 12px">Текущий город: <strong id="currentCityLabel">${escapeHtml(currentCity)}</strong></p>
      `;
    } catch (err) {
      const container = document.getElementById("cityContent");
      if (container) container.innerHTML = `<p class="plan-entry-hint">Не удалось загрузить настройки города.</p>`;
    }
  }

  async function selectCity(name, lat, lon) {
    try {
      await fetchJson("/api/user/city", {
        method: "PATCH",
        body: JSON.stringify({ city_name: name, city_lat: lat, city_lon: lon }),
      });
      showUiNotice(`Город: ${name}`, "success");
      await renderCity();
    } catch (_err) {
      showUiNotice("Не удалось сохранить город", "error");
    }
  }

  // ── Admin Dashboard ──────────────────────────────────────────────────────

  async function renderAdminDashboard() {
    elements.draftDetail.innerHTML = `<div class="detail-loader"><div class="loader"></div> Загрузка…</div>`;
    enterDetailView();
    syncMobileNavigation();

    try {
      const data = await fetchJson("/api/admin/dashboard");
      const q = data.video_queue || {};
      const mem = data.memory || {};
      const disk = data.disk || {};
      const llm = data.llm || {};
      const worker = data.worker || {};
      const isAdmin = data.is_admin || false;

      // Labels
      const STATUS_RU = { pending: "В очереди", running: "Выполняется", completed: "Готово", failed: "Ошибка", cancelled: "Отменено" };
      const TYPE_RU = { clean: "Очистка", montage: "Монтаж", grade: "Цветокоррекция", compose: "Сборка", canva_export: "Canva" };
      const STEP_RU = { preparing: "Подготовка", analyzing: "Анализ", transcribing: "Транскрипция", detecting_silence: "Поиск пауз", processing: "Обработка", assembling: "Сборка", encoding: "Кодирование", grading: "Коррекция", subtitles: "Субтитры", music: "Музыка", broll: "B-roll", color_grading: "Цвет", done: "Готово", queued: "В очереди", saving: "Сохранение", rendering: "Рендеринг" };

      // Video queue summary
      const byStatus = q.by_status || {};
      const statusRows = Object.entries(byStatus).map(([status, types]) => {
        const total = Object.values(types).reduce((s, v) => s + v, 0);
        const detail = Object.entries(types).map(([t, c]) => `${TYPE_RU[t] || t}: ${c}`).join(", ");
        const color = { pending: "var(--brand)", running: "#4a90d9", completed: "var(--good)", failed: "var(--danger, #e53935)" }[status] || "var(--hint)";
        return `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
          <span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>${escapeHtml(STATUS_RU[status] || status)}</span>
          <span style="color:var(--hint);font-size:12px">${detail} (${total})</span>
        </div>`;
      }).join("");

      // Recent tasks
      const recent = (q.recent || []).slice(0, 10).map(t => {
        const statusColor = { pending: "var(--brand)", running: "#4a90d9", completed: "var(--good)", failed: "var(--danger)" }[t.status] || "var(--hint)";
        return `<div style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);font-size:12px;align-items:center">
          <span style="min-width:50px;color:var(--hint)">#${escapeHtml(t.draft_id)}</span>
          <span style="min-width:55px">${escapeHtml(TYPE_RU[t.type] || t.type)}</span>
          <span style="color:${statusColor};font-weight:600;min-width:65px">${escapeHtml(STATUS_RU[t.status] || t.status)}</span>
          <span style="color:var(--hint);flex:1">${t.step ? escapeHtml(STEP_RU[t.step] || t.step) : ""} ${t.progress ? t.progress + "%" : ""}</span>
          <span style="color:var(--muted)">${t.duration_sec ? t.duration_sec + "с" : ""}</span>
        </div>`;
      }).join("");

      // Memory bar
      const ramPct = mem.ram_percent || 0;
      const ramBar = `<div style="display:flex;align-items:center;gap:8px;margin:4px 0">
        <span style="min-width:40px;font-size:12px;color:var(--hint)">RAM</span>
        <div style="flex:1;height:8px;background:var(--border);border-radius:4px;overflow:hidden">
          <div style="width:${ramPct}%;height:100%;background:${ramPct > 80 ? "var(--danger)" : "var(--brand)"};border-radius:4px"></div>
        </div>
        <span style="min-width:90px;font-size:11px;color:var(--hint)">${mem.ram_used_mb || 0}/${mem.ram_total_mb || 0} МБ</span>
      </div>`;

      const swapPct = mem.swap_percent || 0;
      const swapBar = `<div style="display:flex;align-items:center;gap:8px;margin:4px 0">
        <span style="min-width:40px;font-size:12px;color:var(--hint)">Swap</span>
        <div style="flex:1;height:8px;background:var(--border);border-radius:4px;overflow:hidden">
          <div style="width:${swapPct}%;height:100%;background:${swapPct > 50 ? "#f59e0b" : "var(--brand)"};border-radius:4px"></div>
        </div>
        <span style="min-width:90px;font-size:11px;color:var(--hint)">${mem.swap_used_mb || 0}/${mem.swap_total_mb || 0} МБ</span>
      </div>`;

      const diskPct = disk.percent || 0;
      const diskBar = `<div style="display:flex;align-items:center;gap:8px;margin:4px 0">
        <span style="min-width:40px;font-size:12px;color:var(--hint)">Диск</span>
        <div style="flex:1;height:8px;background:var(--border);border-radius:4px;overflow:hidden">
          <div style="width:${diskPct}%;height:100%;background:${diskPct > 85 ? "var(--danger)" : "var(--brand)"};border-radius:4px"></div>
        </div>
        <span style="min-width:90px;font-size:11px;color:var(--hint)">${disk.used_gb || 0}/${disk.total_gb || 0} ГБ</span>
      </div>`;

      elements.draftDetail.innerHTML = `
        <div class="detail-grid">
          ${renderBackButton()}
          <div class="detail-top">
            <p class="eyebrow">${uiIcon("gauge")}<span>Очереди</span></p>
            <h2 class="detail-title">Обработка видео</h2>
          </div>

          <section class="section">
            <h3>${uiIcon("play-circle")} Worker</h3>
            <div style="display:flex;align-items:center;gap:8px;font-size:13px">
              <span style="width:10px;height:10px;border-radius:50%;background:${worker.alive ? "var(--good)" : "var(--danger)"}"></span>
              <span>${worker.alive ? "Работает" : "Остановлен"}</span>
            </div>
            <div style="font-size:12px;color:var(--hint);margin-top:4px">Задач в работе: ${q.active || 0}</div>
          </section>

          <section class="section">
            <h3>${uiIcon("stack")} Очередь видео</h3>
            ${statusRows || '<div style="font-size:13px;color:var(--hint)">Нет задач</div>'}
          </section>

          <section class="section">
            <h3>${uiIcon("clock-counter-clockwise")} Последние задачи</h3>
            <div style="font-size:13px">${recent || '<div style="color:var(--hint)">Нет задач</div>'}</div>
          </section>

          ${isAdmin ? `
          <section class="section">
            <h3>${uiIcon("brain")} LLM запросы</h3>
            <div style="font-size:13px">Сегодня: <strong>${llm.today || 0}</strong> · Всего: ${llm.total || 0}</div>
          </section>

          <section class="section">
            <h3>${uiIcon("cpu")} Ресурсы</h3>
            ${ramBar}${swapBar}${diskBar}
          </section>

          <section class="section">
            <div class="actions-row" style="gap:8px">
              <button class="secondary-button compact" type="button" data-action="adminResetStuck" data-args='[null]'>
                ${uiIcon("arrow-counter-clockwise")} Сбросить залипшие
              </button>
              <button class="secondary-button compact" type="button" data-action="adminRestartWorker" data-args='[null]'>
                ${uiIcon("play")} Перезапустить worker
              </button>
            </div>
          </section>` : ""}
        </div>`;
    } catch (e) {
      elements.draftDetail.innerHTML = `<div class="detail-empty">${renderGuidedState({
        title: "Доступ запрещён",
        body: e.message || "Нет прав администратора",
      })}</div>`;
    }
    syncMobileNavigation();
  }

  async function adminResetStuck(_btn) {
    try {
      const res = await fetchJson("/api/admin/reset-stuck-tasks", { method: "POST" });
      showUiNotice(`Сброшено задач: ${res.reset}`, "success");
      await renderAdminDashboard();
    } catch (e) { showUiNotice("Ошибка: " + (e.message || ""), "error"); }
  }

  async function adminRestartWorker(_btn) {
    try {
      await fetchJson("/api/admin/restart-worker", { method: "POST" });
      showUiNotice("Worker перезапущен", "success");
      await renderAdminDashboard();
    } catch (e) { showUiNotice("Ошибка: " + (e.message || ""), "error"); }
  }

  // ── Team management ──────────────────────────────────────────────────────

  async function renderTeam() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Команда";
    elements.draftList.innerHTML = `<button class="back-button" type="button" data-action="goBackToSettings">${uiIcon("arrow-left")}<span>Назад</span></button>`;
    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("users")}<span>Настройки</span></p>
          <h2 class="detail-title">Команда</h2>
        </div>
        <div id="teamContent" class="section">
          <div class="account-card skeleton"><div class="skeleton-line"></div></div>
        </div>
      </div>
    `;
    enterDetailView();

    try {
      const teamsData = await fetchJson("/api/teams");
      const teams = teamsData?.items || [];
      const container = document.getElementById("teamContent");
      if (!container) return;

      if (teams.length === 0) {
        container.innerHTML = `
          <p class="settings-hint">У вас пока нет команды.</p>
          <div class="keyword-form keyword-add-row">
            <input id="newTeamName" type="text" placeholder="Название команды">
            <button class="secondary-button" type="button" data-action="createNewTeam">Создать</button>
          </div>
        `;
        return;
      }

      let html = "";
      for (const t of teams) {
        const detail = await fetchJson(`/api/teams/${t.team_id}`);
        const isOwner = detail.role === "owner";
        const roleLabels = { owner: "Владелец", editor: "Редактор", viewer: "Читатель" };

        const membersHtml = (detail.members || []).map((m) => {
          const roleLabel = roleLabels[m.role] || m.role;
          const removeBtn = isOwner && m.telegram_id !== detail.created_by
            ? ` <button class="chip-remove-btn" type="button" data-action="removeTeamMember" data-args='${JSON.stringify([t.team_id, m.telegram_id])}' title="Удалить">&times;</button>`
            : "";
          const displayName = m.username ? `@${escapeHtml(m.username)}` : m.first_name ? escapeHtml(m.first_name) : `ID: ${m.telegram_id}`;
          return `
            <div class="team-member-row">
              <span class="team-member-id">${displayName}</span>
              <span class="keyword-chip">${escapeHtml(roleLabel)}${removeBtn}</span>
            </div>`;
        }).join("");

        const inviteBtn = isOwner
          ? `<button class="secondary-button" type="button" data-action="createTeamInvite" data-args='${JSON.stringify([t.team_id])}'>${uiIcon("user-plus")}<span>Пригласить</span></button>`
          : "";

        // Connected accounts for this team
        const connectedAccounts = (detail.connected_accounts || []);
        const connectedAccountsHtml = connectedAccounts.length > 0
          ? `<div class="team-accounts-section">
              <h4>Подключённые аккаунты</h4>
              <div class="accounts-list">${connectedAccounts.map((a) => accountCardHtml(a, { readOnly: !isOwner })).join("")}</div>
            </div>`
          : "";

        // Avatar section — use native <label>+<input> for Telegram WebView compat
        const avatarInputId = `avatarUpload-${t.team_id}`;
        const avatarUploadLabel = isOwner
          ? `<label class="secondary-button avatar-upload-label" for="${avatarInputId}">${uiIcon("upload")}<span>${detail.has_avatar ? "Заменить аватарку" : "Загрузить аватарку"}</span></label>
             <input id="${avatarInputId}" type="file" accept="image/jpeg,image/png,image/webp" style="position:absolute;width:1px;height:1px;opacity:0;overflow:hidden" data-on-change="uploadTeamAvatar" data-args='${JSON.stringify([t.team_id])}' />`
          : "";
        const avatarHtml = detail.has_avatar
          ? `<div class="team-avatar-section">
               <img src="${escapeHtml(detail.avatar_url)}" alt="Аватарка" class="team-avatar-preview" />
               ${avatarUploadLabel}
             </div>`
          : isOwner
            ? `<div class="team-avatar-section">
                 <p class="settings-hint">Аватарка не загружена — она используется на слайдах карусели.</p>
                 ${avatarUploadLabel}
               </div>`
            : "";

        html += `
          <section class="section settings-section">
            <h3>${uiIcon("users")}<span>${escapeHtml(t.name)}</span></h3>
            <p class="settings-hint">Ваша роль: <strong>${escapeHtml(roleLabels[detail.role] || detail.role)}</strong></p>
            ${avatarHtml}
            <div class="team-members-list">${membersHtml}</div>
            ${connectedAccountsHtml}
            <div id="inviteResult-${t.team_id}"></div>
            ${inviteBtn}
          </section>
        `;
      }

      html += `
        <section class="section settings-section">
          <h3>Создать новую команду</h3>
          <div class="keyword-form keyword-add-row">
            <input id="newTeamName" type="text" placeholder="Название команды">
            <button class="secondary-button" type="button" data-action="createNewTeam">Создать</button>
          </div>
        </section>
      `;

      container.innerHTML = html;
    } catch (err) {
      const container = document.getElementById("teamContent");
      if (container) container.innerHTML = `<p class="plan-entry-hint">Не удалось загрузить команды.</p>`;
    }
  }

  async function createNewTeam() {
    const input = document.getElementById("newTeamName");
    const name = String(input?.value || "").trim();
    if (!name) { input?.focus(); return; }
    try {
      await fetchJson("/api/teams", { method: "POST", body: JSON.stringify({ name }) });
      showUiNotice("Команда создана", "success");
      renderTeam();
    } catch (_err) {
      showUiNotice("Не удалось создать команду", "error");
    }
  }

  async function createTeamInvite(teamId) {
    try {
      const result = await fetchJson(`/api/teams/${teamId}/invites`, {
        method: "POST",
        body: JSON.stringify({ role: "editor", max_uses: 5 }),
      });
      if (result?.deep_link) {
        const container = document.getElementById(`inviteResult-${teamId}`);
        if (container) {
          container.innerHTML = `
            <div class="invite-link-box">
              <p class="settings-hint">Отправьте ссылку коллеге в Telegram:</p>
              <div class="keyword-form keyword-add-row">
                <input type="text" value="${escapeHtml(result.deep_link)}" readonly data-action="_selectInput">
                <button class="secondary-button" type="button" data-action="copyText" data-args='${JSON.stringify([result.deep_link])}'>Копировать</button>
              </div>
            </div>
          `;
        }
        showUiNotice("Ссылка-приглашение создана", "success");
      }
    } catch (_err) {
      showUiNotice("Не удалось создать приглашение", "error");
    }
  }

  async function removeTeamMember(teamId, memberId) {
    const confirmed = await confirmAction("Удалить участника из команды?");
    if (!confirmed) return;
    try {
      await fetchJson(`/api/teams/${teamId}/members/${memberId}`, { method: "DELETE" });
      showUiNotice("Участник удалён", "success");
      renderTeam();
    } catch (_err) {
      showUiNotice("Не удалось удалить участника", "error");
    }
  }

  async function uploadTeamAvatar(teamId, _value, inputEl) {
    // Called via data-on-change on <input type="file">
    const file = inputEl?.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      showUiNotice("Файл слишком большой (макс. 2 МБ)", "error");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    try {
      const headers = { "X-Team-Id": teamId };
      const initData = window.Telegram?.WebApp?.initData;
      if (initData) headers["X-Telegram-Init-Data"] = initData;
      const resp = await fetch(`/api/teams/${teamId}/avatar`, {
        method: "POST",
        headers,
        body: formData,
      });
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${body}`);
      }
      showUiNotice("Аватарка загружена", "success");
      renderTeam();
    } catch (err) {
      showUiNotice(`Не удалось загрузить: ${err.message}`, "error");
    }
  }

  // ── Promo code activation + admin management ─────────────────────────────

  async function renderPromo() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Подписка";
    elements.draftList.innerHTML = `<button class="back-button" type="button" data-action="goBackToSettings">${uiIcon("arrow-left")}<span>Назад</span></button>`;

    // Load user plan to show current subscription
    let planInfo = "";
    try {
      const plan = await fetchJson("/api/user/plan");
      const tierLabels = { free: "Бесплатный", student: "Студент", expert: "Эксперт" };
      const tierLabel = tierLabels[plan.effective_tier] || plan.effective_tier;
      const trialInfo = plan.trial_ends_at
        ? ` · до ${new Date(plan.trial_ends_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" })}`
        : "";
      planInfo = `
        <section class="section settings-section">
          <h3>${uiIcon("crown")}<span>Текущая подписка</span></h3>
          <p class="promo-plan-badge"><strong>${escapeHtml(tierLabel)}</strong>${trialInfo}</p>
        </section>
      `;
    } catch (_err) { /* ignore */ }

    // Check if admin
    let adminHtml = "";
    try {
      const promos = await fetchJson("/api/admin/promos");
      // If we get here, user is admin
      const tierLabelsAdmin = { expert: "Эксперт", student: "Студент" };
      const rows = (promos.items || []).map((p) => {
        const exp = p.expires_at ? new Date(p.expires_at).toLocaleDateString("ru-RU") : "—";
        const exhausted = p.uses_count >= p.max_uses;
        return `
          <tr class="${exhausted ? "promo-exhausted" : ""}">
            <td><code>${escapeHtml(p.code)}</code></td>
            <td>${escapeHtml(tierLabelsAdmin[p.tier] || p.tier)}</td>
            <td>${p.duration_days} дн.</td>
            <td>${p.uses_count} из ${p.max_uses}</td>
            <td>${exp}</td>
          </tr>`;
      }).join("");

      adminHtml = `
        <section class="section settings-section">
          <h3>${uiIcon("shield")}<span>Управление промокодами</span></h3>
          <div class="promo-gen-form">
            <div class="keyword-add-row">
              <label class="promo-field"><span class="promo-field-label">Тариф</span>
                <select id="promoTier">
                  <option value="expert">Эксперт</option>
                  <option value="student">Студент</option>
                </select>
              </label>
              <label class="promo-field"><span class="promo-field-label">Срок (дней)</span>
                <input id="promoDays" type="number" value="30" min="1" max="365">
              </label>
            </div>
            <div class="keyword-add-row" style="margin-top:8px">
              <label class="promo-field"><span class="promo-field-label">Макс. использований</span>
                <input id="promoMaxUses" type="number" value="5" min="1" max="100">
              </label>
              <label class="promo-field"><span class="promo-field-label">Кол-во кодов</span>
                <input id="promoCount" type="number" value="1" min="1" max="50">
              </label>
            </div>
            <div class="keyword-add-row" style="margin-top:8px">
              <label class="promo-field"><span class="promo-field-label">Префикс</span>
                <input id="promoPrefix" type="text" value="AROMA">
              </label>
              <button class="secondary-button" type="button" data-action="generatePromos">Создать</button>
            </div>
          </div>
          <div id="promoGenResult"></div>
          ${promos.items.length > 0 ? `
            <div class="promo-table-wrap">
              <table class="promo-table">
                <thead><tr><th>Код</th><th>Тариф</th><th>Срок</th><th>Использований</th><th>Истекает</th></tr></thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          ` : `<p class="plan-entry-hint">Промокодов пока нет.</p>`}
        </section>
      `;
    } catch (_err) {
      // Not admin — that's fine
    }

    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="detail-grid">
        <div class="detail-top">
          <p class="eyebrow">${uiIcon("ticket")}<span>Настройки</span></p>
          <h2 class="detail-title">Подписка</h2>
        </div>
        ${planInfo}
        <section class="section settings-section">
          <h3>${uiIcon("ticket")}<span>Активировать промокод</span></h3>
          <p class="settings-hint">Введите код, чтобы активировать подписку.</p>
          <div class="keyword-form keyword-add-row">
            <input id="promoCodeInput" type="text" placeholder="AROMA-XXXXXX" style="text-transform:uppercase">
            <button class="secondary-button" type="button" data-action="activatePromo">Активировать</button>
          </div>
          <div id="promoActivateResult"></div>
        </section>
        ${adminHtml}
      </div>
    `;
    enterDetailView();
  }

  async function activatePromo() {
    const input = document.getElementById("promoCodeInput");
    const code = String(input?.value || "").trim().toUpperCase();
    if (!code) { input?.focus(); return; }
    const resultEl = document.getElementById("promoActivateResult");
    try {
      const result = await fetchJson("/api/promo/activate", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      const endsAt = result.ends_at
        ? new Date(result.ends_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" })
        : "";
      if (resultEl) resultEl.innerHTML = `<p class="promo-success">Подписка активирована: <strong>${escapeHtml(result.tier)}</strong>${endsAt ? ` до ${endsAt}` : ""}</p>`;
      if (input) input.value = "";
      showUiNotice("Промокод активирован!", "success");
    } catch (err) {
      if (resultEl) resultEl.innerHTML = `<p class="promo-error">Промокод не найден или истёк.</p>`;
      showUiNotice("Не удалось активировать промокод", "error");
    }
  }

  async function generatePromos() {
    const tier = document.getElementById("promoTier")?.value || "expert";
    const days = parseInt(document.getElementById("promoDays")?.value || "30", 10);
    const count = parseInt(document.getElementById("promoCount")?.value || "1", 10);
    const max_uses = parseInt(document.getElementById("promoMaxUses")?.value || "5", 10);
    const prefix = document.getElementById("promoPrefix")?.value?.trim() || "AROMA";
    const resultEl = document.getElementById("promoGenResult");
    try {
      const result = await fetchJson("/api/admin/promos", {
        method: "POST",
        body: JSON.stringify({ tier, days, count, prefix, max_uses }),
      });
      const codes = (result.codes || []).map((c) => `<code>${escapeHtml(c)}</code>`).join("<br>");
      if (resultEl) resultEl.innerHTML = `<div class="promo-gen-codes"><p class="settings-hint">Созданные коды:</p>${codes}</div>`;
      showUiNotice(`Создано ${result.codes.length} промокодов`, "success");
      // Reload to show in table
      setTimeout(() => renderPromo(), 1500);
    } catch (_err) {
      showUiNotice("Не удалось создать промокоды", "error");
    }
  }

  async function setTheme(themeId) {
    applyTheme(themeId);
    document.querySelectorAll(".theme-swatch").forEach(el => {
      el.classList.toggle("active", el.dataset.themeId === themeId);
    });
    try {
      await fetchJson("/api/preferences/theme", { method: "PATCH", body: JSON.stringify({ theme: themeId }) });
    } catch (e) {
      console.warn("Theme save failed", e);
    }
  }

  async function renderTheme() {
    const THEMES = [
      { id:"terracotta",   label:"Терракот",     accent:"#b45c3d" },
      { id:"racing-green", label:"Изумруд",  accent:"#2a8a50" },
      { id:"champagne",    label:"Шампань",       accent:"#c8a86a" },
      { id:"violet",       label:"Фиалка",        accent:"#9060c8" },
      { id:"teal",         label:"Бирюза",        accent:"#3a9098" },
      { id:"raspberry",    label:"Малина",        accent:"#b04870" },
    ];
    let res;
    try { res = await fetchJson("/api/preferences/theme"); } catch (_e) { res = {}; }
    const current = res.theme || document.body.dataset.theme || "terracotta";

    const swatches = THEMES.map(t => `
      <button class="theme-swatch${t.id === current ? " active" : ""}"
        data-action="setTheme" data-args='["${t.id}"]'
        data-theme-id="${t.id}"
        style="--sw-accent:${t.accent}">
        <span class="theme-swatch-preview"></span>
        <span class="theme-swatch-label">${t.label}</span>
      </button>`).join("");

    elements.draftDetail.innerHTML = renderBackButton() + `
      <div class="settings-section-content">
        <h2 class="settings-section-title">Цветовая тема</h2>
        <p class="settings-section-hint">Выберите цветовую схему интерфейса</p>
        <div class="theme-grid">${swatches}</div>
      </div>`;
    enterDetailView();
  }

  return {
    addKeywordItem,
    removeKeywordItem,
    openKeywordTopic,
    loadKeywords,
    loadSettings,
    renderSettingsSwitcher,
    renderSettingsMenu,
    renderBrandAndKeywords,
    goBackToSettings,
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
    switchAccountsTeam,
    renderTrackedHashtags,
    addTrackedHashtag,
    removeTrackedHashtag,
    renderMonitoredAccounts,
    addMonitoredAccountFromSettings,
    removeMonitoredAccountFromSettings,
    renderTeam,
    createNewTeam,
    createTeamInvite,
    removeTeamMember,
    uploadTeamAvatar,
    renderPromo,
    activatePromo,
    generatePromos,
    setTheme,
    renderTheme,
    renderCity,
    selectCity,
    renderAdminDashboard,
    adminResetStuck,
    adminRestartWorker,
  };
}
