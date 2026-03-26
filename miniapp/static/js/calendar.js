/**
 * Content Calendar 2.0 — visual monthly grid with drag-and-drop scheduling.
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

  const DAY_HEADERS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

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
    // Convert Sunday=0 to Monday-based: Mon=0, Tue=1, ..., Sun=6
    return day === 0 ? 6 : day - 1;
  }

  function statusDotClass(type) {
    if (type === "published") return "cal-dot--published";
    if (type === "scheduled") return "cal-dot--scheduled";
    return "cal-dot--draft";
  }

  function statusBadge(type) {
    const labels = { published: "Опубликовано", scheduled: "Запланировано", draft: "Черновик" };
    const tones = { published: "good", scheduled: "warn", draft: "neutral" };
    return `<span class="tag tag--${tones[type] || "neutral"}">${labels[type] || type}</span>`;
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  // ── Data loading ─────────────────────────────────────────────────────────

  async function loadCalendar(monthOverride) {
    const month = monthOverride || state.calendarMonth;
    state.calendarMonth = month;
    state.calendarLoading = true;
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

  function toggleDayExpand(dateKey) {
    state.calendarExpandedDay = state.calendarExpandedDay === dateKey ? null : dateKey;
    renderCalendar();
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

    // Default to 12:00 of the target day
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

      // Create floating clone
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

    // Highlight cell under finger
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

  // ── Render ───────────────────────────────────────────────────────────────

  function renderCalendar() {
    const container = elements.draftList;
    if (!container) return;

    const month = state.calendarMonth;
    const today = todayStr();
    const daysInMonth = getDaysInMonth(month);
    const firstDayOffset = getFirstDayOfWeek(month);
    const days = state.calendarDays || {};

    // Header with navigation
    let html = `
      <div class="cal-header">
        <button class="cal-nav-btn" data-action="calPrevMonth" type="button">${uiIcon("chevron-left", 18)}</button>
        <div class="cal-header-center">
          <h2 class="cal-month-title">${escapeHtml(monthLabel(month))}</h2>
          <button class="cal-today-btn" data-action="calGoToday" type="button">Сегодня</button>
        </div>
        <button class="cal-nav-btn" data-action="calNextMonth" type="button">${uiIcon("chevron-right", 18)}</button>
      </div>
    `;

    if (state.calendarLoading) {
      html += `<div class="cal-loading"><div class="loading-spinner"></div></div>`;
      container.innerHTML = html;
      _attachCalendarEvents(container);
      return;
    }

    // Day headers
    html += `<div class="cal-day-headers">`;
    for (const dh of DAY_HEADERS) {
      html += `<div class="cal-day-header">${dh}</div>`;
    }
    html += `</div>`;

    // Grid
    html += `<div class="cal-grid">`;

    // Empty cells before first day
    for (let i = 0; i < firstDayOffset; i++) {
      html += `<div class="cal-cell cal-cell--empty"></div>`;
    }

    // Day cells
    const { year, month: mon } = parseMonth(month);
    for (let d = 1; d <= daysInMonth; d++) {
      const dateKey = `${year}-${String(mon).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const dayItems = days[dateKey] || [];
      const isToday = dateKey === today;
      const isExpanded = dateKey === state.calendarExpandedDay;
      const isWeekend = ((firstDayOffset + d - 1) % 7) >= 5;

      // Collect unique dot types
      const dotTypes = new Set(dayItems.map((i) => i.type));

      html += `<div class="cal-cell${isToday ? " cal-cell--today" : ""}${isExpanded ? " cal-cell--expanded" : ""}${isWeekend ? " cal-cell--weekend" : ""}" data-cal-day="${dateKey}">`;
      html += `  <div class="cal-cell-header" data-action="calToggleDay" data-date="${dateKey}">`;
      html += `    <span class="cal-cell-num">${d}</span>`;
      if (dayItems.length > 0) {
        html += `<div class="cal-dots">`;
        for (const dt of dotTypes) {
          html += `<span class="cal-dot ${statusDotClass(dt)}"></span>`;
        }
        html += `</div>`;
      }
      html += `  </div>`;

      // If expanded, show items
      if (isExpanded && dayItems.length > 0) {
        html += `<div class="cal-day-items">`;
        for (const item of dayItems) {
          const icon = contentKindIcon(item.kind);
          const time = formatTime(item.scheduled_at || item.published_at);
          html += `
            <div class="cal-item" draggable="true"
              data-cal-draft-id="${escapeHtml(item.draft_id)}"
              data-cal-date="${dateKey}"
              data-action="calOpenDraft" data-draft-id="${escapeHtml(item.draft_id)}">
              <div class="cal-item-icon">${uiIcon(icon, 14)}</div>
              <div class="cal-item-text">
                <span class="cal-item-topic">${escapeHtml((item.topic || "").substring(0, 40))}</span>
                ${time ? `<span class="cal-item-time">${time}</span>` : ""}
              </div>
              <div class="cal-item-badge">${statusBadge(item.type)}</div>
            </div>
          `;
        }
        html += `</div>`;
      }

      // Empty day "+" button
      if (dayItems.length === 0 && !isExpanded) {
        html += `<div class="cal-cell-empty-add" data-action="calCreateOnDay" data-date="${dateKey}">+</div>`;
      }

      html += `</div>`;
    }

    // Fill remaining cells to complete the grid row
    const totalCells = firstDayOffset + daysInMonth;
    const remaining = totalCells % 7 === 0 ? 0 : 7 - (totalCells % 7);
    for (let i = 0; i < remaining; i++) {
      html += `<div class="cal-cell cal-cell--empty"></div>`;
    }

    html += `</div>`;

    // Expanded day detail panel below grid
    if (state.calendarExpandedDay) {
      const dayItems = days[state.calendarExpandedDay] || [];
      const dayNum = parseInt(state.calendarExpandedDay.split("-")[2], 10);
      const monthIdx = parseInt(state.calendarExpandedDay.split("-")[1], 10) - 1;
      const dayLabel = `${dayNum} ${MONTHS_RU[monthIdx].toLowerCase()}`;

      html += `<div class="cal-expanded-panel">`;
      html += `<div class="cal-expanded-header">`;
      html += `  <h3>${escapeHtml(dayLabel)}</h3>`;
      html += `  <span class="cal-expanded-count">${dayItems.length} ${_pluralize(dayItems.length, "элемент", "элемента", "элементов")}</span>`;
      html += `</div>`;

      if (dayItems.length === 0) {
        html += `<div class="cal-expanded-empty">Нет контента на этот день</div>`;
      } else {
        for (const item of dayItems) {
          const icon = contentKindIcon(item.kind);
          const time = formatTime(item.scheduled_at || item.published_at);
          html += `
            <div class="cal-expanded-item" draggable="true"
              data-cal-draft-id="${escapeHtml(item.draft_id)}"
              data-cal-date="${state.calendarExpandedDay}"
              data-action="calOpenDraft" data-draft-id="${escapeHtml(item.draft_id)}">
              <div class="cal-expanded-item-icon">${uiIcon(icon, 18)}</div>
              <div class="cal-expanded-item-body">
                <div class="cal-expanded-item-topic">${escapeHtml(item.topic || "Без темы")}</div>
                <div class="cal-expanded-item-meta">
                  ${kindLabel(item.kind)} ${time ? `· ${time}` : ""}
                </div>
                ${item.preview ? `<div class="cal-expanded-item-preview">${escapeHtml(item.preview)}</div>` : ""}
              </div>
              <div class="cal-expanded-item-status">${statusBadge(item.type)}</div>
            </div>
          `;
        }
      }
      html += `</div>`;
    }

    container.innerHTML = html;
    _attachCalendarEvents(container);
    if (window.lucide) lucide.createIcons();
  }

  function _pluralize(n, one, few, many) {
    const abs = Math.abs(n) % 100;
    const n1 = abs % 10;
    if (abs > 10 && abs < 20) return many;
    if (n1 > 1 && n1 < 5) return few;
    if (n1 === 1) return one;
    return many;
  }

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

    // Day expand toggle
    container.querySelectorAll("[data-action='calToggleDay']").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleDayExpand(el.dataset.date);
      });
    });

    // Open draft
    container.querySelectorAll("[data-action='calOpenDraft']").forEach((el) => {
      el.addEventListener("click", (e) => {
        // Don't navigate if dragging
        if (e.defaultPrevented) return;
        const draftId = el.dataset.draftId;
        if (draftId) openDraft(draftId);
      });
    });

    // Create on day (navigate to create)
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
    toggleDayExpand,
  };
}
