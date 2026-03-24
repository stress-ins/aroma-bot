const STORAGE_KEY = "aroma_onboarded";

const SLIDES = [
  { icon: "book-open", title: "База знаний", body: "74 эфирных масла, смеси и симптомы. Используйте поиск и фильтры для быстрого доступа к карточкам." },
  { icon: "pen-tool", title: "Контент-студия", body: "Создавайте посты, карусели и Reels. AI готовит черновик — вы редактируете и публикуете." },
  { icon: "sparkles", title: "Идеи и планирование", body: "Тренды, контент-планы и AI-рекомендации помогут вести соцсети системно." },
];

const HELP_MAP = {
  "content/drafts": "Черновики ваших постов и каруселей. Откройте карточку → отредактируйте текст → согласуйте с командой → опубликуйте в Threads, Instagram или Telegram.",
  "content/create": "Создайте новый пост: выберите формат (пост, карусель, серия), задайте тему и платформу. AI подготовит черновик, который вы сможете отредактировать.",
  "content/plans": "Контент-план на неделю. Нажмите на день, чтобы создать черновик. Перетаскивайте карточки для смены даты. Из плана можно сразу перейти к редактированию и публикации.",
  "content/reels": "Создание Reels: загрузите видео → удалите паузы и слова-паразиты → соберите из кадров с шаблонами и анимацией → скачайте готовый ролик.",
  "content/archive": "Архив опубликованного контента. Смотрите статистику, повторно используйте удачные посты или репостите на другие платформы.",
  "content/mentions": "Отслеживание упоминаний бренда в Telegram, Threads и Instagram. Новые упоминания приходят автоматически.",
  "content/trends": "Актуальные тренды ароматерапии из соцсетей. Нажмите на тренд, чтобы создать пост на его основе.",
  "content/settings": "Настройки приложения: цветовая тема, выбор AI-моделей, управление командой и подпиской.",
  "handbook/aromas": "74 эфирных масла: свойства, дозировки, противопоказания и вопросы для рефлексии. Используйте поиск или фильтр по симптомам.",
  "handbook/blends": "Готовые смеси с рецептами и пропорциями. Нажмите на ингредиент для перехода к карточке масла. Можно создать свою смесь в конструкторе.",
  "handbook/symptoms": "Поиск масла по симптому или состоянию. Выберите проблему — получите список масел с рекомендациями по применению.",
};

export function createOnboardingModule(deps) {
  const { state, icon } = deps;

  function isOnboarded() {
    try { return localStorage.getItem(STORAGE_KEY) === "1"; } catch { return true; }
  }

  function maybeShow() {
    if (isOnboarded()) return;
    let current = 0;
    const overlay = document.createElement("div");
    overlay.className = "onboarding-overlay";

    function render() {
      const slide = SLIDES[current];
      const isLast = current === SLIDES.length - 1;
      const dots = SLIDES.map((_, i) => `<span class="onboarding-dot${i === current ? " active" : ""}" role="img" aria-label="Слайд ${i + 1} из ${SLIDES.length}"></span>`).join("");
      overlay.innerHTML = `
        <div class="onboarding-slide">
          <div class="onboarding-icon">${icon(slide.icon, 48)}</div>
          <h2 class="onboarding-title">${slide.title}</h2>
          <p class="onboarding-body">${slide.body}</p>
          <div class="onboarding-dots">${dots}</div>
          <div class="onboarding-actions">
            <button class="primary-button onboarding-btn-next" type="button">${isLast ? "Начать" : "Далее"}</button>
            <button class="ghost-button onboarding-btn-skip" type="button">Пропустить</button>
          </div>
        </div>`;
      overlay.querySelector(".onboarding-btn-next").addEventListener("click", () => { if (isLast) finish(); else { current++; render(); } });
      overlay.querySelector(".onboarding-btn-skip").addEventListener("click", finish);
    }

    function finish() {
      try { localStorage.setItem(STORAGE_KEY, "1"); } catch {}
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

  return { maybeShow, initHelpFab };
}
