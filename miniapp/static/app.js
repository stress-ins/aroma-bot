// CSS import for Vite bundling — ignored when served as raw ES module
// import "./app.css";
import { registerWindowBridge } from "./js/bridge.js";
import { createCarouselModule } from "./js/carousel.js";
import { createContentModule } from "./js/content.js";
import { createCoreModule } from "./js/core.js";
import { createCreateModule } from "./js/create.js";
import { createDraftsModule } from "./js/drafts.js";
import { createPublishModule } from "./js/publish.js";
import { createScheduleModule } from "./js/schedule.js";
import { createPlansModule } from "./js/plans.js";
import { createCalendarModule } from "./js/calendar.js";
import { createArchiveModule } from "./js/archive.js";
import { createMentionsModule } from "./js/mentions.js";
import { createBlendConstructorModule } from "./js/blend_constructor.js";
import { createReferencesModule } from "./js/references.js";
import { createReelsModule } from "./js/reels.js";
import { createOnboardingModule } from "./js/onboarding.js";
import { createRuntimeModule } from "./js/runtime.js";
import { createSessionModule } from "./js/session.js";
import { createSettingsModule } from "./js/settings.js";
import { createRecommendationsModule } from "./js/recommendations.js";
import { createShellModule } from "./js/shell.js";
import { createStockPhotosModule } from "./js/stock_photos.js";
import { createTeamsModule } from "./js/teams.js";
import { createTrendsModule } from "./js/trends.js";
import { createAnalyticsModule } from "./js/analytics.js";

const state = {
  mode: "content", // 'content' or 'handbook'
  tab: new URLSearchParams(window.location.search).get("tab") || "drafts",
  draftId: new URLSearchParams(window.location.search).get("draft_id") || "",
  selectedCreateTool: null,
  referenceAccess: null,
  referenceAccessError: "",
  referenceItems: [],
  referenceSearch: "",
  referenceFilter: "",
  referenceFilterParent: "",
  selectedReference: null,
  inbox: [],
  inboxKind: "all",
  drafts: [],
  plans: [],
  reels: [],
  selectedPlan: null,
  selectedKeywordTopicIdx: null,
  selected: null,
  selectedReels: null,
  selectedFrameIndex: 0,
  status: null,
  keywords: null,
  settingsSection: "status",
  settingsInDetail: false,
  mobileView: "list", // 'list' or 'detail'
  lastHandbookTab: "aromas",
  pendingCarouselNotes: {},
  pendingCarouselOps: {},
  pendingReelsNotes: {},
  pendingReelsPrompts: {},
  openPromptPanels: {},
  userRole: "assistant", // "expert" | "assistant" | "publisher"
  _fromContext: null,
  plansSubMode: "publications",
  contentSubMode: "drafts",
  inspirationSubTab: (() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t === "trends") return "trends";
    return "drafts";
  })(),
  contentSubTab: (() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t === "plans") return "plans";
    return "publications";
  })(),
  mentions: [],
  mentionsFilter: { platform: "all", status: "pending" },
  activeTeamId: localStorage.getItem("activeTeamId") || null,
  teams: [],
  /** @type {{ active: boolean, draftId: string|null, progress: number, fileName: string, error: string|null, xhr: XMLHttpRequest|null }} */
  videoUpload: { active: false, draftId: null, progress: 0, fileName: "", error: null, xhr: null },
};

const MODE_TABS = {
  handbook: [
    { id: "aromas", label: "Ароматы" },
    { id: "blends", label: "Смеси" },
    { id: "symptoms", label: "Симптомы" },
    { id: "concepts", label: "Теория" },
    { id: "practices", label: "Практики" },
    { id: "sounds", label: "Звуки" },
  ],
};

document.body.dataset.mode = "content";
document.body.dataset.tab = state.tab;

let reelRefreshTimer = null;
let carouselRefreshTimer = null;
let draftRefreshTimer = null;
let bootstrapWatchdogTimer = null;
let appBootstrapped = false;
let startupLoadInFlight = false;
let uiNoticeTimer = null;
const carouselNoteSaveTimers = {};
const reelsNoteSaveTimers = {};
const reelsPromptSaveTimers = {};

// Forward-declared module functions — assigned during module initialization below
let loadInbox, loadReels, loadKeywords, loadSettings, loadTrends;
let renderCreate, renderCreateTool;
let renderDraftList, openDraft, openReels, renderDraftDetail, renderEmptyDetail;
let renderInbox, renderStatus, renderPlans, renderReels, renderReelsDetail, renderKeywords;
let addRewrite, removeRewrite, savePlatformTone, saveUploadPostPrefs, saveImageModels, setTheme, connectPlatform, switchAccountsTeam;
let addTrackedHashtag, removeTrackedHashtag;
let addMonitoredAccountFromSettings, removeMonitoredAccountFromSettings;
let addKeywordItem, removeKeywordItem, openKeywordTopic;
let addForbiddenPhrase, removeForbiddenPhrase;
let createNewTeam, createTeamInvite, removeTeamMember, activatePromo, generatePromos, selectCity;
let adminResetStuck, adminRestartWorker;
let goBackToSettings;
let saveContentReviewDraft, saveThreadsReviewDraft, polishContentDraft, refreshDraftMetrics, moveDraftToTeam;
let recommendHashtags, applyRecommendedHashtags, adaptTone, startRepurpose, saveSeriesPost, regenSeriesPost, regenSeriesAll, coherenceCheck;
let loadCurrentTab, safeLoadCurrentTab, retryCurrentTab;
let publishDraft, cancelPublishSchedule, loadPublishStatus;
let openPendingReelsCreation, finalizePendingReelsCreation, recoverPendingReelsCreation;
let refreshReelsDetail;

function initScrollFade(container) {
  if (!container || container._scrollFadeInit) return;
  container._scrollFadeInit = true;

  const update = () => {
    const { scrollTop, scrollHeight, clientHeight } = container;
    container.classList.toggle('has-scroll-top', scrollTop > 8);
    container.classList.toggle('has-scroll-bottom', scrollTop + clientHeight < scrollHeight - 8);
  };

  container.addEventListener('scroll', update, { passive: true });
  if (window.ResizeObserver) new ResizeObserver(update).observe(container);
  new MutationObserver(update).observe(container, { childList: true, subtree: true });
  update();
}

// ── Range slider fill color (WebKit doesn't support ::-webkit-slider-progress) ──
function _updateRangeFill(el) {
  const min = parseFloat(el.min) || 0;
  const max = parseFloat(el.max) || 100;
  const val = parseFloat(el.value) || 0;
  const pct = ((val - min) / (max - min)) * 100;
  el.style.background = `linear-gradient(to right, var(--brand) 0%, var(--brand) ${pct}%, var(--border) ${pct}%, var(--border) 100%)`;
}
document.addEventListener("input", (e) => {
  if (e.target?.type === "range") _updateRangeFill(e.target);
});
// Apply to all existing range inputs on DOM mutations
new MutationObserver(() => {
  document.querySelectorAll('input[type="range"]').forEach(_updateRangeFill);
}).observe(document.body, { childList: true, subtree: true });

const elements = {
  tabsContainer: document.getElementById("tabsContainer"),
  filtersContainer: document.getElementById("filtersContainer"),
  listPanel: document.getElementById("listPanel"),
  detailPanel: document.getElementById("detailPanel"),
  draftList: document.getElementById("draftList"),
  draftDetail: document.getElementById("draftDetail"),
  draftCount: document.getElementById("draftCount"),
  headerTabs: document.getElementById("headerTabs"),
  contentSubTabs: document.getElementById("contentSubTabs"),
  listTitle: document.getElementById("topbarTitle"),
  emptyState: document.getElementById("emptyState"),
  kindFilter: document.getElementById("kindFilter"),
  statusFilter: document.getElementById("statusFilter"),
  feedbackFilter: document.getElementById("feedbackFilter"),
  queryFilter: document.getElementById("queryFilter"),
  modeContent: document.getElementById("modeContent"),
  modeHandbook: document.getElementById("modeHandbook"),
  settingsButton: document.getElementById("settingsButton"),
  bootFallback: document.getElementById("bootFallback"),
  bootFallbackTitle: document.getElementById("bootFallbackTitle"),
  bootFallbackText: document.getElementById("bootFallbackText"),
  bootFallbackReload: document.getElementById("bootFallbackReload"),
  bottomTabBar: document.getElementById("bottomTabBar"),
};

const SOURCE_TYPE_LABELS = {
  citrus:  "Цитрусовые",
  herb:    "Травяные",
  flower:  "Цветочные",
  tree:    "Древесные",
  resin:   "Смолистые",
  spice:   "Пряные",
  grass:   "Злаковые",
  root:    "Корневые",
  wood:    "Деревянистые",
};

const SOURCE_TYPE_ICONS = {
  herb:   "🌿",
  citrus: "🍋",
  flower: "🌸",
  tree:   "🌲",
  resin:  "🫚",
  spice:  "🌶️",
  grass:  "🌾",
  root:   "🌱",
  wood:   "🪵",
};

const SYMPTOM_CATEGORY_ICONS = {
  "БЕССОННИЦА":   "😴",
  "БОЛЬ":         "⚡",
  "СТРЕСС":       "🧠",
  "КОЖА":         "🫧",
  "СИНДРОМ":      "🩺",
  "ГОРМОНАЛЬНЫЕ": "⚗️",
  "ИНФЕКЦИЯ":     "🦠",
  "РАК":          "🎗️",
  "СЕРДЕЧНЫЙ":    "❤️",
  "ГРИПП":        "🤧",
  "ДИАБЕТ":       "💉",
  "ВИРУС":        "🦠",
  "ОЖОГИ":        "🔥",
  "РАНЫ":         "🩹",
  "ЭКЗЕМА":       "🫧",
  "ДЕРМАТИТ":     "🫧",
  "ЗАПОР":        "🌀",
  "КАШЕЛЬ":       "💨",
  "АЛЛЕРГИЯ":     "🌸",
  "АСТМА":        "💨",
  "АРТРИТ":       "🦴",
  "ДЕПРЕССИЯ":    "💭",
  "ТРЕВОГА":      "💭",
  "УСТАЛОСТЬ":    "🔋",
  "ВЫСОКОЕ":      "❤️",
  "НИЗКОЕ":       "❤️",
  "МИГРЕНЬ":      "🤕",
  "ГОЛОВНАЯ":     "🤕",
  "ОЖИРЕНИЕ":     "⚖️",
  "ВОСПАЛЕНИЕ":   "🔥",
  "ГРИБОК":       "🍄",
  "ПАРАЗИТЫ":     "🦠",
  "АКНЕ":         "🫧",
  "ВАРИКОЗ":      "🩸",
  "ОТЁКИ":        "💧",
};

const BLEND_CATEGORY_ICONS = {
  "ЭМОЦИИ И НАСТРОЕНИЕ":    "💛",
  "ЭНЕРГИЯ И МОТИВАЦИЯ":    "⚡",
  "РАССЛАБЛЕНИЕ И СОН":     "🌙",
  "ЗДОРОВЬЕ И ИММУНИТЕТ":   "🛡️",
  "БОЛЬ И ВОССТАНОВЛЕНИЕ":  "🦴",
  "ДЫХАНИЕ И ГОЛОВА":       "🫁",
  "ЖЕНСКОЕ ЗДОРОВЬЕ":       "🌸",
  "МУЖСКОЕ ЗДОРОВЬЕ":       "🔱",
  "ДЕТСКАЯ КОЛЛЕКЦИЯ":      "🧒",
  "ДУХОВНОСТЬ":             "✨",
  "КРАСОТА И УХОД":         "🌿",
};

const SYMPTOM_PARENT_GROUP_ICONS = {
  "НЕРВНАЯ СИСТЕМА":                            "🧠",
  "КРОВЕНОСНАЯ И СЕРДЕЧНО-СОСУДИСТАЯ СИСТЕМА":  "❤️",
  "ДЫХАТЕЛЬНАЯ СИСТЕМА":                        "🫁",
  "ПИЩЕВАРИТЕЛЬНАЯ СИСТЕМА":                    "🫄",
  "ОПОРНО-ДВИГАТЕЛЬНАЯ СИСТЕМА":                "🦴",
  "ЭНДОКРИННАЯ СИСТЕМА":                        "⚗️",
  "ИММУННАЯ СИСТЕМА":                           "🛡️",
  "РЕПРОДУКТИВНАЯ СИСТЕМА":                     "🌸",
  "МОЧЕВЫДЕЛИТЕЛЬНАЯ СИСТЕМА":                  "💧",
  "КОЖА И ПОКРОВЫ":                             "🫧",
  "ОРГАНЫ ЗРЕНИЯ И СЛУХА":                      "👁️",
  "ПСИХИКА И ЭМОЦИИ":                           "💭",
  "СОН И ОТДЫХ":                                "😴",
  "ЭНЕРГИЯ":                                    "⚡",
  "ОБЩЕЕ И РАЗНОЕ":                             "🌿",
};

const CONCEPT_TYPE_ICONS = {
  chakra:  "🔮",
  system:  "🧬",
  founder: "👤",
  energy:  "✨",
  method:  "🛠️",
};

const PRACTICE_TYPE_ICONS = {
  breath:     "🫁",
  meditation: "🧘",
  body:       "⚡",
};

const PRACTICE_RU_LABELS = {
  breath:     "Дыхание",
  meditation: "Медитация",
  body:       "Телесная",
};

const RU_KIND_LABELS = {
  threads: "Тредс",
  threads_series: "Серия Тредс",
  content_series: "Контент-серия",
  instagram: "Инстаграм",
  telegram: "Телеграм",
  reels: "Рилсы",
  reels_v2: "Рилсы",
  carousel: "Карусель",
  youtube_video: "YouTube видео",
};

const RU_STATUS_LABELS = {
  draft: "Черновик",
  in_review: "На согласовании",
  approved: "Согласовано",
  rejected: "Не согласовано",
  published: "Опубликовано",
  scheduled: "Запланировано",
  video_uploaded: "Видео загружено",
  checking: "Проверка",
  passed: "Проверено",
  failed: "Ошибка",
  publishing: "Публикуется",
};

const RU_FEEDBACK_LABELS = {
  worked: "Сработало",
  missed: "Не сработало",
  approved: "Одобрено",
};

const HANDBOOK_CATEGORY_META = {
  aromas: {
    category: "aroma",
    title: "Ароматы",
    label: "аромат",
    searchLabel: "Поиск аромата",
    searchPlaceholder: "Например: лаванда",
    empty: "Ароматы не найдены.",
    selectPrompt: "Выберите аромат из списка.",
    locked: "Доступ к справочнику ароматов ограничен.",
    count: (items) => `${items.length} карточек`,
  },
  concepts: {
    category: "concept",
    title: "Теория",
    label: "теоретическую карточку",
    searchLabel: "Поиск темы",
    searchPlaceholder: "Например: лимбическая система",
    empty: "Теоретические карточки не найдены.",
    selectPrompt: "Выберите теоретическую карточку из списка.",
    locked: "Доступ к теоретическим карточкам ограничен.",
    count: (items) => `${items.length} карточек`,
  },
  practices: {
    category: "practice",
    title: "Практики",
    label: "практику",
    searchLabel: "Поиск практики",
    searchPlaceholder: "Например: квадратное дыхание",
    empty: "Практики не найдены.",
    selectPrompt: "Выберите практику из списка.",
    locked: "Доступ к справочнику практик ограничен.",
    count: (items) => `${items.length} карточек`,
  },
  sounds: {
    category: "sound",
    title: "Звуки",
    label: "звуковую карточку",
    searchLabel: "Поиск звука",
    searchPlaceholder: "Например: гонг",
    empty: "Звуки не найдены.",
    selectPrompt: "Выберите звуковую карточку из списка.",
    locked: "Доступ к справочнику звуков ограничен.",
    count: (items) => `${items.length} карточек`,
  },
  blends: {
    category: "blend",
    title: "Смеси",
    label: "смесь",
    searchLabel: "Поиск смеси",
    searchPlaceholder: "Harmony, Joy, Grounding...",
    empty: "Смеси не найдены.",
    selectPrompt: "Выберите смесь из списка.",
    locked: "Доступ к разделу Смеси закрыт.",
    count: (items) => `${items.length} смесей`,
  },
  symptoms: {
    category: "symptom",
    title: "Симптомы",
    label: "симптом",
    searchLabel: "Поиск симптома",
    searchPlaceholder: "бессонница, мигрень, стресс...",
    empty: "Симптомы не найдены.",
    selectPrompt: "Введите симптом для поиска.",
    locked: "Доступ к разделу Симптомы закрыт.",
    count: (items) => `${items.length} симптомов`,
  },
};

function handbookCategoryIcon(tabId) {
  const glyphMap = {
    aromas: "🌿",
    blends: "🌀",
    symptoms: "🫀",
    concepts: "🧭",
    practices: "🫁",
    sounds: "🔔",
  };
  const glyph = glyphMap[String(tabId || "").toLowerCase()] || "•";
  return `<span class="kind-glyph handbook-glyph" aria-hidden="true">${glyph}</span>`;
}

function aromaCardIcon(item, tabId) {
  if (tabId === "aromas") {
    const sourceType = String(item.source_type || "").toLowerCase();
    // For non-herb types use the category icon directly (citrus→🍋, spice→🌶️ etc.).
    // For herb-type cards let name-based matching run first (lavender→🪻, rose→🌹).
    if (sourceType && sourceType !== "herb") {
      const sourceIcon = SOURCE_TYPE_ICONS[sourceType];
      if (sourceIcon) return sourceIcon;
    }
    const name = (item.name || "").toLowerCase();
    const family = (item.botanical_family || "").toLowerCase();
    if (name.includes("апельсин") || name.includes("orange") || family.includes("rutaceae")) return "🍊";
    if (name.includes("лаванд") || name.includes("lavend")) return "🪻";
    if (name.includes("мята") || name.includes("mint") || name.includes("peppermint")) return "🌿";
    if (name.includes("роза") || name.includes("rose")) return "🌹";
    if (name.includes("лимон") || name.includes("lemon")) return "🍋";
    if (name.includes("кедр") || name.includes("cedar") || name.includes("сосн") || name.includes("pine")) return "🌲";
    if (name.includes("ромашк") || name.includes("chamomile")) return "🌼";
    if (name.includes("имбир") || name.includes("ginger")) return "🫚";
    if (name.includes("эвкалипт") || name.includes("eucalyptus")) return "🍃";
    if (name.includes("иланг") || name.includes("ylang")) return "🌸";
    return "🌿";
  }
  if (tabId === "blends") return "🌀";
  if (tabId === "symptoms") return "🫀";
  if (tabId === "concepts") return conceptTypeMeta(item.source_type).icon;
  if (tabId === "practices") {
    const type = (item.source_type || "").toLowerCase();
    if (type === "body")       return "⚡";
    if (type === "meditation") return "🧘";
    if (type === "breath")     return "🫁";
    return "🫁";
  }
  return handbookCategoryIcon(tabId);
}

function handbookCardBadge(tabId, item = {}) {
  const sourceType = String(item.source_type || "").trim();
  if (tabId === "aromas" && sourceType) {
    const key = sourceType.toLowerCase();
    return SOURCE_TYPE_LABELS[key] || sourceType;
  }
  if (tabId === "blends") {
    const bc = String(item.blend_category || "").trim();
    if (bc) {
      const icon = BLEND_CATEGORY_ICONS[bc] || "";
      return icon ? icon + "\u00a0" + toSentenceCase(bc) : toSentenceCase(bc);
    }
    return "Смесь";
  }
  if (tabId === "symptoms") {
    const pg = String(item.parent_group || "").trim();
    if (pg) {
      const icon = SYMPTOM_PARENT_GROUP_ICONS[pg] || "";
      const words = pg.split(" ");
      const raw = words.length > 1 && pg.length > 14 ? words[0] + "\u2026" : pg;
      const label = toSentenceCase(raw);
      return icon ? icon + "\u00a0" + label : label;
    }
    return "Симптом";
  }
  if (tabId === "concepts") {
    return conceptTypeMeta(sourceType).label;
  }
  if (tabId === "practices") {
    return PRACTICE_RU_LABELS[sourceType.toLowerCase()] || "Практика";
  }
  if (tabId === "sounds") return "Звук";
  return "";
}

function conceptTypeMeta(sourceType) {
  const metaMap = {
    method:    { label: "Метод",   icon: "🛠️" },
    founder:   { label: "Автор",   icon: "👤" },
    system:    { label: "Система", icon: "🧬" },
    chakra:    { label: "Чакра",   icon: "🔮" },
    energy:    { label: "Энергия", icon: "✨" },
    archetype: { label: "Архетип", icon: "✧" },
  };
  return metaMap[String(sourceType || "").trim()] || { label: "Теория", icon: "•" };
}

function formatCourseSourceLabel(value) {
  const COURSE_NAMES = {
    rudn_olfactotherapy_1l:   "Ольфактотерапия, модуль 1",
    rudn_olfactotherapy_2l:   "Ольфактотерапия, модуль 2",
    rudn_olfactotherapy_3l:   "Ольфактотерапия, модуль 3",
    rudn_olfactotherapy_4l:   "Ольфактотерапия, модуль 4",
    rudn_olfactotherapy_5_1l: "Ольфактотерапия, модуль 5.1",
    rudn_olfactotherapy_5_2l: "Ольфактотерапия, модуль 5.2",
    rudn_olfactotherapy_6l:   "Ольфактотерапия, модуль 6",
  };
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => COURSE_NAMES[part] || part)
    .join(" · ");
}

function referenceHeroBadges(reference) {
  const badges = [
    { label: "Тип", value: handbookCardBadge(state.tab, reference) || currentHandbookMeta().title, tone: "type" },
    { label: "Фокус", value: reference.chakra_focus || "", tone: "chakra" },
    { label: "Полярность", value: reference.polarity || "", tone: "polarity" },
    { label: "Курс", value: formatCourseSourceLabel(reference.course_source), tone: "course" },
  ].filter((item) => item.value);
  return badges.map((item) => `
    <div class="reference-badge reference-badge-${escapeHtml(item.label.toLowerCase().replace(/[^a-zа-я0-9]+/gi, "-"))} tone-${escapeHtml(item.tone)}">
      <span class="reference-badge-label">${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
    </div>
  `).join("");
}

/**
 * Convert ALL_CAPS strings (from PDF) to sentence case for display.
 * "АЛЛЕРГИЧЕСКИЙ РИНИТ" → "Аллергический ринит"
 * Mixed-case strings are returned unchanged.
 */
function toSentenceCase(str) {
  if (!str) return str;
  const s = String(str).trim();
  const letters = s.replace(/[^а-яёa-zА-ЯЁA-Z]/g, "");
  if (!letters || letters !== letters.toUpperCase()) return s;
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatInlineMarkdown(value) {
  return value
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(.+?)__/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/_(.+?)_/g, "<em>$1</em>");
}

function renderMarkdown(value) {
  const source = String(value || "").trim();
  if (!source) return "";

  // Handle code fences first
  const FENCE_RE = /```([\s\S]*?)```/g;
  const fenceMap = {};
  let fenceIndex = 0;
  const withoutFences = source.replace(FENCE_RE, (_, content) => {
    const key = `\x00FENCE${fenceIndex++}\x00`;
    fenceMap[key] = content.trim();
    return key;
  });

  const lines = withoutFences.split(/\r?\n/);
  const chunks = [];
  let listItems = [];

  const flushList = () => {
    if (!listItems.length) return;
    chunks.push(`<ul>${listItems.join("")}</ul>`);
    listItems = [];
  };

  for (const rawLine of lines) {
    const escapedLine = escapeHtml(rawLine.trim());
    if (!escapedLine) {
      flushList();
      continue;
    }
    if (/^#{1,3}\s+/.test(escapedLine)) {
      flushList();
      const level = Math.min((escapedLine.match(/^#+/) || ["#"])[0].length + 2, 5);
      const text = escapedLine.replace(/^#{1,3}\s+/, "");
      chunks.push(`<h${level}>${formatInlineMarkdown(text)}</h${level}>`);
      continue;
    }
    if (/^[-*]\s+/.test(escapedLine)) {
      listItems.push(`<li>${formatInlineMarkdown(escapedLine.replace(/^[-*]\s+/, ""))}</li>`);
      continue;
    }
    flushList();
    chunks.push(`<p>${formatInlineMarkdown(escapedLine)}</p>`);
  }
  flushList();
  let result = chunks.join("");

  // Replace fence sentinels with code blocks
  for (const key of Object.keys(fenceMap)) {
    const escaped = escapeHtml(fenceMap[key]);
    const raw = fenceMap[key];
    const block = `<div class="code-block"><pre>${escaped}</pre><button class="copy-btn" data-action="_copyCodeBlock">Копировать</button></div>`;
    result = result.replace(escapeHtml(key), block).replace(key, block);
  }

  return result;
}

function stripMarkdown(value) {
  return String(value || "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .trim();
}

function payloadSection(title, content) {
  if (!content) return "";
  return `<section class="section"><h3>${sectionHeadingIcon(title)}${escapeHtml(title)}</h3><div class="detail-preview detail-markdown">${renderMarkdown(content)}</div></section>`;
}

function detailFactMarkup(label, value) {
  if (!value) return "";
  return `
    <div class="detail-fact">
      <span class="detail-fact-label">${escapeHtml(label)}</span>
      <strong class="detail-fact-value">${escapeHtml(value)}</strong>
    </div>
  `;
}

function icon(name, size = 18) {
  return `<i class="ph ph-${name}" style="font-size:${size}px;display:block;flex-shrink:0"></i>`;
}

function uiIcon(name) {
  const PHOSPHOR_MAP = {
    card:       "file-text",
    slides:     "grid-four",
    prompt:     "terminal-window",
    regenerate: "arrow-counter-clockwise",
    chat:       "chat-square",
    pptx:       "presentation-chart",
    note:       "pencil-line",
    reject:     "x",
    close:      "x",
    "x":        "x",
    trash:      "trash",
    delete:     "trash",
    undo:       "arrow-counter-clockwise",
    back:       "caret-left",
    gear:       "gear",
    eye:        "eye",
    approve:    "check",
    sparkle:    "sparkle",
    scissors:   "scissors",
    video:      "video-camera",
    "file-video": "file-video",
    text:       "text-align-left",
    nps:        "heart",
    therapy:    "first-aid",
    psyche:     "brain",
    plus:       "plus",
    minus:      "minus",
    history:    "clock",
    passport:   "file-text",
    reel:       "film-slate",
    image:      "image",
    search:     "magnifying-glass",
    download:   "download",
    upload:     "upload",
    sunrise:    "sunrise",
    sun:        "sun",
    moon:       "moon",
    threads:    "at",
    instagram:  "instagram-logo",
    telegram:   "paper-plane-tilt",
    plan:       "calendar-dots",
    play:       "play",
    layers:     "stack",
    loader:     "spinner",
    calendar:   "calendar-dots",
    link:       "link",
    "external-link": "arrow-square-out",
    "message-circle": "chat-circle",
    camera:     "camera",
    "check-circle": "check-circle",
    users:      "users",
    "user-plus": "user-plus",
    "user-minus": "user-minus",
    ticket:     "ticket",
    shield:     "shield",
    crown:      "crown",
    send:       "paper-plane-tilt",
    copy:       "copy",
    zap:        "lightning",
    bot:        "robot",
    publish:    "upload",
    palette:    "palette",
    activity:   "activity",
    "arrow-left": "arrow-left",
    "alert-circle": "warning-circle",
    check:      "check",
    lock:       "lock",
    "bar-chart-3": "chart-bar",
    "columns-2": "columns",
    "corner-down-right": "arrow-bend-down-right",
    hash:       "hash",
    heart:      "heart",
    "refresh-cw": "arrow-clockwise",
    repeat:     "repeat",
    "thumbs-up": "thumbs-up",
    "align-left": "text-align-left",
    "at-sign":  "at",
    clock:      "clock",
    "file-text": "file-text",
    music:      "music-notes",
    list:       "list-bullets",
    "layout-grid": "grid-four",
    "arrow-up-right": "arrow-up-right",
    "arrow-down-left": "arrow-down-left",
    "pen-tool": "pen-nib",
    compass:    "compass",
    lightbulb:  "lightbulb",
    settings:   "gear-six",
    grid:       "grid-four",
    stop:       "stop",
    gauge:      "gauge",
    cpu:        "cpu",
    "arrow-counter-clockwise": "arrow-counter-clockwise",
    "clock-counter-clockwise": "clock-counter-clockwise",
    "play-circle": "play-circle",
    brain:      "brain",
    stack:      "stack",
    list:       "rows",
    "chevron-down": "caret-down",
    "chevron-up": "caret-up",
    "chevron-left": "caret-left",
    "chevron-right": "caret-right",
    archive:    "archive-box",
    pencil:     "pencil",
    "pencil-simple": "pencil-simple",
    warning:    "warning",
    bell:       "bell",
    palette:    "palette",
    "film-slate": "film-slate",
    save:       "floppy-disk",
    star:       "star",
    "share-2":  "share-network",
    "trash-2":  "trash",
    film:       "film-strip",
    scan:       "scan",
    tools:      "wrench",
    "tech-check": "scan",
    "copy-plus": "copy",
    sparkles:   "sparkle",
    "map-pin":  "map-pin",
    "sliders-horizontal": "sliders-horizontal",
    award:      "trophy",
    trophy:     "trophy",
    "trending-up": "trend-up",
  };
  return `<span class="ui-icon ui-icon-${escapeHtml(name)}">${icon(PHOSPHOR_MAP[name] || name, 16)}</span>`;
}

function sectionHeadingIcon(title) {
  const iconMap = {
    // ── Карточки контента ──
    "Превью": "eye",
    "Угол": "compass",
    "Текст": "text-aa",
    "CTA": "megaphone",
    "Паспорт карточки": "identification-card",
    "Паспорт аромата": "identification-card",
    "Описание": "text-align-left",
    "Промпт для изображения": "magic-wand",
    "Какие вопросы поднимает": "question",
    // ── Справочник ──
    "О концепции": "lightbulb",
    "О практике": "book-open",
    "Действие на НПС": "brain",
    "Терапевтические свойства": "first-aid",
    "Психологические свойства": "smiley",
    "Исторические сведения": "clock-counter-clockwise",
    'Ресурс "+"': "plus-circle",
    'Ресурс "-"': "minus-circle",
    // ── Рилс: сценарий ──
    "Сценарий": "scroll",
    "Концепция": "lightbulb",
    "Кадры": "stack",
    "Кадры и промпты": "stack",
    "Замечания": "note-pencil",
    "Видео": "video-camera",
    // ── Рилс: видео пайплайн ──
    "color-grade": "palette",       // Цветокоррекция → палитра
    "montage": "film-slate",         // Автомонтаж → хлопушка
    "scissors": "waveform",         // Нарезка пауз → звуковая волна
    "film": "film-strip",           // Сборка из кадров → плёнка
    "tools": "wrench",              // Инструменты → гаечный ключ
    "video": "play-circle",         // Предпросмотр → плеер
    "tech-check": "shield-check",   // Проверка → щит с галочкой
    "publish": "paper-plane-tilt",  // Публикация → отправка
    "music": "music-notes",          // Музыка → ноты
  };
  return uiIcon(iconMap[title] || "card");
}

function actionLabel(icon, text) {
  return `${uiIcon(icon)}<span>${escapeHtml(text)}</span>`;
}

function tagMarkup(label, tone = "neutral") {
  if (!label) return "";
  const safeTone = String(tone || "neutral")
    .replace(/[^a-z0-9_-]/gi, "")
    .toLowerCase();
  if (safeTone === "pending") {
    return `<span class="tag tag-pending">${escapeHtml(label)}</span>`;
  }
  return `<span class="tag tag-${safeTone}">${escapeHtml(label)}</span>`;
}

/**
 * Render a progressive-loading image with LQIP blur-up.
 * Falls back gracefully: if no lqip/thumb, renders a plain <img>.
 */
function progressiveImg(src, { thumb, lqip, alt = "", cls = "", loading = "lazy" } = {}) {
  if (!src) return "";
  if (!lqip && !thumb) {
    return `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" class="${escapeHtml(cls)}" loading="${loading}">`;
  }
  const initialSrc = thumb || src;
  return `<div class="progressive-img ${escapeHtml(cls)}">` +
    `<img class="progressive-img__full" src="${escapeHtml(initialSrc)}" data-full="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="${loading}">` +
    (lqip ? `<img class="progressive-img__lqip" src="${escapeHtml(lqip)}" alt="" aria-hidden="true">` : "") +
    `</div>`;
}

function contentKindIcon(kind) {
  const iconMap = {
    content:        "note",
    threads:        "note",
    threads_series: "threads",
    plan:           "plan",
    reels:          "reel",
    reels_v2:       "reel",
    carousel:       "layers",
    content_series: "pencil",
    youtube_video:  "video",
    instagram:      "instagram",
    telegram:       "telegram",
  };
  const normalized = String(kind || "").toLowerCase();
  return uiIcon(iconMap[normalized] || "note");
}

function promptDisclosureKey(rawKey = "", fallbackSeed = "") {
  const normalized = String(rawKey || fallbackSeed || "prompt")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9:_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || "prompt";
}

function isPromptDisclosureOpen(rawKey = "", defaultOpen = false) {
  const key = promptDisclosureKey(rawKey);
  if (Object.prototype.hasOwnProperty.call(state.openPromptPanels, key)) {
    return Boolean(state.openPromptPanels[key]);
  }
  return Boolean(defaultOpen);
}

function promptDisclosureMarkup(rawKey, bodyMarkup, {
  defaultOpen = false,
  openLabel = "Показать промпт",
  closeLabel = "Скрыть промпт",
} = {}) {
  const key = promptDisclosureKey(rawKey);
  const isOpen = isPromptDisclosureOpen(key, defaultOpen);
  return `
    <div class="prompt-disclosure${isOpen ? " is-open" : ""}" data-prompt-key="${escapeHtml(key)}">
      <button
        class="secondary-button prompt-toggle"
        type="button"
        aria-expanded="${isOpen ? "true" : "false"}"
        data-default-open="${defaultOpen ? "true" : "false"}"
        data-open-label="${escapeHtml(openLabel)}"
        data-close-label="${escapeHtml(closeLabel)}"
        data-action="togglePromptDisclosure" data-args='${JSON.stringify([key, null])}'
      >${actionLabel(isOpen ? "chevron-up" : "chevron-down", isOpen ? closeLabel : openLabel)}</button>
      <div class="prompt-card"${isOpen ? "" : " hidden"}>${bodyMarkup}</div>
    </div>
  `;
}

function togglePromptDisclosure(rawKey = "", button) {
  const key = promptDisclosureKey(rawKey);
  const container = button instanceof HTMLElement ? button.closest(".prompt-disclosure") : null;
  const card = container?.querySelector(".prompt-card");
  const defaultOpen = button instanceof HTMLElement && button.dataset.defaultOpen === "true";
  const nextOpen = !isPromptDisclosureOpen(key, defaultOpen);
  state.openPromptPanels[key] = nextOpen;
  if (container instanceof HTMLElement) {
    container.classList.toggle("is-open", nextOpen);
  }
  if (card instanceof HTMLElement) {
    card.hidden = !nextOpen;
  }
  if (button instanceof HTMLElement) {
    const openLabel = button.dataset.openLabel || "Показать промпт";
    const closeLabel = button.dataset.closeLabel || "Скрыть промпт";
    button.setAttribute("aria-expanded", nextOpen ? "true" : "false");
    button.innerHTML = actionLabel(nextOpen ? "chevron-up" : "chevron-down", nextOpen ? closeLabel : openLabel);
  }
}

window.togglePromptDisclosure = togglePromptDisclosure;

function promptSection(title, prompt, copyLabel = "Скопировать промпт", promptKey = "") {
  if (!prompt) return "";
  const disclosureKey = promptDisclosureKey(promptKey, `${title}:${String(prompt).slice(0, 48)}`);
  return `
    <section class="section">
      <h3>${uiIcon("prompt")}${escapeHtml(title)}</h3>
      ${promptDisclosureMarkup(disclosureKey, `
        <div class="detail-preview prompt-preview">${escapeHtml(prompt)}</div>
        <div class="actions-row prompt-actions">
          <button class="secondary-button" type="button" data-action="copyText" data-args='${JSON.stringify([String(prompt)])}'>${actionLabel("copy", copyLabel)}</button>
        </div>
      `)}
    </section>
  `;
}


function isContentReviewKind(kind) {
  const normalized = String(kind || "").trim().toLowerCase();
  return normalized === "threads" || normalized === "instagram" || normalized === "telegram";
}

function frameDraftKey(draftId, index) {
  return `${draftId}:${index}`;
}

async function sendDraftToChat(draftId, button) {
  await withButtonFeedback(button, "Отправляю...", async () => {
    await fetchJson(`/api/drafts/${draftId}/send`, { method: "POST", body: "{}" });
  }, "Отправлено");
  const tg = window.Telegram?.WebApp;
  if (tg?.showAlert) tg.showAlert("Черновик отправлен в чат");
  else showUiNotice("Черновик отправлен в чат", "success");
}

async function approveThreadsSeries(draftId, btn) {
  await withButtonFeedback(btn, "Согласовываю...", async () => {
    const draft = await fetchJson(`/api/threads-series/${draftId}/approve`, { method: "POST", body: "{}" });
    mergeDraftIntoState(draft);
    renderDraftList();
    renderDraftDetail(draft);
  }, "Согласовано");
}

async function regenSlot(draftId, slot, btn) {
  const noteInput = document.getElementById(`regenNote_${slot}_${draftId}`);
  const note = noteInput ? noteInput.value.trim() : "";
  const textareaEl = document.getElementById(`slotText_${slot}_${draftId}`);
  if (textareaEl) {
    textareaEl.disabled = true;
    textareaEl.classList.add("is-generating");
  }
  await withButtonFeedback(btn, "Пишу...", async () => {
    const draft = await fetchJson(`/api/threads-series/${draftId}/regen-slot`, {
      method: "POST",
      body: JSON.stringify({ slot, note: note || null }),
      timeout: 30000,
    });
    mergeDraftIntoState(draft);
    renderDraftList();
    renderDraftDetail(draft);
  }, "Готово");
}

async function regenerateSeriesPosts(draftId, btn) {
  await withButtonFeedback(btn, "Генерирую посты...", async () => {
    const draft = await fetchJson(`/api/threads-series/${draftId}/regenerate-posts`, {
      method: "POST",
      timeout: 60000,
    });
    mergeDraftIntoState(draft);
    renderDraftList();
    renderDraftDetail(draft);
  }, "Готово");
}

async function saveThreadsSlot(draftId, slot, btn) {
  const textEl = document.getElementById(`slotText_${slot}_${draftId}`);
  const timeEl = document.getElementById(`slotTime_${slot}_${draftId}`);
  const text = textEl ? textEl.value : null;
  const scheduled_time = timeEl ? timeEl.value : null;
  await withButtonFeedback(btn, "Сохраняю...", async () => {
    const draft = await fetchJson(`/api/threads-series/${draftId}/slot`, {
      method: "PATCH",
      body: JSON.stringify({ slot, text, scheduled_time }),
    });
    mergeDraftIntoState(draft);
    renderDraftList();
    renderDraftDetail(draft);
  }, "Сохранено");
}

async function showSlotHistory(draftId, slot) {
  const data = await fetchJson(`/api/threads-series/${draftId}/slot-history/${slot}`);
  const versions = data.versions || [];
  const slotLabels = { morning: "УТРО", day: "ДЕНЬ", evening: "ВЕЧЕР" };
  const label = slotLabels[slot] || slot;
  if (!versions.length) {
    showUiNotice(`История ${label}: нет сохранённых версий`, "info");
    return;
  }
  const listHtml = versions.slice().reverse().map((v, i) => `
    <div class="slot-history-item">
      <span class="slot-history-date">${escapeHtml(v.created_at ? new Date(v.created_at).toLocaleString("ru") : "")}</span>
      <p class="slot-history-text">${escapeHtml(v.text || "")}</p>
    </div>
  `).join("");
  const tg = window.Telegram?.WebApp;
  if (tg?.showAlert) {
    tg.showAlert(versions.slice().reverse().map((v, i) => `${i + 1}. ${v.text || ""}`).join("\n\n---\n\n"));
  } else {
    const notice = document.createElement("div");
    notice.className = "slot-history-overlay";
    notice.innerHTML = `<div class="slot-history-modal"><h3>История ${escapeHtml(label)}</h3>${listHtml}<button class="primary-button" data-action="_closeSlotHistory">Закрыть</button></div>`;
    document.body.appendChild(notice);
  }
}

async function scheduleThreadsSeries(draftId, date, slots, btn) {
  console.log("[scheduleThreadsSeries] draftId:", draftId, "date:", date, "btn:", btn?.id);
  if (!draftId || !date) {
    showUiNotice("Не выбран черновик или дата", "error");
    return;
  }
  await withButtonFeedback(btn, "Планирую...", async () => {
    const result = await fetchJson("/api/publish/schedule-series", {
      method: "POST",
      body: JSON.stringify({ draft_id: draftId, date, slots }),
    });
    const count = (result.scheduled || []).length;
    showUiNotice(count > 0 ? `Запланировано ${count} поста` : "Нет доступных слотов (просрочены?)", count > 0 ? "success" : "warning");
    if (count > 0) {
      const draft = await fetchJson(`/api/drafts/${draftId}`);
      mergeDraftIntoState(draft);
      state.contentSubTab = "plans";
      state.plansSubMode = "publications";
      setTab("plans");
      await safeLoadCurrentTab();
    }
  }, "Запланировано");
}

async function publishScheduledNow(draftId, kind, slotOrBtn, btn) {
  // Support old 3-arg calls: publishScheduledNow(id, kind, btn)
  let slot = slotOrBtn;
  if (slotOrBtn instanceof HTMLElement) { btn = slotOrBtn; slot = ""; }

  if (kind === "threads_series" && slot) {
    const confirmed = await confirmAction("Опубликовать этот пост сейчас?");
    if (!confirmed) return;
    await withButtonFeedback(btn, "Публикую...", async () => {
      await fetchJson(`/api/threads-series/${draftId}/slots/${slot}/publish-now`, {
        method: "POST",
        body: "{}",
        timeout: 60000,
      });
      showUiNotice("Публикация запущена", "success");
      await loadPlansFeedImpl();
    }, "Отправлено");
    return;
  }

  const confirmed = await confirmAction("Опубликовать сейчас? Запланированное время будет проигнорировано.");
  if (!confirmed) return;

  if (kind === "threads_series") {
    await publishThreadsSeriesNow(draftId, btn);
    return;
  }

  await withButtonFeedback(btn, "Публикую...", async () => {
    await fetchJson(`/api/publish/${draftId}`, {
      method: "POST",
      body: "{}",
      timeout: 60000,
    });
    showUiNotice("Публикация запущена", "success");
    await loadPlansFeedImpl();
  }, "Отправлено");
}

async function retryPublication(draftId, platform, slot, btn) {
  await withButtonFeedback(btn, "Публикую...", async () => {
    if (slot) {
      await fetchJson(`/api/threads-series/${draftId}/publish-now`, {
        method: "POST",
        body: "{}",
        timeout: 120000,
      });
    } else {
      await fetchJson(`/api/publish/${draftId}`, {
        method: "POST",
        body: "{}",
        timeout: 60000,
      });
    }
    showUiNotice("Повторная публикация запущена", "success");
    await loadPlansFeedImpl();
  }, "Отправлено");
}

async function publishThreadsSeriesNow(draftId, btn) {
  const confirmed = await confirmAction("Опубликовать все посты серии сейчас? Между постами будет пауза 30 секунд.");
  if (!confirmed) return;
  await withButtonFeedback(btn, "Публикую...", async () => {
    const result = await fetchJson(`/api/threads-series/${draftId}/publish-now`, {
      method: "POST",
      body: "{}",
      timeout: 120000,
    });
    const ok = (result.results || []).filter(r => r.status === "ok").length;
    const errs = (result.results || []).filter(r => r.status === "error").length;
    const errorDetails = (result.results || []).filter(r => r.error).map(r => `${r.slot}: ${r.error}`);
    if (errorDetails.length) showUiNotice(errorDetails.join("\n"), "error");
    showUiNotice(
      errs ? `Опубликовано ${ok}, ошибок ${errs}` : `Все ${ok} поста опубликованы`,
      errs ? "warning" : "success",
    );
    const draft = await fetchJson(`/api/drafts/${draftId}`);
    if (draft) {
      mergeDraftIntoState(draft);
      renderDraftList();
      renderDraftDetail(draft);
    }
  }, "Опубликовано");
}

function openThreadsScheduler(draftId) {
  const container = document.getElementById(`scheduler_${draftId}`);
  if (!container) return;
  container.hidden = !container.hidden;
  if (!container.hidden) _renderThreadsSchedulerDates(draftId);
}

function _renderThreadsSchedulerDates(draftId) {
  const container = document.getElementById(`schedulerDates_${draftId}`);
  if (!container) return;
  const today = new Date();
  const buttons = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    const iso = d.toISOString().slice(0, 10);
    const label = i === 0 ? "Сегодня" : i === 1 ? "Завтра" : d.toLocaleDateString("ru", { weekday: "short", day: "numeric", month: "short" });
    return `<button class="date-picker-btn" type="button" data-date="${iso}" data-action="_selectSchedulerDate" data-args='${JSON.stringify([draftId, iso, null])}'>${escapeHtml(label)}</button>`;
  }).join("");
  container.innerHTML = buttons;
}

function _selectSchedulerDate(draftId, date, btn) {
  const container = document.getElementById(`schedulerDates_${draftId}`);
  container?.querySelectorAll(".date-picker-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  const scheduleBtn = document.getElementById(`schedulerSubmit_${draftId}`);
  if (scheduleBtn) {
    scheduleBtn.dataset.date = date;
    scheduleBtn.disabled = false;
  }
}

function confirmAction(message) {
  const tg = window.Telegram?.WebApp;
  if (tg?.showConfirm) {
    return new Promise((resolve) => {
      tg.showConfirm(message, (confirmed) => resolve(Boolean(confirmed)));
    });
  }
  return Promise.resolve(window.confirm(message));
}

async function deleteDraft(draftId, kind = "drafts", button) {
  const confirmed = await confirmAction("Удалить этот черновик?");
  if (!confirmed) return;
  if (button instanceof HTMLElement) {
    await withButtonFeedback(button, "Удаляю...", async () => {
      await fetchJson(`/api/drafts/${draftId}`, { method: "DELETE" });
    }, "Удалено");
  } else {
    await fetchJson(`/api/drafts/${draftId}`, { method: "DELETE" });
  }
  if (kind === "reels") {
    state.reels = state.reels.filter((item) => item.draft_id !== draftId);
    state.drafts = state.drafts.filter((item) => item.draft_id !== draftId);
    if (state.selectedReels?.draft_id === draftId) state.selectedReels = null;
    renderEmptyDetail();
    renderDraftList();
  } else {
    state.drafts = state.drafts.filter((item) => item.draft_id !== draftId);
    if (state.draftId === draftId) {
      state.draftId = "";
      state.selected = null;
      renderEmptyDetail();
    }
    renderDraftList();
  }
}

function kindLabel(value) {
  return RU_KIND_LABELS[String(value || "").toLowerCase()] || String(value || "");
}

function statusLabel(value) {
  return RU_STATUS_LABELS[String(value || "").toLowerCase()] || String(value || "");
}

function feedbackLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) return "Без реакции";
  return RU_FEEDBACK_LABELS[normalized] || String(value || "");
}

function statusTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "approved" || normalized === "published") return "status-positive";
  if (normalized === "scheduled") return "status-review";
  if (normalized === "rejected") return "status-negative";
  if (normalized === "in_review") return "status-review";
  return "status-neutral";
}

function feedbackTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "worked") return "feedback-worked";
  if (normalized === "missed") return "feedback-missed";
  return "feedback-neutral";
}

function sourceTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "/plan") return "source-plan";
  if (normalized === "/content") return "source-content";
  if (normalized === "/miniapp") return "source-miniapp";
  return "source-neutral";
}

function sourceLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "/plan") return "Из плана";
  if (normalized === "/content") return "Контент";
  if (normalized === "/miniapp") return "";
  return String(value || "");
}

function draftHeroSummary(draft, payload, mainText) {
  const preview = stripMarkdown(draft.preview || mainText || "");
  if (preview) return preview.slice(0, 180);
  if (payload?.angle) return `Опорный angle: ${String(payload.angle).trim()}`;
  if (payload?.hook) return `Главный hook: ${String(payload.hook).trim()}`;
  return "Материал готов к редакторскому проходу и согласованию.";
}

function pluralize(n, forms) {
  const abs = Math.abs(n) % 100;
  const n1 = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (n1 > 1 && n1 < 5) return forms[1];
  if (n1 === 1) return forms[0];
  return forms[2];
}

function formatPlanDate(value) {
  let text = String(value || "").trim();
  if (!text) return "";
  if (/T/.test(text) && !/[Z+\-]\d{0,4}$/.test(text)) text += "Z";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return date.toLocaleDateString("ru-RU") + " " + date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function humanizeRequestMessage(error) {
  if (error?.status === 402) return "Требуется подписка";
  if (error?.status === 403) return "Нет доступа";
  if (error?.status === 504) return "Сервер не ответил вовремя";
  if (error?.status >= 500) return "Ошибка сервера";
  if (error?.message === "request_timeout") return "Превышено время ожидания";
  if (error?.message === "network_error") return "Нет соединения";
  return error?.message || "Неизвестная ошибка";
}

function showRequestError(prefix, error) {
  showUiNotice(`${prefix}: ${humanizeRequestMessage(error)}`, "error");
}

const {
  syncMobileNavigation,
  renderBackButton,
  goBackToList,
  enterDetailView,
  isEditingDetailForm,
  bindTextareaAutoExpand,
  bindKeyboardDismiss,
  bindTapAnimation,
  bindCardKeyboardActivation,
  bindKeyboardViewportAssist,
  bindPullToRefresh,
  bindSwipeBack,
  bindBottomTabBar,
} = createShellModule({
  state,
  elements,
  uiIcon,
  setMode,
  setTab,
  safeLoadCurrentTab: (...args) => safeLoadCurrentTab(...args),
  HANDBOOK_CATEGORY_META,
  initScrollFade,
});

const coreCallbacks = {
  setTab: (...args) => setTab(...args),
  renderDraftList: () => renderDraftList(),
  renderDraftDetail: (draft) => renderDraftDetail(draft),
  enterDetailView: () => enterDetailView(),
  loadDrafts: () => loadDrafts(),
  openDraft: (draftId) => openDraft(draftId),
  syncMobileNavigation: () => syncMobileNavigation(),
  isBootstrapped: () => appBootstrapped,
  renderReels: () => renderReels(),
  renderReelsDetail: (draft) => renderReelsDetail(draft),
};

function getInitDataHeaders() {
  const initData = window.Telegram?.WebApp?.initData;
  const headers = initData ? { "X-Telegram-Init-Data": initData } : {};
  if (state.activeTeamId) headers["X-Team-Id"] = state.activeTeamId;
  return headers;
}

const analytics = createAnalyticsModule({ getInitDataHeaders });

const {
  interactiveCardAttrs,
  renderDetailLoader,
  renderPanelLoader,
  renderPanelError,
  renderGuidedState,
  showUiNotice,
  renderDetailError,
  draftSummaryFromDraft,
  upsertDraftSummary,
  draftGenerationLabel,
  generationStateMarkup,
  isPendingDraftId,
  openPendingDraftCreation,
  finalizePendingDraftCreation,
  recoverPendingDraftCreation,
  mergeDraftIntoState,
  mergeReelsIntoState,
  setEmptyState,
  showBootFallback,
  hideBootFallback,
  showRuntimeWarning,
  copyText,
  fetchJson,
  withButtonFeedback,
  updateCurrentDraft,
  aromaSection,
  aromaHtmlSection,
} = createCoreModule({
  state,
  elements,
  escapeHtml,
  uiIcon,
  sectionHeadingIcon,
  renderBackButton,
  renderMarkdown,
  getInitDataHeaders,
  getCurrentDraftId: () => state.draftId || state.selectedReels?.draft_id || "",
  timers: {
    getUiNotice: () => uiNoticeTimer,
    setUiNotice: (value) => { uiNoticeTimer = value; },
  },
  callbacks: coreCallbacks,
});

const teamsModule = createTeamsModule({
  state,
  elements,
  api: (method, url, body) => fetchJson(url, {
    method,
    ...(body ? { body: JSON.stringify(body) } : {}),
  }),
  escapeHtml,
  icon: uiIcon,
});

const sessionCallbacks = {
  refreshReelsDetail: null,
};

const {
  clearBackgroundRefreshes,
  isCurrentDraftDetail,
  isCurrentReelsDetail,
  authQueryString,
  applyTelegramTheme,
  applyTheme,
  filtersToQueryString,
  initDataHeaders,
  scheduleReelsRefresh,
  scheduleCarouselRefresh,
  scheduleDraftRefresh,
  loadDrafts,
} = createSessionModule({
  state,
  elements,
  timers: {
    getReelRefresh: () => reelRefreshTimer,
    setReelRefresh: (value) => { reelRefreshTimer = value; },
    getCarouselRefresh: () => carouselRefreshTimer,
    setCarouselRefresh: (value) => { carouselRefreshTimer = value; },
    getDraftRefresh: () => draftRefreshTimer,
    setDraftRefresh: (value) => { draftRefreshTimer = value; },
  },
  fetchJson,
  renderDraftList: () => renderDraftList(),
  renderDraftDetail: (draft) => renderDraftDetail(draft),
  renderReels: () => renderReels(),
  renderReelsDetail: (draft) => renderReelsDetail(draft),
  renderEmptyDetail: () => renderEmptyDetail(),
  renderDetailError,
  hasPendingCarouselOperations: (draftId) => hasPendingCarouselOperations(draftId),
  setCarouselSlideOperation: (draftId, idx, val) => setCarouselSlideOperation(draftId, idx, val),
  clearAllCarouselOperations: (draftId) => clearAllCarouselOperations(draftId),
  isEditingDetailForm,
  syncMobileNavigation,
  enterDetailView,
  openDraft: (draftId) => openDraft(draftId),
  scheduleReelsDetailRefresh: (draftId) => sessionCallbacks.refreshReelsDetail(draftId),
});

const {
  bufferedCarouselNote,
  hasPendingCarouselOperations,
  clearAllCarouselOperations,
  setCarouselSlideOperation,
  renderSlides,
  saveCarouselSlideText,
  handleCarouselSlideNoteInput,
  regenerateCarouselSlide,
  regenerateCarouselAll,
  selectCarouselSlideVersion,
  deleteCarouselSlideVersion,
  previewCarouselSlide,
  carouselSwiperGoTo,
  setSlidesViewMode,
  downloadCarouselPptx,
  importCarouselPptx,
  exportToCanva,
  importFromCanva,
  selectCanvaDesign,
} = createCarouselModule({
  state,
  carouselNoteSaveTimers,
  frameDraftKey,
  escapeHtml,
  uiIcon,
  actionLabel,
  formatPlanDate,
  fetchJson,
  withButtonFeedback,
  showRequestError,
  showUiNotice,
  confirmAction,
  authQueryString,
  initDataHeaders,
  isCurrentDraftDetail,
  isPromptDisclosureOpen,
  mergeDraftIntoState,
  renderDraftList: (...args) => renderDraftList(...args),
  renderDraftDetail: (...args) => renderDraftDetail(...args),
  scheduleCarouselRefresh,
});

const {
  loadPlans: loadPlansImpl,
  loadPlansFeed: loadPlansFeedImpl,
  setPlanStatusFilter,
  setPlanPlatformFilter,
  setPlanDateFilter,
  openPlanDetail,
  planEntryTargetKind,
  planEntryFormatLabel,
  relatedDraftsForEntry,
  openPlan,
  generateDraftFromPlan,
  openPlanRelatedDraft,
  renderPlans: renderPlansImpl,
  renderPlanDetail,
  activatePlan,
} = createPlansModule({
  state,
  elements,
  escapeHtml,
  uiIcon,
  actionLabel,
  tagMarkup,
  interactiveCardAttrs,
  contentKindIcon,
  progressiveImg,
  kindLabel,
  sourceLabel,
  sourceTone,
  formatPlanDate,
  renderBackButton,
  renderMarkdown,
  renderGuidedState,
  setEmptyState,
  renderDetailLoader,
  detailFactMarkup,
  fetchJson,
  withButtonFeedback,
  upsertDraftSummary,
  draftSummaryFromDraft,
  setTab,
  enterDetailView,
  syncMobileNavigation,
  loadPlans,
  loadDrafts,
  loadReels: (...a) => loadReels(...a),
  openDraft: (...a) => openDraft(...a),
  openReels: (...a) => openReels(...a),
  openPendingReelsCreation: (...a) => openPendingReelsCreation(...a),
  finalizePendingReelsCreation: (...a) => finalizePendingReelsCreation(...a),
  recoverPendingReelsCreation: (...a) => recoverPendingReelsCreation(...a),
  scheduleDraftRefresh,
});
renderPlans = renderPlansImpl;

// ── Mentions module ──────────────────────────────────────────────────────────

const mentionsModule = createMentionsModule({
  state,
  elements: { plansContainer: null, draftDetail: elements.draftDetail },
  fetchJson,
  escapeHtml,
  withButtonFeedback,
  showUiNotice,
  enterDetailView,
  syncMobileNavigation,
  renderBackButton,
});

window.mentionsModule = mentionsModule;

// ── Archive module ──────────────────────────────────────────────────────────

const archiveModule = createArchiveModule({
  state,
  elements,
  escapeHtml,
  uiIcon,
  tagMarkup,
  renderBackButton,
  renderMarkdown,
  renderGuidedState,
  fetchJson,
  withButtonFeedback,
  confirmAction,
  enterDetailView,
  syncMobileNavigation,
});

window.archiveModule = archiveModule;

// ── Calendar module ──────────────────────────────────────────────────────────

const calendarModule = createCalendarModule({
  state,
  elements,
  escapeHtml,
  uiIcon,
  contentKindIcon,
  progressiveImg,
  kindLabel,
  fetchJson,
  showUiNotice,
  enterDetailView,
  syncMobileNavigation,
  openDraft: (...a) => openDraft(...a),
  setTab,
});

window.calendarModule = calendarModule;

function setPlansSubMode(mode) {
  state.plansSubMode = mode;
  if (mode === "mentions") state.selectedMention = null;
  if (mode === "calendar") state.contentSubTab = "calendar";
  else if (mode === "publications") state.contentSubTab = "plans";
  else if (mode === "mentions") state.contentSubTab = "mentions";
  else if (mode === "archive") state.contentSubTab = "archive";
  if (mode === "calendar") {
    void calendarModule.loadCalendar();
  } else {
    renderPlans();
  }
  renderContentSubTabs();
}

function setContentSubMode(mode) {
  state.contentSubMode = mode;
  state.inspirationSubTab = mode === "trends" ? "trends" : "drafts";
  if (mode === "drafts") {
    setTab("drafts");
  } else {
    setTab("trends");
  }
  void safeLoadCurrentTab("Не удалось загрузить раздел");
}

function openMentionDetail(mentionId) { mentionsModule.openMentionDetail(mentionId); }
function closeMentionDetail() { mentionsModule.closeMentionDetail(); }
function generateReplies(mentionId, btn) { return mentionsModule.generateReplies(mentionId, btn); }
function publishReply(mentionId, replyId, btn) { return mentionsModule.publishReply(mentionId, replyId, btn); }
function ignoreMentionAction(mentionId, btn) { return mentionsModule.ignoreMentionAction(mentionId, btn); }
function setMentionsFilter(key, value) { mentionsModule.setMentionsFilter(key, value); }

// Archive action wrappers
function openArchiveDetail(pubId) { archiveModule.openArchiveDetail(pubId); }
function openArchiveForm(pubId) { archiveModule.openArchiveForm(pubId); }
function savePublication(pubId, btn) { return archiveModule.savePublication(pubId, btn); }
function deletePublication(pubId, btn) { return archiveModule.deletePublication(pubId, btn); }
function importFromUrl(btn) { return archiveModule.importFromUrl(btn); }
function toggleArchiveStats() { archiveModule.toggleArchiveStats(); }
function setArchivePlatformFilter(v) { archiveModule.setArchivePlatformFilter(v); }
function setArchiveScore(name, value) { return archiveModule.setArchiveScore(name, value); }
function bulkImportFromAccount(platform, btn) { return archiveModule.bulkImportFromAccount(platform, btn); }

const reelsCallbacks = {
  renderReels: null,
  renderReelsDetail: null,
};

const {
  renderReelsDetail: renderReelsDetailMarkup,
  saveReelsScenario,
  regenerateReelsStoryboard,
  regenerateAllReelsFrames,
  saveReelsFrameFields,
  saveReelsFramePrompt,
  saveReelsFrameNote,
  regenerateReelsFrame,
  handleReelsFramePromptInput,
  handleReelsFrameNoteInput,
  // V2 functions:
  regenConcept,
  regenScenario,
  regenCaption,
  regenFrameImage,
  regenFrameImageWithPrompt,
  recoverFrameImage,
  upgradeToFull,
  generateReelsImages,
  approveReels,
  scheduleFrameOverlaySave,
  saveFrameImagePrompt,
  autoResize,
  // Phase 4 functions:
  publishReels,
  retryPlatform,
  // Video compose & upload & cleaning
  composeReelVideo,
  uploadReelsVideo,
  cleanReelsVideo,
  splitReelsClips,
  checkAndPublish,
  // Feature: copy caption + fullscreen image
  copyReelsCaption,
  openReelsImageFullscreen,
  openReelsPreview,
  openBotUploadLink,
  // Screen 5 video tools
  jumpToReelsStep,
  runTechCheck,
  composeReelsVideo,
  reuploadVideo,
  proceedToPublish,
  gradePreview,
  gradeShowProfiles,
  gradeSelectProfile,
  gradeApply,
  startMontage,
  notifyWhenReady,
} = createReelsModule({
  state,
  reelsNoteSaveTimers,
  reelsPromptSaveTimers,
  frameDraftKey,
  escapeHtml,
  uiIcon,
  sectionHeadingIcon,
  actionLabel,
  tagMarkup,
  statusLabel,
  statusTone,
  sourceLabel,
  sourceTone,
  draftGenerationLabel,
  generationStateMarkup,
  renderBackButton,
  renderDetailLoader,
  renderMarkdown,
  isPromptDisclosureOpen,
  fetchJson,
  withButtonFeedback,
  showRequestError,
  confirmAction,
  mergeReelsIntoState,
  scheduleReelsRefresh,
  showUiNotice,
  getInitDataHeaders,
  formatPlanDate,
  callbacks: reelsCallbacks,
});

async function loadStatus() {
  state.status = await fetchJson("/api/status");
  renderStatus();
}

async function loadPlans() {
  if (state.plansSubMode === "calendar") {
    await calendarModule.loadCalendar();
    return;
  }
  await Promise.all([loadPlansImpl(), loadPlansFeedImpl()]);
}

async function loadSchedule() {
  await loadScheduleImpl();
  renderScheduleListImpl();
  renderScheduleDetailImpl();
}

const {
  currentHandbookMeta,
  loadReferenceAccess,
  loadReferences,
  openReference,
  openDailyOilReference,
  renderReferences,
  renderReferencesLocked,
  renderReferencesUnavailable,
  openAroma,
  renderAromas,
  renderAromasLocked,
  handleSmartSearch,
  runSmartSearch,
  clearSmartSearch,
  createContentFromOil,
  toggleReferenceFilters,
} = createReferencesModule({
  state,
  elements,
  HANDBOOK_CATEGORY_META,
  escapeHtml,
  renderMarkdown,
  interactiveCardAttrs,
  renderBackButton,
  renderDetailLoader,
  renderGuidedState,
  handbookCategoryIcon,
  aromaCardIcon,
  handbookCardBadge,
  aromaSection,
  aromaHtmlSection,
  fetchJson,
  enterDetailView,
  syncMobileNavigation,
  setEmptyState,
  conceptTypeMeta,
  formatCourseSourceLabel,
  tagMarkup,
  stripMarkdown,
  toSentenceCase,
  showUiNotice,
  SOURCE_TYPE_ICONS,
  SYMPTOM_CATEGORY_ICONS,
  SYMPTOM_PARENT_GROUP_ICONS,
  BLEND_CATEGORY_ICONS,
  CONCEPT_TYPE_ICONS,
  PRACTICE_TYPE_ICONS,
  PRACTICE_RU_LABELS,
});

const {
  openBlendConstructor,
  addRecoOilToBlend,
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
} = createBlendConstructorModule({
  state,
  elements,
  escapeHtml,
  fetchJson,
  confirmAction,
  enterDetailView,
  syncMobileNavigation,
  renderBackButton,
  renderDetailLoader,
  showUiNotice,
  tagMarkup,
  openReference,
});

const {
  openRecommendationsWizard,
  closeRecommendationsWizard,
  isWizardOpen: isRecoWizardOpen,
  renderWizard: renderRecoWizard,
  recoWizardNext,
  recoWizardBack,
  recoSelectMood,
  recoSelectGoal,
  recoUpdateSymptoms,
  recoToggleAroma,
  recoUpdateContra,
  submitRecommendations,
} = createRecommendationsModule({
  state,
  elements,
  fetchJson,
  escapeHtml,
  renderBackButton,
  renderDetailLoader,
  enterDetailView,
  syncMobileNavigation,
  openReference,
  showUiNotice,
});

const _publishMod = createPublishModule({
  fetchJson,
  withButtonFeedback,
  escapeHtml,
  tagMarkup,
  uiIcon,
  showUiNotice,
  confirmAction,
  mergeDraftIntoState,
  renderDraftList: () => renderDraftList(),
  renderDraftDetail: (d) => renderDraftDetail(d),
});
const { renderPublishPanel } = _publishMod;
({ publishDraft, cancelPublishSchedule, loadPublishStatus } = _publishMod);

const {
  loadSchedule: loadScheduleImpl,
  renderScheduleList: renderScheduleListImpl,
  renderScheduleDetail: renderScheduleDetailImpl,
} = createScheduleModule({
  state,
  elements,
  escapeHtml,
  tagMarkup,
  kindLabel,
  contentKindIcon,
  progressiveImg,
  formatPlanDate,
  statusLabel,
  statusTone,
  fetchJson,
  withButtonFeedback,
  setEmptyState,
  syncMobileNavigation,
  renderBackButton,
  interactiveCardAttrs,
});

const _stockPhotosMod = createStockPhotosModule({
  escapeHtml,
  uiIcon,
  fetchJson,
  withButtonFeedback,
  showUiNotice,
  showRequestError,
  mergeDraftIntoState,
  initDataHeaders,
});

({
  saveContentReviewDraft,
  saveThreadsReviewDraft,
  polishContentDraft,
  renderDraftList,
  openDraft,
  renderDraftDetail,
  renderEmptyDetail,
  refreshDraftMetrics,
  moveDraftToTeam,
  recommendHashtags,
  applyRecommendedHashtags,
  adaptTone,
  startRepurpose,
  saveSeriesPost,
  regenSeriesPost,
  regenSeriesAll,
  coherenceCheck,
} = createDraftsModule({
  stockPhotoActions: _stockPhotosMod,
  state,
  elements,
  escapeHtml,
  renderBackButton,
  renderDetailLoader,
  renderGuidedState,
  renderDetailError,
  payloadSection,
  promptSection,
  detailFactMarkup,
  actionLabel,
  tagMarkup,
  contentKindIcon,
  progressiveImg,
  kindLabel,
  sourceLabel,
  sourceTone,
  statusLabel,
  statusTone,
  feedbackLabel,
  feedbackTone,
  draftGenerationLabel,
  draftHeroSummary,
  generationStateMarkup,
  formatPlanDate,
  stripMarkdown,
  uiIcon,
  interactiveCardAttrs,
  isPendingDraftId,
  isContentReviewKind,
  renderSlides,
  renderPublishPanel,
  fetchJson,
  withButtonFeedback,
  mergeDraftIntoState,
  scheduleCarouselRefresh,
  scheduleDraftRefresh,
  setEmptyState,
  enterDetailView,
  syncMobileNavigation,
  renderMarkdown,
  showRequestError,
  showUiNotice,
  callbacks: {
    renderDraftList: (...args) => renderDraftList(...args),
    renderDraftDetail: (...args) => renderDraftDetail(...args),
    openReels: (...args) => openReels(...args),
  },
}));

const _settingsMod = createSettingsModule({
  state,
  elements,
  escapeHtml,
  uiIcon,
  actionLabel,
  interactiveCardAttrs,
  renderBackButton,
  renderGuidedState,
  withButtonFeedback,
  fetchJson,
  confirmAction,
  showUiNotice,
  setEmptyState,
  syncMobileNavigation,
  enterDetailView,
  applyTheme,
});
const { renderBrand: renderBrandImpl, loadForbiddenPhrases: loadForbiddenPhrasesImpl, loadPolicy: loadPolicyImpl, renderAccounts: renderAccountsImpl } = _settingsMod;
({
  addKeywordItem, removeKeywordItem, openKeywordTopic,
  loadKeywords, loadSettings,
  goBackToSettings,
  renderStatus, renderKeywords,
  addForbiddenPhrase, removeForbiddenPhrase,
  addRewrite, removeRewrite, savePlatformTone, saveUploadPostPrefs,
  saveImageModels,
  setTheme,
  connectPlatform, switchAccountsTeam,
  addTrackedHashtag, removeTrackedHashtag,
  addMonitoredAccountFromSettings, removeMonitoredAccountFromSettings,
  createNewTeam, createTeamInvite, removeTeamMember,
  activatePromo, generatePromos,
  selectCity,
  adminResetStuck,
  adminRestartWorker,
} = _settingsMod);

let selectTrendsPlatform, selectTrendsPeriod, refreshTrends, openTrendsPost, createFromInsight, addMonitoredAccount, removeMonitoredAccount, generateTrendCards, createFromTrendCard;
({
  loadTrends,
  selectTrendsPlatform,
  selectTrendsPeriod,
  refreshTrends,
  openTrendsPost,
  createFromInsight,
  addMonitoredAccount,
  removeMonitoredAccount,
  generateTrendCards,
  createFromTrendCard,
} = createTrendsModule({
  state,
  elements,
  escapeHtml,
  uiIcon,
  actionLabel,
  renderBackButton,
  renderGuidedState,
  withButtonFeedback,
  fetchJson,
  confirmAction,
  showUiNotice,
  setEmptyState,
  syncMobileNavigation,
  enterDetailView,
}));

({
  renderCreate, renderCreateTool,
} = createCreateModule({
  state,
  elements,
  uiIcon,
  interactiveCardAttrs,
  contentKindIcon,
  progressiveImg,
  renderGuidedState,
  renderBackButton,
  setEmptyState,
  syncMobileNavigation,
  enterDetailView,
  fetchJson,
  showRequestError,
  showUiNotice,
  escapeHtml,
  openPendingDraftCreation,
  finalizePendingDraftCreation,
  recoverPendingDraftCreation,
  openPendingReelsCreation: (...a) => openPendingReelsCreation(...a),
  finalizePendingReelsCreation: (...a) => finalizePendingReelsCreation(...a),
  recoverPendingReelsCreation: (...a) => recoverPendingReelsCreation(...a),
  openDraft: (...a) => openDraft(...a),
  openReels: (...a) => openReels(...a),
  setTab,
  loadPlans,
  renderPlanDetail,
}));

const _runtimeMod = createRuntimeModule({
  state,
  elements,
  MODE_TABS,
  HANDBOOK_CATEGORY_META,
  appState: {
    isBootstrapped: () => appBootstrapped,
    setBootstrapped: (value) => { appBootstrapped = value; },
    startupLoadInFlight: () => startupLoadInFlight,
    setStartupLoadInFlight: (value) => { startupLoadInFlight = value; },
  },
  timers: {
    getBootstrapWatchdog: () => bootstrapWatchdogTimer,
    setBootstrapWatchdog: (value) => { bootstrapWatchdogTimer = value; },
    getReelRefresh: () => reelRefreshTimer,
    setReelRefresh: (value) => { reelRefreshTimer = value; },
  },
  applyTelegramTheme,
  bindTextareaAutoExpand,
  bindTapAnimation,
  bindPullToRefresh,
  bindSwipeBack,
  bindKeyboardDismiss,
  bindCardKeyboardActivation,
  bindKeyboardViewportAssist,
  bindBottomTabBar,
  setMode,
  setTab,
  loadReferenceAccess,
  loadDrafts,
  loadInbox: (...a) => loadInbox(...a),
  loadPlans,
  loadReels: (...a) => loadReels(...a),
  loadSchedule,
  loadReferences,
  loadSettings,
  loadStatus,
  loadKeywords,
  loadTrends: (...a) => loadTrends(...a),
  renderCreate,
  showBootFallback,
  hideBootFallback,
  showRuntimeWarning,
  renderPanelLoader,
});
const { bindBootFallbackReload, bindStartupErrorFallbacks, bootstrap: bootstrapImpl } = _runtimeMod;
({ loadCurrentTab, safeLoadCurrentTab, retryCurrentTab } = _runtimeMod);
window._currentTabRefresh = () => {
  // Reload if list panel is empty or shows a loader/error placeholder
  const list = document.getElementById("draftList");
  const hasRealContent = list && list.children.length > 0
    && !list.querySelector(".panel-loader-card, .boot-fallback, .detail-loader-card");
  if (!hasRealContent) {
    safeLoadCurrentTab("Не удалось обновить раздел");
  }
};

const onboarding = createOnboardingModule({ state, icon });
window.resetOnboarding = onboarding.resetOnboarding;

({
  loadInbox,
  loadReels,
  openReels,
  openPendingReelsCreation,
  finalizePendingReelsCreation,
  recoverPendingReelsCreation,
  renderInbox,
  renderReels,
  renderReelsDetail,
  refreshReelsDetail,
} = createContentModule({
  state,
  elements,
  escapeHtml,
  stripMarkdown,
  renderBackButton,
  renderDetailLoader,
  renderGuidedState,
  renderDetailError,
  interactiveCardAttrs,
  contentKindIcon,
  progressiveImg,
  kindLabel,
  sourceLabel,
  sourceTone,
  statusLabel,
  statusTone,
  tagMarkup,
  formatPlanDate,
  fetchJson,
  setEmptyState,
  syncMobileNavigation,
  enterDetailView,
  setTab,
  clearBackgroundRefreshes,
  mergeReelsIntoState,
  scheduleReelsRefresh,
  isCurrentReelsDetail,
  isEditingDetailForm,
  showUiNotice,
  callbacks: {
    renderReelsDetailMarkup,
    renderDraftList: () => { if (typeof renderDraftList === "function") renderDraftList(); },
  },
}));

sessionCallbacks.refreshReelsDetail = refreshReelsDetail;

function setMode(m) {
  clearBackgroundRefreshes();
  state.mode = m;
  document.body.dataset.mode = m;
  analytics.trackPageView(m, state.tab);
  elements.modeContent.classList.toggle("active", m === "content");
  elements.modeHandbook.classList.toggle("active", m === "handbook");
  elements.settingsButton?.classList.toggle("active", m === "content" && state.tab === "settings");
  const tabs = MODE_TABS[m] || [];
  elements.tabsContainer.innerHTML = tabs.map((t) => {
    const label = HANDBOOK_CATEGORY_META[t.id]
      ? `${handbookCategoryIcon(t.id)}<span>${escapeHtml(t.label)}</span>`
      : `<span>${escapeHtml(t.label)}</span>`;
    return `<button class="tab-button${state.tab === t.id ? " active" : ""}" data-tab="${t.id}" type="button" role="tab" aria-selected="${state.tab === t.id}">${label}</button>`;
  }).join("");
  elements.tabsContainer.querySelectorAll(".tab-button").forEach(b => {
    b.addEventListener("click", () => {
      const targetTab = b.dataset.tab;
      if (targetTab === state.tab && HANDBOOK_CATEGORY_META[targetTab] && state.selectedReference) {
        state.selectedReference = null;
        state.mobileView = "list";
        renderReferences();
        syncMobileNavigation();
        return;
      }
      setTab(targetTab);
      void safeLoadCurrentTab("Не удалось загрузить вкладку");
    });
  });
  // Hide tabs wrapper when no tabs (content mode has no pill tabs)
  const tabsWrapper = elements.tabsContainer.closest(".tabs-wrapper");
  if (tabsWrapper) tabsWrapper.hidden = tabs.length === 0;
  if (tabsWrapper && tabs.length > 0) {
    const checkScrollEnd = () => {
      const el = elements.tabsContainer;
      const atEnd = el.scrollWidth - el.scrollLeft - el.clientWidth < 8;
      tabsWrapper.classList.toggle("scrolled-end", atEnd);
    };
    elements.tabsContainer.addEventListener("scroll", checkScrollEnd, { passive: true });
    requestAnimationFrame(checkScrollEnd);
  }
  const _contentHidden = ["settings", "create", "inbox", "plans", "schedule", "keywords", "status", "drafts", "trends"];
  if (!(m === "content" && _contentHidden.includes(state.tab)) && tabs.length > 0 && !tabs.find(t => t.id === state.tab)) setTab(tabs[0].id);
  renderContentSubTabs();
  syncMobileNavigation();
}

const SECTION_TITLES = {
  drafts: "Вдохновение", trends: "Вдохновение",
  plans: "Контент",
  create: "Создать", settings: "Настройки",
  schedule: "Расписание", inbox: "Согласование",
  keywords: "Ключи", status: "Статус",
  aromas: "Ароматы", concepts: "Концепции", practices: "Практики", sounds: "Звуки",
  blends: "Смеси", symptoms: "Симптомы",
};

/* ── Inspiration sub-tabs (pill-style below section title) ────────────── */
const INSPIRATION_SUB_TABS = [
  { id: "drafts", label: "Черновики" },
  { id: "trends", label: "Тренды" },
];

const _TABS_SHOWING_INSPIRATION_SUB = new Set(["drafts", "trends"]);

/* ── Content sub-tabs (pill-style below section title) ─────────────────── */
const CONTENT_SUB_TABS = [
  { id: "calendar", label: "Календарь" },
  { id: "plans", label: "Планы" },
  { id: "mentions", label: "Упоминания" },
  { id: "publications", label: "Публикации" },
  { id: "archive", label: "Архив" },
];

const _TABS_SHOWING_CONTENT_SUB = new Set(["plans"]);

function renderContentSubTabs() {
  const container = elements.contentSubTabs;
  if (!container) return;

  if (state.mode === "content" && _TABS_SHOWING_INSPIRATION_SUB.has(state.tab)) {
    container.innerHTML = INSPIRATION_SUB_TABS.map(t =>
      `<button class="content-sub-tab${state.inspirationSubTab === t.id ? " active" : ""}" data-subtab="${t.id}" data-group="inspiration" type="button"><span>${escapeHtml(t.label)}</span></button>`
    ).join("");
    container.querySelectorAll(".content-sub-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.subtab;
        if (!target || target === state.inspirationSubTab) return;
        switchInspirationSubTab(target);
      });
    });
    return;
  }

  if (state.mode === "content" && _TABS_SHOWING_CONTENT_SUB.has(state.tab)) {
    container.innerHTML = CONTENT_SUB_TABS.map(t =>
      `<button class="content-sub-tab${state.contentSubTab === t.id ? " active" : ""}" data-subtab="${t.id}" data-group="content" type="button"><span>${escapeHtml(t.label)}</span></button>`
    ).join("");
    container.querySelectorAll(".content-sub-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.subtab;
        if (!target || target === state.contentSubTab) return;
        switchContentSubTab(target);
      });
    });
    return;
  }

  container.innerHTML = "";
}

function switchInspirationSubTab(subTab) {
  state.inspirationSubTab = subTab;
  if (subTab === "drafts") {
    setTab("drafts");
    void safeLoadCurrentTab("Не удалось загрузить черновики");
  } else if (subTab === "trends") {
    setTab("trends");
    void safeLoadCurrentTab("Не удалось загрузить тренды");
  }
}

function switchContentSubTab(subTab) {
  state.contentSubTab = subTab;
  if (subTab === "calendar") {
    state.plansSubMode = "calendar";
    setTab("plans");
    void calendarModule.loadCalendar();
  } else if (subTab === "publications") {
    state.plansSubMode = "publications";
    setTab("plans");
    void safeLoadCurrentTab("Не удалось загрузить публикации");
  } else if (subTab === "plans") {
    state.plansSubMode = "plans";
    setTab("plans");
    void safeLoadCurrentTab("Не удалось загрузить планы");
  } else if (subTab === "mentions") {
    state.plansSubMode = "mentions";
    setTab("plans");
    void safeLoadCurrentTab("Не удалось загрузить упоминания");
  } else if (subTab === "archive") {
    state.plansSubMode = "archive";
    setTab("plans");
    void safeLoadCurrentTab("Не удалось загрузить архив");
  }
}

function setTab(t) {
  clearBackgroundRefreshes();
  state.tab = t;
  document.body.dataset.tab = t;
  analytics.trackPageView(state.mode, t);
  const titleOverride = _TABS_SHOWING_INSPIRATION_SUB.has(t) ? "Вдохновение" : (_TABS_SHOWING_CONTENT_SUB.has(t) ? "Контент" : null);
  if (elements.topbarTitle) elements.topbarTitle.textContent = titleOverride || (SECTION_TITLES[t] ?? t);
  state.mobileView = "list";
  state.draftId = "";
  state.selected = null;
  state.selectedCreateTool = null;
  if (t !== "keywords" && t !== "settings") state.selectedKeywordTopicIdx = null;
  elements.settingsButton?.classList.toggle("active", state.mode === "content" && t === "settings");

  if (HANDBOOK_CATEGORY_META[t]) {
    state.lastHandbookTab = t;
    state.referenceSearch = "";
    state.referenceFilter = "";
    state.referenceFilterParent = "";
    if (state.selectedReference?.category !== HANDBOOK_CATEGORY_META[t].category) {
      state.selectedReference = null;
    }
  }

  const p = new URLSearchParams(window.location.search);
  p.set("tab", t);
  p.delete("draft_id");
  history.replaceState({}, "", `${window.location.pathname}?${p.toString()}`);

  syncMobileNavigation();
  elements.tabsContainer.querySelectorAll(".tab-button").forEach(b => {
    const isActive = b.dataset.tab === t;
    b.classList.toggle("active", isActive);
    b.setAttribute("aria-selected", String(isActive));
    if (isActive) b.scrollIntoView({ inline: "center", behavior: "smooth", block: "nearest" });
  });
  elements.filtersContainer.hidden = !["drafts", "inbox"].includes(t);
  renderContentSubTabs();

  // Clear panels immediately to prevent showing tools/content from previous tab
  if (elements.headerTabs) elements.headerTabs.innerHTML = "";
  const _navTabs = document.getElementById("topbarNavTabs");
  if (_navTabs) _navTabs.innerHTML = "";
  setEmptyState(true);
  elements.listTitle.textContent = "Загрузка...";
  // Preserve search bar in handbook tabs — renderReferences will update the count
  if (!HANDBOOK_CATEGORY_META[t]) elements.draftCount.textContent = "";
  elements.draftList.innerHTML = renderPanelLoader("Загружаю раздел");
  elements.draftDetail.innerHTML = renderDetailLoader("Загружаю раздел");

  renderContentSubTabs();
  syncMobileNavigation();
}

async function bootstrap() {
  // Allow teams module to reload current tab on team switch
  state._reloadCurrentTab = () => safeLoadCurrentTab("Не удалось загрузить вкладку");

  const sharedBlendId = new URLSearchParams(window.location.search).get("shared");
  if (sharedBlendId) {
    await bootstrapImpl();
    openSharedBlend(sharedBlendId);
    teamsModule.loadAndRenderSwitcher();
    return;
  }
  onboarding.maybeShow();
  onboarding.initHelpFab();
  await bootstrapImpl();
  teamsModule.loadAndRenderSwitcher();
}

bindBootFallbackReload();
bindStartupErrorFallbacks();
registerWindowBridge({
  state,
  setMode,
  setTab,
  loadSettings,
  renderCreate,
  renderCreateTool,
  retryCurrentTab,
  openDraft,
  openAroma,
  openReference,
  openDailyOilReference,
  copyText,
  openReels,
  refreshReelsDetail,
  openPlan,
  generateDraftFromPlan,
  openPlanRelatedDraft,
  activatePlan,
  updateDraft: updateCurrentDraft,
  sendDraftToChat,
  deleteDraft,
  saveCarouselSlideText,
  regenerateCarouselSlide,
  regenerateCarouselAll,
  selectCarouselSlideVersion,
  deleteCarouselSlideVersion,
  handleCarouselSlideNoteInput,
  previewCarouselSlide,
  carouselSwiperGoTo,
  setSlidesViewMode,
  downloadCarouselPptx,
  importCarouselPptx,
  exportToCanva,
  importFromCanva,
  selectCanvaDesign,
  saveReelsScenario,
  regenerateReelsStoryboard,
  regenerateAllReelsFrames,
  saveReelsFrameFields,
  saveReelsFramePrompt,
  saveReelsFrameNote,
  regenerateReelsFrame,
  handleReelsFramePromptInput,
  handleReelsFrameNoteInput,
  regenConcept,
  regenScenario,
  regenCaption,
  regenFrameImage,
  regenFrameImageWithPrompt,
  recoverFrameImage,
  upgradeToFull,
  generateReelsImages,
  approveReels,
  scheduleFrameOverlaySave,
  saveFrameImagePrompt,
  autoResize,
  publishReels,
  retryPlatform,
  composeReelVideo,
  uploadReelsVideo,
  cleanReelsVideo,
  splitReelsClips,
  checkAndPublish,
  copyReelsCaption,
  openReelsImageFullscreen,
  openReelsPreview,
  openBotUploadLink,
  jumpToReelsStep,
  runTechCheck,
  composeReelsVideo,
  reuploadVideo,
  proceedToPublish,
  gradePreview,
  gradeShowProfiles,
  gradeSelectProfile,
  gradeApply,
  startMontage,
  notifyWhenReady,
  approveThreadsSeries,
  regenSlot,
  regenerateSeriesPosts,
  saveThreadsSlot,
  showSlotHistory,
  scheduleThreadsSeries,
  openThreadsScheduler,
  publishThreadsSeriesNow,
  publishScheduledNow,
  retryPublication,
  saveContentReviewDraft,
  saveThreadsReviewDraft,
  polishContentDraft,
  moveDraftToTeam,
  openKeywordTopic,
  addKeywordItem,
  removeKeywordItem,
  addForbiddenPhrase,
  removeForbiddenPhrase,
  addRewrite,
  removeRewrite,
  savePlatformTone,
  saveUploadPostPrefs,
  saveImageModels,
  setTheme,
  connectPlatform,
  switchAccountsTeam,
  createNewTeam,
  createTeamInvite,
  removeTeamMember,
  activatePromo,
  generatePromos,
  selectCity,
  adminResetStuck,
  adminRestartWorker,
  goBackToSettings,
  setPlanStatusFilter,
  setPlanPlatformFilter,
  setPlanDateFilter,
  openPlanDetail,
  publishDraft,
  cancelPublishSchedule,
  goBackToList,
  renderReferences,
  setPlansSubMode,
  setContentSubMode,
  switchContentSubTab,
  openMentionDetail,
  closeMentionDetail,
  generateReplies,
  publishReply,
  ignoreMentionAction,
  setMentionsFilter,
  openArchiveDetail,
  openArchiveForm,
  savePublication,
  deletePublication,
  importFromUrl,
  toggleArchiveStats,
  setArchivePlatformFilter,
  setArchiveScore,
  bulkImportFromAccount,
  handleSmartSearch,
  runSmartSearch,
  clearSmartSearch,
  createContentFromOil,
  toggleReferenceFilters,
  openBlendConstructor,
  addRecoOilToBlend,
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
  openRecommendationsWizard,
  closeRecommendationsWizard,
  recoWizardNext,
  recoWizardBack,
  recoSelectMood,
  recoSelectGoal,
  recoUpdateSymptoms,
  recoToggleAroma,
  recoUpdateContra,
  submitRecommendations,
  _selectSchedulerDate,
  _renderThreadsSchedulerDates,
  selectTrendsPlatform,
  selectTrendsPeriod,
  refreshTrends,
  openTrendsPost,
  createFromInsight,
  addMonitoredAccount,
  removeMonitoredAccount,
  addMonitoredAccountFromSettings,
  removeMonitoredAccountFromSettings,
  addTrackedHashtag,
  removeTrackedHashtag,
  // New features (roadmap sprint 1-6)
  recommendHashtags,
  applyRecommendedHashtags,
  adaptTone,
  startRepurpose,
  saveSeriesPost,
  regenSeriesPost,
  regenSeriesAll,
  coherenceCheck,
  generateTrendCards,
  createFromTrendCard,
  refreshDraftMetrics,
  shareBlend,
  // Stock photo picker
  searchStockPhotos: (...a) => _stockPhotosMod.searchStockPhotos(...a),
  selectStockPhoto: (...a) => _stockPhotosMod.selectStockPhoto(...a),
  uploadDraftPhoto: (...a) => _stockPhotosMod.uploadDraftPhoto(...a),
});

reelsCallbacks.renderReels = () => { renderReels(); renderDraftList(); };
reelsCallbacks.renderReelsDetail = renderReelsDetail;

// ── Analytics tracking wrappers for key user actions ──
{
  const _origOpenDraft = window.openDraft;
  window.openDraft = (...args) => {
    analytics.track("draft_open", "content", { draft_id: args[0] });
    return _origOpenDraft(...args);
  };
  const _origOpenReference = window.openReference;
  window.openReference = (...args) => {
    analytics.track("card_view", "reference", { slug: args[0], category: args[1] });
    return _origOpenReference(...args);
  };
  const _origPublishDraft = window.publishDraft;
  window.publishDraft = (...args) => {
    analytics.track("publish", "content", { draft_id: args[0] });
    return _origPublishDraft(...args);
  };
  const _origRunSmartSearch = window.runSmartSearch;
  window.runSmartSearch = (...args) => {
    analytics.track("search", "navigation", { query: state.referenceSearch });
    return _origRunSmartSearch(...args);
  };
  const _origSubmitBlendConstructor = window.submitBlendConstructor;
  window.submitBlendConstructor = (...args) => {
    analytics.track("blend_action", "reference", { action: "submit" });
    return _origSubmitBlendConstructor(...args);
  };
  const _origRenderCreateTool = window.renderCreateTool;
  window.renderCreateTool = (...args) => {
    analytics.track("draft_create", "content", { kind: args[0] });
    return _origRenderCreateTool(...args);
  };
}

// Auto-resize for textareas is handled by shell.js bindTextareaAutoExpand()
function refreshIcons() { /* Phosphor icons are CSS-based, no initialization needed */ }

bootstrap()
  .then(() => {
    refreshIcons();
    initScrollFade(elements.draftList);
  })
  .catch((err) => {
    console.error("bootstrap failed", err);
    document.body.classList.add("app-ready");
  });

