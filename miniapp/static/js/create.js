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
  } = deps;

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
        <article ${interactiveCardAttrs("Выбрать инструмент Пост для соцсетей")} class="create-card${state.selectedCreateTool === "content" ? " active" : ""} interactive-card" data-tool="content" onclick="renderCreateTool('content')">
          <div class="draft-kind">${contentKindIcon("content")}<span>контент</span></div>
          <h3 class="draft-topic">Пост для соцсетей</h3>
          <div class="draft-preview">Threads, Instagram или Telegram.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Сценарий и раскадровка")} class="create-card${state.selectedCreateTool === "reels" ? " active" : ""} interactive-card" data-tool="reels" onclick="renderCreateTool('reels')">
          <div class="draft-kind">${contentKindIcon("reels")}<span>рилсы</span></div>
          <h3 class="draft-topic">Сценарий + раскадровка</h3>
          <div class="draft-preview">Сценарий и 4 кадра визуализации.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Контент-план")} class="create-card${state.selectedCreateTool === "plan" ? " active" : ""} interactive-card" data-tool="plan" onclick="renderCreateTool('plan')">
          <div class="draft-kind">${contentKindIcon("plan")}<span>план</span></div>
          <h3 class="draft-topic">Контент-план</h3>
          <div class="draft-preview">Сбор трендов и план на неделю.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Карусель")} class="create-card${state.selectedCreateTool === "carousel" ? " active" : ""} interactive-card" data-tool="carousel" onclick="renderCreateTool('carousel')">
          <div class="draft-kind">${contentKindIcon("carousel")}<span>карусель</span></div>
          <h3 class="draft-topic">Карусель</h3>
          <div class="draft-preview">5 слайдов с промптами для картинок.</div>
        </article>
        <article ${interactiveCardAttrs("Выбрать инструмент Серия Threads")} class="create-card${state.selectedCreateTool === "threads_series" ? " active" : ""} interactive-card" data-tool="threads_series" onclick="renderCreateTool('threads_series')">
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
            <div class="field-grid">
              <label>Цель<select name="goal_key"><option value="trust">Доверие</option><option value="authority">Экспертность</option><option value="engagement">Вовлечённость</option><option value="sales">Продажи</option></select></label>
              <label>Формат
                <div class="platform-format-select">
                  <label class="platform-format-option"><input type="radio" name="format_key" value="threads" checked>${uiIcon("threads")}<span>Threads</span></label>
                  <label class="platform-format-option"><input type="radio" name="format_key" value="instagram">${uiIcon("instagram")}<span>Instagram</span></label>
                  <label class="platform-format-option"><input type="radio" name="format_key" value="telegram">${uiIcon("telegram")}<span>Telegram</span></label>
                </div>
              </label>
            </div>
            <button class="primary-button" type="submit">Собрать черновик</button>
          </form>
        </section>
      `;
    } else if (toolId === "reels") {
      formHtml = `
        <section class="section create-tool-panel">
          <h3>СОЗДАТЬ РИЛС</h3>
          <form class="create-form" data-create-reels>
            <label>Тема рилса
              <textarea name="topic" placeholder="Например: момент когда тело само переключается в отдых через запах"></textarea>
            </label>
            <p class="field-help">Опишите через сцену, состояние или ощущение — так легче получить рабочий сценарий.</p>
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
    if (contentForm) bindTopicForm(contentForm, { pendingText: "Создаю...", onSubmit: async (topic) => {
      const goal = contentForm.querySelector("select[name='goal_key']").value;
      const format = contentForm.querySelector("[name='format_key']:checked")?.value || "threads";
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

  return {
    bindTopicForm,
    renderCreate,
    renderCreateTool,
  };
}
