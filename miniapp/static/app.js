import { createCarouselModule } from "./js/carousel.js";
import { createContentModule } from "./js/content.js";
import { createCreateModule } from "./js/create.js";
import { createDraftsModule } from "./js/drafts.js";
import { createPlansModule } from "./js/plans.js";
import { createReferencesModule } from "./js/references.js";
import { createReelsModule } from "./js/reels.js";
import { createRuntimeModule } from "./js/runtime.js";
import { createSettingsModule } from "./js/settings.js";
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
  pendingCarouselNotes: {},
  pendingCarouselOps: {},
  pendingReelsNotes: {},
  pendingReelsPrompts: {},
};

const MODE_TABS = {
  content: [
    { id: "create", label: "Создать" },
    { id: "inbox", label: "Согласование" },
    { id: "drafts", label: "Черновики" },
    { id: "plans", label: "Планы" },
    { id: "reels", label: "Рилсы" },
    { id: "keywords", label: "Ключи" },
    { id: "status", label: "Статус" },
  ],
  handbook: [
    { id: "aromas", label: "Ароматы" },
    { id: "concepts", label: "Теория" },
    { id: "practices", label: "Практики" },
    { id: "sounds", label: "Звуки" },
  ],
};

let reelRefreshTimer = null;
let carouselRefreshTimer = null;
let bootstrapWatchdogTimer = null;
let appBootstrapped = false;
let startupLoadInFlight = false;
let uiNoticeTimer = null;
const carouselNoteSaveTimers = {};
const reelsNoteSaveTimers = {};
const reelsPromptSaveTimers = {};

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
};

const RU_KIND_LABELS = {
  threads: "Тредс",
  instagram: "Инстаграм",
  telegram: "Телеграм",
  reels: "Рилсы",
  carousel: "Карусель",
};

const RU_STATUS_LABELS = {
  draft: "Черновик",
  in_review: "На согласовании",
  approved: "Согласовано",
  rejected: "Не согласовано",
  published: "Опубликовано",
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
};

function handbookCategoryIcon(tabId) {
  const glyphMap = {
    aromas: "🌿",
    concepts: "🧭",
    practices: "🫁",
    sounds: "🔔",
  };
  const glyph = glyphMap[String(tabId || "").toLowerCase()] || "•";
  return `<span class="kind-glyph handbook-glyph" aria-hidden="true">${glyph}</span>`;
}

function handbookCardBadge(tabId, item = {}) {
  const sourceType = String(item.source_type || "").trim();
  if (tabId === "aromas" && sourceType) return sourceType;
  if (tabId === "concepts") {
    return conceptTypeMeta(sourceType).label;
  }
  if (tabId === "practices") return "Практика";
  if (tabId === "sounds") return "Звук";
  return "";
}

function conceptTypeMeta(sourceType) {
  const metaMap = {
    method: { label: "Метод", icon: "◌" },
    founder: { label: "Автор", icon: "◍" },
    system: { label: "Система", icon: "◎" },
    chakra: { label: "Чакра", icon: "✦" },
    energy: { label: "Энергия", icon: "≈" },
  };
  return metaMap[String(sourceType || "").trim()] || { label: "Теория", icon: "•" };
}

function formatCourseSourceLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const match = part.match(/^rudn_olfactotherapy_(.+)$/);
      if (!match) return part;
      return `PDF ${match[1].replaceAll("_", ".")}`;
    })
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
  const lines = source.split(/\r?\n/);
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
  return chunks.join("");
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

function uiIcon(name) {
  const icons = {
    card: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2"></rect><path d="M8 9h8M8 13h5"></path></svg>`,
    slides: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="M8 9h8M8 13h6"></path></svg>`,
    prompt: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 8h10M7 12h8M7 16h6"></path><path d="M5 5h14v14H5z"></path></svg>`,
    regenerate: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v6h-6"></path><path d="M20 12a8 8 0 1 1-2.3-5.7L20 8"></path></svg>`,
    chat: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14v9H9l-4 3V7Z"></path></svg>`,
    pptx: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4h7l5 5v11H7z"></path><path d="M14 4v5h5"></path></svg>`,
    note: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 17.5V20h2.5L18 10.5 15.5 8 6 17.5Z"></path><path d="M14.5 9l2.5 2.5"></path></svg>`,
    reject: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10"></path><path d="M17 7 7 17"></path></svg>`,
    trash: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"></path><path d="M9 7V5h6v2"></path><path d="M7 7l1 12h8l1-12"></path><path d="M10 11v5M14 11v5"></path></svg>`,
    back: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"></path></svg>`,
    gear: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v3"></path><path d="M12 18v3"></path><path d="m4.9 4.9 2.1 2.1"></path><path d="m17 17 2.1 2.1"></path><path d="M3 12h3"></path><path d="M18 12h3"></path><path d="m4.9 19.1 2.1-2.1"></path><path d="m17 7 2.1-2.1"></path><circle cx="12" cy="12" r="3.5"></circle></svg>`,
    eye: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
    approve: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5 9 16l10-10"></path></svg>`,
    sparkle: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7L12 3Z"></path><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"></path></svg>`,
    text: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M12 7v10M8 17h8"></path></svg>`,
    nps: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-6-4.35-6-10a3.5 3.5 0 0 1 6-2.4A3.5 3.5 0 0 1 18 11c0 5.65-6 10-6 10Z"></path></svg>`,
    therapy: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v16M4 12h16"></path></svg>`,
    psyche: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4a6 6 0 0 1 6 6c0 3-2 4-3 5s-1 2-1 3h-4c0-1-1-2-1-3s-3-2-3-5a6 6 0 0 1 6-6Z"></path><path d="M10 21h4"></path></svg>`,
    plus: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 6v12M6 12h12"></path></svg>`,
    minus: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12"></path></svg>`,
    history: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.3-5.7L4 9"></path><path d="M12 8v5l3 2"></path></svg>`,
    passport: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="4" width="12" height="16" rx="2"></rect><path d="M9 8h6M9 12h6M9 16h4"></path></svg>`,
    reel: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="6" width="16" height="12" rx="2"></rect><path d="M8 6v12M16 6v12"></path></svg>`,
    image: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="m8 14 2.5-2.5L13 14l2-2 3 3"></path><circle cx="9" cy="9" r="1.2"></circle></svg>`,
  };
  return `<span class="ui-icon ui-icon-${escapeHtml(name)}">${icons[name] || icons.prompt}</span>`;
}

function sectionHeadingIcon(title) {
  const iconMap = {
    "Превью": "card",
    "Угол": "sparkle",
    "Текст": "text",
    "CTA": "chat",
    "Паспорт карточки": "passport",
    "Описание": "card",
    "Какие вопросы поднимает": "prompt",
    "Действие на НПС": "nps",
    "Терапевтические свойства": "therapy",
    "Психологические свойства": "psyche",
    'Ресурс "+"': "plus",
    'Ресурс "-"': "minus",
    "Исторические сведения": "history",
    "Промпт для изображения": "prompt",
    "Сценарий": "reel",
    "Кадры и промпты": "slides",
  };
  return uiIcon(iconMap[title] || "card");
}

function actionLabel(icon, text) {
  return `${uiIcon(icon)}<span>${escapeHtml(text)}</span>`;
}

function interactiveCardAttrs(label) {
  return `role="button" tabindex="0" aria-label="${escapeHtml(label)}"`;
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
  const glyphMap = {
    content: "✍️",
    plan: "🗓️",
    reels: "🎬",
    carousel: "🖼️",
    threads: "✍️",
    instagram: "📸",
    telegram: "✈️",
  };
  const normalized = String(kind || "").toLowerCase();
  const glyph = glyphMap[normalized] || "•";
  return `<span class="kind-glyph kind-glyph-${escapeHtml(normalized)}" aria-hidden="true">${glyph}</span>`;
}

function promptSection(title, prompt, copyLabel = "Скопировать промпт") {
  if (!prompt) return "";
  return `
    <section class="section">
      <h3>${uiIcon("prompt")}${escapeHtml(title)}</h3>
      <details class="prompt-disclosure">
        <summary class="secondary-button prompt-toggle">${actionLabel("eye", "Показать промпт")}</summary>
        <div class="prompt-card">
          <div class="detail-preview prompt-preview">${escapeHtml(prompt)}</div>
          <div class="actions-row prompt-actions">
            <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(String(prompt))})'>${actionLabel("prompt", copyLabel)}</button>
          </div>
        </div>
      </details>
    </section>
  `;
}

function renderDetailLoader(label = "Открываю карточку", subtitle = "Подгружаю данные и собираю экран.", extraClass = "") {
  return `
    <div class="detail-loader-card${extraClass ? ` ${escapeHtml(extraClass)}` : ""}" aria-live="polite">
      <div class="brand-loader" aria-hidden="true">
        <span class="brand-loader-ring"></span>
        <span class="brand-loader-letter">A</span>
      </div>
      <div class="detail-loader-copy">
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(subtitle)}</span>
      </div>
    </div>
  `;
}

function renderPanelLoader(label = "Загружаю данные") {
  return `
    <div class="detail-loader-card panel-loader-card" aria-live="polite">
      <div class="brand-loader" aria-hidden="true">
        <span class="brand-loader-ring"></span>
        <span class="brand-loader-letter">A</span>
      </div>
      <div class="detail-loader-copy">
        <strong>${escapeHtml(label)}</strong>
        <span>Собираю и обновляю содержимое раздела.</span>
      </div>
    </div>
  `;
}

function renderPanelError(title, message) {
  return `
    <div class="boot-fallback boot-fallback-inline is-error">
      <div class="boot-fallback-copy">
        <p class="eyebrow">Нужна повторная попытка</p>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(message)}</p>
      </div>
      <button class="secondary-button" type="button" onclick="retryCurrentTab()">Повторить</button>
    </div>
  `;
}

function renderGuidedState({
  eyebrow = "Следующий шаг",
  title,
  body = "",
  actionLabel = "",
  action = "",
  tone = "soft",
} = {}) {
  return `
    <div class="guided-state tone-${escapeHtml(tone)}">
      <div class="guided-state-copy">
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h3>${escapeHtml(title || "Пока ничего не выбрано")}</h3>
        ${body ? `<p>${escapeHtml(body)}</p>` : ""}
      </div>
      ${actionLabel && action ? `<div class="guided-state-actions"><button class="secondary-button" type="button" onclick="${action}">${escapeHtml(actionLabel)}</button></div>` : ""}
    </div>
  `;
}

function showUiNotice(message, tone = "info") {
  let notice = document.getElementById("uiNotice");
  if (!notice) {
    notice = document.createElement("div");
    notice.id = "uiNotice";
    notice.className = "ui-notice";
    document.body.appendChild(notice);
  }
  notice.textContent = String(message || "");
  notice.className = `ui-notice is-visible tone-${tone}`;
  window.clearTimeout(uiNoticeTimer);
  uiNoticeTimer = window.setTimeout(() => {
    notice.classList.remove("is-visible");
  }, 2400);
}

function renderDetailError(title, message, retryAction = "retryCurrentTab()") {
  return `
    <div class="detail-grid">
      ${renderBackButton()}
      <div class="boot-fallback boot-fallback-inline is-error">
        <div class="boot-fallback-copy">
          <p class="eyebrow">Нужна повторная попытка</p>
          <h2>${escapeHtml(title)}</h2>
          <p>${escapeHtml(message)}</p>
        </div>
        <button class="secondary-button" type="button" onclick="${retryAction}">Повторить</button>
      </div>
    </div>
  `;
}

function draftSummaryFromDraft(draft) {
  if (!draft) return null;
  return {
    draft_id: draft.draft_id,
    kind: draft.kind,
    topic: draft.topic,
    source: draft.source,
    created_at: draft.created_at,
    status: draft.status,
    feedback: draft.feedback || "",
    preview: draft.preview || "",
    slides_count: draft.slides_count || 0,
    storyboard_count: draft.storyboard_count || 0,
    images_ready: draft.images_ready || 0,
    generation_pending: Boolean(draft.generation_pending),
  };
}

function upsertDraftSummary(summary) {
  if (!summary?.draft_id) return;
  state.drafts = [
    summary,
    ...state.drafts.filter((item) => item.draft_id !== summary.draft_id),
  ];
}

function draftGenerationLabel(draft) {
  if (!draft?.generation_pending) return "";
  if (draft.kind === "carousel") {
    const total = Number(draft.slides_count || 0);
    const ready = Number(draft.images_ready || 0);
    return total ? `Ещё генерируется ${ready}/${total}` : "Ещё генерируется";
  }
  if (draft.kind === "reels") {
    const total = Number(draft.storyboard_count || 0);
    const ready = Number(draft.images_ready || 0);
    return total ? `Ещё генерируется ${ready}/${total}` : "Ещё генерируется";
  }
  return "Ещё генерируется";
}

function generationStateMarkup(item, kind = "draft") {
  if (!item?.generation_pending) return "";
  const stage = String(item.generation_stage || "").trim();
  const message = String(item.generation_message || "").trim();
  const title = kind === "reels"
    ? (stage === "scenario" ? "Собираю сценарий и раскадровку" : stage === "images" ? "Генерирую кадры" : "Собираю рилс")
    : (stage === "slides" ? "Собираю структуру карусели" : stage === "images" ? "Генерирую картинки" : "Собираю карточку");
  return `
    <section class="section section-accent">
      <div class="section-heading">
        <h3>${uiIcon("sparkle")}${escapeHtml(title)}</h3>
        <p>${escapeHtml(message || "Подождите ещё немного, мы обновим карточку автоматически.")}</p>
      </div>
      ${renderDetailLoader(title, message || "Подождите ещё немного, данные догружаются.", "detail-loader-card-compact")}
    </section>
  `;
}

function isPendingDraftId(value) {
  return String(value || "").startsWith("pending-");
}

function buildPendingDraft(kind, topic) {
  const draftId = `pending-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  return {
    draft_id: draftId,
    kind,
    topic,
    source: "/miniapp",
    created_at: new Date().toISOString(),
    status: "draft",
    feedback: "",
    preview: "Генерируем черновик...",
    slides_count: kind === "carousel" ? 5 : 0,
    storyboard_count: kind === "reels" ? 4 : 0,
    images_ready: 0,
    generation_pending: true,
    payload: {},
  };
}

function openPendingDraftCreation(kind, topic) {
  const draft = buildPendingDraft(kind, topic);
  state.pendingCreateRecovery = {
    draft_id: draft.draft_id,
    kind,
    topic,
    started_at: Date.now(),
  };
  state.draftId = draft.draft_id;
  state.selected = draft;
  setTab("drafts");
  upsertDraftSummary(draftSummaryFromDraft(draft));
  renderDraftList();
  renderDraftDetail(draft);
  enterDetailView();
  return draft;
}

function finalizePendingDraftCreation(draft) {
  const d = draft;
  if (!d?.draft_id) return;
  state.pendingCreateRecovery = null;
  state.draftId = d.draft_id;
  state.selected = d;
  state.drafts = state.drafts.filter((item) => !isPendingDraftId(item.draft_id));
  upsertDraftSummary(draftSummaryFromDraft(d));
  renderDraftList();
  renderDraftDetail(d);
  enterDetailView();
  void loadDrafts();
}

async function recoverPendingDraftCreation(kind, topic, pendingDraftId) {
  const startedAt = Date.now();
  state.pendingCreateRecovery = {
    draft_id: pendingDraftId,
    kind,
    topic,
    started_at: startedAt,
  };
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      const params = new URLSearchParams();
      params.set("limit", "20");
      params.set("kind", kind);
      const data = await fetchJson(`/api/drafts?${params.toString()}`, { timeout: 20000 });
      state.drafts = (data.items || []).filter((item) => item.draft_id !== pendingDraftId);
      const recovered = state.drafts.find((item) => {
        const createdAt = new Date(item.created_at || 0).getTime();
        return item.kind === kind
          && item.topic === topic
          && item.source === "/miniapp"
          && (Number.isNaN(createdAt) || createdAt >= startedAt - 10_000);
      });
      if (recovered?.draft_id) {
        state.pendingCreateRecovery = null;
        state.draftId = recovered.draft_id;
        renderDraftList();
        await openDraft(recovered.draft_id);
        return true;
      }
      renderDraftList();
    } catch (_error) {
      // Keep pending UI visible while the backend finishes creating the draft.
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
  elements.draftDetail.innerHTML = renderDetailError(
    "Черновик создаётся дольше обычного",
    "Мы продолжаем ждать создание карточки. Откройте Черновики ещё раз или повторите позже.",
    "retryCurrentTab()",
  );
  syncMobileNavigation();
  return false;
}

function isContentReviewKind(kind) {
  const normalized = String(kind || "").trim().toLowerCase();
  return normalized === "threads" || normalized === "instagram" || normalized === "telegram";
}

function frameDraftKey(draftId, index) {
  return `${draftId}:${index}`;
}

function mergeDraftIntoState(draft) {
  if (!draft?.draft_id) return;
  state.selected = draft;
  state.draftId = draft.draft_id;
  state.drafts = state.drafts.map((item) => item.draft_id === draft.draft_id ? { ...item, ...draft } : item);
}

function mergeReelsIntoState(draft) {
  if (!draft?.draft_id) return;
  state.selectedReels = draft;
  state.reels = state.reels.map((item) => item.draft_id === draft.draft_id ? { ...item, ...draft } : item);
}

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
  downloadCarouselPptx,
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
  authQueryString: _authQueryString,
  isCurrentDraftDetail,
  mergeDraftIntoState,
  renderDraftList,
  renderDraftDetail,
  scheduleCarouselRefresh,
});

function clearBackgroundRefreshes() {
  window.clearTimeout(reelRefreshTimer);
  window.clearTimeout(carouselRefreshTimer);
  reelRefreshTimer = null;
  carouselRefreshTimer = null;
}

function isCurrentDraftDetail(draftId) {
  return state.mode === "content" && state.tab === "drafts" && state.mobileView === "detail" && state.draftId === draftId;
}

function isCurrentReelsDetail(draftId) {
  return state.mode === "content" && state.tab === "reels" && state.mobileView === "detail" && state.selectedReels?.draft_id === draftId;
}

function _authQueryString() {
  const initData = window.Telegram?.WebApp?.initData;
  if (!initData) return "";
  return `?init_data=${encodeURIComponent(initData)}`;
}

async function sendDraftToChat(draftId, button) {
  await withButtonFeedback(button, "Отправляю...", async () => {
    await fetchJson(`/api/drafts/${draftId}/send`, { method: "POST", body: "{}" });
  }, "Отправлено");
  const tg = window.Telegram?.WebApp;
  if (tg?.showAlert) tg.showAlert("Черновик отправлен в чат");
  else showUiNotice("Черновик отправлен в чат", "success");
}

async function saveContentReviewDraft(draftId, button) {
  return saveContentReviewDraftImpl(draftId, button);
}

async function polishContentDraft(draftId, button) {
  return polishContentDraftImpl(draftId, button);
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

async function withButtonFeedback(button, pendingLabel, handler, doneLabel = "Готово") {
  const target = button instanceof HTMLElement ? button : null;
  const originalHtml = target?.innerHTML || "";
  if (target) {
    target.disabled = true;
    target.classList.remove("did-complete", "did-error");
    target.classList.add("is-busy");
    target.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${escapeHtml(pendingLabel)}</span>`;
  }
  try {
    const result = await handler();
    if (target) {
      target.disabled = false;
      target.classList.remove("is-busy");
      target.classList.add("did-complete");
      target.innerHTML = `<span>${escapeHtml(doneLabel)}</span>`;
      window.setTimeout(() => {
        target.classList.remove("did-complete");
        target.innerHTML = originalHtml;
      }, 900);
    }
    return result;
  } catch (error) {
    if (target) {
      target.disabled = false;
      target.classList.remove("is-busy");
      target.classList.add("did-error");
      target.innerHTML = "<span>Ошибка</span>";
      window.setTimeout(() => {
        target.classList.remove("did-error");
        target.innerHTML = originalHtml;
      }, 1200);
    }
    throw error;
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
  const text = String(value || "").trim();
  if (!text) return "";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return date.toLocaleDateString("ru-RU");
}

function setEmptyState(hidden, text = "Ничего не найдено.") {
  elements.emptyState.hidden = hidden;
  if (hidden) {
    elements.emptyState.textContent = "";
  } else if (typeof text === "string") {
    elements.emptyState.textContent = text;
  } else {
    elements.emptyState.innerHTML = renderGuidedState(text || {});
  }
  elements.emptyState.style.display = hidden ? "none" : "block";
}

function showBootFallback(title, text, isError = false) {
  if (!elements.bootFallback) return;
  elements.bootFallback.hidden = false;
  elements.bootFallback.classList.toggle("is-error", isError);
  if (elements.bootFallbackTitle) elements.bootFallbackTitle.textContent = title;
  if (elements.bootFallbackText) elements.bootFallbackText.textContent = text;
}

function hideBootFallback() {
  if (!elements.bootFallback) return;
  elements.bootFallback.hidden = true;
  elements.bootFallback.classList.remove("is-error");
}

function humanizeRequestMessage(message) {
  if (message === "request_timeout") {
    return "Сервер отвечает слишком долго. Действие могло уже запуститься, проверьте карточку ещё раз.";
  }
  if (message === "Load failed" || message === "Failed to fetch") {
    return "Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.";
  }
  return message;
}

function showRequestError(prefix, error) {
  const message = error?.message || String(error || "unknown_error");
  showUiNotice(`${prefix}: ${humanizeRequestMessage(message)}`, "error");
}

function showRuntimeWarning(prefix, error) {
  const message = error?.message || String(error || "unknown_error");
  const humanMessage = humanizeRequestMessage(message);
  if (!appBootstrapped) {
    showBootFallback(prefix, humanMessage, true);
    return;
  }
  hideBootFallback();
  setEmptyState(true);
  elements.listTitle.textContent = "Загрузка";
  elements.draftCount.textContent = "";
  elements.draftList.innerHTML = renderPanelError(prefix, humanMessage);
  if (!elements.draftDetail.innerHTML.trim()) {
    elements.draftDetail.innerHTML = renderDetailLoader("Подождите ещё немного");
  }
}

async function copyText(value) {
  const text = String(value || "").trim();
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "readonly");
      field.style.position = "absolute";
      field.style.left = "-9999px";
      document.body.appendChild(field);
      field.select();
      document.execCommand("copy");
      document.body.removeChild(field);
    }
  } catch (error) {
    showRequestError("Не удалось скопировать промпт", error);
    return;
  }
  const tg = window.Telegram?.WebApp;
  if (tg?.showAlert) tg.showAlert("Промпт скопирован");
  else showUiNotice("Промпт скопирован", "success");
}

async function addKeywordItem(topicIdx, field, form, button) {
  return addKeywordItemImpl(topicIdx, field, form, button);
}

async function removeKeywordItem(topicIdx, field, word, button) {
  return removeKeywordItemImpl(topicIdx, field, word, button);
}

function openKeywordTopic(topicIdx) {
  return openKeywordTopicImpl(topicIdx);
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

window.goBackToList = goBackToList;

const {
  loadPlans: loadPlansImpl,
  planEntryTargetKind,
  planEntryFormatLabel,
  relatedDraftsForEntry,
  openPlan,
  generateDraftFromPlan,
  openPlanRelatedDraft,
  renderPlans: renderPlansImpl,
  renderPlanDetail,
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
  renderGuidedState,
  setEmptyState,
  renderDetailLoader,
  fetchJson,
  withButtonFeedback,
  upsertDraftSummary,
  draftSummaryFromDraft,
  setTab,
  enterDetailView,
  syncMobileNavigation,
  loadPlans,
  loadDrafts,
  loadReels,
  openDraft,
  openReels,
});

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
  fetchJson,
  withButtonFeedback,
  showRequestError,
  mergeReelsIntoState,
  scheduleReelsRefresh,
  callbacks: reelsCallbacks,
});

function applyTelegramTheme() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  tg.ready();
  tg.expand();
  const bgColor = tg.themeParams.secondary_bg_color;
  const textColor = tg.themeParams.text_color;
  if (bgColor) document.documentElement.style.setProperty("--panel", bgColor);
  if (textColor) document.documentElement.style.setProperty("--text", textColor);
  document.body.classList.toggle("tg-theme-dark", tg.colorScheme === "dark");
}

function filtersToQueryString() {
  const params = new URLSearchParams();
  if (elements.kindFilter.value) params.set("kind", elements.kindFilter.value);
  if (elements.statusFilter.value) params.set("status", elements.statusFilter.value);
  if (elements.feedbackFilter.value) params.set("feedback", elements.feedbackFilter.value);
  if (elements.queryFilter.value.trim()) params.set("query", elements.queryFilter.value.trim());
  params.set("limit", "100");
  return params.toString();
}

function _initDataHeader() {
  const initData = window.Telegram?.WebApp?.initData;
  return initData ? { "X-Telegram-Init-Data": initData } : {};
}

function scheduleReelsRefresh(draftId, attempts = 10) {
  if (!draftId || attempts <= 0) return;
  window.clearTimeout(reelRefreshTimer);
  reelRefreshTimer = window.setTimeout(async () => {
    try {
      const { shouldContinue } = await refreshReelsDetailImpl(draftId);
      if (shouldContinue) scheduleReelsRefresh(draftId, attempts - 1);
    } catch (_e) { scheduleReelsRefresh(draftId, attempts - 1); }
  }, 4000);
}

function scheduleCarouselRefresh(draftId, attempts = 12) {
  if (!draftId || attempts <= 0) return;
  window.clearTimeout(carouselRefreshTimer);
  carouselRefreshTimer = window.setTimeout(async () => {
    try {
      const draft = await fetchJson(`/api/carousel/${draftId}`);
      const payload = draft.payload || {};
      const slideImages = Array.isArray(payload.slide_images) ? payload.slide_images : [];
      const slideCount = Array.isArray(payload.slides) ? payload.slides.length : 0;
      const readyCount = slideImages.filter(Boolean).length;
      state.drafts = state.drafts.map((d) => d.draft_id === draft.draft_id ? { ...d, ...draft } : d);
      if (isCurrentDraftDetail(draft.draft_id)) {
        state.selected = draft;
        renderDraftList();
        if (!isEditingDetailForm() && !hasPendingCarouselOperations(draft.draft_id)) renderDraftDetail(draft);
      }
      if (draft.generation_pending || readyCount < slideCount) scheduleCarouselRefresh(draftId, attempts - 1);
    } catch (_e) { scheduleCarouselRefresh(draftId, attempts - 1); }
  }, 5000);
}

async function fetchJson(url, options = {}) {
  const { timeout = 12000, ...fetchOptions } = options;
  const extraHeaders = url.startsWith("/api/") ? _initDataHeader() : {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...extraHeaders },
      signal: controller.signal,
      ...fetchOptions,
    });
  } catch (error) {
    clearTimeout(timer);
    if (error?.name === "AbortError") {
      throw new Error("request_timeout");
    }
    throw error;
  }
  clearTimeout(timer);
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload?.detail ? ` (${payload.detail})` : "";
    } catch (_e) {}
    throw new Error(`${response.status} ${response.statusText}${detail}`);
  }
  return response.json();
}

async function loadDrafts() {
  const data = await fetchJson(`/api/drafts?${filtersToQueryString()}`, { timeout: 20000 });
  state.drafts = data.items || [];
  renderDraftList();
  const preferredId = state.draftId || "";
  if (!preferredId) {
    renderEmptyDetail();
    return;
  }
  if (isPendingDraftId(preferredId)) {
    if (state.selected?.draft_id === preferredId) {
      renderDraftDetail(state.selected);
      enterDetailView();
      return;
    }
    state.draftId = "";
    renderEmptyDetail();
    return;
  }
  try {
    await openDraft(preferredId);
  } catch (error) {
    console.error("miniapp failed to open preferred draft", error);
    const message = error?.message === "request_timeout"
      ? "Карточка открывается слишком долго. Список уже загружен, можно повторить открытие."
      : (error?.message || "Не удалось открыть карточку.");
    elements.draftDetail.innerHTML = renderDetailError("Не удалось открыть карточку", message, `openDraft('${preferredId}')`);
    syncMobileNavigation();
  }
}

async function loadInbox() { return loadInboxImpl(); }

async function loadStatus() {
  state.status = await fetchJson("/api/status");
  renderStatus();
}

async function loadPlans() {
  return loadPlansImpl();
}

async function loadReels() { return loadReelsImpl(); }

async function loadKeywords() {
  return loadKeywordsImpl();
}

async function loadSettings() {
  return loadSettingsImpl();
}

function renderCreate() {
  return renderCreateImpl();
}

function renderCreateTool(toolId) {
  return renderCreateToolImpl(toolId);
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
  handbookCardBadge,
  aromaSection,
  fetchJson,
  enterDetailView,
  syncMobileNavigation,
  setEmptyState,
  conceptTypeMeta,
  formatCourseSourceLabel,
  tagMarkup,
  stripMarkdown,
});

const {
  saveContentReviewDraft: saveContentReviewDraftImpl,
  polishContentDraft: polishContentDraftImpl,
  renderDraftList: renderDraftListImpl,
  openDraft: openDraftImpl,
  renderDraftDetail: renderDraftDetailImpl,
  renderEmptyDetail: renderEmptyDetailImpl,
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
  },
});

const {
  addKeywordItem: addKeywordItemImpl,
  removeKeywordItem: removeKeywordItemImpl,
  openKeywordTopic: openKeywordTopicImpl,
  loadKeywords: loadKeywordsImpl,
  loadSettings: loadSettingsImpl,
  renderStatus: renderStatusImpl,
  renderKeywords: renderKeywordsImpl,
} = createSettingsModule({
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

const {
  renderCreate: renderCreateImpl,
  renderCreateTool: renderCreateToolImpl,
} = createCreateModule({
  state,
  elements,
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
  openPendingReelsCreation,
  finalizePendingReelsCreation,
  recoverPendingReelsCreation,
  openDraft,
  openReels,
  setTab,
  loadPlans,
  renderPlanDetail,
});

const {
  loadCurrentTab: loadCurrentTabImpl,
  safeLoadCurrentTab: safeLoadCurrentTabImpl,
  bootstrap: bootstrapImpl,
  retryCurrentTab: retryCurrentTabImpl,
  bindBootFallbackReload,
  bindStartupErrorFallbacks,
} = createRuntimeModule({
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
  loadInbox,
  loadPlans,
  loadReels,
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

const {
  loadInbox: loadInboxImpl,
  loadReels: loadReelsImpl,
  openReels: openReelsImpl,
  openPendingReelsCreation: openPendingReelsCreationImpl,
  finalizePendingReelsCreation: finalizePendingReelsCreationImpl,
  recoverPendingReelsCreation: recoverPendingReelsCreationImpl,
  renderInbox: renderInboxImpl,
  renderReels: renderReelsImpl,
  renderReelsDetail: renderReelsDetailImpl,
  refreshReelsDetail: refreshReelsDetailImpl,
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
});

function aromaSection(title, content) {
  if (!content) return "";
  return `<section class="section"><h3>${sectionHeadingIcon(title)}${escapeHtml(title)}</h3><div class="detail-preview detail-markdown">${renderMarkdown(content)}</div></section>`;
}

function renderDraftList() {
  return renderDraftListImpl();
}

async function openDraft(id) {
  return openDraftImpl(id);
}

async function openReels(id) { return openReelsImpl(id); }

function renderDraftDetail(d) {
  return renderDraftDetailImpl(d);
}

function renderEmptyDetail() {
  return renderEmptyDetailImpl();
}

function setMode(m) {
  clearBackgroundRefreshes();
  state.mode = m;
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

function setTab(t) {
  clearBackgroundRefreshes();
  state.tab = t; 
  state.mobileView = "list"; 
  state.selectedCreateTool = null; 
  if (t !== "keywords" && t !== "settings") state.selectedKeywordTopicIdx = null;
  elements.settingsButton?.classList.toggle("active", state.mode === "content" && t === "settings");
  
  if (HANDBOOK_CATEGORY_META[t]) {
    state.referenceSearch = "";
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
  elements.filtersContainer.hidden = (t !== "drafts");
  
  // Clear panels immediately to prevent showing tools/content from previous tab
  elements.listTitle.textContent = "Загрузка...";
  elements.draftCount.textContent = "";
  elements.draftList.innerHTML = renderPanelLoader("Загружаю раздел");
  elements.draftDetail.innerHTML = renderDetailLoader("Загружаю раздел");
  
  syncMobileNavigation();
}

async function loadCurrentTab() { return loadCurrentTabImpl(); }

async function safeLoadCurrentTab(prefix = "Не удалось загрузить раздел") {
  return safeLoadCurrentTabImpl(prefix);
}

function openPendingReelsCreation(topic) { return openPendingReelsCreationImpl(topic); }

function finalizePendingReelsCreation(draft) { return finalizePendingReelsCreationImpl(draft); }

async function recoverPendingReelsCreation(topic, pendingDraftId) { return recoverPendingReelsCreationImpl(topic, pendingDraftId); }

async function bootstrap() { return bootstrapImpl(); }

bindBootFallbackReload();
bindStartupErrorFallbacks();

window.retryCurrentTab = retryCurrentTabImpl;

window.openDraft = openDraft;
window.openAroma = openAroma;
window.openReference = openReference;
window.copyText = copyText;
window.openReels = openReels;
window.openPlan = openPlan;
window.generateDraftFromPlan = generateDraftFromPlan;
window.openPlanRelatedDraft = openPlanRelatedDraft;
window.updateDraft = async (action, payload, button) => {
  const currentDraftId = state.draftId || state.selectedReels?.draft_id || "";
  if (!currentDraftId) return;
  const request = async () => fetchJson(`/api/drafts/${currentDraftId}/${action}`, { method: "POST", body: JSON.stringify(payload) });
  const d = button instanceof HTMLElement
    ? await withButtonFeedback(button, "Сохраняю...", request, "Готово")
    : await request();
  if (state.tab === "reels" || d.kind === "reels") {
    mergeReelsIntoState(d);
    renderReels();
    renderReelsDetail(d);
    return;
  }
  mergeDraftIntoState(d);
  renderDraftDetail(d);
  renderDraftList();
};
window.sendDraftToChat = sendDraftToChat;
window.deleteDraft = deleteDraft;
window.saveCarouselSlideText = saveCarouselSlideText;
window.regenerateCarouselSlide = regenerateCarouselSlide;
window.regenerateCarouselAll = regenerateCarouselAll;
window.selectCarouselSlideVersion = selectCarouselSlideVersion;
window.deleteCarouselSlideVersion = deleteCarouselSlideVersion;
window.handleCarouselSlideNoteInput = handleCarouselSlideNoteInput;
window.downloadCarouselPptx = downloadCarouselPptx;
window.saveReelsScenario = saveReelsScenario;
window.regenerateReelsStoryboard = regenerateReelsStoryboard;
window.regenerateAllReelsFrames = regenerateAllReelsFrames;
window.saveReelsFrameFields = saveReelsFrameFields;
window.saveReelsFramePrompt = saveReelsFramePrompt;
window.saveReelsFrameNote = saveReelsFrameNote;
window.regenerateReelsFrame = regenerateReelsFrame;
window.handleReelsFramePromptInput = handleReelsFramePromptInput;
window.handleReelsFrameNoteInput = handleReelsFrameNoteInput;
window.saveContentReviewDraft = saveContentReviewDraft;
window.polishContentDraft = polishContentDraft;
window.openKeywordTopic = openKeywordTopic;
window.addKeywordItem = addKeywordItem;
window.removeKeywordItem = removeKeywordItem;
window.renderCreateTool = renderCreateTool;
window.openCreateTool = (toolId = "content") => {
  setMode("content");
  setTab("create");
  renderCreate();
  renderCreateTool(toolId);
};
window.openSettingsSection = async (section) => {
  state.settingsSection = section === "keywords" ? "keywords" : "status";
  if (state.tab !== "settings") {
    setMode("content");
    setTab("settings");
  }
  await loadSettings();
};

function renderInbox() { return renderInboxImpl(); }

function renderStatus() {
  return renderStatusImpl();
}

function renderPlans() {
  return renderPlansImpl();
}

function renderReels() { return renderReelsImpl(); }

reelsCallbacks.renderReels = renderReels;
reelsCallbacks.renderReelsDetail = renderReelsDetail;

function renderReelsDetail(r) {
  return renderReelsDetailImpl(r);
}

function renderKeywords() {
  return renderKeywordsImpl();
}
bootstrap();
