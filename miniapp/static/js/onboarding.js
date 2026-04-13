const STORAGE_KEY = "aroma_onboarded";
const WALKTHROUGH_KEY = "aroma_walkthrough_done";

const SLIDES = [
  { icon: "book-open", title: "База знаний", body: "Десятки эфирных масел, смеси и симптомы. Используйте поиск и фильтры для быстрого доступа к карточкам." },
  { icon: "pen-tool", title: "Контент-студия", body: "Создавайте посты, карусели и Reels. AI готовит черновик — вы редактируете и публикуете." },
  { icon: "sparkles", title: "Идеи и планирование", body: "Тренды, контент-планы и AI-рекомендации помогут вести соцсети системно." },
];

const WALKTHROUGH_STEPS = [
  {
    selector: "#bottomTabBar",
    title: "Навигация между разделами",
    body: "Переключайтесь между идеями, контентом, базой знаний и настройками.",
  },
  {
    selector: '#bottomTabBar [data-tab="create"]',
    title: "Создайте первый контент",
    body: "Нажмите «+», чтобы создать пост, карусель или Reels.",
  },
  {
    selector: '#bottomTabBar [data-tab="aromas"]',
    title: "Справочник масел и смесей",
    body: "Масла, готовые смеси и поиск по симптомам — всё в одном месте.",
  },
  {
    selector: '#bottomTabBar [data-tab="settings"]',
    title: "Настройте под себя",
    body: "Цветовая тема, AI-модели и управление командой.",
  },
];

const TOTAL_STEPS = SLIDES.length + WALKTHROUGH_STEPS.length;

const HELP_MAP = {
  "content/drafts": "Черновики ваших постов и каруселей. Откройте карточку → отредактируйте текст → согласуйте с командой → опубликуйте в Threads, Instagram или Telegram.",
  "content/create": "Создайте новый пост: выберите формат (пост, карусель, серия), задайте тему и платформу. AI подготовит черновик, который вы сможете отредактировать.",
  "content/plans": "Контент-план на неделю. Нажмите на день, чтобы создать черновик. Перетаскивайте карточки для смены даты. Из плана можно сразу перейти к редактированию и публикации.",
  "content/reels": "Создание Reels: загрузите видео → удалите паузы и слова-паразиты → соберите из кадров с шаблонами и анимацией → скачайте готовый ролик.",
  "content/archive": "Архив опубликованного контента. Смотрите статистику, повторно используйте удачные посты или репостите на другие платформы.",
  "content/mentions": "Отслеживание упоминаний бренда в Telegram, Threads и Instagram. Новые упоминания приходят автоматически.",
  "content/trends": "Актуальные тренды ароматерапии из соцсетей. Нажмите на тренд, чтобы создать пост на его основе.",
  "content/settings": "Настройки приложения: цветовая тема, выбор AI-моделей, управление командой и подпиской.",
  "handbook/aromas": "Десятки эфирных масел: свойства, дозировки, противопоказания и вопросы для рефлексии. Используйте поиск или фильтр по симптомам.",
  "handbook/blends": "Готовые смеси с рецептами и пропорциями. Нажмите на ингредиент для перехода к карточке масла. Можно создать свою смесь в конструкторе.",
  "handbook/symptoms": "Поиск масла по симптому или состоянию. Выберите проблему — получите список масел с рекомендациями по применению.",
};

export function createOnboardingModule(deps) {
  const { state, icon } = deps;

  function isOnboarded() {
    try { return localStorage.getItem(STORAGE_KEY) === "1"; } catch { return true; }
  }

  function isWalkthroughDone() {
    try { return localStorage.getItem(WALKTHROUGH_KEY) === "1"; } catch { return true; }
  }

  function buildProgressIndicator(_step) {
    // Removed text "Шаг X из 7" — dots already show progress
    return "";
  }

  function maybeShow() {
    if (isOnboarded()) {
      if (!isWalkthroughDone()) {
        requestAnimationFrame(() => startWalkthrough());
      }
      return;
    }
    let current = 0;
    const overlay = document.createElement("div");
    overlay.className = "onboarding-overlay";

    function render() {
      const slide = SLIDES[current];
      const isLast = current === SLIDES.length - 1;
      const dots = SLIDES.map((_, i) => `<span class="onboarding-dot${i === current ? " active" : ""}" role="img" aria-label="Слайд ${i + 1} из ${SLIDES.length}"></span>`).join("");
      overlay.innerHTML = `
        <div class="onboarding-slide">
          ${buildProgressIndicator(current + 1)}
          <div class="onboarding-icon">${icon(slide.icon, 48)}</div>
          <h2 class="onboarding-title">${slide.title}</h2>
          <p class="onboarding-body">${slide.body}</p>
          <div class="onboarding-dots">${dots}</div>
          <div class="onboarding-actions">
            <button class="primary-button onboarding-btn-next" type="button">${isLast ? "Далее" : "Далее"}</button>
            <button class="ghost-button onboarding-btn-skip" type="button">Пропустить</button>
          </div>
        </div>`;
      overlay.querySelector(".onboarding-btn-next").addEventListener("click", () => {
        if (isLast) {
          finishSlides();
        } else {
          current++;
          render();
        }
      });
      overlay.querySelector(".onboarding-btn-skip").addEventListener("click", finishAll);
    }

    function finishSlides() {
      try { localStorage.setItem(STORAGE_KEY, "1"); } catch {}
      overlay.classList.add("is-leaving");
      overlay.addEventListener("animationend", () => {
        overlay.remove();
        startWalkthrough();
      }, { once: true });
      setTimeout(() => {
        if (overlay.parentNode) {
          overlay.remove();
          startWalkthrough();
        }
      }, 400);
    }

    function finishAll() {
      try { localStorage.setItem(STORAGE_KEY, "1"); } catch {}
      try { localStorage.setItem(WALKTHROUGH_KEY, "1"); } catch {}
      overlay.classList.add("is-leaving");
      overlay.addEventListener("animationend", () => overlay.remove(), { once: true });
      setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 400);
    }

    let touchStartX = 0, touchStartY = 0;
    overlay.addEventListener("touchstart", (e) => { touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; }, { passive: true });
    overlay.addEventListener("touchend", (e) => {
      const dx = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(dx) < 50 || Math.abs(e.changedTouches[0].clientY - touchStartY) > Math.abs(dx)) return;
      if (dx < 0 && current < SLIDES.length - 1) { current++; render(); }
      else if (dx > 0 && current > 0) { current--; render(); }
    }, { passive: true });

    render();
    document.body.appendChild(overlay);
  }

  function startWalkthrough() {
    if (isWalkthroughDone()) return;
    let stepIndex = 0;

    const overlayEl = document.createElement("div");
    overlayEl.className = "walkthrough-overlay";
    overlayEl.setAttribute("role", "dialog");
    overlayEl.setAttribute("aria-label", "Интерактивное обучение");
    document.body.appendChild(overlayEl);

    function renderStep() {
      const step = WALKTHROUGH_STEPS[stepIndex];
      if (!step) { finishWalkthrough(); return; }
      const target = document.querySelector(step.selector);
      if (!target) { stepIndex++; renderStep(); return; }

      // Clear previous content
      overlayEl.innerHTML = "";

      // Position spotlight
      const rect = target.getBoundingClientRect();
      const padding = 8;

      const spotlight = document.createElement("div");
      spotlight.className = "walkthrough-spotlight";
      spotlight.style.top = `${rect.top - padding}px`;
      spotlight.style.left = `${rect.left - padding}px`;
      spotlight.style.width = `${rect.width + padding * 2}px`;
      spotlight.style.height = `${rect.height + padding * 2}px`;
      overlayEl.appendChild(spotlight);

      // Tooltip
      const tooltip = document.createElement("div");
      tooltip.className = "walkthrough-tooltip";
      const globalStep = SLIDES.length + stepIndex + 1;

      tooltip.innerHTML = `
        <div class="walkthrough-tooltip-content">
          ${buildProgressIndicator(globalStep)}
          <h3 class="walkthrough-tooltip-title">${step.title}</h3>
          <p class="walkthrough-tooltip-body">${step.body}</p>
          <div class="walkthrough-tooltip-actions">
            <button class="primary-button walkthrough-btn-next" type="button">${stepIndex === WALKTHROUGH_STEPS.length - 1 ? "Готово" : "Далее"}</button>
            <button class="ghost-button walkthrough-btn-skip" type="button">Пропустить</button>
          </div>
        </div>`;

      // Position tooltip above or below target
      const spaceBelow = window.innerHeight - rect.bottom;
      const spaceAbove = rect.top;
      if (spaceAbove > spaceBelow && spaceAbove > 160) {
        tooltip.classList.add("walkthrough-tooltip-above");
        tooltip.style.bottom = `${window.innerHeight - rect.top + padding + 12}px`;
      } else {
        tooltip.classList.add("walkthrough-tooltip-below");
        tooltip.style.top = `${rect.bottom + padding + 12}px`;
      }
      // Center horizontally relative to target, but constrain to viewport
      tooltip.style.left = `${Math.max(12, Math.min(window.innerWidth - 300, rect.left + rect.width / 2 - 144))}px`;

      overlayEl.appendChild(tooltip);

      // Bind buttons
      tooltip.querySelector(".walkthrough-btn-next").addEventListener("click", advanceStep);
      tooltip.querySelector(".walkthrough-btn-skip").addEventListener("click", finishWalkthrough);

      // Auto-advance if the target element is tapped
      function onTargetTap() {
        target.removeEventListener("click", onTargetTap);
        advanceStep();
      }
      target.addEventListener("click", onTargetTap);

      // Dismiss on overlay click (outside tooltip and spotlight)
      overlayEl.addEventListener("click", function onOverlayClick(e) {
        if (e.target === overlayEl) {
          overlayEl.removeEventListener("click", onOverlayClick);
          target.removeEventListener("click", onTargetTap);
          finishWalkthrough();
        }
      });
    }

    function advanceStep() {
      stepIndex++;
      if (stepIndex >= WALKTHROUGH_STEPS.length) {
        finishWalkthrough();
      } else {
        renderStep();
      }
    }

    function finishWalkthrough() {
      try { localStorage.setItem(WALKTHROUGH_KEY, "1"); } catch {}
      overlayEl.classList.add("is-leaving");
      overlayEl.addEventListener("animationend", () => overlayEl.remove(), { once: true });
      setTimeout(() => { if (overlayEl.parentNode) overlayEl.remove(); }, 400);
    }

    renderStep();
  }

  function resetOnboarding() {
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
    try { localStorage.removeItem(WALKTHROUGH_KEY); } catch {}
    maybeShow();
  }

  function initHelpFab() {
    const fab = document.createElement("button");
    fab.className = "help-fab";
    fab.type = "button";
    fab.setAttribute("aria-label", "Справка");
    fab.innerHTML = icon("question", 22);
    document.body.appendChild(fab);

    let popover = null;
    fab.addEventListener("click", () => {
      if (popover) { popover.remove(); popover = null; return; }
      const text = HELP_MAP[`${state.mode}/${state.tab}`] || "Нажмите на элемент для подробностей.";
      popover = document.createElement("div");
      popover.className = "help-popover";
      popover.setAttribute("role", "dialog");
      popover.setAttribute("aria-label", "Справка");
      popover.innerHTML = `<p>${text}</p><button class="ghost-button help-popover-close" type="button">Понятно</button>`;
      document.body.appendChild(popover);
      popover.querySelector(".help-popover-close").addEventListener("click", () => { popover.remove(); popover = null; });
    });

    new MutationObserver(() => {
      fab.style.display = document.body.classList.contains("is-keyboard-open") ? "none" : "";
    }).observe(document.body, { attributes: true, attributeFilter: ["class"] });
  }

  return { maybeShow, initHelpFab, startWalkthrough, resetOnboarding };
}
