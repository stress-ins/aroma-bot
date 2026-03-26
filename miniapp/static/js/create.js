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
          timeout: 20000,
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

    // Character counter
    const MAX_TOPIC_LEN = 200;
    let counter = form.querySelector(".char-counter");
    if (!counter) {
      counter = document.createElement("span");
      counter.className = "char-counter";
      topicField.parentNode.appendChild(counter);
    }
    const updateCounter = () => {
      const len = topicField.value.length;
      counter.textContent = `${len}/${MAX_TOPIC_LEN}`;
      counter.classList.toggle("warn", len > MAX_TOPIC_LEN * 0.8);
    };
    updateCounter();
    topicField.addEventListener("input", updateCounter);

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
    elements.draftCount.textContent = "";
    setEmptyState(true);

    const _cc = (tool, label) => state.selectedCreateTool === tool ? " active" : "";

    elements.draftList.innerHTML = `
      <div class="create-list">
        <div class="create-group-label">Текст</div>
        <article ${interactiveCardAttrs("Выбрать инструмент Пост для соцсетей")} class="create-card${_cc("content")} interactive-card" data-tool="content" data-action="renderCreateTool" data-args='["content"]'>
          <div class="draft-kind">${contentKindIcon("content")}<span>контент</span></div>
          <h3 class="draft-topic">Пост для соцсетей</h3>
          <div class="draft-preview">Instagram или Telegram.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Серия Threads")} class="create-card${_cc("threads_series")} interactive-card" data-tool="threads_series" data-action="renderCreateTool" data-args='["threads_series"]'>
          <div class="draft-kind">${contentKindIcon("threads_series")}<span>серия</span></div>
          <h3 class="draft-topic">Серия Threads</h3>
          <div class="draft-preview">Три поста: утро / день / вечер.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Контент-серия")} class="create-card${_cc("content_series")} interactive-card" data-tool="content_series" data-action="renderCreateTool" data-args='["content_series"]'>
          <div class="draft-kind">${contentKindIcon("content_series")}<span>серия</span></div>
          <h3 class="draft-topic">Контент-серия</h3>
          <div class="draft-preview">5-7 постов с единой темой.</div>
        </article>

        <div class="create-group-label">Видео</div>
        <article ${interactiveCardAttrs("Выбрать инструмент Сценарий и раскадровка")} class="create-card${_cc("reels")} interactive-card" data-tool="reels" data-action="renderCreateTool" data-args='["reels"]'>
          <div class="draft-kind">${contentKindIcon("reels")}<span>рилсы</span></div>
          <h3 class="draft-topic">Сценарий + раскадровка</h3>
          <div class="draft-preview">Сценарий и 4 кадра визуализации.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент YouTube-видео")} class="create-card${_cc("youtube")} interactive-card" data-tool="youtube" data-action="renderCreateTool" data-args='["youtube"]'>
          <div class="draft-kind">${contentKindIcon("youtube_video")}<span>YouTube видео</span></div>
          <h3 class="draft-topic">YouTube-видео</h3>
          <div class="draft-preview">Сценарий, B-roll, обложка, описание.</div>
        </article>

        <div class="create-group-label">Визуал</div>
        <article ${interactiveCardAttrs("Выбрать инструмент Карусель")} class="create-card${_cc("carousel")} interactive-card" data-tool="carousel" data-action="renderCreateTool" data-args='["carousel"]'>
          <div class="draft-kind">${contentKindIcon("carousel")}<span>карусель</span></div>
          <h3 class="draft-topic">Карусель</h3>
          <div class="draft-preview">5 слайдов с промптами для картинок.</div>
        </article>

        <div class="create-group-label">Планирование</div>
        <article ${interactiveCardAttrs("Выбрать инструмент Контент-план")} class="create-card${_cc("plan")} interactive-card" data-tool="plan" data-action="renderCreateTool" data-args='["plan"]'>
          <div class="draft-kind">${contentKindIcon("plan")}<span>план</span></div>
          <h3 class="draft-topic">Контент-план</h3>
          <div class="draft-preview">Сбор трендов и план на неделю.</div>
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

    let blendBannerHtml = "";
    const _blendTools = ["content", "carousel", "threads_series", "reels"];
    if (_blendTools.includes(toolId)) {
      try {
        const bcRaw = sessionStorage.getItem("blend_create_context");
        if (bcRaw) {
          const bc = JSON.parse(bcRaw);
          const oilCount = bc.oils?.length || 0;
          blendBannerHtml = `<div class="blend-context-banner">
            <div class="blend-context-banner-body"><strong>${escapeHtml(bc.name || "Смесь")}</strong>${oilCount} ${oilCount === 1 ? "масло" : oilCount < 5 ? "масла" : "масел"} · контекст передаётся в генерацию</div>
            <button type="button" class="blend-context-banner-dismiss" data-action="_dismissBlendContext" aria-label="Убрать контекст">&times;</button>
          </div>`;
        }
      } catch (_e) { /* ignore */ }
    }

    let dailyOilBannerHtml = "";
    if (_blendTools.includes(toolId)) {
      try {
        const doRaw = sessionStorage.getItem("daily_oil_context");
        if (doRaw) {
          const doc = JSON.parse(doRaw);
          dailyOilBannerHtml = `<div class="blend-context-banner daily-oil-context-banner">
            <div class="blend-context-banner-body"><i class="ph ph-sparkle" style="font-size:14px;vertical-align:-2px;margin-right:4px"></i><strong>${escapeHtml(doc.oil_name || "Масло дня")}</strong> · ${escapeHtml((doc.reason || "").slice(0, 60))}</div>
            <button type="button" class="blend-context-banner-dismiss" data-action="_dismissDailyOilContext" aria-label="Убрать контекст">&times;</button>
          </div>`;
        }
      } catch (_e) { /* ignore */ }
    }

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
            <label class="lightweight-toggle">
              <input type="checkbox" name="lightweight">
              <span>Быстрое планирование</span>
              <span class="field-help" style="margin:0">Только концепция + сценарий + описание. Без раскадровки и картинок.</span>
            </label>
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
            <div class="carousel-layout-picker">
              <p class="field-label">Раскладка слайда</p>
              <div class="layout-option-row">
                <label class="layout-option layout-option--active" id="layoutOptOverlay">
                  <input type="radio" name="layout_style" value="overlay" checked hidden>
                  <div class="layout-preview layout-preview--overlay">
                    <div class="lp-image"></div>
                    <div class="lp-text-overlay"></div>
                  </div>
                  <span>Полное фото</span>
                </label>
                <label class="layout-option" id="layoutOptEditorial">
                  <input type="radio" name="layout_style" value="editorial" hidden>
                  <div class="layout-preview layout-preview--editorial">
                    <div class="lp-image" style="height:55%"></div>
                    <div class="lp-text-block">
                      <span class="lp-highlight"></span>
                      <span class="lp-line"></span>
                    </div>
                  </div>
                  <span>Редакционная <small>(55%/45%)</small></span>
                </label>
              </div>
            </div>
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
    } else if (toolId === "youtube") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>Создать YouTube-видео</h3>
          <form class="create-form" data-create-youtube>
            <label>Тема<textarea name="topic" placeholder="Например: 5 масел для глубокого сна"></textarea></label>
            <p class="field-help">Тема станет основой сценария. Чем конкретнее — тем лучше результат.</p>
            <div class="field-grid">
              <label>Формат
                <select name="subformat">
                  <option value="talking_head">Talking Head (один спикер)</option>
                  <option value="listicle">Listicle / Top-N</option>
                  <option value="podcast">Подкаст / Интервью</option>
                </select>
              </label>
              <label>Цель
                <select name="goal">
                  <option value="trust">Доверие</option>
                  <option value="authority">Экспертность</option>
                  <option value="engagement">Вовлечённость</option>
                  <option value="sales">Продажи</option>
                </select>
              </label>
              <label>Эмоция
                <select name="emotion">
                  <option value="calm">Спокойствие</option>
                  <option value="curiosity">Любопытство</option>
                  <option value="inspiration">Вдохновение</option>
                  <option value="joy">Радость</option>
                  <option value="trust">Доверие</option>
                </select>
              </label>
              <label>Длительность
                <select name="duration_target">
                  <option value="5">5 мин</option>
                  <option value="10" selected>10 мин</option>
                  <option value="15">15 мин</option>
                  <option value="20">20 мин</option>
                  <option value="30">30 мин</option>
                </select>
              </label>
            </div>
            <button class="primary-button" type="submit">Создать сценарий</button>
          </form>
        </section>
      `;
    } else if (toolId === "content_series") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>Создать контент-серию</h3>
          <form class="create-form" data-create-content-series>
            <label>Шаблон
              <select name="template_key" id="seriesTemplateSelect">
                <option value="custom">Произвольная</option>
              </select>
            </label>
            <p class="field-help" id="seriesTemplateHint">Выберите шаблон или создайте произвольную серию.</p>
            <label>Тема<textarea name="topic" placeholder="Например: лаванда — масло недели"></textarea></label>
            <div class="field-grid">
              <label>Цель
                <select name="goal_key">
                  <option value="trust">Доверие</option>
                  <option value="authority">Экспертность</option>
                  <option value="engagement">Вовлечённость</option>
                  <option value="sales">Продажи</option>
                </select>
              </label>
              <label>Формат постов
                <select name="format_key">
                  <option value="instagram">Instagram</option>
                  <option value="telegram">Telegram</option>
                </select>
              </label>
              <label>Количество постов
                <select name="post_count">
                  <option value="5" selected>5 постов</option>
                  <option value="6">6 постов</option>
                  <option value="7">7 постов</option>
                </select>
              </label>
            </div>
            <button class="primary-button" type="submit">Создать серию</button>
          </form>
        </section>
      `;
    }

    // Inject context banners before <form> inside the section
    const contextBanners = blendBannerHtml + dailyOilBannerHtml;
    if (contextBanners && formHtml) {
      formHtml = formHtml.replace(/<form /, contextBanners + "<form ");
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
      const doRaw = sessionStorage.getItem("daily_oil_context");
      let daily_oil_context = null;
      if (doRaw) { try { daily_oil_context = JSON.parse(doRaw); } catch(_e) {} }
      const pending = openPendingDraftCreation(format, topic);
      try {
        const draft = await fetchJson("/api/generate/content", {
          method: "POST",
          timeout: 45000,
          body: JSON.stringify({ topic, goal_key: goal, format_key: format, blend_context, daily_oil_context }),
        });
        sessionStorage.removeItem("blend_create_context");
        sessionStorage.removeItem("daily_oil_context");
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
      const lightweight = reelsForm.querySelector("input[name='lightweight']")?.checked || false;
      const bcRaw = sessionStorage.getItem("blend_create_context");
      let blend_context = null;
      if (bcRaw) { try { blend_context = JSON.parse(bcRaw); } catch(_e) {} }
      const doRaw = sessionStorage.getItem("daily_oil_context");
      let daily_oil_context = null;
      if (doRaw) { try { daily_oil_context = JSON.parse(doRaw); } catch(_e) {} }
      const requestStartedAt = Date.now();
      const pending = openPendingReelsCreation(topic);
      try {
        const reel = await fetchJson("/api/generate/reels", {
          method: "POST",
          timeout: 45000,
          body: JSON.stringify({ topic, goal, emotion, lightweight, blend_context, daily_oil_context }),
        });
        sessionStorage.removeItem("blend_create_context");
        sessionStorage.removeItem("daily_oil_context");
        finalizePendingReelsCreation(reel);
      } catch (error) {
        if (error?.message === "request_timeout") {
          await recoverPendingReelsCreation(topic, pending.draft_id, requestStartedAt);
          return;
        }
        throw error;
      }
    } });

    const planForm = elements.draftDetail.querySelector("[data-create-plan]");
    if (planForm) {
      planForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        setTab("plans");
        elements.draftDetail.innerHTML = renderDetailLoader("Собираю план…");
        enterDetailView();

        try {
          const plan = await fetchJson("/api/generate/plan", { method: "POST", body: JSON.stringify({}), timeout: 45000 });
          state.selectedPlan = plan;
          await loadPlans();
          renderPlanDetail(plan);
          enterDetailView();
        } catch (err) {
          elements.draftDetail.innerHTML = renderBackButton() +
            `<div class="detail-empty"><p>Не удалось собрать план</p></div>`;
          throw err;
        }
      });
    }

    const carouselForm = elements.draftDetail.querySelector("[data-create-carousel]");
    if (carouselForm) {
      bindSuggestButton(carouselForm, () => ({
        goal_key: "trust",
        format_key: "carousel",
      }));
      carouselForm.querySelectorAll('[name="layout_style"]').forEach((radio) => {
        radio.addEventListener("change", () => {
          carouselForm.querySelectorAll(".layout-option").forEach((lbl) =>
            lbl.classList.toggle("layout-option--active", lbl.querySelector("input") === radio)
          );
        });
      });
    }
    if (carouselForm) bindTopicForm(carouselForm, { pendingText: "Создаю...", onSubmit: async (topic) => {
      const bcRaw = sessionStorage.getItem("blend_create_context");
      let blend_context = null;
      if (bcRaw) { try { blend_context = JSON.parse(bcRaw); } catch(_e) {} }
      const doRaw = sessionStorage.getItem("daily_oil_context");
      let daily_oil_context = null;
      if (doRaw) { try { daily_oil_context = JSON.parse(doRaw); } catch(_e) {} }
      const layoutStyle = carouselForm.querySelector('[name="layout_style"]:checked')?.value || "overlay";
      const pending = openPendingDraftCreation("carousel", topic);
      try {
        const draft = await fetchJson("/api/generate/carousel", {
          method: "POST",
          timeout: 45000,
          body: JSON.stringify({ topic, blend_context, daily_oil_context, layout_style: layoutStyle }),
        });
        sessionStorage.removeItem("blend_create_context");
        sessionStorage.removeItem("daily_oil_context");
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
      const doRaw = sessionStorage.getItem("daily_oil_context");
      let daily_oil_context = null;
      if (doRaw) { try { daily_oil_context = JSON.parse(doRaw); } catch(_e) {} }
      const pending = openPendingDraftCreation("threads_series", topic);
      try {
        const draft = await fetchJson("/api/generate/threads-series", {
          method: "POST",
          timeout: 60000,
          body: JSON.stringify({ topic, goal_key, emotion, blend_context, daily_oil_context }),
        });
        sessionStorage.removeItem("blend_create_context");
        sessionStorage.removeItem("daily_oil_context");
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

    // ── Content Series form ─────────────────────────────────────────
    const contentSeriesForm = elements.draftDetail.querySelector("[data-create-content-series]");
    if (contentSeriesForm) {
      // Load templates
      (async () => {
        try {
          const data = await fetchJson("/api/series/templates");
          const select = contentSeriesForm.querySelector("#seriesTemplateSelect");
          const hint = contentSeriesForm.querySelector("#seriesTemplateHint");
          if (select && data.templates) {
            data.templates.forEach(t => {
              const opt = document.createElement("option");
              opt.value = t.key;
              opt.textContent = t.label;
              select.appendChild(opt);
            });
            select.addEventListener("change", () => {
              const tmpl = data.templates.find(t => t.key === select.value);
              if (hint) hint.textContent = tmpl ? tmpl.description : "Произвольная серия.";
              const countSelect = contentSeriesForm.querySelector("select[name='post_count']");
              if (tmpl && countSelect) countSelect.value = String(tmpl.post_count);
            });
          }
        } catch (_e) { /* templates optional */ }
      })();

      bindTopicForm(contentSeriesForm, { pendingText: "Создаю серию...", onSubmit: async (topic) => {
        const goal_key = contentSeriesForm.querySelector("select[name='goal_key']")?.value || "trust";
        const format_key = contentSeriesForm.querySelector("select[name='format_key']")?.value || "instagram";
        const post_count = parseInt(contentSeriesForm.querySelector("select[name='post_count']")?.value || "5", 10);
        const template_key = contentSeriesForm.querySelector("select[name='template_key']")?.value || "custom";
        const pending = openPendingDraftCreation("content_series", topic);
        try {
          const draft = await fetchJson("/api/generate/content-series", {
            method: "POST",
            timeout: 90000,
            body: JSON.stringify({ topic, goal_key, format_key, post_count, template_key }),
          });
          finalizePendingDraftCreation(draft);
          await openDraft(draft.draft_id);
        } catch (error) {
          if (error?.message === "request_timeout") {
            await recoverPendingDraftCreation("content_series", topic, pending.draft_id);
            return;
          }
          throw error;
        }
      } });
    }

    // ── YouTube form ────────────────────────────────────────────────
    const youtubeForm = elements.draftDetail.querySelector("[data-create-youtube]");
    if (youtubeForm) {
      youtubeForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const topic = youtubeForm.querySelector("textarea[name='topic']")?.value?.trim();
        if (!topic) return;
        const subformat = youtubeForm.querySelector("select[name='subformat']")?.value || "talking_head";
        const goal = youtubeForm.querySelector("select[name='goal']")?.value || "trust";
        const emotion = youtubeForm.querySelector("select[name='emotion']")?.value || "calm";
        const duration_target = parseInt(youtubeForm.querySelector("select[name='duration_target']")?.value || "10", 10);
        const pending = openPendingDraftCreation("youtube_video", topic);
        try {
          const draft = await fetchJson("/api/generate/youtube", {
            method: "POST",
            timeout: 90000,
            body: JSON.stringify({ topic, subformat, goal, emotion, duration_target }),
          });
          finalizePendingDraftCreation(draft);
          await openDraft(draft.draft_id);
        } catch (error) {
          if (error?.message === "request_timeout") {
            await recoverPendingDraftCreation("youtube_video", topic, pending.draft_id);
            return;
          }
          throw error;
        }
      });
    }
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
