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
        <textarea id="blendBrief" class="field-textarea" placeholder="\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0441\u043c\u0435\u0441\u044c \u0434\u043b\u044f \u043a\u043e\u043d\u0446\u0435\u043d\u0442\u0440\u0430\u0446\u0438\u0438 \u0438 \u0442\u0432\u043e\u0440\u0447\u0435\u0441\u0442\u0432\u0430" oninput="updateConstructBtn()">${escapeHtml(prefill)}</textarea>
      </label></section>
      <section class="section"><h3>\u0416\u0435\u043b\u0430\u0435\u043c\u044b\u0439 \u044d\u0444\u0444\u0435\u043a\u0442</h3>
        <div class="chip-list">${effects.map(e => `<button class="chip chip-selectable" data-effect="${e}" onclick="toggleEffect(this)">${e}</button>`).join("")}</div>
        <input type="text" id="blendCustomEffect" class="field-input" style="margin-top:8px" placeholder="\u0421\u0432\u043e\u0439 \u044d\u0444\u0444\u0435\u043a\u0442, \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0431\u043e\u0434\u0440\u043e\u0441\u0442\u044c \u0441 \u0443\u0442\u0440\u0430">
      </section>
      <section class="section"><h3>\u0421\u043a\u043e\u0440\u043e\u0441\u0442\u044c \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f</h3>
        <div class="radio-row">${speeds.map(([l,v]) => `<button class="chip chip-selectable ${v==="medium"?"is-selected":""}" data-speed="${v}" onclick="selectSpeed(this)">${l}</button>`).join("")}</div>
      </section>
      <section class="section"><h3>\u0421\u043f\u043e\u0441\u043e\u0431 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u0438\u044f</h3>
        <div class="radio-row">${apps.map(([l,v]) => `<button class="chip chip-selectable ${v==="any"?"is-selected":""}" data-app="${v}" onclick="selectApp(this)">${l}</button>`).join("")}</div>
      </section>
      <section class="section"><label class="field-label">\u041f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043a\u0430\u0437\u0430\u043d\u0438\u044f (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)
        <input type="text" id="blendContra" placeholder="\u0411\u0435\u0440\u0435\u043c\u0435\u043d\u043d\u043e\u0441\u0442\u044c, \u0430\u043b\u043b\u0435\u0440\u0433\u0438\u044f, \u0434\u0435\u0442\u0438..." class="field-input">
      </label></section>
      <button class="primary-button" id="constructBtn" onclick="submitBlendConstructor(this)" ${!prefill ? "disabled" : ""}>\u041f\u043e\u0434\u043e\u0431\u0440\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
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
          <button class="oil-edit-toggle ${o.active ? "is-on" : "is-off"}" onclick="blendToggleOil('${escapeHtml(id)}')">${o.active ? "\u2713" : "\u2715"}</button>
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
    window.blendToggleOil = (oilId) => {
      const oil = blendState.oils.find(o => (o.db_id || o.name_ru) === oilId);
      if (!oil) return;
      if (oil.active && blendState.oils.filter(o => o.active).length <= 1) return;
      oil.active = !oil.active;
      recalcDrops();
      rerender();
    };
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
        ${result.restrictions?.length ? `<div class="blend-restrictions">${result.restrictions.map(r => `<div class="blend-restriction-row"><span class="chip chip-bad">${escapeHtml(r.condition)}</span><span>\u0438\u0441\u043a\u043b\u044e\u0447\u0438\u0442\u044c ${(r.oils_to_exclude || []).join(", ")}</span></div>`).join("")}</div>` : ""}
      </div>
      ${result.incompatible_oils?.length ? `<section class="section section-warning"><h3>\u26a0\ufe0f \u041d\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u044f\u0442\u044c \u0432 \u044d\u0442\u0443 \u0441\u043c\u0435\u0441\u044c</h3>${result.incompatible_oils.map(o => `<div class="incompat-row"><span class="chip chip-bad">${escapeHtml(o.name_ru)}</span><span>${escapeHtml(o.reason)}</span></div>`).join("")}</section>` : ""}
      <section class="section section-adjust">
        <h3>\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0432\u043e\u0451 \u043c\u0430\u0441\u043b\u043e</h3>
        <p class="field-help">\u0423\u043a\u0430\u0436\u0438\u0442\u0435 \u043c\u0430\u0441\u043b\u043e \u2014 \u0418\u0418 \u043f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442 \u0441\u043c\u0435\u0441\u044c \u0441 \u0435\u0433\u043e \u0443\u0447\u0451\u0442\u043e\u043c</p>
        <div class="blend-adjust-row">
          <input type="text" id="blendCustomOilInput" class="field-input" placeholder="\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u041b\u0430\u0432\u0430\u043d\u0434\u0430">
          <button class="secondary-button" id="blendAdjustBtn" type="button" onclick="blendAdjustWithOil(this)">\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c</button>
        </div>
        <button class="secondary-button" id="blendRegenBtn" type="button" style="margin-top:8px;width:100%" onclick="blendRegenerate(this)">\u041f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
      </section>
      <div class="blend-actions-stack">
        <div class="actions-grid-two">
          <button class="primary-button" id="blendSaveBtn" type="button" onclick="blendSaveCurrentBlend(this)">\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c</button>
          <button class="secondary-button" type="button" onclick="blendCreateContent()">\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043a\u043e\u043d\u0442\u0435\u043d\u0442</button>
        </div>
        <div id="blendContentPicker" hidden style="margin-top:6px">
          <p class="field-help" style="margin-bottom:6px">\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0444\u043e\u0440\u043c\u0430\u0442:</p>
          <div class="chip-list">
            <button class="chip chip-selectable" onclick="blendLaunchContent('content')">\u041f\u043e\u0441\u0442</button>
            <button class="chip chip-selectable" onclick="blendLaunchContent('threads_series')">\u0421\u0435\u0440\u0438\u044f Threads</button>
            <button class="chip chip-selectable" onclick="blendLaunchContent('carousel')">\u041a\u0430\u0440\u0443\u0441\u0435\u043b\u044c</button>
          </div>
        </div>
        <div class="actions-grid-two">
          <button class="secondary-button" onclick="openBlendConstructor()">\u041d\u043e\u0432\u0430\u044f \u0441\u043c\u0435\u0441\u044c</button>
          <button class="secondary-button" onclick="clearSmartSearch()">\u041a \u0431\u0430\u0437\u0435</button>
        </div>
      </div>
    </div>`;
  }

  async function openSavedBlends() {
    enterDetailView();
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      <p class="eyebrow">\u0421\u041e\u0425\u0420\u0410\u041d\u0401\u041d\u041d\u042b\u0415 \u0421\u041c\u0415\u0421\u0418</p>
      <div id="savedBlendsList" class="saved-blends-list"><p class="field-help">\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</p></div>
      <button class="primary-button" onclick="openBlendConstructor()">\u041d\u043e\u0432\u0430\u044f \u0441\u043c\u0435\u0441\u044c</button>
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
        <div class="saved-blend-card">
          <h3>${escapeHtml(b.title)}</h3>
          ${b.brief ? `<p class="field-help">${escapeHtml(b.brief)}</p>` : ""}
          <div class="draft-meta">${(b.tags || []).map(t => tagMarkup(t, "brand")).join("")}</div>
          <div class="saved-blend-oils">${(b.oils || []).map(o => `${escapeHtml(o.name_ru)} ${o.drops}\u043a.`).join(" \u00b7 ")}</div>
          <button class="danger-button" style="margin-top:6px" onclick="deleteSavedBlend('${escapeHtml(b.id || b._id)}',this)">\u0423\u0434\u0430\u043b\u0438\u0442\u044c</button>
        </div>`).join("");
    } catch {
      const el = document.getElementById("savedBlendsList");
      if (el) el.innerHTML = `<p class="field-help">\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c</p>`;
    }
  }

  async function deleteSavedBlend(id, btn) {
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
    elements.draftDetail.innerHTML = `<div class="detail-grid">
      ${renderBackButton()}
      ${renderDetailLoader("\u041f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u044e \u0441\u043c\u0435\u0441\u044c", "\u0421\u043e\u0441\u0442\u0430\u0432\u043b\u044f\u044e \u043d\u043e\u0432\u044b\u0439 \u0432\u0430\u0440\u0438\u0430\u043d\u0442 \u0440\u0435\u0446\u0435\u043f\u0442\u0430 \u0441 \u0442\u0435\u043c\u0438 \u0436\u0435 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u0430\u043c\u0438.")}
    </div>`;
    fetchJson("/api/blend-constructor/construct", {
      method: "POST",
      body: JSON.stringify(req),
    }).then(result => {
      renderBlendResult(result);
    }).catch(() => {
      if (prevResult) renderBlendResult(prevResult);
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437.", "error");
    });
  }

  function blendAdjustWithOil(btn) {
    const input = document.getElementById("blendCustomOilInput");
    const oil = input?.value.trim();
    if (!oil || !_blendState?.origRequest) return;
    const req = _blendState.origRequest;
    if (btn) { btn.disabled = true; btn.textContent = "\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u044e..."; }
    fetchJson("/api/blend-constructor/adjust", {
      method: "POST",
      body: JSON.stringify({...req, custom_oils: [oil]}),
    }).then(result => {
      _blendState.origRequest = {...req, custom_oils: [oil]};
      renderBlendResult(result);
    }).catch(() => {
      showUiNotice("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0441\u043c\u0435\u0441\u044c", "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u041f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0438\u0442\u044c"; }
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
    blendLaunchContent,
    blendRegenerate,
    blendAdjustWithOil,
    openSavedBlends,
    deleteSavedBlend,
    shareBlend,
    openSharedBlend,
  };
}
