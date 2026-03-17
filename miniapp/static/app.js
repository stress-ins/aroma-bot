import { registerWindowBridge } from "./js/bridge.js";
import { createCarouselModule } from "./js/carousel.js";
import { createContentModule } from "./js/content.js";
import { createCoreModule } from "./js/core.js";
import { createCreateModule } from "./js/create.js";
import { createDraftsModule } from "./js/drafts.js";
import { createPublishModule } from "./js/publish.js";
import { createScheduleModule } from "./js/schedule.js";
import { createPlansModule } from "./js/plans.js";
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
  mentions: [],
  mentionsFilter: { platform: "all", status: "pending" },
};

const MODE_TABS = {
  content: [
    { id: "create", label: "Создать" },
    { id: "inbox", label: "Согласование" },
    { id: "drafts", label: "Черновики" },
    { id: "plans", label: "Планы" },
    { id: "reels", label: "Рилсы" },
    { id: "schedule", label: "Расписание" },
    { id: "keywords", label: "Ключи" },
    { id: "status", label: "Статус" },
  ],
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
let bootstrapWatchdogTimer = null;
let appBootstrapped = false;
let startupLoadInFlight = false;
let uiNoticeTimer = null;
const carouselNoteSaveTimers = {};
const reelsNoteSaveTimers = {};
const reelsPromptSaveTimers = {};

// Forward-declared module functions — assigned during module initialization below
let loadInbox, loadReels, loadKeywords, loadSettings;
let renderCreate, renderCreateTool;
let renderDraftList, openDraft, openReels, renderDraftDetail, renderEmptyDetail;
let renderInbox, renderStatus, renderPlans, renderReels, renderReelsDetail, renderKeywords;
let addRewrite, removeRewrite, savePlatformTone, saveUploadPostPrefs, saveImageModels, connectPlatform;
let addKeywordItem, removeKeywordItem, openKeywordTopic;
let addForbiddenPhrase, removeForbiddenPhrase;
let saveContentReviewDraft, saveThreadsReviewDraft, polishContentDraft, refreshDraftMetrics;
let loadCurrentTab, safeLoadCurrentTab, retryCurrentTab;
let publishDraft, cancelPublishSchedule, loadPublishStatus;
let openPendingReelsCreation, finalizePendingReelsCreation, recoverPendingReelsCreation;
let refreshReelsDetail;

const elements = {
  tabsContainer: document.getElementById("tabsContainer"),
  filtersContainer: document.getElementById("filtersContainer"),
  listPanel: document.getElementById("listPanel"),
  detailPanel: document.getElementById("detailPanel"),
  draftList: document.getElementById("draftList"),
  draftDetail: document.getElementById("draftDetail"),
  draftCount: document.getElementById("draftCount"),
  listTitle: document.getElementById("listTitle"),
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
  topbarTitle: document.querySelector(".topbar-title"),
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
  instagram: "Инстаграм",
  telegram: "Телеграм",
  reels: "Рилсы",
  reels_v2: "Рилсы",
  carousel: "Карусель",
};

const RU_STATUS_LABELS = {
  draft: "Черновик",
  in_review: "На согласовании",
  approved: "Согласовано",
  rejected: "Не согласовано",
  published: "Опубликовано",
  scheduled: "Запланировано",
};

const RU_FEEDBACK_LABELS = {
  worked: "Сработало",
  missed: "Не сработало",
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
    method:  { label: "Метод",   icon: "🛠️" },
    founder: { label: "Автор",   icon: "👤" },
    system:  { label: "Система", icon: "🧬" },
    chakra:  { label: "Чакра",   icon: "🔮" },
    energy:  { label: "Энергия", icon: "✨" },
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
    const block = `<div class="code-block"><pre>${escaped}</pre><button class="copy-btn" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent).then(()=>{this.innerHTML='${icon("check", 13)}';setTimeout(()=>this.textContent='Копировать',1200)})">Копировать</button></div>`;
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
  return `<i data-lucide="${name}" width="${size}" height="${size}" stroke-width="1.75" style="display:block;flex-shrink:0"></i>`;
}

function uiIcon(name) {
  const LUCIDE_MAP = {
    card:       "file-text",
    slides:     "layout-grid",
    prompt:     "square-terminal",
    regenerate: "rotate-ccw",
    chat:       "message-square",
    pptx:       "presentation",
    note:       "pencil-line",
    reject:     "x",
    close:      "x",
    "x":        "x",
    trash:      "trash-2",
    back:       "chevron-left",
    gear:       "settings-2",
    eye:        "eye",
    approve:    "check",
    sparkle:    "sparkles",
    text:       "align-left",
    nps:        "heart",
    therapy:    "cross",
    psyche:     "brain",
    plus:       "plus",
    minus:      "minus",
    history:    "clock",
    passport:   "file-text",
    reel:       "play",
    image:      "image",
    download:   "download",
    upload:     "upload",
    sunrise:    "sunrise",
    sun:        "sun",
    moon:       "moon",
    threads:    "at-sign",
    instagram:  "instagram",
    telegram:   "send",
    plan:       "calendar-days",
    play:       "play",
    layers:     "layers",
    loader:     "loader-circle",
    calendar:   "calendar-days",
    link:       "link",
    "external-link": "external-link",
    "message-circle": "message-circle",
    camera:     "camera",
    "check-circle": "check-circle",
  };
  return `<span class="ui-icon ui-icon-${escapeHtml(name)}">${icon(LUCIDE_MAP[name] || "square-terminal", 16)}</span>`;
}

function sectionHeadingIcon(title) {
  const iconMap = {
    "Превью": "card",
    "Угол": "sparkle",
    "Текст": "text",
    "CTA": "chat",
    "Паспорт карточки": "passport",
    "Паспорт аромата": "passport",
    "О концепции": "sparkle",
    "О практике": "passport",
    "Описание": "card",
    "Какие вопросы поднимает": "prompt",
    "Действие на НПС": "nps",
    "Терапевтические свойства": "therapy",
    "Психологические свойства": "psyche",
    'Ресурс "+"': "plus",
    'Ресурс "-"': "minus",
    "Исторические сведения": "history",
    "Промпт для изображения": "prompt",
    "Сценарий": "play",
    "Кадры и промпты": "layers",
  };
  return uiIcon(iconMap[title] || "card");
}

function actionLabel(icon, text) {
  return `${uiIcon(icon)}<span>${escapeHtml(text)}</span>`;
}

function tagMarkup(label, tone = "neutral") {
  const safeTone = String(tone || "neutral")
    .replace(/[^a-z0-9_-]/gi, "")
    .toLowerCase();
  if (safeTone === "pending") {
    return `<span class="tag tag-pending">${escapeHtml(label)}</span>`;
  }
  return `<span class="tag tag-${safeTone}">${escapeHtml(label)}</span>`;
}

function contentKindIcon(kind) {
  const iconMap = {
    content:        "note",
    threads:        "note",
    threads_series: "note",
    plan:           "plan",
    reels:          "play",
    carousel:       "layers",
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
        onclick='togglePromptDisclosure(${JSON.stringify(key)}, this)'
      >${actionLabel("eye", isOpen ? closeLabel : openLabel)}</button>
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
    button.innerHTML = actionLabel("eye", nextOpen ? closeLabel : openLabel);
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
          <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(String(prompt))})'>${actionLabel("prompt", copyLabel)}</button>
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
    notice.innerHTML = `<div class="slot-history-modal"><h3>История ${escapeHtml(label)}</h3>${listHtml}<button class="primary-button" onclick="this.closest('.slot-history-overlay').remove()">Закрыть</button></div>`;
    document.body.appendChild(notice);
  }
}

async function scheduleThreadsSeries(draftId, date, slots, btn) {
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
      setTab("plans");
      await safeLoadCurrentTab();
    }
  }, "Запланировано");
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
    return `<button class="date-picker-btn" type="button" data-date="${iso}" onclick="_selectSchedulerDate('${draftId}', '${iso}', this)">${escapeHtml(label)}</button>`;
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
    if (state.selectedReels?.draft_id === draftId) state.selectedReels = null;
    renderReels();
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
  if (normalized === "/miniapp") return "Mini App";
  return String(value || "");
}

function draftHeroSummary(draft, payload, mainText) {
  const preview = stripMarkdown(draft.preview || mainText || "");
  if (preview) return preview.slice(0, 180);
  if (payload?.angle) return `Опорный angle: ${String(payload.angle).trim()}`;
  if (payload?.hook) return `Главный hook: ${String(payload.hook).trim()}`;
  return "Материал готов к редакторскому проходу и согласованию.";
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
  bindSwipeBack,
  bindBottomTabBar,
} = createShellModule({
  state,
  elements,
  uiIcon,
  setMode,
  setTab,
  safeLoadCurrentTab,
  HANDBOOK_CATEGORY_META,
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
  getInitDataHeaders: () => {
    const initData = window.Telegram?.WebApp?.initData;
    return initData ? { "X-Telegram-Init-Data": initData } : {};
  },
  getCurrentDraftId: () => state.draftId || state.selectedReels?.draft_id || "",
  timers: {
    getUiNotice: () => uiNoticeTimer,
    setUiNotice: (value) => { uiNoticeTimer = value; },
  },
  callbacks: coreCallbacks,
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
  filtersToQueryString,
  initDataHeaders,
  scheduleReelsRefresh,
  scheduleCarouselRefresh,
  loadDrafts,
} = createSessionModule({
  state,
  elements,
  timers: {
    getReelRefresh: () => reelRefreshTimer,
    setReelRefresh: (value) => { reelRefreshTimer = value; },
    getCarouselRefresh: () => carouselRefreshTimer,
    setCarouselRefresh: (value) => { carouselRefreshTimer = value; },
  },
  fetchJson,
  renderDraftList: () => renderDraftList(),
  renderDraftDetail: (draft) => renderDraftDetail(draft),
  renderReels: () => renderReels(),
  renderReelsDetail: (draft) => renderReelsDetail(draft),
  renderEmptyDetail: () => renderEmptyDetail(),
  renderDetailError,
  hasPendingCarouselOperations: (draftId) => hasPendingCarouselOperations(draftId),
  isEditingDetailForm,
  syncMobileNavigation,
  enterDetailView,
  openDraft: (draftId) => openDraft(draftId),
  scheduleReelsDetailRefresh: (draftId) => sessionCallbacks.refreshReelsDetail(draftId),
});

const {
  bufferedCarouselNote,
  hasPendingCarouselOperations,
  renderSlides,
  saveCarouselSlideText,
  handleCarouselSlideNoteInput,
  regenerateCarouselSlide,
  regenerateCarouselAll,
  selectCarouselSlideVersion,
  deleteCarouselSlideVersion,
  previewCarouselSlide,
  carouselSwiperGoTo,
  downloadCarouselPptx,
  importCarouselPptx,
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
  confirmAction,
  authQueryString,
  initDataHeaders,
  isCurrentDraftDetail,
  isPromptDisclosureOpen,
  mergeDraftIntoState,
  renderDraftList,
  renderDraftDetail,
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
});
renderPlans = renderPlansImpl;

// ── Mentions module ──────────────────────────────────────────────────────────

const mentionsModule = createMentionsModule({
  state,
  elements: { plansContainer: null },
  fetchJson,
  escapeHtml,
  withButtonFeedback,
});

window.mentionsModule = mentionsModule;

function setPlansSubMode(mode) {
  state.plansSubMode = mode;
  if (mode === "mentions") state.selectedMention = null;
  renderPlans();
}

function openMentionDetail(mentionId) { mentionsModule.openMentionDetail(mentionId); }
function closeMentionDetail() { mentionsModule.closeMentionDetail(); }
function generateReplies(mentionId, btn) { return mentionsModule.generateReplies(mentionId, btn); }
function publishReply(mentionId, replyId, btn) { return mentionsModule.publishReply(mentionId, replyId, btn); }
function ignoreMentionAction(mentionId, btn) { return mentionsModule.ignoreMentionAction(mentionId, btn); }
function setMentionsFilter(key, value) { mentionsModule.setMentionsFilter(key, value); }

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
  generateReelsImages,
  approveReels,
  scheduleFrameOverlaySave,
  saveFrameImagePrompt,
  autoResize,
  // Phase 4 functions:
  publishReels,
  retryPlatform,
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
  callbacks: reelsCallbacks,
});

async function loadStatus() {
  state.status = await fetchJson("/api/status");
  renderStatus();
}

async function loadPlans() {
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
  renderReferences,
  renderReferencesLocked,
  renderReferencesUnavailable,
  openAroma,
  renderAromas,
  renderAromasLocked,
  handleSmartSearch,
  runSmartSearch,
  clearSmartSearch,
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
} = createBlendConstructorModule({
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

({
  saveContentReviewDraft,
  saveThreadsReviewDraft,
  polishContentDraft,
  renderDraftList,
  openDraft,
  renderDraftDetail,
  renderEmptyDetail,
  refreshDraftMetrics,
} = createDraftsModule({
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
  setEmptyState,
  enterDetailView,
  syncMobileNavigation,
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
});
const { renderBrand: renderBrandImpl, loadForbiddenPhrases: loadForbiddenPhrasesImpl, loadPolicy: loadPolicyImpl, renderAccounts: renderAccountsImpl } = _settingsMod;
({
  addKeywordItem, removeKeywordItem, openKeywordTopic,
  loadKeywords, loadSettings,
  renderStatus, renderKeywords,
  addForbiddenPhrase, removeForbiddenPhrase,
  addRewrite, removeRewrite, savePlatformTone, saveUploadPostPrefs,
  saveImageModels,
  connectPlatform,
} = _settingsMod);

({
  renderCreate, renderCreateTool,
} = createCreateModule({
  state,
  elements,
  uiIcon,
  interactiveCardAttrs,
  contentKindIcon,
  renderGuidedState,
  renderBackButton,
  setEmptyState,
  syncMobileNavigation,
  enterDetailView,
  fetchJson,
  showRequestError,
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
  renderCreate,
  showBootFallback,
  hideBootFallback,
  showRuntimeWarning,
  renderPanelLoader,
});
const { bindBootFallbackReload, bindStartupErrorFallbacks, bootstrap: bootstrapImpl } = _runtimeMod;
({ loadCurrentTab, safeLoadCurrentTab, retryCurrentTab } = _runtimeMod);

const onboarding = createOnboardingModule({ state, icon });

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
  callbacks: {
    renderReelsDetailMarkup,
  },
}));

sessionCallbacks.refreshReelsDetail = refreshReelsDetail;

function setMode(m) {
  clearBackgroundRefreshes();
  state.mode = m;
  document.body.dataset.mode = m;
  elements.modeContent.classList.toggle("active", m === "content");
  elements.modeHandbook.classList.toggle("active", m === "handbook");
  elements.settingsButton?.classList.toggle("active", m === "content" && state.tab === "settings");
  const tabs = MODE_TABS[m] || [];
  elements.tabsContainer.innerHTML = tabs.map((t) => {
    const label = HANDBOOK_CATEGORY_META[t.id]
      ? `${handbookCategoryIcon(t.id)}<span>${escapeHtml(t.label)}</span>`
      : `<span>${escapeHtml(t.label)}</span>`;
    return `<button class="tab-button${state.tab === t.id ? " active" : ""}" data-tab="${t.id}" type="button">${label}</button>`;
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
  if (!(m === "content" && state.tab === "settings") && !tabs.find(t => t.id === state.tab)) setTab(tabs[0].id);
  syncMobileNavigation();
}

const SECTION_TITLES = {
  drafts: "Черновики", reels: "Рилсы", plans: "Планы",
  create: "Создать", settings: "Настройки",
  aromas: "Ароматы", concepts: "Концепции", practices: "Практики", sounds: "Звуки",
  blends: "Смеси", symptoms: "Симптомы",
};

function setTab(t) {
  clearBackgroundRefreshes();
  state.tab = t;
  document.body.dataset.tab = t;
  if (elements.topbarTitle) elements.topbarTitle.textContent = SECTION_TITLES[t] ?? t;
  state.mobileView = "list";
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
  elements.tabsContainer.querySelectorAll(".tab-button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
  elements.filtersContainer.hidden = !["drafts", "inbox"].includes(t);
  
  // Clear panels immediately to prevent showing tools/content from previous tab
  setEmptyState(true);
  elements.listTitle.textContent = "Загрузка...";
  elements.draftCount.textContent = "";
  elements.draftList.innerHTML = renderPanelLoader("Загружаю раздел");
  elements.draftDetail.innerHTML = renderDetailLoader("Загружаю раздел");
  
  syncMobileNavigation();
}

async function bootstrap() {
  const sharedBlendId = new URLSearchParams(window.location.search).get("shared");
  if (sharedBlendId) {
    await bootstrapImpl();
    openSharedBlend(sharedBlendId);
    return;
  }
  onboarding.maybeShow();
  onboarding.initHelpFab();
  return bootstrapImpl();
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
  copyText,
  openReels,
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
  downloadCarouselPptx,
  importCarouselPptx,
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
  generateReelsImages,
  approveReels,
  scheduleFrameOverlaySave,
  saveFrameImagePrompt,
  autoResize,
  publishReels,
  retryPlatform,
  approveThreadsSeries,
  regenSlot,
  saveThreadsSlot,
  showSlotHistory,
  scheduleThreadsSeries,
  openThreadsScheduler,
  saveContentReviewDraft,
  saveThreadsReviewDraft,
  polishContentDraft,
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
  connectPlatform,
  setPlanStatusFilter,
  setPlanPlatformFilter,
  setPlanDateFilter,
  openPlanDetail,
  publishDraft,
  cancelPublishSchedule,
  goBackToList,
  renderReferences,
  setPlansSubMode,
  openMentionDetail,
  closeMentionDetail,
  generateReplies,
  publishReply,
  ignoreMentionAction,
  setMentionsFilter,
  handleSmartSearch,
  runSmartSearch,
  clearSmartSearch,
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
});

reelsCallbacks.renderReels = renderReels;
reelsCallbacks.renderReelsDetail = renderReelsDetail;

// Auto-resize .prompt-note-field textareas so content fits without inner scroll
document.addEventListener("input", (e) => {
  if (e.target.matches(".prompt-note-field textarea")) {
    const el = e.target;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }
});
document.addEventListener("click", () => {
  requestAnimationFrame(() => {
    document.querySelectorAll(".prompt-note-field textarea").forEach((el) => {
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    });
  });
});
function refreshIcons() { if (window.lucide) lucide.createIcons(); }

bootstrap().then(() => refreshIcons());

if (window.lucide) {
  const _lcObs = new MutationObserver((mutations) => {
    const hasNewIcons = mutations.some(m =>
      [...m.addedNodes].some(n =>
        n.nodeType === 1 && (n.matches?.("[data-lucide]") || n.querySelector?.("[data-lucide]"))
      )
    );
    if (hasNewIcons) lucide.createIcons();
  });
  _lcObs.observe(document.getElementById("app") || document.body, { childList: true, subtree: true });
}
