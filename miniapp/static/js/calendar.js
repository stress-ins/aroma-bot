/**
 * Content Calendar 2.0 — visual monthly grid with colored kind-dots,
 * week-strip detail view, and post cards.
 */
export function createCalendarModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    uiIcon,
    contentKindIcon,
    kindLabel,
    fetchJson,
    showUiNotice,
    enterDetailView,
    syncMobileNavigation,
    openDraft,
    setTab,
  } = deps;

  // ── State ────────────────────────────────────────────────────────────────
  if (!state.calendarMonth) {
    const now = new Date();
    state.calendarMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  }
  if (!state.calendarDays) state.calendarDays = {};
  if (!state.calendarExpandedDay) state.calendarExpandedDay = null;
  if (!state.calendarLoading) state.calendarLoading = false;

  const MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
  ];

  const MONTHS_RU_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
  ];

  const DAY_HEADERS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

  const WEEKDAYS_SHORT = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];

  const WEEKDAYS_FULL = [
    "воскресенье", "понедельник", "вторник", "среда",
    "четверг", "пятница", "суббота",
  ];

  const KIND_LABELS = {
    threads: "Тредс",
    threads_series: "Серия тредс",
    reels: "Рилс",
    reels_v2: "Рилс",
    carousel: "Карусель",
    content: "Контент",
    content_series: "Серия",
    instagram: "Instagram",
    youtube_video: "YouTube",
    plan: "План",
    telegram: "Telegram",
  };

  /** Legend items: kind => label */
  const LEGEND_KINDS = [
    { kind: "threads", label: "Тредс" },
    { kind: "reels", label: "Рилс" },
    { kind: "carousel", label: "Карусель" },
    { kind: "instagram", label: "Instagram" },
  ];

  // ── Helpers ──────────────────────────────────────────────────────────────

  function parseMonth(monthStr) {
    const [y, m] = monthStr.split("-").map(Number);
    return { year: y, month: m };
  }

  function monthLabel(monthStr) {
    const { year, month } = parseMonth(monthStr);
    return `${MONTHS_RU[month - 1]} ${year}`;
  }

  function prevMonth(monthStr) {
    const { year, month } = parseMonth(monthStr);
    const m = month - 1;
    if (m < 1) return `${year - 1}-12`;
    return `${year}-${String(m).padStart(2, "0")}`;
  }

  function nextMonth(monthStr) {
    const { year, month } = parseMonth(monthStr);
    const m = month + 1;
    if (m > 12) return `${year + 1}-01`;
    return `${year}-${String(m).padStart(2, "0")}`;
  }

  function todayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function getDaysInMonth(monthStr) {
    const { year, month } = parseMonth(monthStr);
    return new Date(year, month, 0).getDate();
  }

  function getFirstDayOfWeek(monthStr) {
    const { year, month } = parseMonth(monthStr);
    const day = new Date(year, month - 1, 1).getDay();
    return day === 0 ? 6 : day - 1;
  }

  function kindDotClass(kind) {
    const normalized = String(kind || "").toLowerCase();
    return `cal-dot--${normalized}`;
  }

  function statusLabel(type) {
    const labels = { published: "Опубликовано", scheduled: "Запланировано", draft: "Черновик" };
    return labels[type] || type;
  }

  function statusClass(type) {
    return `cpc-status--${type || "draft"}`;
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  function formatDateFull(dateKey) {
    const parts = dateKey.split("-").map(Number);
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    const dayNum = parts[2];
    const monthIdx = parts[1] - 1;
    const weekday = WEEKDAYS_FULL[d.getDay()];
    return `${dayNum} ${MONTHS_RU_GENITIVE[monthIdx]}, ${weekday}`;
  }

  function _pluralPub(n) {
    const abs = Math.abs(n) % 100;
    const n1 = abs % 10;
    if (abs > 10 && abs < 20) return "публикаций";
    if (n1 === 1) return "публикация";
    if (n1 > 1 && n1 < 5) return "публикации";
    return "публикаций";
  }

  /**
   * Get the Monday-based week containing a given date key.
   * Returns array of 7 date strings (Mon..Sun).
   */
  function getWeekDays(dateKey) {
    const parts = dateKey.split("-").map(Number);
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    const dayOfWeek = d.getDay(); // 0=Sun
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
    const monday = new Date(d);
    monday.setDate(d.getDate() + mondayOffset);

    const week = [];
    for (let i = 0; i < 7; i++) {
      const wd = new Date(monday);
      wd.setDate(monday.getDate() + i);
      const key = `${wd.getFullYear()}-${String(wd.getMonth() + 1).padStart(2, "0")}-${String(wd.getDate()).padStart(2, "0")}`;
      week.push(key);
    }
    return week;
  }

  /**
   * Get up to 3 preview dots for a day's posts (by kind).
   */
  function getDotsPreview(items) {
    const preview = items.slice(0, 3);
    return preview.map((item) => item.kind || "content");
  }

  // ── Data loading ─────────────────────────────────────────────────────────

  async function loadCalendar(monthOverride) {
    const month = monthOverride || state.calendarMonth;
    state.calendarMonth = month;
    state.calendarLoading = true;

    // Set title immediately — never show "Загрузка..." in header
    if (elements.listTitle) {
      elements.listTitle.textContent = "Контент";
    }

    renderCalendar();

    try {
      const data = await fetchJson(`/api/calendar?month=${month}`);
      state.calendarDays = data.days || {};
    } catch (e) {
      console.error("Failed to load calendar", e);
      state.calendarDays = {};
    }
    state.calendarLoading = false;
    renderCalendar();
  }

  // ── Navigation ───────────────────────────────────────────────────────────

  function goToPrevMonth() {
    state.calendarExpandedDay = null;
    loadCalendar(prevMonth(state.calendarMonth));
  }

  function goToNextMonth() {
    state.calendarExpandedDay = null;
    loadCalendar(nextMonth(state.calendarMonth));
  }

  function goToToday() {
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    state.calendarExpandedDay = todayStr();
    loadCalendar(month);
  }

  function selectDay(dateKey) {
    if (state.calendarExpandedDay === dateKey) {
      // Deselect — go back to grid
      state.calendarExpandedDay = null;
    } else {
      state.calendarExpandedDay = dateKey;
    }
    renderCalendar();
  }

  function backToGrid() {
    state.calendarExpandedDay = null;
    renderCalendar();
  }

  // ── Week strip navigation ───────────────────────────────────────────────

  function goToPrevWeek() {
    if (!state.calendarExpandedDay) return;
    const parts = state.calendarExpandedDay.split("-").map(Number);
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    d.setDate(d.getDate() - 7);
    const newKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    // Load month if needed
    const newMonth = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    state.calendarExpandedDay = newKey;
    if (newMonth !== state.calendarMonth) {
      loadCalendar(newMonth);
    } else {
      renderCalendar();
    }
  }

  function goToNextWeek() {
    if (!state.calendarExpandedDay) return;
    const parts = state.calendarExpandedDay.split("-").map(Number);
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    d.setDate(d.getDate() + 7);
    const newKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const newMonth = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    state.calendarExpandedDay = newKey;
    if (newMonth !== state.calendarMonth) {
      loadCalendar(newMonth);
    } else {
      renderCalendar();
    }
  }

  // ── Drag & Drop (reschedule) ─────────────────────────────────────────────

  let _dragDraftId = null;
  let _dragSourceDate = null;

  function handleDragStart(e) {
    const el = e.target.closest("[data-cal-draft-id]");
    if (!el) return;
    _dragDraftId = el.dataset.calDraftId;
    _dragSourceDate = el.dataset.calDate;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", _dragDraftId);
    el.classList.add("cal-item--dragging");
  }

  function handleDragEnd(e) {
    const el = e.target.closest("[data-cal-draft-id]");
    if (el) el.classList.remove("cal-item--dragging");
    _dragDraftId = null;
    _dragSourceDate = null;
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const cell = e.target.closest("[data-cal-day]");
    if (cell) cell.classList.add("cal-cell--drag-over");
  }

  function handleDragLeave(e) {
    const cell = e.target.closest("[data-cal-day]");
    if (cell) cell.classList.remove("cal-cell--drag-over");
  }

  async function handleDrop(e) {
    e.preventDefault();
    const cell = e.target.closest("[data-cal-day]");
    if (cell) cell.classList.remove("cal-cell--drag-over");

    if (!_dragDraftId || !cell) return;
    const targetDate = cell.dataset.calDay;
    if (!targetDate || targetDate === _dragSourceDate) return;

    const newScheduledAt = `${targetDate}T12:00:00+00:00`;

    try {
      await fetchJson(`/api/calendar/${_dragDraftId}/reschedule`, {
        method: "PATCH",
        body: JSON.stringify({ scheduled_at: newScheduledAt }),
      });
      showUiNotice("Перенесено", "success");
      await loadCalendar();
    } catch (err) {
      console.error("Reschedule failed", err);
      showUiNotice("Не удалось перенести", "error");
    }
  }

  // ── Touch drag for mobile ───────────────────────────────────────────────

  let _touchDraftId = null;
  let _touchSourceDate = null;
  let _touchClone = null;
  let _longPressTimer = null;

  function handleTouchStart(e) {
    const el = e.target.closest("[data-cal-draft-id]");
    if (!el) return;
    _longPressTimer = setTimeout(() => {
      _touchDraftId = el.dataset.calDraftId;
      _touchSourceDate = el.dataset.calDate;
      el.classList.add("cal-item--dragging");

      _touchClone = el.cloneNode(true);
      _touchClone.classList.add("cal-item--ghost");
      document.body.appendChild(_touchClone);
      const touch = e.touches[0];
      _touchClone.style.left = `${touch.clientX - 40}px`;
      _touchClone.style.top = `${touch.clientY - 20}px`;
    }, 400);
  }

  function handleTouchMove(e) {
    if (!_touchDraftId) {
      if (_longPressTimer) { clearTimeout(_longPressTimer); _longPressTimer = null; }
      return;
    }
    e.preventDefault();
    const touch = e.touches[0];
    if (_touchClone) {
      _touchClone.style.left = `${touch.clientX - 40}px`;
      _touchClone.style.top = `${touch.clientY - 20}px`;
    }

    document.querySelectorAll(".cal-cell--drag-over").forEach((c) => c.classList.remove("cal-cell--drag-over"));
    const target = document.elementFromPoint(touch.clientX, touch.clientY);
    const cell = target?.closest("[data-cal-day]");
    if (cell) cell.classList.add("cal-cell--drag-over");
  }

  async function handleTouchEnd(e) {
    if (_longPressTimer) { clearTimeout(_longPressTimer); _longPressTimer = null; }
    if (!_touchDraftId) return;

    document.querySelectorAll(".cal-item--dragging").forEach((el) => el.classList.remove("cal-item--dragging"));
    document.querySelectorAll(".cal-cell--drag-over").forEach((c) => c.classList.remove("cal-cell--drag-over"));

    if (_touchClone) { _touchClone.remove(); _touchClone = null; }

    const touch = e.changedTouches[0];
    const target = document.elementFromPoint(touch.clientX, touch.clientY);
    const cell = target?.closest("[data-cal-day]");

    if (cell) {
      const targetDate = cell.dataset.calDay;
      if (targetDate && targetDate !== _touchSourceDate) {
        const newScheduledAt = `${targetDate}T12:00:00+00:00`;
        try {
          await fetchJson(`/api/calendar/${_touchDraftId}/reschedule`, {
            method: "PATCH",
            body: JSON.stringify({ scheduled_at: newScheduledAt }),
          });
          showUiNotice("Перенесено", "success");
          await loadCalendar();
        } catch (err) {
          showUiNotice("Не удалось перенести", "error");
        }
      }
    }

    _touchDraftId = null;
    _touchSourceDate = null;
  }

  // ── Render: month grid view ─────────────────────────────────────────────

  function renderGridView() {
    const month = state.calendarMonth;
    const today = todayStr();
    const daysInMonth = getDaysInMonth(month);
    const firstDayOffset = getFirstDayOfWeek(month);
    const days = state.calendarDays || {};
    const selectedDay = state.calendarExpandedDay;

    let html = "";

    // Header with navigation
    html += `
      <div class="cal-header">
        <button class="cal-nav-btn" data-action="calPrevMonth" type="button">${uiIcon("chevron-left", 18)}</button>
        <div class="cal-header-center">
          <h2 class="cal-month-title">${escapeHtml(monthLabel(month))}</h2>
          <button class="cal-today-btn" data-action="calGoToday" type="button">Сегодня</button>
        </div>
        <button class="cal-nav-btn" data-action="calNextMonth" type="button">${uiIcon("chevron-right", 18)}</button>
      </div>
    `;

    // Day headers
    html += `<div class="cal-day-headers">`;
    for (const dh of DAY_HEADERS) {
      html += `<div class="cal-day-header">${dh}</div>`;
    }
    html += `</div>`;

    // Grid
    html += `<div class="cal-grid">`;

    for (let i = 0; i < firstDayOffset; i++) {
      html += `<div class="cal-cell cal-cell--empty"></div>`;
    }

    const { year, month: mon } = parseMonth(month);
    for (let d = 1; d <= daysInMonth; d++) {
      const dateKey = `${year}-${String(mon).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const dayItems = days[dateKey] || [];
      const isToday = dateKey === today;
      const isSelected = dateKey === selectedDay;
      const isWeekend = ((firstDayOffset + d - 1) % 7) >= 5;

      let cellClasses = "cal-cell";
      if (isToday) cellClasses += " cal-cell--today";
      if (isSelected) cellClasses += " cal-cell--selected";
      if (isWeekend) cellClasses += " cal-cell--weekend";

      html += `<div class="${cellClasses}" data-cal-day="${dateKey}">`;
      html += `  <div class="cal-cell-header" data-action="calSelectDay" data-date="${dateKey}">`;
      html += `    <span class="cal-cell-num">${d}</span>`;

      // Dots: first 3 posts by kind
      if (dayItems.length > 0) {
        const dotKinds = getDotsPreview(dayItems);
        html += `<div class="cal-dots">`;
        for (const kind of dotKinds) {
          html += `<span class="cal-dot ${kindDotClass(kind)}"></span>`;
        }
        html += `</div>`;
      }

      html += `  </div>`;

      // Count badge if > 3
      if (dayItems.length > 3) {
        html += `<div class="cal-count">${dayItems.length}</div>`;
      }

      // Empty day "+" button
      if (dayItems.length === 0) {
        html += `<div class="cal-cell-empty-add" data-action="calCreateOnDay" data-date="${dateKey}">+</div>`;
      }

      html += `</div>`;
    }

    // Fill remaining cells
    const totalCells = firstDayOffset + daysInMonth;
    const remaining = totalCells % 7 === 0 ? 0 : 7 - (totalCells % 7);
    for (let i = 0; i < remaining; i++) {
      html += `<div class="cal-cell cal-cell--empty"></div>`;
    }

    html += `</div>`;

    // Legend
    html += `<div class="cal-legend">`;
    for (const item of LEGEND_KINDS) {
      html += `<div class="cal-legend-item"><div class="cal-dot ${kindDotClass(item.kind)}"></div><span>${escapeHtml(item.label)}</span></div>`;
    }
    html += `</div>`;

    return html;
  }

  // ── Render: week strip + day detail ─────────────────────────────────────

  function renderWeekStripView() {
    const selectedDay = state.calendarExpandedDay;
    if (!selectedDay) return "";

    const today = todayStr();
    const days = state.calendarDays || {};
    const weekDays = getWeekDays(selectedDay);

    // Determine month label from selected day
    const selParts = selectedDay.split("-").map(Number);
    const selMonthLabel = `${MONTHS_RU[selParts[1] - 1]} ${selParts[0]}`;

    let html = "";

    // Back to grid
    html += `<button class="cal-back-to-grid" data-action="calBackToGrid" type="button">${uiIcon("chevron-left", 14)} Вернуться к сетке</button>`;

    // Week strip wrapper
    html += `<div class="cal-week-strip-wrap">`;

    // Header: month + nav
    html += `<div class="cal-week-strip-header">`;
    html += `  <button class="cal-week-strip-nav" data-action="calPrevWeek" type="button">${uiIcon("chevron-left", 14)}</button>`;
    html += `  <span class="cal-month-title">${escapeHtml(selMonthLabel)}</span>`;
    html += `  <button class="cal-week-strip-nav" data-action="calNextWeek" type="button">${uiIcon("chevron-right", 14)}</button>`;
    html += `</div>`;

    // Week days
    html += `<div class="cal-week-strip">`;
    for (let i = 0; i < 7; i++) {
      const dateKey = weekDays[i];
      const dateParts = dateKey.split("-").map(Number);
      const dayNum = dateParts[2];
      const dayDate = new Date(dateParts[0], dateParts[1] - 1, dateParts[2]);
      const wdIdx = dayDate.getDay(); // 0=Sun
      const wdLabel = WEEKDAYS_SHORT[wdIdx];
      const isSelected = dateKey === selectedDay;
      const isToday = dateKey === today;
      const dayItems = days[dateKey] || [];

      let dayClasses = "cal-week-strip-day";
      if (isSelected) dayClasses += " cal-week-strip-day--selected";
      if (isToday && !isSelected) dayClasses += " cal-week-strip-day--today";

      html += `<div class="${dayClasses}" data-action="calSelectDay" data-date="${dateKey}">`;
      html += `  <span class="cal-week-strip-wd">${wdLabel}</span>`;
      html += `  <div class="cal-week-strip-cell">`;
      html += `    <span class="cal-week-strip-num">${dayNum}</span>`;

      if (dayItems.length > 0) {
        const dotKinds = getDotsPreview(dayItems);
        html += `<div class="cal-week-strip-dots">`;
        for (const kind of dotKinds) {
          html += `<span class="cal-dot ${kindDotClass(kind)}"></span>`;
        }
        html += `</div>`;
      }

      html += `  </div>`;
      html += `</div>`;
    }
    html += `</div>`;
    html += `</div>`; // end wrap

    // Day detail header
    const dayItems = days[selectedDay] || [];
    const dateFormatted = formatDateFull(selectedDay);
    const countText = `${dayItems.length} ${_pluralPub(dayItems.length)}`;

    html += `<div class="day-detail-header">`;
    html += `  <div>`;
    html += `    <div class="ddh-date">${escapeHtml(dateFormatted)}</div>`;
    html += `    <div class="ddh-count">${escapeHtml(countText)}</div>`;
    html += `  </div>`;
    html += `  <button class="ddh-add-btn" data-action="calCreateOnDay" data-date="${selectedDay}" type="button">+ Добавить</button>`;
    html += `</div>`;

    // Post cards
    if (dayItems.length > 0) {
      html += `<div class="day-posts">`;
      for (const item of dayItems) {
        const normalizedKind = String(item.kind || "content").toLowerCase();
        const kindLabelText = KIND_LABELS[normalizedKind] || kindLabel(item.kind);
        const time = formatTime(item.scheduled_at || item.published_at);
        const typeIcon = contentKindIcon(item.kind);

        html += `<div class="cal-post-card cal-post-card--${escapeHtml(normalizedKind)}" data-action="calOpenDraft" data-draft-id="${escapeHtml(item.draft_id)}">`;
        html += `  <div class="cpc-top">`;
        html += `    <div class="cpc-badge">${typeIcon} ${escapeHtml(kindLabelText)}</div>`;
        html += `    <span class="cpc-time">${time ? escapeHtml(time) : ""}</span>`;
        html += `  </div>`;

        if (item.topic) {
          html += `  <div class="cpc-title">${escapeHtml(item.topic)}</div>`;
        } else if (item.preview) {
          html += `  <div class="cpc-title">${escapeHtml(item.preview)}</div>`;
        }

        html += `  <div class="cpc-meta">`;
        html += `    <span class="cpc-type">${escapeHtml(kindLabelText)}</span>`;
        html += `    <span class="cpc-status ${statusClass(item.type)}">${escapeHtml(statusLabel(item.type))}</span>`;
        html += `  </div>`;
        html += `</div>`;
      }
      html += `</div>`;
    } else {
      html += `<div class="cal-expanded-empty">Нет контента на этот день</div>`;
    }

    return html;
  }

  // ── Render: main entry ──────────────────────────────────────────────────

  function renderCalendar() {
    const container = elements.draftList;
    if (!container) return;

    // Always set title to "Контент"
    if (elements.listTitle) {
      elements.listTitle.textContent = "Контент";
    }

    // Loading state: show skeleton
    if (state.calendarLoading) {
      let html = renderGridView(); // Show header structure
      // Replace grid with skeleton
      html = `
        <div class="cal-header">
          <button class="cal-nav-btn" data-action="calPrevMonth" type="button">${uiIcon("chevron-left", 18)}</button>
          <div class="cal-header-center">
            <h2 class="cal-month-title">${escapeHtml(monthLabel(state.calendarMonth))}</h2>
            <button class="cal-today-btn" data-action="calGoToday" type="button">Сегодня</button>
          </div>
          <button class="cal-nav-btn" data-action="calNextMonth" type="button">${uiIcon("chevron-right", 18)}</button>
        </div>
        <div class="cal-skeleton">
          <div class="cal-skeleton-card"></div>
          <div class="cal-skeleton-card"></div>
          <div class="cal-skeleton-card"></div>
        </div>
      `;
      container.innerHTML = html;
      _attachCalendarEvents(container);
      return;
    }

    // If a day is selected, show week strip + detail
    let html;
    if (state.calendarExpandedDay) {
      html = renderWeekStripView();
    } else {
      html = renderGridView();
    }

    container.innerHTML = html;
    _attachCalendarEvents(container);
  }

  // ── Event binding ───────────────────────────────────────────────────────

  function _attachCalendarEvents(container) {
    // Navigation
    container.querySelectorAll("[data-action='calPrevMonth']").forEach((btn) => {
      btn.addEventListener("click", goToPrevMonth);
    });
    container.querySelectorAll("[data-action='calNextMonth']").forEach((btn) => {
      btn.addEventListener("click", goToNextMonth);
    });
    container.querySelectorAll("[data-action='calGoToday']").forEach((btn) => {
      btn.addEventListener("click", goToToday);
    });

    // Day selection (grid cells and week strip days)
    container.querySelectorAll("[data-action='calSelectDay']").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        selectDay(el.dataset.date);
      });
    });

    // Back to grid
    container.querySelectorAll("[data-action='calBackToGrid']").forEach((btn) => {
      btn.addEventListener("click", backToGrid);
    });

    // Week navigation
    container.querySelectorAll("[data-action='calPrevWeek']").forEach((btn) => {
      btn.addEventListener("click", goToPrevWeek);
    });
    container.querySelectorAll("[data-action='calNextWeek']").forEach((btn) => {
      btn.addEventListener("click", goToNextWeek);
    });

    // Open draft (post cards)
    container.querySelectorAll("[data-action='calOpenDraft']").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.defaultPrevented) return;
        const draftId = el.dataset.draftId;
        if (draftId) openDraft(draftId);
      });
    });

    // Create on day
    container.querySelectorAll("[data-action='calCreateOnDay']").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        setTab("create");
      });
    });

    // HTML5 drag & drop
    container.addEventListener("dragstart", handleDragStart);
    container.addEventListener("dragend", handleDragEnd);
    container.addEventListener("dragover", handleDragOver);
    container.addEventListener("dragleave", handleDragLeave);
    container.addEventListener("drop", handleDrop);

    // Touch drag
    container.addEventListener("touchstart", handleTouchStart, { passive: true });
    container.addEventListener("touchmove", handleTouchMove, { passive: false });
    container.addEventListener("touchend", handleTouchEnd);
  }

  // ── Public API ───────────────────────────────────────────────────────────

  return {
    loadCalendar,
    renderCalendar,
    goToPrevMonth,
    goToNextMonth,
    goToToday,
    toggleDayExpand: selectDay,
  };
}
