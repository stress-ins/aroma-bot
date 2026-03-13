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
      </section>
    `;
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
    container.innerHTML = (phrases || []).map((phrase) => `
      <span class="keyword-chip">
        <span>${escapeHtml(phrase)}</span>
        <button type="button" aria-label="Удалить ${escapeHtml(phrase)}" onclick='removeForbiddenPhrase(${JSON.stringify(String(phrase))})'>×</button>
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
    if (!state.status) {
      state.status = await fetchJson("/api/status");
    }
    renderStatus();
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
        <section class="section settings-section">
          <h3>Запрещённые фразы</h3>
          <p class="settings-hint">Эти фразы будут исключены из всех сгенерированных текстов.</p>
          <div id="forbiddenPhrasesList" class="chips-list keyword-items"></div>
          <div class="keyword-form keyword-add-row">
            <input id="forbiddenPhraseInput" type="text" placeholder="Добавить фразу…">
            <button class="secondary-button" type="button" onclick="addForbiddenPhrase()">Добавить</button>
          </div>
        </section>
      </div>
    ` : `<div class="detail-empty">${renderGuidedState({
      eyebrow: "Статус",
      title: "Проверьте состояние источников",
      body: "Слева собраны все подключенные источники и их текущее состояние.",
    })}</div>`);
    if (inSettings) {
      void loadForbiddenPhrases();
      enterDetailView();
    } else {
      syncMobileNavigation();
    }
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
                      <button type="button" aria-label="Удалить ${escapeHtml(item)}" onclick='removeKeywordItem(${selectedTopic.topic_idx}, ${JSON.stringify(String(field))}, ${JSON.stringify(String(item))}, this)'>×</button>
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

  return {
    addKeywordItem,
    removeKeywordItem,
    openKeywordTopic,
    loadKeywords,
    loadSettings,
    renderSettingsSwitcher,
    renderStatus,
    renderKeywords,
    loadForbiddenPhrases,
    addForbiddenPhrase,
    removeForbiddenPhrase,
  };
}
