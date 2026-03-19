export function createCreateModule(deps) {
  const {
    state,
    elements,
    uiIcon,
    interactiveCardAttrs,
    contentKindIcon,
    renderGuidedState,
    renderBackButton,
    setEmptyState,
    syncMobileNavigation,
    enterDetailView,
    fetchJson,
    showRequestError,
    openPendingDraftCreation,
    finalizePendingDraftCreation,
    recoverPendingDraftCreation,
    openPendingReelsCreation,
    finalizePendingReelsCreation,
    recoverPendingReelsCreation,
    openDraft,
    openReels,
    setTab,
    loadPlans,
    renderPlanDetail,
    showUiNotice,
    escapeHtml,
  } = deps;

  function bindSuggestButton(form, getParams) {
    const btn = form.querySelector(".suggest-topic-btn");
    const dropdown = form.querySelector(".suggest-topics-dropdown");
    const topicField = form.querySelector("textarea[name='topic']");
    if (!btn || !dropdown || !topicField) return;

    btn.addEventListener("click", async () => {
      dropdown.hidden = false;
      dropdown.innerHTML = `<div class="suggest-topics-loading"><span class="button-spinner" aria-hidden="true"></span><span>Генерирую темы...</span></div>`;
      btn.disabled = true;
      try {
        const params = getParams();
        const data = await fetchJson("/api/suggest-topics", {
          method: "POST",
          body: JSON.stringify(params),
        });
        if (!data.topics || !data.topics.length) {
          dropdown.innerHTML = `<div class="suggest-topics-loading">Нет тем</div>`;
          return;
        }
        dropdown.innerHTML = `<p class="suggest-topics-hint">Нажмите на тему, чтобы выбрать</p>` + data.topics.map(t =>
          `<button type="button" class="suggest-topic-item" role="option">${escapeHtml(t)}</button>`
        ).join("");
        dropdown.querySelectorAll(".suggest-topic-item").forEach(item => {
          item.addEventListener("click", () => {
            topicField.value = item.textContent;
            topicField.dispatchEvent(new Event("input", { bubbles: true }));
            dropdown.hidden = true;
          });
        });
      } catch (err) {
        dropdown.hidden = true;
        showUiNotice("Не удалось предложить темы", "error");
      } finally {
        btn.disabled = false;
      }
    });
  }

  function bindTopicForm(form, config) {
    const topicField = form.querySelector("textarea[name='topic']");
    const submitButton = form.querySelector("button[type='submit']");
    if (!topicField || !submitButton) return;

    const updateState = () => {
      submitButton.disabled = !topicField.value.trim();
    };

    updateState();
    topicField.addEventListener("input", updateState);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const topic = topicField.value.trim();
      if (!topic) {
        topicField.focus();
        return;
      }

      const originalHtml = submitButton.innerHTML;
      submitButton.disabled = true;
      submitButton.classList.remove("did-complete", "did-error");
      submitButton.classList.add("is-busy");
      submitButton.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${config.pendingText || "Собираю..."}</span>`;

      try {
        await config.onSubmit(topic);
        submitButton.classList.remove("is-busy");
        submitButton.classList.add("did-complete");
        submitButton.innerHTML = `<span>${config.doneText || "Готово"}</span>`;
        window.setTimeout(() => {
          submitButton.classList.remove("did-complete");
          submitButton.innerHTML = originalHtml;
          updateState();
        }, 1200);
      } catch (error) {
        submitButton.classList.add("did-error");
        showRequestError(config.errorPrefix || "Не удалось выполнить действие", error);
        window.setTimeout(() => {
          submitButton.classList.remove("did-error");
          submitButton.innerHTML = originalHtml;
          updateState();
        }, 1200);
      } finally {
        submitButton.disabled = false;
        submitButton.classList.remove("is-busy");
      }
    });
  }

  function renderCreate() {
    elements.listTitle.textContent = "Инструменты";
    elements.draftCount.textContent = "5 типов";
    setEmptyState(true);

    elements.draftList.innerHTML = `
      <div class="create-list">
        <article ${interactiveCardAttrs("Выбрать инструмент Пост для соцсетей")} class="create-card${state.selectedCreateTool === "content" ? " active" : ""} interactive-card" data-tool="content" data-action="renderCreateTool" data-args='["content"]'>
          <div class="draft-kind">${contentKindIcon("content")}<span>контент</span></div>
          <h3 class="draft-topic">Пост для соцсетей</h3>
          <div class="draft-preview">Instagram или Telegram.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Сценарий и раскадровка")} class="create-card${state.selectedCreateTool === "reels" ? " active" : ""} interactive-card" data-tool="reels" data-action="renderCreateTool" data-args='["reels"]'>
          <div class="draft-kind">${contentKindIcon("reels")}<span>рилсы</span></div>
          <h3 class="draft-topic">Сценарий + раскадровка</h3>
          <div class="draft-preview">Сценарий и 4 кадра визуализации.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Контент-план")} class="create-card${state.selectedCreateTool === "plan" ? " active" : ""} interactive-card" data-tool="plan" data-action="renderCreateTool" data-args='["plan"]'>
          <div class="draft-kind">${contentKindIcon("plan")}<span>план</span></div>
          <h3 class="draft-topic">Контент-план</h3>
          <div class="draft-preview">Сбор трендов и план на неделю.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Карусель")} class="create-card${state.selectedCreateTool === "carousel" ? " active" : ""} interactive-card" data-tool="carousel" data-action="renderCreateTool" data-args='["carousel"]'>
          <div class="draft-kind">${contentKindIcon("carousel")}<span>карусель</span></div>
          <h3 class="draft-topic">Карусель</h3>
          <div class="draft-preview">5 слайдов с промптами для картинок.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Серия Threads")} class="create-card${state.selectedCreateTool === "threads_series" ? " active" : ""} interactive-card" data-tool="threads_series" data-action="renderCreateTool" data-args='["threads_series"]'>
          <div class="draft-kind">${contentKindIcon("threads_series")}<span>серия</span></div>
          <h3 class="draft-topic">Серия Threads</h3>
          <div class="draft-preview">Три поста: утро / день / вечер.</div>
        </article>
      </div>
    `;

    if (!state.selectedCreateTool) {
      elements.draftDetail.innerHTML = `<div class="detail-empty">${renderGuidedState({
        eyebrow: "Создать",
        title: "Выберите формат для старта",
        body: "Слева доступны быстрые сценарии для контента, рилса, плана недели и карусели.",
      })}</div>`;
      syncMobileNavigation();
      return;
    }

    renderCreateTool(state.selectedCreateTool);
  }

  function renderCreateTool(toolId) {
    state.selectedCreateTool = toolId;

    elements.draftList.querySelectorAll(".create-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.tool === toolId);
    });

    let formHtml = "";
    if (toolId === "content") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>Создать контент</h3>
          <form class="create-form" data-create-content>
            <label>Тема<textarea name="topic" placeholder="Например: как мягко переключиться после рабочего дня"></textarea></label>
            <p class="field-help">Сформулируйте тему как готовую мысль. Так черновик сразу получится ближе к нужной подаче.</p>
            <button type="button" class="suggest-topic-btn">${uiIcon("zap")}<span>Предложи тему</span></button>
            <div class="suggest-topics-dropdown" hidden></div>
            <div class="field-grid">
              <label>Цель<select name="goal_key"><option value="trust">Доверие</option><option value="authority">Экспертность</option><option value="engagement">Вовлечённость</option><option value="sales">Продажи</option></select></label>
              <label>Формат
                <div class="platform-format-select">
                  <label class="platform-format-option"><input type="radio" name="format_key" value="instagram" checked>${uiIcon("instagram")}<span>Instagram</span></label>
                  <label class="platform-format-option"><input type="radio" name="format_key" value="telegram">${uiIcon("telegram")}<span>Telegram</span></label>
                </div>
              </label>
            </div>
            <button class="primary-button" type="submit">Собрать черновик</button>
          </form>
          ${_trendSuggestionsPanel("instagram")}
        </section>
      `;
    } else if (toolId === "reels") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>СОЗДАТЬ РИЛС</h3>
          <form class="create-form" data-create-reels>
            <div class="field-grid">
              <label>Цель публикации
                <select name="goal">
                  <option value="trust">Доверие</option>
                  <option value="sale">Продажа</option>
                  <option value="engagement">Вовлечение</option>
                  <option value="expertise">Экспертность</option>
                </select>
              </label>
              <label>Эмоция зрителя
                <select name="emotion">
                  <option value="calm">Спокойствие</option>
                  <option value="joy">Радость</option>
                  <option value="curiosity">Любопытство</option>
                  <option value="inspiration">Вдохновение</option>
                  <option value="trust">Доверие</option>
                  <option value="mild_anxiety">Лёгкая тревога</option>
                </select>
              </label>
            </div>
            <label>Тема рилса
              <textarea name="topic" placeholder="Например: момент когда тело само переключается в отдых через запах"></textarea>
            </label>
            <p class="field-help">Опишите через сцену, состояние или ощущение — так легче получить рабочий сценарий.</p>
            <button type="button" class="suggest-topic-btn">${uiIcon("zap")}<span>Предложи тему</span></button>
            <div class="suggest-topics-dropdown" hidden></div>
            <button class="primary-button" type="submit" disabled>Создать рилс</button>
          </form>
        </section>
      `;
    } else if (toolId === "plan") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>Создать план</h3>
          <form class="create-form" data-create-plan>
            <div class="detail-preview">Собирает актуальные тренды и сохраняет недельный план с карточками, из которых можно сразу запускать черновики.</div>
            <button class="primary-button" type="submit">Собрать план на неделю</button>
          </form>
        </section>
      `;
    } else if (toolId === "carousel") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>Создать карусель</h3>
          <form class="create-form" data-create-carousel>
            <label>Тема<textarea name="topic" placeholder="Например: утренний ритуал с маслами"></textarea></label>
            <p class="field-help">Лучше работает тема с обещанием результата: что человек поймет, почувствует или сможет сделать после карусели.</p>
            <button type="button" class="suggest-topic-btn">${uiIcon("zap")}<span>Предложи тему</span></button>
            <div class="suggest-topics-dropdown" hidden></div>
            <button class="primary-button" type="submit">Собрать карусель</button>
          </form>
        </section>
      `;
    } else if (toolId === "threads_series") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>Создать серию Threads</h3>
          <form class="create-form" data-create-threads-series>
            <label>Тема<textarea name="topic" placeholder="Например: как восстановиться после перегруженной недели"></textarea></label>
            <p class="field-help">Тема станет основой для трёх постов: утреннего наблюдения, дневного совета и вечернего вопроса.</p>
            <button type="button" class="suggest-topic-btn">${uiIcon("zap")}<span>Предложи тему</span></button>
            <div class="suggest-topics-dropdown" hidden></div>
            <div class="field-grid">
              <label>Цель
                <select name="goal_key">
                  <option value="trust">Доверие</option>
                  <option value="authority">Экспертность</option>
                  <option value="engagement">Вовлечённость</option>
                  <option value="sales">Продажи</option>
                </select>
              </label>
              <label>Тональность
                <select name="emotion">
                  <option value="calm">Спокойная</option>
                  <option value="inspiration">Вдохновляющая</option>
                  <option value="curiosity">Любопытство</option>
                  <option value="trust">Доверие</option>
                  <option value="joy">Радость</option>
                </select>
              </label>
            </div>
            <button class="primary-button" type="submit">Создать серию</button>
          </form>
        </section>
      `;
    }

    elements.draftDetail.innerHTML = `
      <div class="detail-grid">
        ${renderBackButton()}
        ${formHtml}
      </div>
    `;

    enterDetailView();

    const contentForm = elements.draftDetail.querySelector("[data-create-content]");
    if (contentForm) {
      bindSuggestButton(contentForm, () => ({
        goal_key: contentForm.querySelector("select[name='goal_key']").value,
        format_key: contentForm.querySelector("[name='format_key']:checked")?.value || "instagram",
      }));
    }
    _bindTrendSuggestionsPanels();
    if (contentForm) bindTopicForm(contentForm, { pendingText: "Создаю...", onSubmit: async (topic) => {
      const goal = contentForm.querySelector("select[name='goal_key']").value;
      const format = contentForm.querySelector("[name='format_key']:checked")?.value || "instagram";
      const bcRaw = sessionStorage.getItem("blend_create_context");
      let blend_context = null;
      if (bcRaw) { try { blend_context = JSON.parse(bcRaw); } catch(_e) {} }
      const pending = openPendingDraftCreation(format, topic);
      try {
        const draft = await fetchJson("/api/generate/content", {
          method: "POST",
          timeout: 45000,
          body: JSON.stringify({ topic, goal_key: goal, format_key: format, blend_context }),
        });
        sessionStorage.removeItem("blend_create_context");
        finalizePendingDraftCreation(draft);
        await openDraft(draft.draft_id);
      } catch (error) {
        if (error?.message === "request_timeout") {
          await recoverPendingDraftCreation(format, topic, pending.draft_id);
          return;
        }
        throw error;
      }
    } });

    const reelsForm = elements.draftDetail.querySelector("[data-create-reels]");
    if (reelsForm) {
      bindSuggestButton(reelsForm, () => ({
        goal_key: reelsForm.querySelector("select[name='goal']")?.value || "trust",
        format_key: "reels_v2",
      }));
    }
    if (reelsForm) bindTopicForm(reelsForm, { pendingText: "Создаю...", onSubmit: async (topic) => {
      const goal = reelsForm.querySelector("select[name='goal']")?.value || "trust";
      const emotion = reelsForm.querySelector("select[name='emotion']")?.value || "calm";
      const bcRaw = sessionStorage.getItem("blend_create_context");
      let blend_context = null;
      if (bcRaw) { try { blend_context = JSON.parse(bcRaw); } catch(_e) {} }
      const pending = openPendingReelsCreation(topic);
      try {
        const reel = await fetchJson("/api/generate/reels", {
          method: "POST",
          timeout: 45000,
          body: JSON.stringify({ topic, goal, emotion, blend_context }),
        });
        sessionStorage.removeItem("blend_create_context");
        finalizePendingReelsCreation(reel);
        await openReels(reel.draft_id);
      } catch (error) {
        if (error?.message === "request_timeout") {
          await recoverPendingReelsCreation(topic, pending.draft_id);
          return;
        }
        throw error;
      }
    } });

    const planForm = elements.draftDetail.querySelector("[data-create-plan]");
    if (planForm) {
      planForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = planForm.querySelector("button");
        button.disabled = true;
        button.textContent = "Собираю...";
        planForm.classList.remove("did-error");
        try {
          const plan = await fetchJson("/api/generate/plan", { method: "POST", body: JSON.stringify({}) });
          state.selectedPlan = plan;
          setTab("plans");
          await loadPlans();
          renderPlanDetail(plan);
          enterDetailView();
        } catch (err) {
          planForm.classList.add("did-error");
          throw err;
        } finally {
          button.disabled = false;
          button.textContent = "Собрать план на неделю";
        }
      });
    }

    const carouselForm = elements.draftDetail.querySelector("[data-create-carousel]");
    if (carouselForm) {
      bindSuggestButton(carouselForm, () => ({
        goal_key: "trust",
        format_key: "carousel",
      }));
    }
    if (carouselForm) bindTopicForm(carouselForm, { pendingText: "Создаю...", onSubmit: async (topic) => {
      const bcRaw = sessionStorage.getItem("blend_create_context");
      let blend_context = null;
      if (bcRaw) { try { blend_context = JSON.parse(bcRaw); } catch(_e) {} }
      const pending = openPendingDraftCreation("carousel", topic);
      try {
        const draft = await fetchJson("/api/generate/carousel", {
          method: "POST",
          timeout: 45000,
          body: JSON.stringify({ topic, blend_context }),
        });
        sessionStorage.removeItem("blend_create_context");
        finalizePendingDraftCreation(draft);
        await openDraft(draft.draft_id);
      } catch (error) {
        if (error?.message === "request_timeout") {
          await recoverPendingDraftCreation("carousel", topic, pending.draft_id);
          return;
        }
        throw error;
      }
    } });

    const threadsSeriesForm = elements.draftDetail.querySelector("[data-create-threads-series]");
    if (threadsSeriesForm) {
      bindSuggestButton(threadsSeriesForm, () => ({
        goal_key: threadsSeriesForm.querySelector("select[name='goal_key']")?.value || "trust",
        format_key: "threads_series",
      }));
    }
    if (threadsSeriesForm) bindTopicForm(threadsSeriesForm, { pendingText: "Создаю...", onSubmit: async (topic) => {
      const goal_key = threadsSeriesForm.querySelector("select[name='goal_key']")?.value || "trust";
      const emotion = threadsSeriesForm.querySelector("select[name='emotion']")?.value || "";
      const bcRaw = sessionStorage.getItem("blend_create_context");
      let blend_context = null;
      if (bcRaw) { try { blend_context = JSON.parse(bcRaw); } catch(_e) {} }
      const pending = openPendingDraftCreation("threads_series", topic);
      try {
        const draft = await fetchJson("/api/generate/threads-series", {
          method: "POST",
          timeout: 60000,
          body: JSON.stringify({ topic, goal_key, emotion, blend_context }),
        });
        sessionStorage.removeItem("blend_create_context");
        finalizePendingDraftCreation(draft);
        await openDraft(draft.draft_id);
      } catch (error) {
        if (error?.message === "request_timeout") {
          await recoverPendingDraftCreation("threads_series", topic, pending.draft_id);
          return;
        }
        throw error;
      }
    } });
  }

  // ── Trend Suggestions Panel ────────────────────────────────────────

  const _suggestionsCache = {};
  const _CACHE_TTL = 3600_000; // 1 hour

  function _trendSuggestionsPanel(platform) {
    return `
      <details class="trend-suggestions-panel" data-platform="${platform}">
        <summary class="trend-suggestions-toggle">
          ${uiIcon("bar-chart-3")} Подсказки из трендов
        </summary>
        <div class="trend-suggestions-body" data-trend-body>
          <div class="suggest-topics-loading"><span class="button-spinner" aria-hidden="true"></span> Загрузка…</div>
        </div>
      </details>
    `;
  }

  function _bindTrendSuggestionsPanels() {
    document.querySelectorAll(".trend-suggestions-panel").forEach((panel) => {
      panel.addEventListener("toggle", async () => {
        if (!panel.open) return;
        const platform = panel.dataset.platform || "instagram";
        const body = panel.querySelector("[data-trend-body]");
        if (!body) return;

        const cacheKey = `trends_${platform}`;
        const cached = _suggestionsCache[cacheKey];
        if (cached && Date.now() - cached.ts < _CACHE_TTL) {
          body.innerHTML = _renderSuggestionsBody(cached.data, platform);
          return;
        }

        try {
          const data = await fetchJson(`/api/trends/suggestions?platform=${platform}`);
          _suggestionsCache[cacheKey] = { data, ts: Date.now() };
          body.innerHTML = _renderSuggestionsBody(data, platform);
        } catch {
          body.innerHTML = `<div class="field-help">Нет данных о трендах</div>`;
        }
      });
    });
  }

  function _renderSuggestionsBody(data, platform) {
    const parts = [];

    if (data.trending_topics?.length) {
      const items = data.trending_topics.map((t) =>
        `<button type="button" class="suggest-topic-item" data-action="_fillTopicFromSuggestion">${escapeHtml(t)}</button>`
      ).join("");
      parts.push(`<div class="trend-suggestions-section"><div class="trend-suggestions-label">Популярные темы</div>${items}</div>`);
    }

    if (data.trending_hashtags?.length && platform === "instagram") {
      const tags = data.trending_hashtags.map((t) => `<span class="trends-tagcloud-chip" style="font-size:0.8rem">#${escapeHtml(t)}</span>`).join(" ");
      parts.push(`<div class="trend-suggestions-section"><div class="trend-suggestions-label">Хэштеги</div><div class="trends-tagcloud">${tags}</div></div>`);
    }

    if (data.hooks?.length && platform === "threads") {
      const items = data.hooks.map((h) =>
        `<button type="button" class="suggest-topic-item" data-action="_fillTopicFromSuggestion">"${escapeHtml(h)}"</button>`
      ).join("");
      parts.push(`<div class="trend-suggestions-section"><div class="trend-suggestions-label">Зацепки (хуки)</div>${items}</div>`);
    }

    if (data.best_times?.length) {
      const times = data.best_times.slice(0, 3).map((t) => `${t.hour}:00`).join(", ");
      parts.push(`<div class="trend-suggestions-section"><div class="trend-suggestions-label">Лучшее время</div><div class="field-help">${times}</div></div>`);
    }

    return parts.length ? parts.join("") : `<div class="field-help">Нет данных о трендах</div>`;
  }

  return {
    bindTopicForm,
    renderCreate,
    renderCreateTool,
    _bindTrendSuggestionsPanels,
  };
}
