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
  return { openRecommendationsWizard, closeRecommendationsWizard, isWizardOpen, renderWizard, recoWizardNext, recoWizardBack, recoSelectMood, recoSelectGoal, recoUpdateSymptoms, recoToggleAroma, recoUpdateContra, submitRecommendations };
}
