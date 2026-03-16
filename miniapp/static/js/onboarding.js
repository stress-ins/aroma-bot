const STORAGE_KEY = "aroma_onboarded";

const SLIDES = [
  { icon: "book-open", title: "Справочник", body: "Найдите масло по симптому или свойству. Дозировки, рецепты, противопоказания." },
  { icon: "pen-tool", title: "Контент-студия", body: "AI подготовит текст для Threads, Instagram или Telegram за минуту." },
  { icon: "sparkles", title: "AI-помощник", body: "Планируйте публикации и управляйте контент-стратегией." },
];

const HELP_MAP = {
  "content/drafts": "Здесь хранятся черновики. Нажмите на карточку для редактирования.",
  "content/create": "Выберите формат и тему. AI сгенерирует черновик за секунды.",
  "handbook/aromas": "200+ эфирных масел. Используйте поиск для быстрого доступа.",
  "handbook/blends": "Готовые смеси с рецептами. Нажмите на ингредиент для перехода.",
  "handbook/symptoms": "Найдите масло по симптому или состоянию.",
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
      const dots = SLIDES.map((_, i) => `<span class="onboarding-dot${i === current ? " active" : ""}"></span>`).join("");
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
      if (window.lucide) lucide.createIcons({ nodes: [overlay] });
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
    fab.innerHTML = icon("help-circle", 22);
    document.body.appendChild(fab);
    if (window.lucide) lucide.createIcons({ nodes: [fab] });

    let popover = null;
    fab.addEventListener("click", () => {
      if (popover) { popover.remove(); popover = null; return; }
      const text = HELP_MAP[`${state.mode}/${state.tab}`] || "Нажмите на элемент для подробностей.";
      popover = document.createElement("div");
      popover.className = "help-popover";
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
