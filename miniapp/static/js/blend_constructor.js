export function createBlendConstructorModule(deps) {
  const {
    state,
    elements,
    escapeHtml,
    fetchJson,
    enterDetailView,
    syncMobileNavigation,
    renderBackButton,
    renderDetailLoader,
    showUiNotice,
    tagMarkup,
    openReference,
  } = deps;

  /* ── Blend Constructor ── */

  let _blendState = null;
  let _oilsCatalog = null;  // cached list from /api/references/aroma

  async function _loadOilsCatalog() {
    if (_oilsCatalog) return _oilsCatalog;
    try {
      const items = await fetchJson("/api/references/aroma");
      _oilsCatalog = (items || []).map(o => ({ slug: o.slug, name: o.name, name_en: o.name_en }));
    } catch { _oilsCatalog = null; return []; }
    return _oilsCatalog;
  }

  function openBlendConstructor(prefill = "") {
    enterDetailView();
    const effects = ["\u043a\u043e\u043d\u0446\u0435\u043d\u0442\u0440\u0430\u0446\u0438\u044f","\u0442\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e","\u0440\u0430\u0441\u0441\u043b\u0430\u0431\u043b\u0435\u043d\u0438\u0435","\u044d\u043d\u0435\u0440\u0433\u0438\u044f","\u0441\u043e\u043d","\u0431\u0430\u043b\u0430\u043d\u0441","\u0437\u0430\u0449\u0438\u0442\u0430"];
    const speeds = [["\u0431\u044b\u0441\u0442\u0440\u043e\u0435","fast"],["\u0441\u0440\u0435\u0434\u043d\u0435\u0435","medium"],["\u043f\u0440\u043e\u043b\u043e\u043d\u0433\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435","extended"]];
    const apps = [["\u0414\u0438\u0444\u0444\u0443\u0437\u043e\u0440","diffuser"],["\u041d\u0430\u043d\u0435\u0441\u0435\u043d\u0438\u0435","topical"],["\u0412\u043d\u0443\u0442\u0440\u044c","internal"],["\u041b\u044e\u0431\u043e\u0439","any"]];
    elements.draftDetail.innerHTML = `<div class="detail-grid blend-constructor-form">
      ${renderBackButton()}
      <p class="eyebrow">\u041a\u041e\u041d\u0421\u0422\u0420\u0423\u041a\u0422\u041e\u0420 \u0421\u041c\u0415\u0421\u0418</p>
      <h2 class="detail-title">\u041e\u043f\u0438\u0448\u0438\u0442\u0435 \u0437\u0430\u0434\u0430\u0447\u0443</h2>
      <section class="section"><label class="field-label">\u0427\u0442\u043e \u043d\u0443\u0436\u043d\u043e \u043e\u0442 \u0441\u043c\u0435\u0441\u0438?
        <textarea id="blendBrief" class="field-textarea" placeholder="\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0441\u043c\u0435\u0441\u044c \u0434\u043b\u044f \u043a\u043e\u043d\u0446\u0435\u043d\u0442\u0440\u0430\u0446\u0438\u0438 \u0438 \u0442\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u0430" data-on-input="updateConstructBtn">${escapeHtml(prefill)}</textarea>
      </label></section>
      <section class="section"><h3>\u0416\u0435\u043b\u0430\u0435\u043c\u044b\u0439 \u044d\u0444\u0444\u0435\u043a\u0442</h3>
        <div class="chip-list">${effects.map(e => `<button class="chip chip-selectable" data-effect="${e}" data-action="toggleEffect" data-args='[null]'>${e}</button>`).join("")}</div>
        <input type="text" id="blendCustomEffect" class="field-input" style="margin-top:8px" placeholder="\u0421\u0432\u043e\u0439 \u044d\u0444\u0444\u0435\u043a\u0442, \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0431\u043e\u0434\u0440\u043e\u0441\u0442\u044c \u0441 \u0443\u0442\u0440\u0430">
      </section>
      <section class="section"><h3>\u0421\u043a\u043e\u0440\u043e\u0441\u0442\u044c \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f</h3>
        <div class="radio-row">${speeds.map(([l,v]) => `<button class="chip chip-selectable ${v==="medium"?"is-selected":""}" data-speed="${v}" data-action="selectSpeed" data-args='[null]'>${l}</button>`).join("")}</div>
      </section>
      <section class="section"><h3>\u0421\u043f\u043e\u0441\u043e\u0431 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u0438\u044f</h3>
        <div class="radio-row">${apps.map(([l,v]) => `<button class="chip chip-selectable ${v==="any"?"is-selected":""}" data-app="${v}" data-action="selectApp" data-args='[null]'>${l}</button>`).join("")}</div>
      </section>
      <section class="section"><label class="field-label">\u041f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043a\u0430\u0437\u0430\u043d\u0438\u044f (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)
        <input type="text" id="blendContra" placeholder="\u0411\u0435\u0440\u0435\u043c\u0435\u043d\u043d\u043e\u0441\u0442\u044c, \u0430\u043b\u043b\u0435\u0440\u0433\u0438\u044f, \u0434\u0435\u0442\u0438..." class="field-input">
      </label></section>
      <button class="primary-button" id="constructBtn" data-action="submitBlendConstructor" data-args='[null]' ${!prefill ? "disabled" : ""}>\u041f\u043e\u0434\u043e\u0431\u0440\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
    </div>`;
  }

  function toggleEffect(btn) { btn.classList.toggle("is-selected"); }
  function selectSpeed(btn) { btn.closest(".radio-row").querySelectorAll(".chip-selectable").forEach(c => c.classList.remove("is-selected")); btn.classList.add("is-selected"); }
  function selectApp(btn) { btn.closest(".radio-row").querySelectorAll(".chip-selectable").forEach(c => c.classList.remove("is-selected")); btn.classList.add("is-selected"); }
  function updateConstructBtn() { const btn = document.getElementById("constructBtn"); const brief = document.getElementById("blendBrief"); if (btn && brief) btn.disabled = !brief.value.trim(); }

  function submitBlendConstructor(btn) {
    const brief = document.getElementById("blendBrief")?.value.trim();
    if (!brief) return;
    const effects = [...document.querySelectorAll(".chip-selectable.is-selected[data-effect]")].map(c => c.dataset.effect);
    const customEffect = document.getElementById("blendCustomEffect")?.value.trim();
    if (customEffect) effects.push(customEffect);
    const speed = document.querySelector("[data-speed].is-selected")?.dataset.speed || "medium";
    const application = document.querySelector("[data-app].is-selected")?.dataset.app || "any";
    const contraindications = document.getElementById("blendContra")?.value.trim() || "";

    // Show full-page loader (like draft generation)
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      ${renderDetailLoader("\u0413\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u044e \u0441\u043c\u0435\u0441\u044c", "\u041f\u043e\u0434\u0431\u0438\u0440\u0430\u044e \u043c\u0430\u0441\u043b\u0430, \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u044e \u0441\u043e\u0432\u043c\u0435\u0441\u0442\u0438\u043c\u043e\u0441\u0442\u044c \u0438 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u044c.")}
    </div>`;

    fetchJson("/api/blend-constructor/construct", {
      method: "POST",
      timeout: 60000,
      body: JSON.stringify({brief, effects, speed, application, contraindications}),
    }).then(result => {
      _blendState = { origRequest: {brief, effects, speed, application, contraindications} };
      try { sessionStorage.setItem("blend_last_result", JSON.stringify(result)); } catch(_e) {}
      renderBlendResult(result);
    }).catch((err) => {
      console.error("[BlendGen] error:", err);
      openBlendConstructor(brief);
      const msg = err?.message === "request_timeout"
        ? "\u0413\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f \u0437\u0430\u043d\u044f\u043b\u0430 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0434\u043e\u043b\u0433\u043e. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430."
        : "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c.";
      setTimeout(() => showUiNotice(msg, "error"), 100);
    });
  }

  /* ── Blend Result ── */

  function renderBlendResult(result) {
    _blendState = Object.assign(_blendState || {}, { oils: result.oils.map(o => ({...o, active: true, _origDrops: o.drops})), result });
    const blendState = _blendState;
    function recalcDrops() {
      const active = blendState.oils.filter(o => o.active);
      if (!active.length) return;
      const sum = active.reduce((s, o) => s + o.drops, 0);
      const target = result.total_drops;
      const scale = target / sum;
      active.forEach(o => { o.displayDrops = Math.max(1, Math.round(o.drops * scale)); });
      const tot = active.reduce((s, o) => s + (o.displayDrops || o.drops), 0);
      const diff = target - tot;
      if (diff !== 0) active[0].displayDrops = (active[0].displayDrops || active[0].drops) + diff;
    }
    function renderOils() {
      return blendState.oils.map(o => {
        const d = o.displayDrops || o.drops;
        const changed = o.active && d !== o._origDrops;
        const id = o.db_id || o.name_ru;
        return `<div class="oil-edit-row ${o.active ? "" : "is-removed"}">
          <button class="oil-edit-toggle ${o.active ? "is-on" : "is-off"}" data-action="blendToggleOil" data-args='${JSON.stringify([id])}'>${o.active ? "\u2713" : "\u2715"}</button>
          <span class="oil-edit-name">${escapeHtml(o.name_ru)}</span>
          <span class="oil-edit-drops ${changed ? "is-recalculated" : ""}">${o.active ? d + " \u043a\u0430\u043f." : "\u2014"}</span>
          <span class="oil-edit-role">${escapeHtml(o.role)}</span>
        </div>`;
      }).join("");
    }
    function renderProfileBars(p) {
      return [["\u041a\u043e\u043d\u0446\u0435\u043d\u0442\u0440\u0430\u0446\u0438\u044f","focus"],["\u0422\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e","creativity"],["\u042d\u043d\u0435\u0440\u0433\u0438\u044f","energy"],["\u0421\u043f\u043e\u043a\u043e\u0439\u0441\u0442\u0432\u0438\u0435","calm"]]
        .filter(([, k]) => (p[k] || 0) > 0)
        .map(([lbl, k]) => `<div class="profile-bar-row"><div class="profile-bar-label"><span>${lbl}</span><span>${p[k]}%</span></div><div class="profile-bar"><div class="profile-bar-fill" style="width:${p[k]}%"></div></div></div>`).join("");
    }
    window.blendToggleOil = function blendToggleOil(oilId) {
      const oil = blendState.oils.find(o => (o.db_id || o.name_ru) === oilId);
      if (!oil) return;
      if (oil.active && blendState.oils.filter(o => o.active).length <= 1) return;
      oil.active = !oil.active;
      recalcDrops();
      rerender();
    }
    function rerender() {
      const active = blendState.oils.filter(o => o.active);
      const total = active.reduce((s, o) => s + (o.displayDrops || o.drops), 0);
      const el = (id) => document.getElementById(id);
      if (el("blendOilsList")) el("blendOilsList").innerHTML = renderOils();
      if (el("blendTotalDrops")) el("blendTotalDrops").textContent = total;
      if (el("blendTotalLabel")) el("blendTotalLabel").textContent = `${total} \u043a\u0430\u043f. \u00b7 10 \u043c\u043b \u0431\u0430\u0437\u044b`;
      if (el("blendProfileBars")) el("blendProfileBars").innerHTML = renderProfileBars(result.profile);
      const warn = el("blendWarn");
      if (warn) { warn.hidden = active.length > 1; if (active.length === 1) warn.textContent = "\u041e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u043e\u0434\u043d\u043e \u043c\u0430\u0441\u043b\u043e \u2014 \u0441\u0438\u043d\u0435\u0440\u0433\u0438\u044f \u043f\u043e\u0442\u0435\u0440\u044f\u043d\u0430."; }
    }
    recalcDrops();
    const p = result.profile || {};
    const totalDrops = blendState.oils.filter(o => o.active).reduce((s, o) => s + (o.displayDrops || o.drops), 0);
    const safetyColor = {safe: "var(--good)", caution: "var(--brand)", warning: "var(--bad)"}[result.safety_status] || "var(--good)";
    const safetyLabel = {safe: "\u2713 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e", caution: "\u26a0 \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e", warning: "\u26d4 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f"}[result.safety_status] || "\u2713 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e";
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      <p class="eyebrow">\u041a\u041e\u041d\u0421\u0422\u0420\u0423\u041a\u0422\u041e\u0420 \u0421\u041c\u0415\u0421\u0418</p>
      <h2 class="detail-title">${escapeHtml(result.title)}</h2>
      <div class="draft-meta">${(result.tags || []).map(t => tagMarkup(t, "brand")).join("")}</div>
      <section class="section">
        <h3>\ud83d\udccb \u0420\u0435\u0446\u0435\u043f\u0442 \u00b7 <span id="blendTotalDrops">${totalDrops}</span> \u043a\u0430\u043f. <span class="section-hint">\u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u2713 \u0447\u0442\u043e\u0431\u044b \u0443\u0431\u0440\u0430\u0442\u044c \u043c\u0430\u0441\u043b\u043e</span></h3>
        <div id="blendOilsList">${renderOils()}</div>
        <div class="blend-total-row"><span>\u0418\u0442\u043e\u0433\u043e:</span><span id="blendTotalLabel">${totalDrops} \u043a\u0430\u043f. \u00b7 10 \u043c\u043b \u0431\u0430\u0437\u044b</span></div>
        <div class="blend-oil-picker" id="blendOilPicker">
          <div class="blend-oil-picker-selected" id="blendSelectedOils"></div>
          <div class="blend-oil-picker-input-wrap">
            <input type="text" id="blendOilSearch" class="field-input" placeholder="\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043c\u0430\u0441\u043b\u043e\u2026" autocomplete="off">
            <div class="blend-oil-dropdown" id="blendOilDropdown" hidden></div>
          </div>
          <button class="secondary-button" id="blendAdjustBtn" type="button" data-action="blendAdjustWithOil" data-args='[null]' disabled>\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c</button>
        </div>
      </section>
      <div class="field-help blend-warn" id="blendWarn" hidden></div>
      <section class="section"><h3>\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0441\u043c\u0435\u0441\u0438</h3><div id="blendProfileBars">${renderProfileBars(p)}</div></section>
      <div class="blend-expert-card blend-expert-aroma">
        <div class="blend-expert-header"><span class="blend-expert-icon">\ud83c\udf3f</span><div><div class="blend-expert-name">\u042d\u043a\u0441\u043f\u0435\u0440\u0442-\u0430\u0440\u043e\u043c\u0430\u0442\u0435\u0440\u0430\u043f\u0435\u0432\u0442</div><div class="blend-expert-sub">\u0421\u0438\u043d\u0435\u0440\u0433\u0438\u044f \u043c\u0430\u0441\u0435\u043b</div></div></div>
        <p class="blend-expert-text">${escapeHtml(result.expert_note)}</p>
        ${result.application_guide ? `<div class="blend-application"><span class="blend-application-label">\u041a\u0430\u043a \u043f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c:</span> ${escapeHtml(result.application_guide)}</div>` : ""}
      </div>
      <div class="blend-expert-card blend-expert-doctor">
        <div class="blend-expert-header"><span class="blend-expert-icon">\u2695\ufe0f</span><div><div class="blend-expert-name">\u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430</div></div><span class="blend-safety-badge" style="color:${safetyColor}">${safetyLabel}</span></div>
        <p class="blend-expert-text">${escapeHtml(result.doctor_note)}</p>
        ${result.restrictions?.length ? `<div class="blend-restrictions">${result.restrictions.map(r => `<div class="blend-restriction-row"><span class="chip chip-bad">${escapeHtml(r.condition)}</span><span>\u0438\u0441\u043a\u043b\u044e\u0447\u0438\u0442\u044c ${escapeHtml((r.oils_to_exclude || []).join(", "))}</span></div>`).join("")}</div>` : ""}
      </div>
      ${result.incompatible_oils?.length ? `<section class="section section-warning"><h3>\u26a0\ufe0f \u041d\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u044f\u0442\u044c \u0432 \u044d\u0442\u0443 \u0441\u043c\u0435\u0441\u044c</h3>${result.incompatible_oils.map(o => `<div class="incompat-row"><span class="chip chip-bad">${escapeHtml(o.name_ru)}</span><span>${escapeHtml(o.reason)}</span></div>`).join("")}</section>` : ""}
      <div class="blend-actions-stack">
        <button class="secondary-button" id="blendRegenBtn" type="button" style="width:100%" data-action="blendRegenerate" data-args='[null]'>\u041f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
        <div class="actions-grid-two">
          <button class="primary-button" id="blendSaveBtn" type="button" data-action="blendSaveCurrentBlend" data-args='[null]'>\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
          <button class="secondary-button" type="button" data-action="blendCreateContent">\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043a\u043e\u043d\u0442\u0435\u043d\u0442</button>
        </div>
        <button class="secondary-button" type="button" style="width:100%" data-action="blendOfWeek" data-args='[null]'>\u2728 \u0421\u043c\u0435\u0441\u044c \u043d\u0435\u0434\u0435\u043b\u0438 (\u043a\u0430\u0440\u0443\u0441\u0435\u043b\u044c + \u043f\u043e\u0441\u0442)</button>
        <div id="blendContentPicker" hidden style="margin-top:6px">
          <p class="field-help" style="margin-bottom:6px">\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0444\u043e\u0440\u043c\u0430\u0442:</p>
          <div class="chip-list">
            <button class="chip chip-selectable" data-action="blendLaunchContent" data-args='["content"]'>\u041f\u043e\u0441\u0442</button>
            <button class="chip chip-selectable" data-action="blendLaunchContent" data-args='["threads_series"]'>\u0421\u0435\u0440\u0438\u044f Threads</button>
            <button class="chip chip-selectable" data-action="blendLaunchContent" data-args='["carousel"]'>\u041a\u0430\u0440\u0443\u0441\u0435\u043b\u044c</button>
          </div>
        </div>
        <div class="actions-grid-two">
          <button class="secondary-button" data-action="openBlendConstructor">\u041d\u043e\u0432\u0430\u044f \u0441\u043c\u0435\u0441\u044c</button>
          <button class="secondary-button" data-action="clearSmartSearch">\u041a \u0431\u0430\u0437\u0435</button>
        </div>
      </div>
    </div>`;
    _initOilPicker(blendState);
  }

  /* ── Oil Picker (search from DB) ── */

  function _initOilPicker(blendState) {
    const searchInput = document.getElementById("blendOilSearch");
    const dropdown = document.getElementById("blendOilDropdown");
    const selectedContainer = document.getElementById("blendSelectedOils");
    const adjustBtn = document.getElementById("blendAdjustBtn");
    if (!searchInput || !dropdown) return;

    // Store on blendState so blendAdjustWithOil can read it
    blendState._pickerOils = [];
    const selectedOils = blendState._pickerOils;

    function renderSelected() {
      if (!selectedContainer) return;
      selectedContainer.innerHTML = selectedOils.map((o, i) =>
        `<span class="blend-oil-chip">${escapeHtml(o.name)} <button class="blend-oil-chip-x" data-idx="${i}">&times;</button></span>`
      ).join("");
      selectedContainer.querySelectorAll(".blend-oil-chip-x").forEach(btn => {
        btn.addEventListener("click", () => {
          selectedOils.splice(Number(btn.dataset.idx), 1);
          renderSelected();
        });
      });
      if (adjustBtn) adjustBtn.disabled = selectedOils.length === 0;
    }

    function showDropdown(items) {
      if (!items.length) { dropdown.hidden = true; return; }
      // Exclude oils already in blend + already selected
      const existingNames = new Set((blendState.oils || []).map(o => o.name_ru?.toLowerCase()));
      const selectedNames = new Set(selectedOils.map(o => o.name.toLowerCase()));
      const filtered = items.filter(o => !existingNames.has(o.name.toLowerCase()) && !selectedNames.has(o.name.toLowerCase()));
      if (!filtered.length) { dropdown.hidden = true; return; }
      dropdown.innerHTML = filtered.slice(0, 8).map(o =>
        `<div class="blend-oil-option" data-slug="${escapeHtml(o.slug)}" data-name="${escapeHtml(o.name)}">${escapeHtml(o.name)}${o.name_en ? ` <span class="blend-oil-option-en">${escapeHtml(o.name_en)}</span>` : ""}</div>`
      ).join("");
      dropdown.hidden = false;
      dropdown.querySelectorAll(".blend-oil-option").forEach(opt => {
        opt.addEventListener("click", () => {
          selectedOils.push({ name: opt.dataset.name, slug: opt.dataset.slug });
          searchInput.value = "";
          dropdown.hidden = true;
          renderSelected();
        });
      });
    }

    let _debounce = null;
    searchInput.addEventListener("input", () => {
      clearTimeout(_debounce);
      const q = searchInput.value.trim().toLowerCase();
      if (!q) { dropdown.hidden = true; return; }
      _debounce = setTimeout(async () => {
        const catalog = await _loadOilsCatalog();
        const matches = catalog.filter(o =>
          o.name.toLowerCase().includes(q) ||
          (o.name_en || "").toLowerCase().includes(q)
        );
        showDropdown(matches);
      }, 150);
    });

    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") dropdown.hidden = true;
    });

    // Close dropdown on click outside
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#blendOilPicker")) dropdown.hidden = true;
    }, { once: false });

    renderSelected();
  }

  async function openSavedBlends() {
    enterDetailView();
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      <p class="eyebrow">\u0421\u041e\u0425\u0420\u0410\u041d\u0401\u041d\u041d\u042b\u0415 \u0421\u041c\u0415\u0421\u0418</p>
      <div id="savedBlendsList" class="saved-blends-list"><p class="field-help">\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</p></div>
      <button class="primary-button" data-action="openBlendConstructor">\u041d\u043e\u0432\u0430\u044f \u0441\u043c\u0435\u0441\u044c</button>
    </div>`;
    try {
      const data = await fetchJson("/api/blend-constructor/saved");
      const items = data.items || [];
      const el = document.getElementById("savedBlendsList");
      if (!el) return;
      if (!items.length) {
        el.innerHTML = `<p class="field-help">\u041f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u044b\u0445 \u0441\u043c\u0435\u0441\u0435\u0439</p>`;
        return;
      }
      el.innerHTML = items.map(b => `
        <div class="saved-blend-card" data-action="openSavedBlendDetail" data-args='${JSON.stringify([b.id || b._id])}' style="cursor:pointer">
          <h3>${escapeHtml(b.title)}</h3>
          ${b.brief ? `<p class="field-help">${escapeHtml(b.brief)}</p>` : ""}
          <div class="draft-meta">${(b.tags || []).map(t => tagMarkup(t, "brand")).join("")}</div>
          <div class="saved-blend-oils">${(b.oils || []).map(o => `${escapeHtml(o.name_ru || o.name || o.name_en || '')} ${o.drops}\u043a.`).join(" \u00b7 ")}</div>
        </div>`).join("");
    } catch {
      const el = document.getElementById("savedBlendsList");
      if (el) el.innerHTML = `<p class="field-help">\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c</p>`;
    }
  }

  async function deleteSavedBlend(id, btn) {
    if (!confirm("\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u0443\u044e \u0441\u043c\u0435\u0441\u044c?")) return;
    if (btn) { btn.disabled = true; btn.textContent = "\u0423\u0434\u0430\u043b\u044f\u044e..."; }
    try {
      await fetchJson(`/api/blend-constructor/saved/${id}`, { method: "DELETE" });
      showUiNotice("\u0421\u043c\u0435\u0441\u044c \u0443\u0434\u0430\u043b\u0435\u043d\u0430", "success");
      openSavedBlends();
    } catch {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c", "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u0423\u0434\u0430\u043b\u0438\u0442\u044c"; }
    }
  }

  function blendSaveCurrentBlend(btn) {
    if (!_blendState?.result) return;
    const r = _blendState.result;
    const req = _blendState.origRequest || {};
    if (btn) { btn.disabled = true; btn.textContent = "\u0421\u043e\u0445\u0440\u0430\u043d\u044f\u044e..."; }
    fetchJson("/api/blend-constructor/saved", {
      method: "POST",
      body: JSON.stringify({
        title: r.title,
        brief: req.brief || "",
        tags: r.tags || [],
        oils: (_blendState.oils || r.oils).filter(o => o.active !== false).map(o => ({name_ru: o.name_ru, name_en: o.name_en, drops: o.displayDrops || o.drops, role: o.role})),
        total_drops: r.total_drops,
        profile: r.profile || {},
        expert_note: r.expert_note || "",
        application_guide: r.application_guide || "",
        safety_status: r.safety_status || "safe",
      }),
    }).then(() => {
      showUiNotice("\u0421\u043c\u0435\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430", "success");
      if (btn) { btn.textContent = "\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e"; }
    }).catch(() => {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c", "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c"; }
    });
  }

  async function blendOfWeek(btn) {
    if (!_blendState?.result) return;
    const r = _blendState.result;
    const req = _blendState.origRequest || {};
    const bc = {
      title: r.title, brief: req.brief || "",
      oils: (_blendState.oils || r.oils).filter(o => o.active !== false).map(o => ({
        name_ru: o.name_ru, name_en: o.name_en || "", drops: o.displayDrops || o.drops, role: o.role || "",
      })),
      total_drops: r.total_drops, profile: r.profile || {},
      expert_note: r.expert_note || "", application_guide: r.application_guide || "",
      tags: r.tags || [],
    };
    await withButtonFeedback(btn, "Создаю...", async () => {
      const result = await fetchJson("/api/blend-constructor/blend-of-week", {
        method: "POST",
        body: JSON.stringify(bc),
        timeout: 30000,
      });
      showUiNotice(`Создано 2 черновика: карусель и пост`, "success");
      // Navigate to drafts tab
      if (typeof window.setTab === "function") window.setTab("drafts");
    }, "Готово");
  }

  function blendCreateContent() {
    const picker = document.getElementById("blendContentPicker");
    if (picker) picker.hidden = !picker.hidden;
  }

  function blendLaunchContent(toolId) {
    if (!_blendState?.result) return;
    const r = _blendState.result;
    const req = _blendState.origRequest || {};
    const oilsList = (_blendState.oils || r.oils).filter(o => o.active !== false).map(o => `${o.name_ru} ${o.displayDrops || o.drops} \u043a\u0430\u043f.`).join(", ");
    const topic = `${r.title}${req.brief ? ": " + req.brief : ""}. \u0421\u043e\u0441\u0442\u0430\u0432: ${oilsList}.`;
    // Save blend context for create form
    try {
      const bc = {
        title: r.title, brief: req.brief || "",
        oils: (_blendState.oils || r.oils).filter(o => o.active !== false).map(o => ({
          name_ru: o.name_ru, name_en: o.name_en || "", drops: o.displayDrops || o.drops, role: o.role || "",
        })),
        total_drops: r.total_drops, profile: r.profile || {},
        expert_note: r.expert_note || "", application_guide: r.application_guide || "",
        tags: r.tags || [],
      };
      sessionStorage.setItem("blend_create_context", JSON.stringify(bc));
    } catch(_e) {}
    if (typeof window.openCreateTool === "function") window.openCreateTool(toolId);
    let attempts = 0;
    const tryFill = () => {
      attempts++;
      const selectors = ["[data-create-content] [name=topic]", "[data-create-threads-series] [name=topic]", "[data-create-carousel] [name=topic]", "#createForm textarea"];
      for (const sel of selectors) {
        const ta = document.querySelector(sel);
        if (ta && !ta.value) { ta.value = topic; ta.dispatchEvent(new Event("input")); return; }
      }
      if (attempts < 15) setTimeout(tryFill, 80);
    };
    setTimeout(tryFill, 80);
  }

  function blendRegenerate(btn) {
    if (!_blendState?.origRequest) return;
    const req = _blendState.origRequest;
    const prevResult = _blendState.result;
    // Collect oils that user toggled off — tell LLM to exclude them
    const excludeOils = (_blendState.oils || [])
      .map(o => o.name_ru);
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      ${renderDetailLoader("\u041f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u044e \u0441\u043c\u0435\u0441\u044c", "\u0421\u043e\u0441\u0442\u0430\u0432\u043b\u044f\u044e \u043d\u043e\u0432\u044b\u0439 \u0432\u0430\u0440\u0438\u0430\u043d\u0442 \u0440\u0435\u0446\u0435\u043f\u0442\u0430 \u0441 \u0442\u0435\u043c\u0438 \u0436\u0435 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u0430\u043c\u0438.")}
    </div>`;
    fetchJson("/api/blend-constructor/construct", {
      method: "POST",
      timeout: 60000,
      body: JSON.stringify({...req, skip_cache: true, exclude_oils: excludeOils}),
    }).then(result => {
      renderBlendResult(result);
    }).catch(() => {
      if (prevResult) renderBlendResult(prevResult);
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437.", "error");
    });
  }

  function blendAdjustWithOil(btn) {
    const oils = (_blendState?._pickerOils || []).map(o => o.name);
    if (!oils.length || !_blendState?.origRequest) return;
    const req = _blendState.origRequest;
    const prevResult = _blendState.result;
    const loaderSub = "\u0414\u043e\u0431\u0430\u0432\u043b\u044f\u044e " + (oils.length > 1 ? oils.length + " \u043c\u0430\u0441\u0435\u043b" : "\u043c\u0430\u0441\u043b\u043e") + " \u0438 \u043f\u0435\u0440\u0435\u0441\u0447\u0438\u0442\u044b\u0432\u0430\u044e \u0440\u0435\u0446\u0435\u043f\u0442.";
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      ${renderDetailLoader("\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u044e \u0441\u043c\u0435\u0441\u044c", loaderSub)}
    </div>`;
    fetchJson("/api/blend-constructor/adjust", {
      method: "POST",
      timeout: 60000,
      body: JSON.stringify({...req, custom_oils: oils}),
    }).then(result => {
      _blendState.origRequest = {...req, custom_oils: oils};
      renderBlendResult(result);
    }).catch(() => {
      if (prevResult) renderBlendResult(prevResult);
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c", "error");
    });
  }

  async function shareBlend(savedId, title) {
    const shareUrl = `https://t.me/aromara_bot?start=blend_${savedId}`;
    const shareText = `${title || "\u0421\u043c\u0435\u0441\u044c"} \u2014 \u0441\u043e\u0437\u0434\u0430\u043d\u043e \u0432 Aroma Trends`;
    if (navigator.share) {
      try {
        await navigator.share({ title: shareText, url: shareUrl });
        return;
      } catch { /* user cancelled — fall through to clipboard */ }
    }
    try {
      await navigator.clipboard.writeText(shareUrl);
      showUiNotice("\u0421\u0441\u044b\u043b\u043a\u0430 \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0430", "success");
    } catch {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443", "error");
    }
  }

  async function openSavedBlendDetail(savedId) {
    enterDetailView();
    elements.draftDetail.innerHTML = `<div class="detail-grid">${renderDetailLoader("\u0417\u0430\u0433\u0440\u0443\u0436\u0430\u044e \u0441\u043c\u0435\u0441\u044c")}</div>`;
    try {
      const blend = await fetchJson(`/api/blend-constructor/saved/${savedId}`);
      state.viewingSavedBlend = blend;
      _renderSavedBlendDetail(blend);
    } catch {
      elements.draftDetail.innerHTML = `<div class="detail-grid">${renderBackButton()}<p class="field-help">\u0421\u043c\u0435\u0441\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430</p></div>`;
    }
  }

  function _renderSavedBlendDetail(blend) {
    const safetyColors = { safe: "var(--good)", caution: "var(--brand)", warning: "var(--bad)" };
    const safetyLabels = { safe: "\u2713 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e", caution: "\u26a0 \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e", warning: "\u26d4 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f" };
    const safetyColor = safetyColors[blend.safety_status] || safetyColors.safe;
    const safetyLabel = safetyLabels[blend.safety_status] || blend.safety_status;
    function renderProfileBars(profile) {
      if (!profile || !Object.keys(profile).length) return "";
      const labels = { focus: "\u0424\u043e\u043a\u0443\u0441", energy: "\u042d\u043d\u0435\u0440\u0433\u0438\u044f", creativity: "\u0422\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e", calm: "\u0421\u043f\u043e\u043a\u043e\u0439\u0441\u0442\u0432\u0438\u0435" };
      return Object.entries(profile).filter(([, v]) => v > 0).map(([k, v]) => `<div class="profile-bar-row"><div class="profile-bar-label"><span>${escapeHtml(labels[k] || k)}</span><span>${v}%</span></div><div class="profile-bar"><div class="profile-bar-fill" style="width:${v}%"></div></div></div>`).join("");
    }
    const savedId = blend.id || blend._id || blend.saved_id;
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      <p class="eyebrow">\u0421\u041e\u0425\u0420\u0410\u041d\u0401\u041d\u041d\u0410\u042f \u0421\u041c\u0415\u0421\u042c</p>
      <h2 class="detail-title">${escapeHtml(blend.title)}</h2>
      ${blend.brief ? `<p class="field-help">${escapeHtml(blend.brief)}</p>` : ""}
      ${(blend.tags || []).length ? `<div class="draft-meta">${blend.tags.map(t => tagMarkup(t, "brand")).join("")}</div>` : ""}
      <section class="section">
        <h3>\ud83d\udccb \u0420\u0435\u0446\u0435\u043f\u0442 \u00b7 ${blend.total_drops || 0} \u043a\u0430\u043f.</h3>
        <div class="saved-blend-oils-detail">${(blend.oils || []).map(o => `<div class="oil-row"><span class="oil-name">${escapeHtml(o.name_ru || o.name || "")}${o.name_en ? ` <span class="oil-name-en">${escapeHtml(o.name_en)}</span>` : ""}</span><span class="oil-drops">${o.drops} \u043a\u0430\u043f.</span>${o.role ? `<span class="oil-role">${escapeHtml(o.role)}</span>` : ""}</div>`).join("")}</div>
        <div class="blend-total-row"><span>\u0418\u0442\u043e\u0433\u043e:</span><span>${blend.total_drops || 0} \u043a\u0430\u043f. \u00b7 10 \u043c\u043b \u0431\u0430\u0437\u044b</span></div>
      </section>
      ${Object.keys(blend.profile || {}).length ? `<section class="section"><h3>\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0441\u043c\u0435\u0441\u0438</h3>${renderProfileBars(blend.profile)}</section>` : ""}
      ${blend.expert_note ? `<div class="blend-expert-card blend-expert-aroma"><div class="blend-expert-header"><span class="blend-expert-icon">\ud83c\udf3f</span><div><div class="blend-expert-name">\u042d\u043a\u0441\u043f\u0435\u0440\u0442-\u0430\u0440\u043e\u043c\u0430\u0442\u0435\u0440\u0430\u043f\u0435\u0432\u0442</div></div></div><p class="blend-expert-text">${escapeHtml(blend.expert_note)}</p>${blend.application_guide ? `<div class="blend-application"><span class="blend-application-label">\u041a\u0430\u043a \u043f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c:</span> ${escapeHtml(blend.application_guide)}</div>` : ""}</div>` : ""}
      <div class="blend-expert-card blend-expert-doctor"><div class="blend-expert-header"><span class="blend-expert-icon">\u2695\ufe0f</span><div><div class="blend-expert-name">\u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430</div></div><span class="blend-safety-badge" style="color:${safetyColor}">${safetyLabel}</span></div></div>
      <div class="blend-actions-stack">
        <button class="secondary-button" type="button" style="width:100%" data-action="savedBlendCreateContent">\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043a\u043e\u043d\u0442\u0435\u043d\u0442</button>
        <div id="savedBlendContentPicker" hidden style="margin-top:6px">
          <p class="field-help" style="margin-bottom:6px">\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0444\u043e\u0440\u043c\u0430\u0442:</p>
          <div class="chip-list">
            <button class="chip chip-selectable" data-action="savedBlendLaunchContent" data-args='["content"]'>\u041f\u043e\u0441\u0442</button>
            <button class="chip chip-selectable" data-action="savedBlendLaunchContent" data-args='["threads_series"]'>\u0421\u0435\u0440\u0438\u044f Threads</button>
            <button class="chip chip-selectable" data-action="savedBlendLaunchContent" data-args='["carousel"]'>\u041a\u0430\u0440\u0443\u0441\u0435\u043b\u044c</button>
          </div>
        </div>
        <div class="actions-grid-two">
          <button class="secondary-button" type="button" data-action="shareBlend" data-args='${JSON.stringify([savedId, blend.title])}'>\u041f\u043e\u0434\u0435\u043b\u0438\u0442\u044c\u0441\u044f</button>
          <button class="danger-button" type="button" data-action="deleteSavedBlendFromDetail" data-args='${JSON.stringify([savedId, null])}'>\u0423\u0434\u0430\u043b\u0438\u0442\u044c</button>
        </div>
      </div>
    </div>`;
    if (window.lucide) lucide.createIcons();
  }

  function savedBlendCreateContent() {
    const picker = document.getElementById("savedBlendContentPicker");
    if (picker) picker.hidden = !picker.hidden;
  }

  function savedBlendLaunchContent(toolId) {
    const blend = state.viewingSavedBlend;
    if (!blend) return;
    const oilsList = (blend.oils || []).map(o => `${o.name_ru || o.name || ""} ${o.drops} \u043a\u0430\u043f.`).join(", ");
    const topic = `${blend.title}${blend.brief ? ": " + blend.brief : ""}. \u0421\u043e\u0441\u0442\u0430\u0432: ${oilsList}.`;
    try {
      const bc = {
        title: blend.title, brief: blend.brief || "",
        oils: (blend.oils || []).map(o => ({
          name_ru: o.name_ru || o.name || "", name_en: o.name_en || "", drops: o.drops, role: o.role || "",
        })),
        total_drops: blend.total_drops, profile: blend.profile || {},
        expert_note: blend.expert_note || "", application_guide: blend.application_guide || "",
        tags: blend.tags || [],
      };
      sessionStorage.setItem("blend_create_context", JSON.stringify(bc));
    } catch(_e) {}
    if (typeof window.openCreateTool === "function") window.openCreateTool(toolId);
    let attempts = 0;
    const tryFill = () => {
      attempts++;
      const selectors = ["[data-create-content] [name=topic]", "[data-create-threads-series] [name=topic]", "[data-create-carousel] [name=topic]", "#createForm textarea"];
      for (const sel of selectors) {
        const ta = document.querySelector(sel);
        if (ta && !ta.value) { ta.value = topic; ta.dispatchEvent(new Event("input")); return; }
      }
      if (attempts < 15) setTimeout(tryFill, 80);
    };
    setTimeout(tryFill, 80);
  }

  async function deleteSavedBlendFromDetail(id, btn) {
    if (!confirm("\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u0443\u044e \u0441\u043c\u0435\u0441\u044c?")) return;
    if (btn) { btn.disabled = true; btn.textContent = "\u0423\u0434\u0430\u043b\u044f\u044e..."; }
    try {
      await fetchJson(`/api/blend-constructor/saved/${id}`, { method: "DELETE" });
      showUiNotice("\u0421\u043c\u0435\u0441\u044c \u0443\u0434\u0430\u043b\u0435\u043d\u0430", "success");
      state.viewingSavedBlend = null;
      openSavedBlends();
    } catch {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0443\u0434\u0430\u043b\u0438\u0442\u044c", "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u0423\u0434\u0430\u043b\u0438\u0442\u044c"; }
    }
  }

  async function openSharedBlend(savedId) {
    enterDetailView();
    elements.draftDetail.innerHTML = `<div class="detail-grid">${renderDetailLoader()}</div>`;
    try {
      const blend = await fetchJson(`/api/blend-constructor/shared/${savedId}`);
      const safetyColors = { safe: "#22c55e", caution: "#f59e0b", warning: "#ef4444" };
      const safetyLabels = { safe: "\u0411\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e", caution: "\u041e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e", warning: "\u041e\u043f\u0430\u0441\u043d\u043e" };
      const safetyColor = safetyColors[blend.safety_status] || safetyColors.safe;
      const safetyLabel = safetyLabels[blend.safety_status] || blend.safety_status;
      function renderProfileBars(profile) {
        if (!profile || !Object.keys(profile).length) return "";
        const labels = { focus: "\u0424\u043e\u043a\u0443\u0441", energy: "\u042d\u043d\u0435\u0440\u0433\u0438\u044f", creativity: "\u0422\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u043e", calm: "\u0421\u043f\u043e\u043a\u043e\u0439\u0441\u0442\u0432\u0438\u0435" };
        return Object.entries(profile).map(([k, v]) => `<div class="profile-bar-row"><span class="profile-bar-label">${escapeHtml(labels[k] || k)}</span><div class="profile-bar-track"><div class="profile-bar-fill" style="width:${v}%"></div></div><span class="profile-bar-value">${v}</span></div>`).join("");
      }
      elements.draftDetail.innerHTML = `<div class="detail-grid">
        ${renderBackButton()}
        <p class="eyebrow">\u0421\u041c\u0415\u0421\u042c</p>
        <h2>${escapeHtml(blend.title)}</h2>
        ${blend.brief ? `<p class="field-help">${escapeHtml(blend.brief)}</p>` : ""}
        ${(blend.tags || []).length ? `<div class="draft-meta">${blend.tags.map(t => tagMarkup(t, "brand")).join("")}</div>` : ""}
        <section class="section">
          <h3>\ud83d\udccb \u0420\u0435\u0446\u0435\u043f\u0442 \u00b7 ${blend.total_drops} \u043a\u0430\u043f.</h3>
          <div class="saved-blend-oils-detail">${(blend.oils || []).map(o => `<div class="oil-row"><span class="oil-name">${escapeHtml(o.name_ru)}${o.name_en ? ` <span class="oil-name-en">${escapeHtml(o.name_en)}</span>` : ""}</span><span class="oil-drops">${o.drops} \u043a\u0430\u043f.</span>${o.role ? `<span class="oil-role">${escapeHtml(o.role)}</span>` : ""}</div>`).join("")}</div>
          <div class="blend-total-row"><span>\u0418\u0442\u043e\u0433\u043e:</span><span>${blend.total_drops} \u043a\u0430\u043f. \u00b7 10 \u043c\u043b \u0431\u0430\u0437\u044b</span></div>
        </section>
        ${Object.keys(blend.profile || {}).length ? `<section class="section"><h3>\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0441\u043c\u0435\u0441\u0438</h3>${renderProfileBars(blend.profile)}</section>` : ""}
        ${blend.expert_note ? `<div class="blend-expert-card blend-expert-aroma"><div class="blend-expert-header"><span class="blend-expert-icon">\ud83c\udf3f</span><div><div class="blend-expert-name">\u042d\u043a\u0441\u043f\u0435\u0440\u0442-\u0430\u0440\u043e\u043c\u0430\u0442\u0435\u0440\u0430\u043f\u0435\u0432\u0442</div></div></div><p class="blend-expert-text">${escapeHtml(blend.expert_note)}</p>${blend.application_guide ? `<div class="blend-application"><span class="blend-application-label">\u041a\u0430\u043a \u043f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c:</span> ${escapeHtml(blend.application_guide)}</div>` : ""}</div>` : ""}
        <div class="blend-expert-card blend-expert-doctor"><div class="blend-expert-header"><span class="blend-expert-icon">\u2695\ufe0f</span><div><div class="blend-expert-name">\u041c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430</div></div><span class="blend-safety-badge" style="color:${safetyColor}">${safetyLabel}</span></div></div>
      </div>`;
      if (window.lucide) lucide.createIcons();
    } catch {
      elements.draftDetail.innerHTML = `<div class="detail-grid">${renderBackButton()}<p class="field-help">\u0421\u043c\u0435\u0441\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430 \u0438\u043b\u0438 \u0431\u044b\u043b\u0430 \u0443\u0434\u0430\u043b\u0435\u043d\u0430</p></div>`;
    }
  }

  return {
    openBlendConstructor,
    toggleEffect,
    selectSpeed,
    selectApp,
    updateConstructBtn,
    submitBlendConstructor,
    blendSaveCurrentBlend,
    blendCreateContent,
    blendOfWeek,
    blendLaunchContent,
    blendRegenerate,
    blendAdjustWithOil,
    openSavedBlends,
    openSavedBlendDetail,
    savedBlendCreateContent,
    savedBlendLaunchContent,
    deleteSavedBlend,
    deleteSavedBlendFromDetail,
    shareBlend,
    openSharedBlend,
  };
}
