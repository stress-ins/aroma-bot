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
    // Legacy — kept for backward compat but unused
    return "";
  }

  function settingsMenuRow(icon, color, title, section, badge) {
    const badgeHtml = badge != null ? `<span class="settings-menu-badge">${escapeHtml(String(badge))}</span>` : "";
    return `<div class="settings-menu-row" onclick="openSettingsSection('${section}')">
      <span class="settings-menu-icon" style="background:${color}"><i data-lucide="${icon}"></i></span>
      <span class="settings-menu-text">${escapeHtml(title)}</span>
      ${badgeHtml}
      <span class="settings-menu-chevron"><i data-lucide="chevron-right"></i></span>
    </div>`;
  }

  async function renderSettingsMenu() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "";

    // Fetch badge data in parallel
    const [planRes, teamsRes, socialRes, statusRes, adminRes] = await Promise.allSettled([
      fetchJson("/api/user/plan"),
      fetchJson("/api/teams"),
      fetchJson("/api/social/status"),
      fetchJson("/api/status"),
      fetchJson("/api/admin/promos"),
    ]);

    const teamCount = teamsRes.status === "fulfilled" ? (teamsRes.value?.items || []).reduce((n, t) => n + (t.member_count || 1), 0) : null;
    const connectedCount = socialRes.status === "fulfilled" ? (socialRes.value?.accounts || []).filter((a) => a.connected).length : null;
    const enabledCount = statusRes.status === "fulfilled" ? (statusRes.value?.items || []).filter((i) => i.enabled).length : null;
    const isAdmin = adminRes.status === "fulfilled";

    let html = `<div class="settings-menu">`;

    // Group: Подписка
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Подписка</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("ticket", "#AF52DE", "Промокод", "promo", isAdmin ? "admin" : null)}
      </div>
    </div>`;

    // Group: Управление
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Управление</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("users", "#007AFF", "Команда", "team", teamCount)}
        ${settingsMenuRow("link", "#34C759", "Аккаунты", "accounts", connectedCount != null ? connectedCount : null)}
      </div>
    </div>`;

    // Group: Контент
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Контент</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("palette", "#FF9500", "Бренд и ключи", "brand", null)}
      </div>
    </div>`;

    // Group: Система
    html += `<div class="settings-menu-group">
      <div class="settings-menu-group-header">Система</div>
      <div class="settings-menu-list">
        ${settingsMenuRow("activity", "#FF3B30", "Источники данных", "status", enabledCount)}
      </div>
    </div>`;

    html += `</div>`;
    elements.draftList.innerHTML = html;

    elements.draftDetail.innerHTML = `<div class="detail-empty">${renderGuidedState({
      eyebrow: "Настройки",
      title: "Выберите раздел",
      body: "Нажмите на пункт меню слева, чтобы перейти к настройкам.",
    })}</div>`;

    if (window.lucide) lucide.createIcons();
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
    if (state.settingsInDetail && state.settingsSection) {
      if (state.settingsSection === "keywords" || state.settingsSection === "brand") {
        if (!state.keywords) {
          state.keywords = await fetchJson("/api/keywords");
        }
        renderBrandAndKeywords();
        return;
      }
      if (state.settingsSection === "accounts") {
        renderAccounts();
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
      if (state.settingsSection === "status") {
        if (!state.status) {
          state.status = await fetchJson("/api/status");
        }
        renderStatus();
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
      <button class="back-button" type="button" onclick="goBackToSettings()">${uiIcon("arrow-left")}<span>Назад</span></button>
      ${topics.map((topic) => `
      <article ${interactiveCardAttrs(`Открыть тему ${topic.name}`)} class="keyword-topic${topic.topic_idx === state.selectedKeywordTopicIdx ? " active" : ""} interactive-card" onclick="openKeywordTopic(${topic.topic_idx})">
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
          <div class="keyword-field">
            <strong>API Key</strong>
            <input id="uploadPostApiKey" type="password" placeholder="Введите API-ключ…" class="draft-textarea">
            <span id="uploadPostKeyStatus" class="plan-entry-hint"></span>
          </div>
          <div class="keyword-field">
            <strong>Username</strong>
            <input id="uploadPostUser" type="text" placeholder="Имя пользователя upload-post" class="draft-textarea">
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
            <div class="keyword-field">
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
        ${keywordsDetailHtml}
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
      ${inSettings ? `<button class="back-button" type="button" onclick="goBackToSettings()">${uiIcon("arrow-left")}<span>Назад</span></button>` : ""}
      ${items.map((item) => `
      <article class="status-card"><strong>${escapeHtml(item.source)}</strong> <span class="${item.enabled ? "status-good" : "status-bad"}">${item.enabled ? "вкл" : "выкл"}</span></article>
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

  function accountCardHtml(acc, opts = {}) {
    const icon = uiIcon(acc.platform === "threads" ? "message-circle" : "camera");
    const label = acc.platform === "threads" ? "Threads" : "Instagram";
    const connected = acc.connected;
    const expiry = formatExpiry(acc.expires_at);
    const readOnly = opts.readOnly || false;

    if (connected) {
      const usernameRow = acc.username ? `<span class="account-username">@${escapeHtml(acc.username)}</span>` : "";
      const statusMeta = `<span class="account-meta">${uiIcon("check-circle")}<span>Подключено</span>${expiry ? ` · до ${expiry}` : ""}</span>`;
      const btn = readOnly
        ? ""
        : `<button class="secondary-button account-full-btn" type="button" onclick="connectPlatform('${acc.platform}')">${uiIcon("regenerate")}<span>Переподключить</span></button>`;
      return `
        <article class="account-card account-card--vertical">
          <div class="account-card-title">${icon}<strong>${label}</strong></div>
          ${usernameRow}
          ${statusMeta}
          ${btn}
        </article>
      `;
    }

    const btn = readOnly
      ? `<span class="account-meta">Не подключено</span>`
      : `<button class="primary-button account-full-btn" type="button" onclick="connectPlatform('${acc.platform}')">${uiIcon("link")}<span>Подключить ${label}</span></button>`;
    return `
      <article class="account-card account-card--vertical">
        <div class="account-card-title">${icon}<strong>${label}</strong></div>
        <span class="account-meta">Не подключено</span>
        ${readOnly ? "" : btn}
      </article>
    `;
  }

  async function renderAccounts() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Аккаунты";
    elements.draftList.innerHTML = `<button class="back-button" type="button" onclick="goBackToSettings()">${uiIcon("arrow-left")}<span>Назад</span></button>`;
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
            ${teams.map((t) => `<button class="team-switcher-chip${t.team_id === currentTeamId ? " active" : ""}" type="button" onclick="switchAccountsTeam('${escapeHtml(t.team_id)}')">${uiIcon("users")}<span>${escapeHtml(t.name)}</span></button>`).join("")}
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
      if (data.url) {
        // Open OAuth URL directly — Instagram now uses /consent/ URL
        // which may not be intercepted by iOS Universal Links
        const tg = window.Telegram?.WebApp;
        if (tg?.openLink) {
          tg.openLink(data.url);
        } else {
          window.open(data.url, "_blank");
        }
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

  // ── Team management ──────────────────────────────────────────────────────

  async function renderTeam() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Команда";
    elements.draftList.innerHTML = `<button class="back-button" type="button" onclick="goBackToSettings()">${uiIcon("arrow-left")}<span>Назад</span></button>`;
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
            <button class="secondary-button" type="button" onclick="createNewTeam()">Создать</button>
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
            ? ` <button class="chip-remove-btn" type="button" onclick="removeTeamMember('${escapeHtml(t.team_id)}', ${m.telegram_id})" title="Удалить">&times;</button>`
            : "";
          const displayName = m.username ? `@${escapeHtml(m.username)}` : `ID: ${m.telegram_id}`;
          return `
            <div class="team-member-row">
              <span class="team-member-id">${displayName}</span>
              <span class="keyword-chip">${escapeHtml(roleLabel)}${removeBtn}</span>
            </div>`;
        }).join("");

        const inviteBtn = isOwner
          ? `<button class="secondary-button" type="button" onclick="createTeamInvite('${escapeHtml(t.team_id)}')">${uiIcon("user-plus")}<span>Пригласить</span></button>`
          : "";

        // Connected accounts for this team
        const connectedAccounts = (detail.connected_accounts || []);
        const connectedAccountsHtml = connectedAccounts.length > 0
          ? `<div class="team-accounts-section">
              <h4>Подключённые аккаунты</h4>
              <div class="accounts-list">${connectedAccounts.map((a) => accountCardHtml(a, { readOnly: !isOwner })).join("")}</div>
            </div>`
          : "";

        html += `
          <section class="section settings-section">
            <h3>${uiIcon("users")}<span>${escapeHtml(t.name)}</span></h3>
            <p class="settings-hint">Ваша роль: <strong>${escapeHtml(roleLabels[detail.role] || detail.role)}</strong></p>
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
            <button class="secondary-button" type="button" onclick="createNewTeam()">Создать</button>
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
                <input type="text" value="${escapeHtml(result.deep_link)}" readonly onclick="this.select()">
                <button class="secondary-button" type="button" onclick="copyText('${escapeHtml(result.deep_link)}')">Копировать</button>
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

  // ── Promo code activation + admin management ─────────────────────────────

  async function renderPromo() {
    elements.listTitle.textContent = "Настройки";
    elements.draftCount.textContent = "Промокод";
    elements.draftList.innerHTML = `<button class="back-button" type="button" onclick="goBackToSettings()">${uiIcon("arrow-left")}<span>Назад</span></button>`;

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
      const rows = (promos.items || []).map((p) => {
        const exp = p.expires_at ? new Date(p.expires_at).toLocaleDateString("ru-RU") : "∞";
        return `
          <tr>
            <td><code>${escapeHtml(p.code)}</code></td>
            <td>${escapeHtml(p.tier)}</td>
            <td>${p.duration_days}д</td>
            <td>${p.uses_count}/${p.max_uses}</td>
            <td>${exp}</td>
          </tr>`;
      }).join("");

      adminHtml = `
        <section class="section settings-section">
          <h3>${uiIcon("shield")}<span>Управление промокодами</span></h3>
          <div class="promo-gen-form">
            <div class="keyword-add-row">
              <select id="promoTier">
                <option value="expert">Expert</option>
                <option value="student">Student</option>
              </select>
              <input id="promoDays" type="number" value="30" min="1" max="365" placeholder="Дней">
              <input id="promoCount" type="number" value="1" min="1" max="50" placeholder="Кол-во">
            </div>
            <div class="keyword-add-row" style="margin-top:8px">
              <input id="promoPrefix" type="text" value="AROMA" placeholder="Префикс">
              <button class="secondary-button" type="button" onclick="generatePromos()">Создать</button>
            </div>
          </div>
          <div id="promoGenResult"></div>
          ${promos.items.length > 0 ? `
            <div class="promo-table-wrap">
              <table class="promo-table">
                <thead><tr><th>Код</th><th>Тариф</th><th>Срок</th><th>Исп.</th><th>Истекает</th></tr></thead>
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
          <h2 class="detail-title">Промокод</h2>
        </div>
        ${planInfo}
        <section class="section settings-section">
          <h3>${uiIcon("ticket")}<span>Активировать промокод</span></h3>
          <p class="settings-hint">Введите код, чтобы активировать подписку.</p>
          <div class="keyword-form keyword-add-row">
            <input id="promoCodeInput" type="text" placeholder="AROMA-XXXXXX" style="text-transform:uppercase">
            <button class="secondary-button" type="button" onclick="activatePromo()">Активировать</button>
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
    const prefix = document.getElementById("promoPrefix")?.value?.trim() || "AROMA";
    const resultEl = document.getElementById("promoGenResult");
    try {
      const result = await fetchJson("/api/admin/promos", {
        method: "POST",
        body: JSON.stringify({ tier, days, count, prefix }),
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
    renderTeam,
    createNewTeam,
    createTeamInvite,
    removeTeamMember,
    renderPromo,
    activatePromo,
    generatePromos,
  };
}
