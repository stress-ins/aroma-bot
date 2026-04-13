export function createRecommendationsModule(deps) {
  const { state, elements, fetchJson, escapeHtml, renderBackButton, renderDetailLoader, enterDetailView, syncMobileNavigation, openReference, showUiNotice } = deps;
  let _wizardOpen = false, _wizardStep = 0, _wizardData = _empty(), _wizardResults = null, _wizardLoading = false;
  function _empty() { return { mood: "", goal: "", symptoms: [], aroma_preferences: [], contraindications: "" }; }
  const MOOD_OPTIONS = [{value:"stressed",label:"Стресс",icon:"fire"},{value:"tired",label:"Усталость",icon:"battery-low"},{value:"anxious",label:"Тревога",icon:"cloud-lightning"},{value:"neutral",label:"Нормально",icon:"smiley"},{value:"energetic",label:"Энергия",icon:"lightning"}];
  const GOAL_OPTIONS = [{value:"relax",label:"Расслабиться"},{value:"focus",label:"Сфокусироваться"},{value:"sleep",label:"Уснуть"},{value:"energy",label:"Энергия"},{value:"mood",label:"Настроение"}];
  const AROMA_OPTIONS = [{value:"citrus",label:"Цитрус"},{value:"floral",label:"Цветы"},{value:"woody",label:"Дерево"},{value:"herbal",label:"Травы"},{value:"spicy",label:"Специи"},{value:"resinous",label:"Смолы"}];
  function openRecommendationsWizard() { _wizardOpen = true; _wizardStep = 0; _wizardData = _empty(); _wizardResults = null; _wizardLoading = false; state._recoWizardOpen = true; state._recoWizardStep = 0; renderWizard(); enterDetailView(); }
  function closeRecommendationsWizard() { _wizardOpen = false; _wizardStep = 0; _wizardResults = null; _wizardLoading = false; state._recoWizardOpen = false; state._recoWizardStep = 0; state.mobileView = "list"; syncMobileNavigation(); }
  function isWizardOpen() { return _wizardOpen; }
  function renderWizard() {
    if (!_wizardOpen) return;
    if (_wizardLoading) { elements.draftDetail.innerHTML = '<div class="detail-grid">' + renderBackButton("closeRecommendationsWizard") + renderDetailLoader("\u041f\u043e\u0434\u0431\u0438\u0440\u0430\u0435\u043c \u043c\u0430\u0441\u043b\u0430", "\u0410\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0435\u043c \u0432\u0430\u0448\u0438 \u043f\u0440\u0435\u0434\u043f\u043e\u0447\u0442\u0435\u043d\u0438\u044f \u0438 \u043f\u043e\u0434\u0431\u0438\u0440\u0430\u0435\u043c \u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0438\u0435 \u043c\u0430\u0441\u043b\u0430.") + '</div>'; return; }
    if (_wizardResults) { _renderResults(); return; }
    const steps = [_renderMoodStep, _renderGoalStep, _renderSymptomsStep, _renderAromaPrefsStep, _renderContraindicationsStep];
    const titles = ["Как вы себя чувствуете?", "Что хотите получить?", "Есть ли симптомы?", "Предпочтения по аромату", "Противопоказания"];
    const stepContent = steps[_wizardStep]();
    const isLast = _wizardStep === steps.length - 1;
    const canProceed = _wizardStep === 0 ? !!_wizardData.mood : _wizardStep === 1 ? !!_wizardData.goal : true;
    const dots = Array.from({length:5},(_,i) => '<div class="reco-progress-dot' + (i <= _wizardStep ? " active" : "") + '"></div>').join("");
    const navBtn = isLast ? '<button class="reco-submit-btn primary-button" data-action="submitRecommendations"' + (!canProceed ? " disabled" : "") + '>Подобрать масла</button>' : '<button class="reco-next-btn primary-button" data-action="recoWizardNext"' + (!canProceed ? " disabled" : "") + '>Далее</button>';
    elements.draftDetail.innerHTML = renderBackButton(_wizardStep > 0 ? "recoWizardBack" : "closeRecommendationsWizard") + '<div class="reco-wizard"><div class="reco-progress">' + dots + '</div><h2 class="reco-step-title">' + titles[_wizardStep] + '</h2><div class="reco-step">' + stepContent + '</div><div class="reco-nav">' + navBtn + '</div></div>';
  }
  function _renderMoodStep() { return '<div class="reco-chips">' + MOOD_OPTIONS.map(o => '<button class="reco-chip' + (_wizardData.mood === o.value ? " active" : "") + '" data-action="recoSelectMood" data-args=\'' + JSON.stringify([o.value]) + '\'><i class="ph ph-' + o.icon + ' reco-chip-icon"></i> ' + escapeHtml(o.label) + '</button>').join("") + '</div>'; }
  function _renderGoalStep() { return '<div class="reco-chips">' + GOAL_OPTIONS.map(o => '<button class="reco-chip' + (_wizardData.goal === o.value ? " active" : "") + '" data-action="recoSelectGoal" data-args=\'' + JSON.stringify([o.value]) + '\'>' + escapeHtml(o.label) + '</button>').join("") + '</div>'; }
  function _renderSymptomsStep() { return '<p class="reco-hint">Необязательно. Перечислите через запятую.</p><textarea class="reco-textarea" placeholder="Головная боль, бессонница..." data-on-input="recoUpdateSymptoms" data-args=\'' + JSON.stringify([]) + '\'>' + _wizardData.symptoms.join(", ") + '</textarea>'; }
  function _renderAromaPrefsStep() { return '<p class="reco-hint">Выберите любимые ароматы (необязательно).</p><div class="reco-chips">' + AROMA_OPTIONS.map(o => '<button class="reco-chip' + (_wizardData.aroma_preferences.includes(o.value) ? " active" : "") + '" data-action="recoToggleAroma" data-args=\'' + JSON.stringify([o.value]) + '\'>' + escapeHtml(o.label) + '</button>').join("") + '</div>'; }
  function _renderContraindicationsStep() { return '<p class="reco-hint">Необязательно.</p><textarea class="reco-textarea" placeholder="Беременность, аллергии..." data-on-input="recoUpdateContra" data-args=\'' + JSON.stringify([]) + '\'>' + escapeHtml(_wizardData.contraindications) + '</textarea>'; }
  function _renderResults() {
    const recs = _wizardResults.recommendations || [], advice = _wizardResults.general_advice || "";
    const cards = recs.map(rec => { const card = rec.card, img = card && card.image_url ? '<img class="reco-card-image" src="' + escapeHtml(card.image_url) + '" alt="' + escapeHtml(rec.name_ru) + '" loading="lazy">' : ""; return '<article class="reco-card">' + img + '<div class="reco-card-body"><h3 class="reco-card-title">' + escapeHtml(rec.name_ru) + '</h3><p class="reco-card-reason">' + escapeHtml(rec.reason) + '</p><div class="reco-card-practice"><strong>Практика на день:</strong><p>' + escapeHtml(rec.daily_practice) + '</p></div><div class="reco-card-actions">' + (rec.slug ? '<button class="reco-card-btn reco-card-btn-detail" data-action="openReference" data-args=\'' + JSON.stringify([rec.slug, "aromas"]) + '\'>Подробнее</button><button class="reco-card-btn reco-card-btn-blend" data-action="addRecoOilToBlend" data-args=\'' + JSON.stringify([rec.name_ru]) + '\'>Добавить в смесь</button>' : '') + '</div></div></article>'; }).join("");
    elements.draftDetail.innerHTML = renderBackButton("closeRecommendationsWizard") + '<div class="reco-wizard"><h2 class="reco-step-title">Ваши масла</h2><div class="reco-results">' + cards + (advice ? '<div class="reco-general-advice"><p>' + escapeHtml(advice) + '</p></div>' : '') + '<button class="reco-restart-btn" data-action="openRecommendationsWizard">Подобрать ещё</button></div></div>';
  }
  function recoWizardNext() { if (_wizardStep < 4) { _wizardStep++; state._recoWizardStep = _wizardStep; renderWizard(); } }
  function recoWizardBack() { if (_wizardStep > 0) { _wizardStep--; state._recoWizardStep = _wizardStep; renderWizard(); } }
  function recoSelectMood(v) { _wizardData.mood = v; renderWizard(); }
  function recoSelectGoal(v) { _wizardData.goal = v; renderWizard(); }
  function recoUpdateSymptoms(v) { _wizardData.symptoms = v.split(",").map(s => s.trim()).filter(Boolean); }
  function recoToggleAroma(v) { const i = _wizardData.aroma_preferences.indexOf(v); if (i >= 0) _wizardData.aroma_preferences.splice(i, 1); else _wizardData.aroma_preferences.push(v); renderWizard(); }
  function recoUpdateContra(v) { _wizardData.contraindications = v; }
  async function submitRecommendations() {
    _wizardLoading = true; renderWizard();
    try { const result = await fetchJson("/api/recommendations/personal", { method: "POST", timeout: 45000, body: JSON.stringify(_wizardData) }); _wizardResults = result; try { sessionStorage.setItem("reco_last_result", JSON.stringify(result)); } catch(_e) {} _wizardLoading = false; renderWizard(); }
    catch (err) { _wizardLoading = false; renderWizard(); showUiNotice("Ошибка подбора. Попробуйте ещё раз.", "error"); }
  }
  // ── Massage Technique Finder Wizard ──────────────────────────────────

  let _massageWizardOpen = false, _massageStep = 0, _massageData = _emptyMassage(), _massageResults = null, _massageLoading = false;
  function _emptyMassage() { return { concern: "", body_zone: "", goal: "", experience: "some", contraindications: "" }; }

  const CONCERN_OPTIONS = [
    {value:"pain",label:"Боль / напряжение",icon:"lightning"},
    {value:"stress",label:"Стресс",icon:"cloud-lightning"},
    {value:"stiffness",label:"Скованность",icon:"lock-simple"},
    {value:"recovery",label:"Восстановление",icon:"heartbeat"},
    {value:"relaxation",label:"Расслабление",icon:"moon"},
    {value:"headache",label:"Головная боль",icon:"head-circuit"},
  ];
  const ZONE_OPTIONS = [
    {value:"back",label:"Спина"},
    {value:"neck",label:"Шея и голова"},
    {value:"feet",label:"Стопы"},
    {value:"face",label:"Лицо"},
    {value:"abdomen",label:"Живот"},
    {value:"full_body",label:"Всё тело"},
    {value:"legs",label:"Ноги"},
  ];
  const MASSAGE_GOAL_OPTIONS = [
    {value:"relieve_pain",label:"Снять боль"},
    {value:"relax",label:"Расслабиться"},
    {value:"restore",label:"Восстановиться"},
    {value:"improve_mobility",label:"Улучшить подвижность"},
    {value:"detox",label:"Детоксикация"},
  ];
  const EXP_OPTIONS = [
    {value:"beginner",label:"Новичок",icon:"baby"},
    {value:"some",label:"Есть опыт",icon:"user"},
    {value:"experienced",label:"Опытный",icon:"user-circle-check"},
  ];

  function openMassageFinder() {
    _massageWizardOpen = true; _massageStep = 0; _massageData = _emptyMassage(); _massageResults = null; _massageLoading = false;
    state._massageWizardOpen = true; state._massageWizardStep = 0;
    _renderMassageWizard(); enterDetailView();
  }
  function closeMassageFinder() {
    _massageWizardOpen = false; _massageStep = 0; _massageResults = null; _massageLoading = false;
    state._massageWizardOpen = false; state._massageWizardStep = 0;
    state.mobileView = "list"; syncMobileNavigation();
  }

  function _renderMassageWizard() {
    if (!_massageWizardOpen) return;
    if (_massageLoading) {
      elements.draftDetail.innerHTML = '<div class="detail-grid">' + renderBackButton("closeMassageFinder") + renderDetailLoader("Подбираем технику", "Анализируем запрос и подбираем подходящие массажные техники.") + '</div>';
      return;
    }
    if (_massageResults) { _renderMassageResults(); return; }

    const steps = [_renderConcernStep, _renderZoneStep, _renderMassageGoalStep, _renderExperienceStep, _renderMassageContraStep];
    const titles = ["Что беспокоит?", "Какая зона тела?", "Какая цель?", "Ваш опыт массажа", "Противопоказания"];
    const stepContent = steps[_massageStep]();
    const isLast = _massageStep === steps.length - 1;
    const canProceed = _massageStep === 0 ? !!_massageData.concern : _massageStep === 1 ? !!_massageData.body_zone : _massageStep === 2 ? !!_massageData.goal : true;
    const dots = Array.from({length: 5}, (_, i) => '<div class="reco-progress-dot' + (i <= _massageStep ? " active" : "") + '"></div>').join("");
    const navBtn = isLast
      ? '<button class="reco-submit-btn primary-button" data-action="submitMassageRecommendations"' + (!canProceed ? " disabled" : "") + '>Подобрать технику</button>'
      : '<button class="reco-next-btn primary-button" data-action="massageWizardNext"' + (!canProceed ? " disabled" : "") + '>Далее</button>';
    elements.draftDetail.innerHTML = renderBackButton(_massageStep > 0 ? "massageWizardBack" : "closeMassageFinder") +
      '<div class="reco-wizard"><div class="reco-progress">' + dots + '</div><h2 class="reco-step-title">' + titles[_massageStep] + '</h2><div class="reco-step">' + stepContent + '</div><div class="reco-nav">' + navBtn + '</div></div>';
  }

  function _renderConcernStep() {
    return '<div class="reco-chips">' + CONCERN_OPTIONS.map(o =>
      '<button class="reco-chip' + (_massageData.concern === o.value ? " active" : "") + '" data-action="massageSelectConcern" data-args=\'' + JSON.stringify([o.value]) + '\'><i class="ph ph-' + o.icon + ' reco-chip-icon"></i> ' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderZoneStep() {
    return '<div class="reco-chips">' + ZONE_OPTIONS.map(o =>
      '<button class="reco-chip' + (_massageData.body_zone === o.value ? " active" : "") + '" data-action="massageSelectZone" data-args=\'' + JSON.stringify([o.value]) + '\'>' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderMassageGoalStep() {
    return '<div class="reco-chips">' + MASSAGE_GOAL_OPTIONS.map(o =>
      '<button class="reco-chip' + (_massageData.goal === o.value ? " active" : "") + '" data-action="massageSelectGoal" data-args=\'' + JSON.stringify([o.value]) + '\'>' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderExperienceStep() {
    return '<div class="reco-chips">' + EXP_OPTIONS.map(o =>
      '<button class="reco-chip' + (_massageData.experience === o.value ? " active" : "") + '" data-action="massageSelectExperience" data-args=\'' + JSON.stringify([o.value]) + '\'><i class="ph ph-' + o.icon + ' reco-chip-icon"></i> ' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderMassageContraStep() {
    return '<p class="reco-hint">Необязательно.</p><textarea class="reco-textarea" placeholder="Тромбоз, беременность, кожные заболевания..." data-on-input="massageUpdateContra" data-args=\'' + JSON.stringify([]) + '\'>' + escapeHtml(_massageData.contraindications) + '</textarea>';
  }

  function _renderMassageResults() {
    const recs = _massageResults.recommendations || [], advice = _massageResults.general_advice || "";
    const cards = recs.map(rec => {
      const card = rec.card;
      const img = card && card.image_url ? '<img class="reco-card-image" src="' + escapeHtml(card.image_url) + '" alt="' + escapeHtml(rec.name_ru) + '" loading="lazy">' : "";
      const oilsHtml = (rec.oils && rec.oils.length) ? '<div class="reco-card-practice"><strong>Масла:</strong><p>' + escapeHtml(rec.oils.join(", ")) + '</p></div>' : "";
      return '<article class="reco-card">' + img +
        '<div class="reco-card-body"><h3 class="reco-card-title">' + escapeHtml(rec.name_ru) + '</h3>' +
        '<p class="reco-card-reason">' + escapeHtml(rec.reason) + '</p>' +
        '<div class="reco-card-practice"><strong>Рекомендация на сеанс:</strong><p>' + escapeHtml(rec.session_advice) + '</p></div>' +
        oilsHtml +
        '<div class="reco-card-actions">' +
        (rec.slug ? '<button class="reco-card-btn reco-card-btn-detail" data-action="openReference" data-args=\'' + JSON.stringify([rec.slug, "massage"]) + '\'>Подробнее</button>' : '') +
        '</div></div></article>';
    }).join("");
    elements.draftDetail.innerHTML = renderBackButton("closeMassageFinder") +
      '<div class="reco-wizard"><h2 class="reco-step-title">Рекомендованные техники</h2><div class="reco-results">' + cards +
      (advice ? '<div class="reco-general-advice"><p>' + escapeHtml(advice) + '</p></div>' : '') +
      '<button class="reco-restart-btn" data-action="openMassageFinder">Подобрать ещё</button></div></div>';
  }

  function massageWizardNext() { if (_massageStep < 4) { _massageStep++; state._massageWizardStep = _massageStep; _renderMassageWizard(); } }
  function massageWizardBack() { if (_massageStep > 0) { _massageStep--; state._massageWizardStep = _massageStep; _renderMassageWizard(); } }
  function massageSelectConcern(v) { _massageData.concern = v; _renderMassageWizard(); }
  function massageSelectZone(v) { _massageData.body_zone = v; _renderMassageWizard(); }
  function massageSelectGoal(v) { _massageData.goal = v; _renderMassageWizard(); }
  function massageSelectExperience(v) { _massageData.experience = v; _renderMassageWizard(); }
  function massageUpdateContra(v) { _massageData.contraindications = v; }

  async function submitMassageRecommendations() {
    _massageLoading = true; _renderMassageWizard();
    try {
      const result = await fetchJson("/api/recommendations/massage", { method: "POST", timeout: 45000, body: JSON.stringify(_massageData) });
      _massageResults = result;
      _massageLoading = false; _renderMassageWizard();
    } catch (err) {
      _massageLoading = false; _renderMassageWizard();
      showUiNotice("Ошибка подбора. Попробуйте ещё раз.", "error");
    }
  }

  // ── Multimodal Protocol Wizard ──────────────────────────────────

  let _protoWizardOpen = false, _protoStep = 0, _protoData = _emptyProto(), _protoResults = null, _protoLoading = false;
  function _emptyProto() { return { concern: "", body_zone: "full_body", goal: "balance", modalities: "all", contraindications: "" }; }

  const PROTO_CONCERN_OPTIONS = [
    {value:"pain",label:"Боль / напряжение",icon:"lightning"},
    {value:"stress",label:"Стресс",icon:"cloud-lightning"},
    {value:"insomnia",label:"Бессонница",icon:"moon"},
    {value:"fatigue",label:"Усталость",icon:"battery-low"},
    {value:"headache",label:"Головная боль",icon:"head-circuit"},
    {value:"anxiety",label:"Тревожность",icon:"heart-half"},
    {value:"stiffness",label:"Скованность",icon:"lock-simple"},
    {value:"immunity",label:"Иммунитет",icon:"shield-check"},
  ];
  const PROTO_ZONE_OPTIONS = [
    {value:"full_body",label:"Всё тело"},
    {value:"back",label:"Спина"},
    {value:"neck",label:"Шея и голова"},
    {value:"feet",label:"Стопы"},
    {value:"abdomen",label:"Живот"},
    {value:"chest",label:"Грудная клетка"},
  ];
  const PROTO_GOAL_OPTIONS = [
    {value:"relieve",label:"Снять боль"},
    {value:"relax",label:"Расслабление"},
    {value:"restore",label:"Восстановление"},
    {value:"balance",label:"Баланс"},
    {value:"heal",label:"Выздоровление"},
  ];
  const MODALITY_OPTIONS = [
    {value:"all",label:"Все 4 модальности",icon:"circles-four"},
    {value:"oil_massage",label:"Масла + Массаж",icon:"hand-palm"},
    {value:"oil_sound",label:"Масла + Звук",icon:"waveform"},
    {value:"oil_crystal",label:"Масла + Кристаллы",icon:"diamond"},
    {value:"massage_sound",label:"Массаж + Звук",icon:"music-notes"},
  ];

  const _MODALITY_ICONS = { oil: "drop", massage: "hand-palm", sound: "waveform", crystal: "diamond" };
  const _MODALITY_LABELS = { oil: "Масло", massage: "Массаж", sound: "Звук", crystal: "Кристалл" };
  const _MODALITY_TAB_MAP = { oil: "aromas", massage: "massage", sound: "sounds", crystal: "crystals" };

  function openProtocolWizard() {
    _protoWizardOpen = true; _protoStep = 0; _protoData = _emptyProto(); _protoResults = null; _protoLoading = false;
    state._protoWizardOpen = true; state._protoWizardStep = 0;
    _renderProtoWizard(); enterDetailView();
  }
  function closeProtocolWizard() {
    _protoWizardOpen = false; _protoStep = 0; _protoResults = null; _protoLoading = false;
    state._protoWizardOpen = false; state._protoWizardStep = 0;
    state.mobileView = "list"; syncMobileNavigation();
  }

  function _renderProtoWizard() {
    if (!_protoWizardOpen) return;
    if (_protoLoading) {
      elements.draftDetail.innerHTML = '<div class="detail-grid">' + renderBackButton("closeProtocolWizard") +
        renderDetailLoader("Составляем протокол", "Подбираем сочетание масла, массажа, звука и кристалла для вашего запроса.") + '</div>';
      return;
    }
    if (_protoResults) { _renderProtoResults(); return; }

    const steps = [_renderProtoConcernStep, _renderProtoZoneStep, _renderProtoGoalStep, _renderProtoModalitiesStep, _renderProtoContraStep];
    const titles = ["Что беспокоит?", "Какая зона тела?", "Какая цель?", "Какие модальности?", "Противопоказания"];
    const stepContent = steps[_protoStep]();
    const isLast = _protoStep === steps.length - 1;
    const canProceed = _protoStep === 0 ? !!_protoData.concern : true;
    const dots = Array.from({length: 5}, (_, i) => '<div class="reco-progress-dot' + (i <= _protoStep ? " active" : "") + '"></div>').join("");
    const navBtn = isLast
      ? '<button class="reco-submit-btn primary-button" data-action="submitProtocolRecommendations"' + (!canProceed ? " disabled" : "") + '>Составить протокол</button>'
      : '<button class="reco-next-btn primary-button" data-action="protoWizardNext"' + (!canProceed ? " disabled" : "") + '>Далее</button>';
    elements.draftDetail.innerHTML = renderBackButton(_protoStep > 0 ? "protoWizardBack" : "closeProtocolWizard") +
      '<div class="reco-wizard"><div class="reco-progress">' + dots + '</div><h2 class="reco-step-title">' + titles[_protoStep] + '</h2><div class="reco-step">' + stepContent + '</div><div class="reco-nav">' + navBtn + '</div></div>';
  }

  function _renderProtoConcernStep() {
    return '<div class="reco-chips">' + PROTO_CONCERN_OPTIONS.map(o =>
      '<button class="reco-chip' + (_protoData.concern === o.value ? " active" : "") + '" data-action="protoSelectConcern" data-args=\'' + JSON.stringify([o.value]) + '\'><i class="ph ph-' + o.icon + ' reco-chip-icon"></i> ' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderProtoZoneStep() {
    return '<div class="reco-chips">' + PROTO_ZONE_OPTIONS.map(o =>
      '<button class="reco-chip' + (_protoData.body_zone === o.value ? " active" : "") + '" data-action="protoSelectZone" data-args=\'' + JSON.stringify([o.value]) + '\'>' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderProtoGoalStep() {
    return '<div class="reco-chips">' + PROTO_GOAL_OPTIONS.map(o =>
      '<button class="reco-chip' + (_protoData.goal === o.value ? " active" : "") + '" data-action="protoSelectGoal" data-args=\'' + JSON.stringify([o.value]) + '\'>' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderProtoModalitiesStep() {
    return '<p class="reco-hint">Какие модальности включить в протокол?</p><div class="reco-chips">' + MODALITY_OPTIONS.map(o =>
      '<button class="reco-chip' + (_protoData.modalities === o.value ? " active" : "") + '" data-action="protoSelectModalities" data-args=\'' + JSON.stringify([o.value]) + '\'><i class="ph ph-' + o.icon + ' reco-chip-icon"></i> ' + escapeHtml(o.label) + '</button>'
    ).join("") + '</div>';
  }
  function _renderProtoContraStep() {
    return '<p class="reco-hint">Необязательно.</p><textarea class="reco-textarea" placeholder="Беременность, аллергии, тромбоз..." data-on-input="protoUpdateContra" data-args=\'' + JSON.stringify([]) + '\'>' + escapeHtml(_protoData.contraindications) + '</textarea>';
  }

  function _renderProtoResults() {
    const r = _protoResults;
    const header = '<div class="proto-header"><h2 class="reco-step-title">' + escapeHtml(r.protocol_name || "Ваш протокол") + '</h2>' +
      (r.protocol_description ? '<p class="proto-description">' + escapeHtml(r.protocol_description) + '</p>' : '') +
      (r.total_duration_min ? '<div class="proto-duration"><i class="ph ph-clock reco-chip-icon"></i> ' + r.total_duration_min + ' мин</div>' : '') + '</div>';

    const modalities = ["oil", "massage", "sound", "crystal"];
    const modalityCards = modalities.map(m => {
      const rec = r[m];
      if (!rec || typeof rec !== "object") return "";
      const card = rec.card;
      const img = card && card.image_url ? '<img class="reco-card-image" src="' + escapeHtml(card.image_url) + '" alt="' + escapeHtml(rec.name_ru || "") + '" loading="lazy">' : "";
      const icon = _MODALITY_ICONS[m] || "circle";
      const label = _MODALITY_LABELS[m] || m;
      const tab = _MODALITY_TAB_MAP[m] || "aromas";
      let details = '<p class="reco-card-reason">' + escapeHtml(rec.reason || "") + '</p>';
      if (rec.usage) details += '<div class="reco-card-practice"><strong>Применение:</strong><p>' + escapeHtml(rec.usage) + '</p></div>';
      if (rec.placement) details += '<div class="reco-card-practice"><strong>Размещение:</strong><p>' + escapeHtml(rec.placement) + '</p></div>';
      if (rec.duration_min) details += '<div class="reco-card-practice"><strong>Длительность:</strong><p>' + rec.duration_min + ' мин</p></div>';
      return '<article class="reco-card proto-modality-card">' + img +
        '<div class="reco-card-body"><div class="proto-modality-badge"><i class="ph ph-' + icon + '"></i> ' + escapeHtml(label) + '</div>' +
        '<h3 class="reco-card-title">' + escapeHtml(rec.name_ru || "") + '</h3>' + details +
        '<div class="reco-card-actions">' +
        (rec.slug ? '<button class="reco-card-btn reco-card-btn-detail" data-action="openReference" data-args=\'' + JSON.stringify([rec.slug, tab]) + '\'>Подробнее</button>' : '') +
        '</div></div></article>';
    }).join("");

    const sessionPlan = (r.session_plan && r.session_plan.length) ? '<div class="proto-session-plan"><h3>План сеанса</h3><ol class="proto-steps">' +
      r.session_plan.map(s => {
        const icon = _MODALITY_ICONS[s.modality] || "circle";
        return '<li class="proto-step-item"><i class="ph ph-' + icon + '"></i> <span>' + escapeHtml(s.action || "") + '</span>' +
          (s.duration_min ? ' <span class="proto-step-duration">' + s.duration_min + ' мин</span>' : '') + '</li>';
      }).join("") + '</ol></div>' : "";

    const synergy = r.synergy ? '<div class="proto-synergy"><h3>Синергия</h3><p>' + escapeHtml(r.synergy) + '</p></div>' : "";
    const advice = r.general_advice ? '<div class="reco-general-advice"><p>' + escapeHtml(r.general_advice) + '</p></div>' : "";

    elements.draftDetail.innerHTML = renderBackButton("closeProtocolWizard") +
      '<div class="reco-wizard">' + header + '<div class="reco-results proto-results">' + modalityCards + sessionPlan + synergy + advice +
      '<button class="reco-restart-btn" data-action="openProtocolWizard">Составить ещё</button></div></div>';
  }

  function protoWizardNext() { if (_protoStep < 4) { _protoStep++; state._protoWizardStep = _protoStep; _renderProtoWizard(); } }
  function protoWizardBack() { if (_protoStep > 0) { _protoStep--; state._protoWizardStep = _protoStep; _renderProtoWizard(); } }
  function protoSelectConcern(v) { _protoData.concern = v; _renderProtoWizard(); }
  function protoSelectZone(v) { _protoData.body_zone = v; _renderProtoWizard(); }
  function protoSelectGoal(v) { _protoData.goal = v; _renderProtoWizard(); }
  function protoSelectModalities(v) { _protoData.modalities = v; _renderProtoWizard(); }
  function protoUpdateContra(v) { _protoData.contraindications = v; }

  async function submitProtocolRecommendations() {
    _protoLoading = true; _renderProtoWizard();
    try {
      const result = await fetchJson("/api/recommendations/protocol", { method: "POST", timeout: 60000, body: JSON.stringify(_protoData) });
      _protoResults = result;
      _protoLoading = false; _renderProtoWizard();
    } catch (err) {
      _protoLoading = false; _renderProtoWizard();
      showUiNotice("Ошибка составления протокола. Попробуйте ещё раз.", "error");
    }
  }

  return {
    openRecommendationsWizard, closeRecommendationsWizard, isWizardOpen, renderWizard,
    recoWizardNext, recoWizardBack, recoSelectMood, recoSelectGoal, recoUpdateSymptoms, recoToggleAroma, recoUpdateContra, submitRecommendations,
    openMassageFinder, closeMassageFinder, massageWizardNext, massageWizardBack,
    massageSelectConcern, massageSelectZone, massageSelectGoal, massageSelectExperience, massageUpdateContra, submitMassageRecommendations,
    openProtocolWizard, closeProtocolWizard, protoWizardNext, protoWizardBack,
    protoSelectConcern, protoSelectZone, protoSelectGoal, protoSelectModalities, protoUpdateContra, submitProtocolRecommendations,
  };
}
