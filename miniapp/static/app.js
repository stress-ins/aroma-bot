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
    { id: "practices", label: "Практики" },
    { id: "sounds", label: "Звуки" },
  ],
};

let reelRefreshTimer = null;
let carouselRefreshTimer = null;
let swipeStart = null;
let bootstrapWatchdogTimer = null;
let appBootstrapped = false;
let startupLoadInFlight = false;
let uiNoticeTimer = null;
let detailEntryTimer = null;
let keyboardViewportTimer = null;
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
    searchLabel: "Поиск аромата",
    searchPlaceholder: "Например: лаванда",
    empty: "Ароматы не найдены.",
    selectPrompt: "Выберите аромат из списка.",
    locked: "Доступ к справочнику ароматов ограничен.",
    count: (items) => `${items.length} карточек`,
  },
  practices: {
    category: "practice",
    title: "Практики",
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
    practices: "🫁",
    sounds: "🔔",
  };
  const glyph = glyphMap[String(tabId || "").toLowerCase()] || "•";
  return `<span class="kind-glyph handbook-glyph" aria-hidden="true">${glyph}</span>`;
}

function handbookCardBadge(tabId, item = {}) {
  const sourceType = String(item.source_type || "").trim();
  if (tabId === "aromas" && sourceType) return sourceType;
  if (tabId === "practices") return "Практика";
  if (tabId === "sounds") return "Звук";
  return "";
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
        <p class="eyebrow">Загрузка</p>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(message)}</p>
      </div>
      <button class="secondary-button" type="button" onclick="retryCurrentTab()">Повторить</button>
    </div>
  `;
}

function renderGuidedState({
  eyebrow = "Навигация",
  title = "Пока пусто",
  body = "Выберите следующий шаг, и мы продолжим.",
  actionLabel = "",
  action = "",
  tone = "soft",
} = {}) {
  return `
    <div class="guided-state tone-${escapeHtml(tone)}">
      <div class="guided-state-copy">
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(body)}</p>
      </div>
      ${actionLabel && action ? `
        <div class="guided-state-actions">
          <button class="secondary-button" type="button" onclick="${action}">${escapeHtml(actionLabel)}</button>
        </div>
      ` : ""}
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
          <p class="eyebrow">Загрузка</p>
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

function planEntryTargetKind(entry = {}) {
  const platform = String(entry.platform || "").trim().toLowerCase();
  const formatLabel = String(entry.format_label || "").trim().toLowerCase();
  if (platform.includes("reels") || formatLabel.includes("reels") || formatLabel.includes("рилс")) return "reels";
  if (formatLabel.includes("карус") || formatLabel.includes("carousel")) return "carousel";
  if (platform.includes("threads")) return "threads";
  if (platform.includes("instagram")) return "instagram";
  if (platform.includes("telegram")) return "telegram";
  return "instagram";
}

function planEntryFormatLabel(entry = {}) {
  const target = planEntryTargetKind(entry);
  return kindLabel(target) || "Контент";
}

function relatedDraftsForEntry(plan = {}, entry = {}) {
  const topic = String(entry.topic || "").trim();
  const related = Array.isArray(plan.related_drafts) ? plan.related_drafts : [];
  if (!topic) return [];
  return related.filter((draft) => String(draft.topic || "").trim() === topic);
}

function slideNoteId(index) {
  return `carouselSlideNote${index}`;
}

function slideTextId(index) {
  return `carouselSlideText${index}`;
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

function bufferedCarouselNote(draftId, index, fallback = "") {
  const key = frameDraftKey(draftId, index);
  return Object.prototype.hasOwnProperty.call(state.pendingCarouselNotes, key)
    ? state.pendingCarouselNotes[key]
    : String(fallback || "");
}

function carouselSlideOperation(draftId, index) {
  return state.pendingCarouselOps[frameDraftKey(draftId, index)] || "";
}

function setCarouselSlideOperation(draftId, index, value = "") {
  const key = frameDraftKey(draftId, index);
  if (!value) {
    delete state.pendingCarouselOps[key];
    return;
  }
  state.pendingCarouselOps[key] = String(value);
}

function hasPendingCarouselOperations(draftId = "") {
  const prefix = draftId ? `${draftId}:` : "";
  return Object.keys(state.pendingCarouselOps).some((key) => key.startsWith(prefix));
}

function carouselSlideStatusMarkup(draftId, index, hasImage) {
  const operation = carouselSlideOperation(draftId, index);
  if (operation) {
    return `<div class="slide-status is-pending">${uiIcon("sparkle")}<span>${escapeHtml(operation)}</span></div>`;
  }
  if (hasImage) {
    return `<div class="slide-status is-ready">${uiIcon("approve")}<span>Картинка готова</span></div>`;
  }
  return `<div class="slide-status is-empty">${uiIcon("image")}<span>Изображение еще готовится</span></div>`;
}

function bufferedReelsNote(draftId, index, fallback = "") {
  const key = frameDraftKey(draftId, index);
  return Object.prototype.hasOwnProperty.call(state.pendingReelsNotes, key)
    ? state.pendingReelsNotes[key]
    : String(fallback || "");
}

function bufferedReelsPrompt(draftId, index, fallback = "") {
  const key = frameDraftKey(draftId, index);
  return Object.prototype.hasOwnProperty.call(state.pendingReelsPrompts, key)
    ? state.pendingReelsPrompts[key]
    : String(fallback || "");
}

function renderSlides(draftId, slides = [], prompts = [], slideImages = [], promptNotes = [], slideVersions = []) {
  const slideItems = Array.isArray(slides) ? slides : [];
  const promptItems = Array.isArray(prompts) ? prompts : [];
  const imageItems = Array.isArray(slideImages) ? slideImages : [];
  const noteItems = Array.isArray(promptNotes) ? promptNotes : [];
  const versionItems = Array.isArray(slideVersions) ? slideVersions : [];
  if (!slideItems.length) return "";
  const readyCount = imageItems.filter(Boolean).length;
  const header = readyCount > 0
    ? `Слайды карусели <span class="meta">${readyCount} / ${slideItems.length} с картинкой</span>`
    : "Слайды карусели";
  return `
    <section class="section">
      <h3>${uiIcon("slides")}${header}</h3>
      <div class="slides">
        ${slideItems.map((slide, index) => {
          const img = imageItems[index];
          const prompt = String(promptItems[index] || "");
          const note = bufferedCarouselNote(draftId, index, String(noteItems[index] || ""));
          const versions = Array.isArray(versionItems[index]) ? versionItems[index] : [];
          const showPromptOpen = !img?.url;
          const imgHtml = img?.url
            ? `<img class="frame-image" src="${escapeHtml(img.url)}" alt="Слайд ${index + 1}" />`
            : `<div class="frame-loading">Картинка недоступна или еще генерируется. Откройте промпт ниже для ручной генерации.</div>`;
          return `
            <article class="slide">
              <strong>Слайд ${index + 1}</strong>
              ${carouselSlideStatusMarkup(draftId, index, Boolean(img?.url))}
              ${imgHtml}
              <label class="prompt-note-field">
                <span>Подпись слайда</span>
                <textarea id="${slideTextId(index)}" placeholder="Текст для этого слайда">${escapeHtml(slide)}</textarea>
              </label>
              <p class="field-help">После правки нажмите «Сохранить подпись», чтобы обновить этот слайд в черновике.</p>
              ${prompt ? `
                <details class="prompt-disclosure"${showPromptOpen ? " open" : ""}>
                  <summary class="secondary-button prompt-toggle">${actionLabel("eye", "Показать промпт")}</summary>
                  <div class="prompt-card">
                    <div class="detail-preview prompt-preview">${escapeHtml(prompt)}</div>
                    <label class="prompt-note-field">
                      <span>Замечание к картинке</span>
                      <textarea id="${slideNoteId(index)}" placeholder="Например: теплее свет, крупнее объект, меньше деталей на фоне" oninput="handleCarouselSlideNoteInput(${JSON.stringify(draftId)}, ${index}, this.value)">${escapeHtml(note)}</textarea>
                    </label>
                    <div class="actions-row prompt-actions">
                      <button class="primary-button" type="button" aria-label="Сохранить текст слайда" onclick="saveCarouselSlideText(${JSON.stringify(draftId)}, ${index}, this)">${actionLabel("text", "Сохранить подпись")}</button>
                      <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(prompt)})'>${actionLabel("prompt", "Скопировать промпт слайда")}</button>
                      <button class="secondary-button" type="button" onclick="regenerateCarouselSlide(${JSON.stringify(draftId)}, ${index}, this)">${actionLabel("regenerate", "Перегенерировать картинку")}</button>
                    </div>
                  </div>
                </details>
              ` : `
                <div class="actions-row prompt-actions">
                  <button class="primary-button" type="button" aria-label="Сохранить текст слайда" onclick="saveCarouselSlideText(${JSON.stringify(draftId)}, ${index}, this)">${actionLabel("text", "Сохранить подпись")}</button>
                </div>
              `}
              ${renderSlideVersions(draftId, index, img, versions)}
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function renderSlideVersions(draftId, slideIndex, currentImage, versions = []) {
  const items = Array.isArray(versions) ? versions : [];
  if (!items.length) return "";
  const currentFilename = String(currentImage?.filename || "").trim();
  return `
    <div class="slide-versions">
      <div class="slide-versions-head">
        <strong>${uiIcon("image")}Версии</strong>
        <span class="meta">${items.length} шт</span>
      </div>
      <div class="slide-version-grid">
        ${items.map((version, versionIndex) => {
          const isCurrent = String(version?.filename || "").trim() === currentFilename;
          return `
            <article class="slide-version-card${isCurrent ? " is-current" : ""}">
              <button
                class="slide-version-thumb"
                type="button"
                onclick="selectCarouselSlideVersion(${JSON.stringify(draftId)}, ${slideIndex}, ${versionIndex}, this)"
                aria-label="${isCurrent ? "Текущая версия" : "Сделать текущей"}"
              >
                <img src="${escapeHtml(version.url || "")}" alt="Версия ${versionIndex + 1} для слайда ${slideIndex + 1}" />
              </button>
              <div class="slide-version-meta">
                <span>${isCurrent ? "Текущая" : `Версия ${versionIndex + 1}`}</span>
                <span class="meta">${escapeHtml(formatPlanDate(version.generated_at) || "сейчас")}</span>
              </div>
              <div class="actions-row slide-version-actions">
                ${isCurrent ? "" : `<button class="secondary-button" type="button" onclick="selectCarouselSlideVersion(${JSON.stringify(draftId)}, ${slideIndex}, ${versionIndex}, this)">${actionLabel("approve", "Сделать текущей")}</button>`}
                ${items.length > 1 ? `<button class="secondary-button" type="button" onclick="deleteCarouselSlideVersion(${JSON.stringify(draftId)}, ${slideIndex}, ${versionIndex}, this)">${actionLabel("trash", "Удалить")}</button>` : ""}
              </div>
            </article>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

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

function isEditingDetailForm() {
  const active = document.activeElement;
  if (!active || !(active instanceof HTMLElement)) return false;
  if (!elements.detailPanel.contains(active)) return false;
  return active.matches("textarea, input, select, [contenteditable='true']");
}

function _authQueryString() {
  const initData = window.Telegram?.WebApp?.initData;
  if (!initData) return "";
  return `?init_data=${encodeURIComponent(initData)}`;
}

async function saveCarouselSlideText(draftId, slideIndex, button) {
  const textField = document.getElementById(slideTextId(slideIndex));
  const text = String(textField?.value || "").trim();
  const apply = async () => {
    const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/text`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    state.selected = draft;
    mergeDraftIntoState(draft);
    renderDraftList();
    if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
  };
  if (button instanceof HTMLElement) {
    await withButtonFeedback(button, "Сохраняю...", apply, "Сохранено");
    return;
  }
  await apply();
}

async function persistCarouselSlideNote(draftId, slideIndex, note) {
  const key = frameDraftKey(draftId, slideIndex);
  state.pendingCarouselNotes[key] = String(note || "");
  const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/note`, {
    method: "POST",
    body: JSON.stringify({ note: String(note || "") }),
  });
  mergeDraftIntoState(draft);
  state.pendingCarouselNotes[key] = String(note || "");
  return draft;
}

function handleCarouselSlideNoteInput(draftId, slideIndex, value) {
  const key = frameDraftKey(draftId, slideIndex);
  state.pendingCarouselNotes[key] = String(value || "");
  window.clearTimeout(carouselNoteSaveTimers[key]);
  carouselNoteSaveTimers[key] = window.setTimeout(() => {
    void persistCarouselSlideNote(draftId, slideIndex, state.pendingCarouselNotes[key]).catch(() => {});
  }, 600);
}

async function regenerateCarouselSlide(draftId, slideIndex, button) {
  const noteField = document.getElementById(slideNoteId(slideIndex));
  const currentNote = String(noteField?.value || bufferedCarouselNote(draftId, slideIndex, "")).trim();
  const note = currentNote || null;
  const apply = async () => {
    setCarouselSlideOperation(
      draftId,
      slideIndex,
      note ? "Учитываю замечание и собираю новый вариант" : "Генерирую новый вариант картинки",
    );
    if (isCurrentDraftDetail(draftId) && state.selected?.draft_id === draftId) {
      renderDraftDetail(state.selected);
    }
    if (currentNote) {
      await persistCarouselSlideNote(draftId, slideIndex, currentNote);
    }
    const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
    mergeDraftIntoState(draft);
    renderDraftList();
    if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
    scheduleCarouselRefresh(draft.draft_id);
  };
  try {
    if (button instanceof HTMLElement) {
      await withButtonFeedback(button, "Генерирую...", apply, "Готово");
      return;
    }
    await apply();
  } catch (error) {
    showRequestError("Не удалось перегенерировать картинку", error);
  } finally {
    setCarouselSlideOperation(draftId, slideIndex, "");
    if (isCurrentDraftDetail(draftId) && state.selected?.draft_id === draftId) {
      renderDraftDetail(state.selected);
    }
  }
}

async function regenerateCarouselAll(draftId, button) {
  await withButtonFeedback(button, "Генерирую...", async () => {
    const draft = await fetchJson(`/api/carousel/${draftId}/regenerate-all`, { method: "POST", body: "{}" });
    state.selected = draft;
    state.draftId = draft.draft_id;
    state.drafts = state.drafts.map((item) => item.draft_id === draft.draft_id ? { ...item, ...draft } : item);
    renderDraftList();
    if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
  }, "Готово");
}

async function selectCarouselSlideVersion(draftId, slideIndex, versionIndex, button) {
  try {
    await withButtonFeedback(button, "Выбираю...", async () => {
      const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/versions/${versionIndex}/select`, {
        method: "POST",
        body: "{}",
      });
      mergeDraftIntoState(draft);
      renderDraftList();
      if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
    }, "Выбрано");
  } catch (error) {
    showRequestError("Не удалось выбрать версию картинки", error);
  }
}

async function deleteCarouselSlideVersion(draftId, slideIndex, versionIndex, button) {
  const confirmed = await confirmAction("Удалить эту версию картинки?");
  if (!confirmed) return;
  try {
    await withButtonFeedback(button, "Удаляю...", async () => {
      const draft = await fetchJson(`/api/carousel/${draftId}/slides/${slideIndex}/versions/${versionIndex}`, {
        method: "DELETE",
      });
      mergeDraftIntoState(draft);
      renderDraftList();
      if (isCurrentDraftDetail(draft.draft_id)) renderDraftDetail(draft);
    }, "Удалено");
  } catch (error) {
    showRequestError("Не удалось удалить версию картинки", error);
  }
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
  const payload = {
    topic: String(document.getElementById("contentTopicField")?.value || "").trim(),
    angle: String(document.getElementById("contentAngleField")?.value || "").trim(),
    hook: String(document.getElementById("contentHookField")?.value || "").trim(),
    caption: String(document.getElementById("contentCaptionField")?.value || "").trim(),
    cta: String(document.getElementById("contentCtaField")?.value || "").trim(),
    hashtags: String(document.getElementById("contentHashtagsField")?.value || "").trim(),
    visual_prompt: String(document.getElementById("contentVisualPromptField")?.value || "").trim(),
    editor_notes: String(document.getElementById("contentEditorNotesField")?.value || "").trim(),
  };
  await withButtonFeedback(button, "Сохраняю...", async () => {
    const draft = await fetchJson(`/api/drafts/${draftId}/content`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    mergeDraftIntoState(draft);
    renderDraftList();
    renderDraftDetail(draft);
  }, "Сохранено");
}

async function polishContentDraft(draftId, button) {
  await withButtonFeedback(button, "Полирую...", async () => {
    const draft = await fetchJson(`/api/drafts/${draftId}/content/polish`, {
      method: "POST",
      body: "{}",
    });
    mergeDraftIntoState(draft);
    renderDraftList();
    renderDraftDetail(draft);
  }, "Готово");
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

async function downloadCarouselPptx(draftId, button) {
  const downloadUrl = `${window.location.origin}/api/carousel/${draftId}/pptx${_authQueryString()}`;
  if (button instanceof HTMLElement) {
    button.classList.add("did-complete");
    window.setTimeout(() => button.classList.remove("did-complete"), 900);
  }
  const tg = window.Telegram?.WebApp;
  if (tg?.openLink) {
    tg.openLink(downloadUrl);
    return;
  }
  window.open(downloadUrl, "_blank", "noopener,noreferrer");
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

async function saveReelsScenario(draftId, button) {
  const scenario = String(document.getElementById("reelsScenarioField")?.value || "").trim();
  const concept = String(document.getElementById("reelsConceptField")?.value || "").trim();
  await withButtonFeedback(button, "Сохраняю...", async () => {
    const draft = await fetchJson(`/api/reels/${draftId}/scenario`, {
      method: "POST",
      body: JSON.stringify({ scenario, concept }),
    });
    state.selectedReels = draft;
    renderReels();
    renderReelsDetail(draft);
  }, "Сохранено");
}

async function regenerateReelsStoryboard(draftId, button) {
  await withButtonFeedback(button, "Собираю заново...", async () => {
    const draft = await fetchJson(`/api/reels/${draftId}/storyboard/regenerate`, {
      method: "POST",
      body: "{}",
    });
    state.selectedReels = draft;
    renderReels();
    renderReelsDetail(draft);
  }, "Готово");
}

async function regenerateAllReelsFrames(draftId, button) {
  await withButtonFeedback(button, "Генерирую кадры...", async () => {
    const draft = await fetchJson(`/api/reels/${draftId}/frames/regenerate-all`, {
      method: "POST",
      body: "{}",
    });
    state.selectedReels = draft;
    renderReels();
    renderReelsDetail(draft);
  }, "Готово");
}

async function saveReelsFrameFields(draftId, frameIndex, button) {
  const scene = String(document.getElementById(`reelsFrameScene${frameIndex}`)?.value || "").trim();
  const angle = String(document.getElementById(`reelsFrameAngle${frameIndex}`)?.value || "").trim();
  const timecode = String(document.getElementById(`reelsFrameTimecode${frameIndex}`)?.value || "").trim();
  await withButtonFeedback(button, "Сохраняю...", async () => {
    const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/fields`, {
      method: "POST",
      body: JSON.stringify({ scene, angle, timecode }),
    });
    state.selectedReels = draft;
    renderReels();
    renderReelsDetail(draft);
  }, "Сохранено");
}

async function saveReelsFramePrompt(draftId, frameIndex, button) {
  const prompt = String(document.getElementById(`reelsFramePrompt${frameIndex}`)?.value || "").trim();
  await withButtonFeedback(button, "Сохраняю...", async () => {
    const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/prompt`, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });
    const key = frameDraftKey(draftId, frameIndex);
    state.pendingReelsPrompts[key] = prompt;
    mergeReelsIntoState(draft);
    renderReels();
    renderReelsDetail(draft);
  }, "Сохранено");
}

async function persistReelsFramePrompt(draftId, frameIndex, prompt) {
  const key = frameDraftKey(draftId, frameIndex);
  state.pendingReelsPrompts[key] = String(prompt || "");
  const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/prompt`, {
    method: "POST",
    body: JSON.stringify({ prompt: String(prompt || "") }),
  });
  mergeReelsIntoState(draft);
  state.pendingReelsPrompts[key] = String(prompt || "");
  return draft;
}

function handleReelsFramePromptInput(draftId, frameIndex, value) {
  const key = frameDraftKey(draftId, frameIndex);
  state.pendingReelsPrompts[key] = String(value || "");
  window.clearTimeout(reelsPromptSaveTimers[key]);
  reelsPromptSaveTimers[key] = window.setTimeout(() => {
    const prompt = String(state.pendingReelsPrompts[key] || "").trim();
    if (!prompt) return;
    void persistReelsFramePrompt(draftId, frameIndex, prompt).catch(() => {});
  }, 600);
}

async function saveReelsFrameNote(draftId, frameIndex, button) {
  const note = String(document.getElementById(`reelsFrameNote${frameIndex}`)?.value || "").trim();
  await withButtonFeedback(button, "Сохраняю...", async () => {
    const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/note`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
    const key = frameDraftKey(draftId, frameIndex);
    state.pendingReelsNotes[key] = note;
    mergeReelsIntoState(draft);
    renderReels();
    renderReelsDetail(draft);
  }, "Сохранено");
}

async function persistReelsFrameNote(draftId, frameIndex, note) {
  const key = frameDraftKey(draftId, frameIndex);
  state.pendingReelsNotes[key] = String(note || "");
  const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/note`, {
    method: "POST",
    body: JSON.stringify({ note: String(note || "") }),
  });
  mergeReelsIntoState(draft);
  state.pendingReelsNotes[key] = String(note || "");
  return draft;
}

function handleReelsFrameNoteInput(draftId, frameIndex, value) {
  const key = frameDraftKey(draftId, frameIndex);
  state.pendingReelsNotes[key] = String(value || "");
  window.clearTimeout(reelsNoteSaveTimers[key]);
  reelsNoteSaveTimers[key] = window.setTimeout(() => {
    void persistReelsFrameNote(draftId, frameIndex, state.pendingReelsNotes[key]).catch(() => {});
  }, 600);
}

async function regenerateReelsFrame(draftId, frameIndex, button) {
  await withButtonFeedback(button, "Генерирую...", async () => {
    const prompt = String(document.getElementById(`reelsFramePrompt${frameIndex}`)?.value || bufferedReelsPrompt(draftId, frameIndex, "")).trim();
    const note = String(document.getElementById(`reelsFrameNote${frameIndex}`)?.value || bufferedReelsNote(draftId, frameIndex, "")).trim();
    if (prompt) await persistReelsFramePrompt(draftId, frameIndex, prompt);
    if (note) await persistReelsFrameNote(draftId, frameIndex, note);
    const draft = await fetchJson(`/api/reels/${draftId}/frames/${frameIndex}/regenerate`, {
      method: "POST",
      body: "{}",
    });
    mergeReelsIntoState(draft);
    renderReels();
    renderReelsDetail(draft);
  }, "Готово");
}

function renderReelsFrames(draftId, frames = []) {
  const frameItems = Array.isArray(frames) ? frames : [];
  if (!frameItems.length) return "";
  return `
    <section class="section">
      <h3>${sectionHeadingIcon("Кадры и промпты")}Кадры и промпты</h3>
      <div class="storyboard">
        ${frameItems.map((frame, index) => {
          const prompt = bufferedReelsPrompt(draftId, index, frame.gemini_prompt || "");
          const note = bufferedReelsNote(draftId, index, frame.review_note || "");
          const assetUrl = frame.current_asset?.url || "";
          const showPromptOpen = !assetUrl;
          return `
            <article class="storyboard-frame">
              <strong>Кадр ${index + 1}${frame.timecode ? ` • ${escapeHtml(frame.timecode)}` : ""}</strong>
              <label class="prompt-note-field">
                <span>Текст / действие кадра</span>
                <textarea id="reelsFrameScene${index}" placeholder="Что происходит в кадре">${escapeHtml(frame.scene || "")}</textarea>
              </label>
              <label class="prompt-note-field">
                <span>Ракурс</span>
                <input id="reelsFrameAngle${index}" type="text" placeholder="Например: макро, фронтальный, средний план" value="${escapeHtml(frame.angle || "")}" />
              </label>
              <label class="prompt-note-field">
                <span>Таймкод</span>
                <input id="reelsFrameTimecode${index}" type="text" placeholder="Например: 0-3 сек" value="${escapeHtml(frame.timecode || "")}" />
              </label>
              ${assetUrl
                ? `<img class="frame-image" src="${escapeHtml(assetUrl)}" alt="Кадр ${index + 1}" />`
                : `<div class="frame-loading">Картинка ещё не готова. Откройте промпт ниже для ручной генерации.</div>`}
              ${prompt ? `
                <details class="prompt-disclosure"${showPromptOpen ? " open" : ""}>
                  <summary class="secondary-button prompt-toggle">${actionLabel("eye", "Показать промпт")}</summary>
                  <div class="prompt-card">
                    <label class="prompt-note-field">
                      <span>Промт кадра</span>
                      <textarea id="reelsFramePrompt${index}" placeholder="Промт для генерации кадра" oninput="handleReelsFramePromptInput('${draftId}', ${index}, this.value)">${escapeHtml(prompt)}</textarea>
                    </label>
                    <label class="prompt-note-field">
                      <span>Замечание к кадру</span>
                      <textarea id="reelsFrameNote${index}" placeholder="Например: теплее, меньше деталей, крупнее объект" oninput="handleReelsFrameNoteInput('${draftId}', ${index}, this.value)">${escapeHtml(note)}</textarea>
                    </label>
                    <div class="actions-row prompt-actions">
                      <button class="secondary-button" type="button" onclick="saveReelsFrameFields('${draftId}', ${index}, this)">${actionLabel("text", "Сохранить кадр")}</button>
                      <button class="secondary-button" type="button" onclick="saveReelsFramePrompt('${draftId}', ${index}, this)">${actionLabel("prompt", "Сохранить промпт")}</button>
                      <button class="secondary-button" type="button" onclick="saveReelsFrameNote('${draftId}', ${index}, this)">${actionLabel("note", "Сохранить замечание")}</button>
                      <button class="secondary-button" type="button" onclick="regenerateReelsFrame('${draftId}', ${index}, this)">${actionLabel("regenerate", "Сгенерировать кадр")}</button>
                      <button class="secondary-button" type="button" onclick='copyText(${JSON.stringify(String(prompt))})'>${actionLabel("prompt", "Скопировать промпт кадра")}</button>
                    </div>
                  </div>
                </details>
              ` : `
                <div class="actions-row prompt-actions">
                  <button class="secondary-button" type="button" onclick="saveReelsFrameFields('${draftId}', ${index}, this)">${actionLabel("text", "Сохранить кадр")}</button>
                </div>
              `}
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
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
    elements.emptyState.innerHTML = renderGuidedState({
      eyebrow: "Список",
      title: text,
      body: "Попробуйте изменить фильтры, поиск или откройте соседний раздел.",
    });
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

function showRequestError(prefix, error) {
  const message = error?.message || String(error || "unknown_error");
  showUiNotice(`${prefix}: ${message}`, "error");
}

function showRuntimeWarning(prefix, error) {
  const message = error?.message || String(error || "unknown_error");
  const humanMessage = message === "request_timeout"
    ? "Сервер отвечает слишком долго. Попробуйте повторить загрузку."
    : message;
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

function keywordFieldEntries(topic) {
  const labels = state.keywords?.field_labels || {};
  const fields = topic?.fields || {};
  return Object.entries(fields).map(([field, items]) => ({
    field,
    label: labels[field] || field,
    items: Array.isArray(items) ? items : [],
  }));
}

async function addKeywordItem(topicIdx, field, form, button) {
  const input = form?.querySelector("input[name='word']");
  const word = String(input?.value || "").trim();
  if (!word) {
    input?.focus();
    return;
  }
  await withButtonFeedback(button, "Добавляю...", async () => {
    const payload = await fetchJson("/api/keywords/add", {
      method: "POST",
      body: JSON.stringify({ topic_idx: topicIdx, field, word }),
    });
    state.keywords = payload;
    renderKeywords();
  }, "Добавлено");
  showUiNotice("Ключ добавлен", "success");
}

async function removeKeywordItem(topicIdx, field, word, button) {
  const confirmed = await confirmAction(`Удалить ключ "${word}"?`);
  if (!confirmed) return;
  await withButtonFeedback(button, "Удаляю...", async () => {
    const payload = await fetchJson("/api/keywords/remove", {
      method: "POST",
      body: JSON.stringify({ topic_idx: topicIdx, field, word }),
    });
    state.keywords = payload;
    renderKeywords();
  }, "Удалено");
  showUiNotice("Ключ удален", "success");
}

function openKeywordTopic(topicIdx) {
  state.selectedKeywordTopicIdx = Number(topicIdx);
  renderKeywords();
  enterDetailView();
}

function syncMobileNavigation() {
  const isMobile = window.matchMedia("(max-width: 760px)").matches;
  if (!isMobile) {
    elements.listPanel.classList.remove("hidden-mobile");
    elements.detailPanel.classList.remove("hidden-mobile");
    return;
  }

  if (state.mobileView === "detail") {
    elements.listPanel.classList.add("hidden-mobile");
    elements.detailPanel.classList.remove("hidden-mobile");
  } else {
    elements.listPanel.classList.remove("hidden-mobile");
    elements.detailPanel.classList.add("hidden-mobile");
  }
}

function renderBackButton() {
  const isMobile = window.matchMedia("(max-width: 760px)").matches;
  if (!isMobile) return "";
  return `<button class="back-button visible" onclick="goBackToList(true)">${uiIcon("back")}<span>Назад к списку</span></button>`;
}

window.goBackToList = (animated = false) => {
  if (animated) {
    animateBackToList();
    return;
  }
  state.mobileView = "list";
  elements.detailPanel.classList.remove("swipe-back-exit", "swipe-back-armed");
  elements.detailPanel.style.removeProperty("--swipe-offset");
  syncMobileNavigation();
};

function enterDetailView() {
  state.mobileView = "detail";
  syncMobileNavigation();
  if (elements.detailPanel) {
    elements.detailPanel.classList.remove("is-entering");
    window.clearTimeout(detailEntryTimer);
    requestAnimationFrame(() => {
      elements.detailPanel.classList.add("is-entering");
      detailEntryTimer = window.setTimeout(() => {
        elements.detailPanel?.classList.remove("is-entering");
      }, 280);
    });
  }
  window.scrollTo(0, 0);
}

function isInteractiveTarget(target) {
  if (!target || !(target instanceof Element)) return false;
  return Boolean(target.closest("textarea, input, select, button, a, [contenteditable='true']"));
}

function isSelectableTextTarget(target) {
  if (!target || !(target instanceof Element)) return false;
  return Boolean(target.closest(".detail-preview, .detail-markdown, .draft-preview, .draft-topic, .detail-title, .section"));
}

function hasActiveTextSelection() {
  const selection = window.getSelection?.();
  return Boolean(selection && String(selection).trim().length > 0);
}

function bindKeyboardDismiss() {
  const dismiss = (event) => {
    const active = document.activeElement;
    if (!active || !(active instanceof HTMLElement)) return;
    if (!active.matches("textarea, input")) return;
    const target = event.target;
    if (target instanceof Element && target.closest("textarea, input, select")) return;
    active.blur();
  };
  document.addEventListener("touchstart", dismiss, { passive: true });
  document.addEventListener("mousedown", dismiss, { passive: true });
}

function bindCardKeyboardActivation() {
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    const card = target.closest(".interactive-card");
    if (!(card instanceof HTMLElement)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    card.click();
  });
}

function ensureFieldAboveKeyboard(target, behavior = "smooth") {
  if (!(target instanceof HTMLElement)) return;
  const viewportHeight = window.visualViewport?.height || window.innerHeight || 0;
  if (!viewportHeight) return;
  const rect = target.getBoundingClientRect();
  const visibleTop = 84;
  const visibleBottom = viewportHeight - 20;
  if (rect.top >= visibleTop && rect.bottom <= visibleBottom) return;
  target.scrollIntoView({
    behavior,
    block: rect.top < visibleTop ? "start" : "center",
    inline: "nearest",
  });
}

function bindKeyboardViewportAssist() {
  const schedule = (target, delay = 0, behavior = "smooth") => {
    if (!(target instanceof HTMLElement)) return;
    window.clearTimeout(keyboardViewportTimer);
    keyboardViewportTimer = window.setTimeout(() => ensureFieldAboveKeyboard(target, behavior), delay);
  };

  document.addEventListener("focusin", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches("textarea, input, select, [contenteditable='true']")) return;
    schedule(target, 0, "auto");
    schedule(target, 120, "smooth");
    schedule(target, 260, "smooth");
  });

  const viewport = window.visualViewport;
  if (!viewport) return;
  const handleViewportChange = () => {
    const active = document.activeElement;
    if (!(active instanceof HTMLElement)) return;
    if (!active.matches("textarea, input, select, [contenteditable='true']")) return;
    schedule(active, 40, "smooth");
  };
  viewport.addEventListener("resize", handleViewportChange);
  viewport.addEventListener("scroll", handleViewportChange);
}
function bindSwipeBack() {
  const isMobile = window.matchMedia("(max-width: 760px)").matches;
  if (!isMobile) return;
  elements.detailPanel.addEventListener("touchstart", (event) => {
    const touch = event.touches[0];
    if (!touch || state.mobileView !== "detail" || isInteractiveTarget(event.target) || isSelectableTextTarget(event.target) || hasActiveTextSelection()) {
      swipeStart = null;
      return;
    }
    swipeStart = { x: touch.clientX, y: touch.clientY };
  }, { passive: true });
  elements.detailPanel.addEventListener("touchmove", (event) => {
    if (!swipeStart || state.mobileView !== "detail" || isInteractiveTarget(event.target) || isSelectableTextTarget(event.target) || hasActiveTextSelection()) return;
    const touch = event.touches[0];
    const dx = Math.max(0, touch.clientX - swipeStart.x);
    const dy = Math.abs(touch.clientY - swipeStart.y);
    if (dx > 10 && dy < 72) {
      elements.detailPanel.classList.add("swipe-back-armed");
      elements.detailPanel.style.setProperty("--swipe-offset", `${Math.min(dx, 96)}px`);
    }
  }, { passive: true });
  elements.detailPanel.addEventListener("touchend", (event) => {
    if (!swipeStart || state.mobileView !== "detail" || hasActiveTextSelection()) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - swipeStart.x;
    const dy = Math.abs(touch.clientY - swipeStart.y);
    swipeStart = null;
    if (dx > 72 && dy < 56 && dx > dy * 1.4) {
      window.goBackToList(true);
      return;
    }
    elements.detailPanel.classList.remove("swipe-back-armed");
    elements.detailPanel.style.removeProperty("--swipe-offset");
  }, { passive: true });
}

function animateBackToList() {
  elements.detailPanel.classList.remove("swipe-back-armed");
  elements.detailPanel.classList.add("swipe-back-exit");
  window.setTimeout(() => {
    state.mobileView = "list";
    elements.detailPanel.classList.remove("swipe-back-exit");
    elements.detailPanel.style.removeProperty("--swipe-offset");
    syncMobileNavigation();
  }, 180);
}

function bindTopicForm(form, config) {
  const topicField = form.querySelector("textarea[name='topic']");
  const submitButton = form.querySelector("button[type='submit']");
  if (!topicField || !submitButton) return;

  const updateState = () => {
    submitButton.disabled = !topicField.value.trim();
  };

  updateState();
  topicField.addEventListener("input", updateState);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const topic = topicField.value.trim();
    if (!topic) {
      topicField.focus();
      return;
    }
    const originalHtml = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.classList.add("is-busy");
    submitButton.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${escapeHtml(config.pendingText)}</span>`;
    try {
      await config.onSubmit(topic);
      submitButton.classList.add("did-complete");
      submitButton.innerHTML = `<span>${escapeHtml(config.doneText || "Готово")}</span>`;
      window.setTimeout(() => {
        submitButton.classList.remove("did-complete");
        submitButton.innerHTML = originalHtml;
        updateState();
      }, 900);
      return;
    } catch (error) {
      submitButton.classList.add("did-error");
      showRequestError(config.errorPrefix || "Не удалось выполнить действие", error);
      window.setTimeout(() => {
        submitButton.classList.remove("did-error");
        submitButton.innerHTML = originalHtml;
        updateState();
      }, 1200);
    } finally {
      submitButton.disabled = false;
      submitButton.classList.remove("is-busy");
    }
  });
}

function applyTelegramTheme() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  tg.ready();
  tg.expand();
  const bgColor = tg.themeParams.secondary_bg_color;
  const textColor = tg.themeParams.text_color;
  if (bgColor) document.documentElement.style.setProperty("--panel", bgColor);
  if (textColor) document.documentElement.style.setProperty("--text", textColor);
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
      const reel = await fetchJson(`/api/reels/${draftId}`);
      const readyFrames = Array.isArray(reel.frames) ? reel.frames.filter((i) => i.current_asset?.url).length : 0;
      state.reels = state.reels.map((i) => i.draft_id === reel.draft_id ? { ...i, ...reel } : i);
      if (isCurrentReelsDetail(reel.draft_id)) {
        state.selectedReels = reel;
        renderReels();
        if (!isEditingDetailForm()) renderReelsDetail(reel);
      }
      if (readyFrames < (reel.frame_count || 0)) scheduleReelsRefresh(draftId, attempts - 1);
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
      if (readyCount < slideCount) scheduleCarouselRefresh(draftId, attempts - 1);
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

async function loadInbox() {
  const params = new URLSearchParams();
  params.set("limit", "100");
  if (state.inboxKind && state.inboxKind !== "all") params.set("kind", state.inboxKind);
  const data = await fetchJson(`/api/inbox?${params.toString()}`);
  state.inbox = data.items || [];
  state.inboxKind = data.kind || "all";
  renderInbox();
}

async function loadStatus() {
  state.status = await fetchJson("/api/status");
  renderStatus();
}

async function loadPlans() {
  const data = await fetchJson("/api/plans?limit=20");
  state.plans = data.items || [];
  renderPlans();
}

async function loadReels() {
  const data = await fetchJson("/api/reels?limit=30");
  state.reels = data.items || [];
  renderReels();
}

async function loadKeywords() {
  state.keywords = await fetchJson("/api/keywords");
  renderKeywords();
}

async function loadSettings() {
  if (state.settingsSection === "keywords") {
    if (!state.keywords) {
      state.keywords = await fetchJson("/api/keywords");
    }
    renderKeywords();
    return;
  }
  if (!state.status) {
    state.status = await fetchJson("/api/status");
  }
  renderStatus();
}

function renderSettingsSwitcher(activeSection) {
  return `
    <section class="settings-switcher">
      <button class="tab-button${activeSection === "status" ? " active" : ""}" type="button" onclick="openSettingsSection('status')">${uiIcon("gear")}<span>Статус</span></button>
      <button class="tab-button${activeSection === "keywords" ? " active" : ""}" type="button" onclick="openSettingsSection('keywords')">${uiIcon("text")}<span>Ключи</span></button>
    </section>
  `;
}

function currentHandbookMeta() {
  return HANDBOOK_CATEGORY_META[state.tab] || HANDBOOK_CATEGORY_META.aromas;
}

async function loadReferenceAccess() {
  if (state.referenceAccess !== null) return state.referenceAccess;
  try {
    const payload = await fetchJson("/api/references/access");
    state.referenceAccess = Boolean(payload?.allowed);
    state.referenceAccessError = "";
  } catch (error) {
    const message = String(error?.message || "");
    if (message.includes("reference_access_denied") || message.includes("403 Forbidden")) {
      state.referenceAccess = false;
      state.referenceAccessError = "";
    } else {
      state.referenceAccess = null;
      state.referenceAccessError = message || "reference_temporarily_unavailable";
    }
  }
  return state.referenceAccess;
}

async function loadReferences(tabId = state.tab) {
  const meta = HANDBOOK_CATEGORY_META[tabId];
  if (!meta) return;
  if (state.referenceAccess === null) {
    await loadReferenceAccess();
  }
  if (state.referenceAccess === null) {
    renderReferencesUnavailable();
    return;
  }
  if (!state.referenceAccess) {
    renderReferencesLocked();
    return;
  }
  const data = await fetchJson(`/api/references/${meta.category}`);
  state.referenceItems = data.items || [];
  
  // Do not automatically pick the first card if nothing is selected
  const selectedSlug = state.selectedReference?.category === meta.category
    ? state.selectedReference?.slug
    : "";
    
  if (selectedSlug) {
    await openReference(selectedSlug, tabId);
  } else {
    renderReferences();
  }
}

async function openReference(slug, tabId = state.tab) {
  const meta = HANDBOOK_CATEGORY_META[tabId];
  if (!slug || !meta) return;
  elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю карточку справочника")}`;
  enterDetailView();
  state.selectedReference = await fetchJson(`/api/references/${meta.category}/${encodeURIComponent(slug)}`);
  state.selectedReference.category = meta.category;
  state.tab = tabId;
  elements.tabsContainer.querySelectorAll(".tab-button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
  renderReferences();
  enterDetailView();
}

function renderReferencePassport(reference) {
  const parts = [
    reference.key ? `Ключ: ${reference.key}` : "",
    reference.botanical_family ? `Семейство / тип: ${reference.botanical_family}` : "",
    reference.origin_countries ? `Источник / традиция: ${reference.origin_countries}` : "",
    reference.extraction_method ? `Форма / метод: ${reference.extraction_method}` : "",
    reference.volatility ? `Длительность / летучесть: ${reference.volatility}` : "",
  ].filter(Boolean);
  return parts.join("\n");
}

function renderReferenceImage(reference) {
  return `
    <section class="section aroma-hero">
      <img class="aroma-image" src="${escapeHtml(reference.image_url)}" alt="${escapeHtml(reference.image_alt)}" />
      <div class="aroma-image-caption">${escapeHtml(reference.image_alt)}</div>
    </section>
  `;
}

function renderReferences() {
  const meta = currentHandbookMeta();
  const items = state.referenceItems || [];
  const query = (state.referenceSearch || "").trim().toLowerCase();
  const filtered = items.filter((item) => `${item.name} ${item.description || ""}`.toLowerCase().includes(query));
  const reference = state.selectedReference;
  
  elements.listTitle.textContent = meta.title;
  elements.draftCount.textContent = query 
    ? `Найдено ${filtered.length} из ${items.length}` 
    : meta.count(items);
    
  setEmptyState(filtered.length > 0, meta.empty);

  let listContainer = document.getElementById("referenceListContainer");
  if (!listContainer) {
    elements.draftList.innerHTML = `
      <div class="aroma-search">
        <label>${escapeHtml(meta.searchLabel)}<input id="referenceSearchInput" type="search" placeholder="${escapeHtml(meta.searchPlaceholder)}" value="${escapeHtml(state.referenceSearch)}" /></label>
      </div>
      <div id="referenceListContainer" class="plans-list"></div>
    `;
    listContainer = document.getElementById("referenceListContainer");
    document.getElementById("referenceSearchInput")?.addEventListener("input", (e) => {
      state.referenceSearch = e.target.value;
      renderReferences();
    });
  } else {
    const searchInput = document.getElementById("referenceSearchInput");
    if (searchInput) {
      searchInput.placeholder = meta.searchPlaceholder;
      searchInput.value = state.referenceSearch;
      const label = searchInput.closest("label");
      if (label) {
        label.firstChild.textContent = meta.searchLabel;
      }
    }
  }

  listContainer.innerHTML = filtered.map((item) => `
    <article ${interactiveCardAttrs(`Открыть карточку ${item.name}`)} class="draft-card${item.slug === reference?.slug ? " active" : ""} interactive-card" onclick="openReference('${item.slug}', '${state.tab}')">
      <div class="draft-kind">${handbookCategoryIcon(state.tab)}${handbookCardBadge(state.tab, item) ? `<span>${escapeHtml(handbookCardBadge(state.tab, item))}</span>` : ""}</div>
      <h3 class="draft-topic">${escapeHtml(item.name)}</h3>
      <div class="draft-preview">${escapeHtml(item.description || "")}</div>
    </article>
  `).join("");

  if (!reference) {
    elements.draftDetail.innerHTML = `
      ${renderBackButton()}
      <div class="detail-empty">
        ${renderGuidedState({
          eyebrow: meta.title,
          title: "Выберите карточку справочника",
          body: meta.selectPrompt,
        })}
      </div>
    `;
    syncMobileNavigation();
    return;
  }

  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      ${renderReferenceImage(reference)}
      ${aromaSection("Паспорт карточки", renderReferencePassport(reference))}
      ${aromaSection("Описание", reference.description)}
      ${aromaSection("Какие вопросы поднимает", reference.questions)}
      ${aromaSection("Действие на НПС", reference.nps_effect)}
      ${aromaSection("Терапевтические свойства", reference.therapeutic_properties)}
      ${aromaSection("Психологические свойства", reference.psychological_properties)}
      ${aromaSection('Ресурс "+"', reference.resource_values?.plus)}
      ${aromaSection('Ресурс "-"', reference.resource_values?.minus)}
      ${aromaSection("Исторические сведения", reference.history)}
    </div>
  `;
  syncMobileNavigation();
}

function renderReferencesLocked() {
  const meta = currentHandbookMeta();
  elements.listTitle.textContent = meta.title;
  elements.draftCount.textContent = "";
  setEmptyState(true);
  elements.draftList.innerHTML = renderGuidedState({
    eyebrow: meta.title,
    title: "Доступ ограничен",
    body: meta.locked,
    tone: "soft",
  });
  elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({ eyebrow: meta.title, title: "Справочник пока недоступен", body: meta.locked, tone: "soft" })}</div>`;
  syncMobileNavigation();
}

function renderReferencesUnavailable() {
  const meta = currentHandbookMeta();
  const message = "Справочник временно недоступен. Попробуйте открыть раздел ещё раз.";
  elements.listTitle.textContent = meta.title;
  elements.draftCount.textContent = "";
  setEmptyState(true);
  elements.draftList.innerHTML = renderGuidedState({
    eyebrow: "Загрузка",
    title: "Справочник временно недоступен",
    body: message,
    actionLabel: "Повторить",
    action: "retryCurrentTab()",
    tone: "soft",
  });
  elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({ eyebrow: "Загрузка", title: "Справочник временно недоступен", body: message, actionLabel: "Повторить", action: "retryCurrentTab()", tone: "soft" })}</div>`;
  syncMobileNavigation();
}

async function openAroma(slug) {
  if (!slug) return;
  await openReference(slug, "aromas");
}

function renderCreate() {
  elements.listTitle.textContent = "Инструменты";
  elements.draftCount.textContent = "4 типа";
  setEmptyState(true);
  
  elements.draftList.innerHTML = `
    <div class="create-list">
      <article ${interactiveCardAttrs("Выбрать инструмент Пост для соцсетей")} class="create-card${state.selectedCreateTool === 'content' ? ' active' : ''} interactive-card" data-tool="content" onclick="renderCreateTool('content')">
        <div class="draft-kind">${contentKindIcon("content")}<span>контент</span></div>
        <h3 class="draft-topic">Пост для соцсетей</h3>
        <div class="draft-preview">Тредс, Инстаграм или Телеграм.</div>
      </article>
      <article ${interactiveCardAttrs("Выбрать инструмент Сценарий и раскадровка")} class="create-card${state.selectedCreateTool === 'reels' ? ' active' : ''} interactive-card" data-tool="reels" onclick="renderCreateTool('reels')">
        <div class="draft-kind">${contentKindIcon("reels")}<span>рилсы</span></div>
        <h3 class="draft-topic">Сценарий + раскадровка</h3>
        <div class="draft-preview">Сценарий и 4 кадра визуализации.</div>
      </article>
      <article ${interactiveCardAttrs("Выбрать инструмент Контент-план")} class="create-card${state.selectedCreateTool === 'plan' ? ' active' : ''} interactive-card" data-tool="plan" onclick="renderCreateTool('plan')">
        <div class="draft-kind">${contentKindIcon("plan")}<span>план</span></div>
        <h3 class="draft-topic">Контент-план</h3>
        <div class="draft-preview">Сбор трендов и план на неделю.</div>
      </article>
      <article ${interactiveCardAttrs("Выбрать инструмент Карусель")} class="create-card${state.selectedCreateTool === 'carousel' ? ' active' : ''} interactive-card" data-tool="carousel" onclick="renderCreateTool('carousel')">
        <div class="draft-kind">${contentKindIcon("carousel")}<span>карусель</span></div>
        <h3 class="draft-topic">Карусель</h3>
        <div class="draft-preview">5 слайдов с промптами для картинок.</div>
      </article>
    </div>
  `;

  if (!state.selectedCreateTool) {
    elements.draftDetail.innerHTML = `
      <div class="detail-empty">
        ${renderGuidedState({
          eyebrow: "Создание",
          title: "Выберите формат для старта",
          body: "Слева доступны быстрые сценарии: пост, рилс, план или карусель. Откройте нужный инструмент, и мы сразу покажем форму.",
        })}
      </div>
    `;
    syncMobileNavigation();
    return;
  }

  renderCreateTool(state.selectedCreateTool);
}

function renderCreateTool(toolId) {
  state.selectedCreateTool = toolId;
  
  // Update active state in the list
  elements.draftList.querySelectorAll(".create-card").forEach(card => {
    card.classList.toggle("active", card.dataset.tool === toolId);
  });

  let formHtml = '';
  if (toolId === 'content') {
    formHtml = `
      <section class="section create-tool-panel">
        <h3>Создать контент</h3>
        <form class="create-form" data-create-content>
          <label>Тема<textarea name="topic" placeholder="Например: как мягко переключиться после рабочего дня"></textarea></label>
          <div class="field-grid">
            <label>Цель<select name="goal_key"><option value="trust">Доверие</option><option value="authority">Экспертность</option><option value="engagement">Вовлечённость</option><option value="sales">Продажи</option></select></label>
            <label>Формат<select name="format_key"><option value="threads">Тредс</option><option value="instagram">Инстаграм</option><option value="telegram">Телеграм</option></select></label>
          </div>
          <button class="primary-button" type="submit">Сгенерировать текст</button>
        </form>
      </section>
    `;
  } else if (toolId === 'reels') {
    formHtml = `
      <section class="section create-tool-panel">
        <h3>Создать рилс</h3>
        <form class="create-form" data-create-reels>
          <label>Тема<textarea name="topic" placeholder="Например: вечерний сенсорный ритуал"></textarea></label>
          <button class="primary-button" type="submit">Сгенерировать раскадровку</button>
        </form>
      </section>
    `;
  } else if (toolId === 'plan') {
    formHtml = `
      <section class="section create-tool-panel">
        <h3>Создать план</h3>
        <form class="create-form" data-create-plan>
          <div class="detail-preview">Собирает актуальные тренды и сохраняет недельный план.</div>
          <button class="primary-button" type="submit">Собрать план на неделю</button>
        </form>
      </section>
    `;
  } else if (toolId === 'carousel') {
    formHtml = `
      <section class="section create-tool-panel">
        <h3>Создать карусель</h3>
        <form class="create-form" data-create-carousel>
          <label>Тема<textarea name="topic" placeholder="Например: утренний ритуал с маслами"></textarea></label>
          <button class="primary-button" type="submit">Сгенерировать карусель</button>
        </form>
      </section>
    `;
  }

  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      ${formHtml}
    </div>
  `;
  
  enterDetailView();

  // Re-bind forms
  const cForm = elements.draftDetail.querySelector("[data-create-content]");
  if (cForm) bindTopicForm(cForm, { pendingText: "Создаю...", onSubmit: async (t) => {
    const g = cForm.querySelector("select[name='goal_key']").value;
    const f = cForm.querySelector("select[name='format_key']").value;
    const pending = openPendingDraftCreation(f, t);
    try {
      const d = await fetchJson("/api/generate/content", {
        method: "POST",
        timeout: 45000,
        body: JSON.stringify({ topic: t, goal_key: g, format_key: f }),
      });
      finalizePendingDraftCreation(d);
      await openDraft(d.draft_id);
    } catch (error) {
      if (error?.message === "request_timeout") {
        await recoverPendingDraftCreation(f, t, pending.draft_id);
        return;
      }
      throw error;
    }
  }});

  const rForm = elements.draftDetail.querySelector("[data-create-reels]");
  if (rForm) bindTopicForm(rForm, { pendingText: "Создаю...", onSubmit: async (t) => {
    const r = await fetchJson("/api/generate/reels", { method: "POST", body: JSON.stringify({ topic: t }) });
    state.selectedReels = r; state.selectedFrameIndex = 0; setTab("reels"); await loadReels(); await openReels(r.draft_id);
  }});

  const pForm = elements.draftDetail.querySelector("[data-create-plan]");
  if (pForm) pForm.addEventListener("submit", async (e) => {
    e.preventDefault(); const b = pForm.querySelector("button"); b.disabled = true; b.textContent = "Собираю...";
    try { const p = await fetchJson("/api/generate/plan", { method: "POST", body: JSON.stringify({}) });
      state.selectedPlan = p; setTab("plans"); await loadPlans(); renderPlanDetail(p); enterDetailView();
    } finally { b.disabled = false; b.textContent = "Собрать план на неделю"; }
  });

  const carForm = elements.draftDetail.querySelector("[data-create-carousel]");
  if (carForm) bindTopicForm(carForm, { pendingText: "Создаю...", onSubmit: async (t) => {
    const pending = openPendingDraftCreation("carousel", t);
    try {
      const d = await fetchJson("/api/generate/carousel", {
        method: "POST",
        timeout: 45000,
        body: JSON.stringify({ topic: t }),
      });
      finalizePendingDraftCreation(d);
      await openDraft(d.draft_id);
    } catch (error) {
      if (error?.message === "request_timeout") {
        await recoverPendingDraftCreation("carousel", t, pending.draft_id);
        return;
      }
      throw error;
    }
  }});
}

function renderAromas() { renderReferences(); }

function aromaSection(title, content) {
  if (!content) return "";
  return `<section class="section"><h3>${sectionHeadingIcon(title)}${escapeHtml(title)}</h3><div class="detail-preview detail-markdown">${renderMarkdown(content)}</div></section>`;
}

function renderAromasLocked() { renderReferencesLocked(); }

function renderDraftList() {
  elements.listTitle.textContent = "Черновики";
  elements.draftCount.textContent = `${state.drafts.length} шт`;
  setEmptyState(state.drafts.length > 0);
  elements.draftList.innerHTML = state.drafts.map((d) => `
    <article ${interactiveCardAttrs(`Открыть черновик ${d.topic}`)} class="draft-card overview-card${d.draft_id === state.draftId ? " active" : ""}${d.generation_pending ? " is-pending" : ""} interactive-card" onclick="openDraft('${d.draft_id}')">
      <div class="overview-card-top">
        <div class="draft-kind">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))}</span></div>
        <span class="overview-card-date">${escapeHtml(formatPlanDate(d.created_at) || "Новый черновик")}</span>
      </div>
      <h3 class="draft-topic">${escapeHtml(d.topic)}</h3>
      <div class="draft-preview">${escapeHtml(stripMarkdown(d.preview || "Без превью"))}</div>
      <div class="draft-meta overview-card-footer">
        ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
        ${d.generation_pending ? tagMarkup(draftGenerationLabel(d), "pending") : ""}
        ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
      </div>
    </article>
  `).join("");
  syncMobileNavigation();
}

async function openDraft(id) {
  if (isPendingDraftId(id) && state.selected?.draft_id === id) {
    renderDraftList();
    renderDraftDetail(state.selected);
    enterDetailView();
    return;
  }
  elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю черновик")}`;
  enterDetailView();
  const d = await fetchJson(`/api/drafts/${id}`, { timeout: 20000 });
  state.selected = d; state.draftId = id;
  renderDraftList(); renderDraftDetail(d); enterDetailView();
}

async function openReels(id) {
  elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю рилс")}`;
  enterDetailView();
  clearBackgroundRefreshes();
  const r = await fetchJson(`/api/reels/${id}`);
  state.selectedReels = r;
  renderReelsDetail(r);
  enterDetailView();
}

async function openPlan(id) {
  elements.draftDetail.innerHTML = `${renderBackButton()}${renderDetailLoader("Открываю план")}`;
  enterDetailView();
  const p = await fetchJson(`/api/plans/${id}`);
  state.selectedPlan = p;
  state.plans = state.plans.map((item) => item.plan_id === p.plan_id ? { ...item, ...p } : item);
  renderPlanDetail(p);
  enterDetailView();
}

async function generateDraftFromPlan(planId, entryIndex, button) {
  const apply = async () => {
    const payload = await fetchJson(`/api/plans/${planId}/generate`, {
      method: "POST",
      body: JSON.stringify({ entry_index: entryIndex }),
    });
    const draft = payload?.draft || null;
    if (draft?.kind === "reels") {
      state.reels = [draft, ...state.reels.filter((item) => item.draft_id !== draft.draft_id)];
    } else if (draft?.draft_id) {
      upsertDraftSummary(draftSummaryFromDraft(draft));
    }
    await loadPlans();
    await openPlan(planId);
    return draft;
  };
  const draft = button instanceof HTMLElement
    ? await withButtonFeedback(button, "Создаю...", apply, "Создано")
    : await apply();
  if (draft?.draft_id) {
    const tg = window.Telegram?.WebApp;
    if (tg?.showAlert) tg.showAlert("Черновик создан и привязан к плану");
  }
}

async function openPlanRelatedDraft(kind, draftId) {
  if (!draftId) return;
  if (kind === "reels") {
    setTab("reels");
    await loadReels();
    await openReels(draftId);
    return;
  }
  setTab("drafts");
  await loadDrafts();
  await openDraft(draftId);
}

function renderDraftDetail(d) {
  if (isPendingDraftId(d?.draft_id)) {
    elements.draftDetail.innerHTML = `
      <div class="detail-grid detail-grid-pending">
        ${renderBackButton()}
        <div class="detail-top">
          <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))} • ${escapeHtml(sourceLabel(d.source || "/miniapp"))}</span></p>
          <h2 class="detail-title">${escapeHtml(d.topic || "Создаём черновик")}</h2>
          <div class="draft-meta">
            ${tagMarkup("Черновик", "status-neutral")}
            ${tagMarkup("Ещё генерируется", "pending")}
          </div>
        </div>
        ${renderDetailLoader("Генерирую карточку", "Сохраняю черновик и подгружаю содержимое.", "detail-loader-card-compact")}
      </div>
    `;
    syncMobileNavigation();
    return;
  }
  const p = d.payload || {};
  const mainText = p.caption || p.scenario || "";
  const heroFacts = [
    detailFactMarkup("Тип", kindLabel(d.kind)),
    detailFactMarkup("Источник", sourceLabel(d.source)),
    detailFactMarkup("Статус", statusLabel(d.status)),
    isContentReviewKind(d.kind) ? detailFactMarkup("Реакция", feedbackLabel(d.feedback)) : "",
    detailFactMarkup("Создан", formatPlanDate(d.created_at)),
  ].join("");
  const reviewActions = isContentReviewKind(d.kind)
    ? `
      <section class="section section-primary">
        <div class="section-heading">
          <h3>${uiIcon("text")}Редакторский review</h3>
          <p>Сначала поправьте главный текст и позиционирование, затем уточните supporting-поля и сохраните версию для согласования.</p>
        </div>
        <div class="content-review-form">
          <div class="content-review-highlight">
            <label><span>Тема</span><textarea id="contentTopicField" placeholder="Тема draft">${escapeHtml(d.topic || "")}</textarea></label>
            <label><span>Angle</span><textarea id="contentAngleField" placeholder="Опорный angle">${escapeHtml(p.angle || "")}</textarea></label>
            <label><span>Hook</span><textarea id="contentHookField" placeholder="Хук">${escapeHtml(p.hook || "")}</textarea></label>
          </div>
          <label class="content-review-lead"><span>Основной текст</span><textarea id="contentCaptionField" placeholder="Текст поста">${escapeHtml(p.caption || "")}</textarea></label>
          <div class="content-review-support-grid">
            <label><span>CTA</span><textarea id="contentCtaField" placeholder="Призыв к действию">${escapeHtml(p.cta || "")}</textarea></label>
            <label><span>Hashtags</span><textarea id="contentHashtagsField" placeholder="#теги">${escapeHtml(p.hashtags || "")}</textarea></label>
            <label><span>Visual prompt</span><textarea id="contentVisualPromptField" placeholder="Промпт для визуала">${escapeHtml(p.visual_prompt || "")}</textarea></label>
            <label><span>Заметка редактора</span><textarea id="contentEditorNotesField" placeholder="Что поправить, на что обратить внимание">${escapeHtml(p.editor_notes || "")}</textarea></label>
          </div>
          <div class="actions-row review-actions">
            <button class="primary-button" type="button" onclick="saveContentReviewDraft('${d.draft_id}', this)">${actionLabel("approve", "Сохранить правки")}</button>
            <button class="secondary-button" type="button" onclick="polishContentDraft('${d.draft_id}', this)">${actionLabel("sparkle", "AI polish")}</button>
          </div>
        </div>
      </section>
      <section class="section section-accent">
        <div class="section-heading">
          <h3>${uiIcon("chat")}Результат публикации</h3>
          <p>После публикации отметьте фактический результат, чтобы видеть, какие материалы реально срабатывают у аудитории.</p>
        </div>
        <div class="draft-meta">
          ${tagMarkup(feedbackLabel(d.feedback), feedbackTone(d.feedback))}
        </div>
        <div class="actions-row">
          <button class="secondary-button" type="button" onclick="updateDraft('feedback', {feedback:'worked'}, this)">${actionLabel("approve", "Сработало")}</button>
          <button class="secondary-button" type="button" onclick="updateDraft('feedback', {feedback:'missed'}, this)">${actionLabel("reject", "Не сработало")}</button>
          <button class="secondary-button" type="button" onclick="updateDraft('feedback', {feedback:''}, this)">${actionLabel("back", "Сбросить")}</button>
        </div>
      </section>
    `
    : "";
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <div class="detail-top detail-hero">
        <div class="detail-hero-copy">
          <p class="eyebrow">${contentKindIcon(d.kind)}<span>${escapeHtml(kindLabel(d.kind))} • ${escapeHtml(sourceLabel(d.source))}</span></p>
          <h2 class="detail-title">${escapeHtml(d.topic)}</h2>
          <p class="detail-summary">${escapeHtml(draftHeroSummary(d, p, mainText))}</p>
          <div class="draft-meta">
            ${tagMarkup(statusLabel(d.status), statusTone(d.status))}
            ${isContentReviewKind(d.kind) ? tagMarkup(feedbackLabel(d.feedback), feedbackTone(d.feedback)) : ""}
            ${tagMarkup(sourceLabel(d.source), sourceTone(d.source))}
          </div>
        </div>
        <div class="detail-hero-side">
          <div class="detail-facts">${heroFacts}</div>
        </div>
        <div class="actions-row detail-actions">
          <button class="secondary-button" onclick="updateDraft('status', {status:'approved'}, this)">${actionLabel("approve", "Согласовать")}</button>
          <button class="secondary-button" onclick="updateDraft('status', {status:'rejected'}, this)">${actionLabel("reject", "Не согласовано")}</button>
          <button class="secondary-button" onclick="sendDraftToChat('${d.draft_id}', this)">${actionLabel("chat", "В чат")}</button>
          ${d.kind === "carousel" ? `<button class="secondary-button" onclick="downloadCarouselPptx('${d.draft_id}', this)">${actionLabel("pptx", "Скачать PPTX")}</button>` : ""}
          ${d.kind === "carousel" ? `<button class="secondary-button" onclick="regenerateCarouselAll('${d.draft_id}', this)">${actionLabel("regenerate", "Перегенерировать все")}</button>` : ""}
          <button class="secondary-button" onclick="deleteDraft('${d.draft_id}', 'drafts', this)">${actionLabel("trash", "Удалить")}</button>
        </div>
      </div>
      ${payloadSection("Превью", d.preview)}
      ${payloadSection("Угол", p.angle)}
      ${payloadSection("Текст", mainText)}
      ${payloadSection("CTA", p.cta)}
      ${reviewActions}
      ${renderSlides(d.draft_id, p.slides, p.img_prompts, p.slide_images, p.img_prompt_notes, p.slide_image_versions)}
      ${promptSection("Промпт для изображения", p.visual_prompt)}
    </div>
  `;
  if (d.kind === "carousel") {
    const readyCount = (p.slide_images || []).filter(Boolean).length;
    const slideCount = (p.slides || []).length;
    if (readyCount < slideCount) scheduleCarouselRefresh(d.draft_id);
  }
}

function renderEmptyDetail() {
  elements.draftDetail.innerHTML = `
    ${renderBackButton()}
    <div class="detail-empty">
      ${renderGuidedState({
        eyebrow: "Детали",
        title: "Выберите элемент из списка",
        body: "Откройте карточку слева, чтобы увидеть детали, правки и быстрые действия.",
      })}
    </div>
  `;
  syncMobileNavigation();
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
  history.replaceState({}, "", `${window.location.pathname}?${p.toString()}`);
  
  elements.tabsContainer.querySelectorAll(".tab-button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
  elements.filtersContainer.hidden = (t !== "drafts");
  
  // Clear panels immediately to prevent showing tools/content from previous tab
  elements.listTitle.textContent = "Загрузка...";
  elements.draftCount.textContent = "";
  elements.draftList.innerHTML = renderPanelLoader("Загружаю раздел");
  elements.draftDetail.innerHTML = renderDetailLoader("Загружаю раздел");
  
  syncMobileNavigation();
}

async function loadCurrentTab() {
  if (state.tab === "create") return renderCreate();
  if (state.tab === "inbox") return await loadInbox();
  if (state.tab === "plans") return await loadPlans();
  if (state.tab === "reels") return await loadReels();
  if (HANDBOOK_CATEGORY_META[state.tab]) return await loadReferences(state.tab);
  if (state.tab === "settings") return await loadSettings();
  if (state.tab === "status") return await loadStatus();
  if (state.tab === "keywords") return await loadKeywords();
  await loadDrafts();
}

async function safeLoadCurrentTab(prefix = "Не удалось загрузить раздел") {
  try {
    await loadCurrentTab();
    hideBootFallback();
    return true;
  } catch (error) {
    console.error("miniapp runtime tab load failed", error);
    showRuntimeWarning(prefix, error);
    return false;
  }
}

async function loadInitialScreen() {
  if (startupLoadInFlight) return false;
  startupLoadInFlight = true;
  showBootFallback(
    "Загружаю интерфейс",
    "Если экран остаётся пустым дольше пары секунд, попробуйте открыть mini app ещё раз.",
    false,
  );
  window.clearTimeout(bootstrapWatchdogTimer);
  bootstrapWatchdogTimer = window.setTimeout(() => {
    if (!appBootstrapped) {
      showBootFallback(
        "Интерфейс загружается слишком долго",
        "Похоже, стартовый экран отвечает медленнее обычного. Можно повторить загрузку.",
        true,
      );
    }
  }, 1800);

  const result = await Promise.race([
    safeLoadCurrentTab("Не удалось загрузить вкладку"),
    new Promise((resolve) => {
      window.setTimeout(() => resolve("timeout"), 8000);
    }),
  ]);

  window.clearTimeout(bootstrapWatchdogTimer);
  startupLoadInFlight = false;

  if (result === true) {
    appBootstrapped = true;
    hideBootFallback();
    return true;
  }
  if (result === "timeout") {
    showBootFallback(
      "Интерфейс загружается слишком долго",
      "Мы не дождались первого ответа. Попробуйте повторить загрузку.",
      true,
    );
    return false;
  }
  return false;
}

async function bootstrap() {
  applyTelegramTheme();
  bindSwipeBack();
  bindKeyboardDismiss();
  bindCardKeyboardActivation();
  bindKeyboardViewportAssist();
  elements.modeContent.addEventListener("click", () => { setMode("content"); void safeLoadCurrentTab("Не удалось загрузить раздел контента"); });
  elements.modeHandbook.addEventListener("click", () => { setMode("handbook"); void safeLoadCurrentTab("Не удалось загрузить справочник"); });
  elements.settingsButton?.addEventListener("click", () => {
    state.settingsSection = state.settingsSection || "status";
    setMode("content");
    setTab("settings");
    void safeLoadCurrentTab("Не удалось загрузить настройки");
  });

  [elements.kindFilter, elements.statusFilter, elements.feedbackFilter].forEach(f => f.addEventListener("change", loadDrafts));

  elements.queryFilter.addEventListener("input", () => {
    clearTimeout(reelRefreshTimer);
    reelRefreshTimer = setTimeout(() => {
      if (state.tab === "drafts") {
        void safeLoadCurrentTab("Не удалось обновить черновики");
      }
    }, 300);
  });
  if (MODE_TABS.handbook.find(t => t.id === state.tab)) state.mode = "handbook";
  setMode(state.mode);
  if (state.mode === "content") {
    void loadReferenceAccess();
  }
  try {
    await loadInitialScreen();
  } catch (error) {
    console.error("miniapp bootstrap fallback failed", error);
  }
}

if (elements.bootFallbackReload) {
  elements.bootFallbackReload.addEventListener("click", () => {
    if (appBootstrapped) {
      window.retryCurrentTab();
      return;
    }
    void loadInitialScreen();
  });
}

window.retryCurrentTab = () => {
  elements.draftList.innerHTML = renderPanelLoader("Повторяю загрузку");
  void safeLoadCurrentTab("Не удалось загрузить вкладку");
};

window.addEventListener("error", () => {
  if (appBootstrapped) return;
  showBootFallback(
    "Интерфейс временно недоступен",
    "Во время загрузки произошла ошибка. Попробуйте обновить экран.",
    true,
  );
});

window.addEventListener("unhandledrejection", () => {
  if (appBootstrapped) return;
  showBootFallback(
    "Интерфейс временно недоступен",
    "Во время загрузки произошла ошибка. Попробуйте обновить экран.",
    true,
  );
});

bootstrap();

// Global Window functions
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

function renderInbox() {
  elements.listTitle.textContent = "Согласование";
  elements.draftCount.textContent = `${state.inbox.length} на проверке`;
  setEmptyState(state.inbox.length > 0, "Очередь пуста.");
  elements.draftList.innerHTML = state.inbox.map(i => `
    <article ${interactiveCardAttrs(`Открыть материал на согласовании ${i.topic}`)} class="draft-card overview-card${i.draft_id === state.draftId ? " active" : ""} interactive-card" onclick="openDraft('${i.draft_id}')">
      <div class="overview-card-top">
        <div class="draft-kind">${contentKindIcon(i.kind)}<span>${escapeHtml(kindLabel(i.kind))}</span></div>
        <span class="overview-card-date">${escapeHtml(formatPlanDate(i.created_at) || "На проверке")}</span>
      </div>
      <h4 class="draft-topic">${escapeHtml(i.topic)}</h4>
      <div class="draft-preview">${escapeHtml(stripMarkdown(i.preview || ""))}</div>
      <div class="draft-meta overview-card-footer">
        ${tagMarkup(statusLabel(i.status || "in_review"), statusTone(i.status || "in_review"))}
        ${tagMarkup(sourceLabel(i.source || "/content"), sourceTone(i.source || "/content"))}
      </div>
    </article>
  `).join("");
  syncMobileNavigation();
}

function renderStatus() {
  const items = state.status?.items || [];
  const inSettings = state.tab === "settings";
  elements.listTitle.textContent = inSettings ? "Настройки" : "Статус";
  elements.draftCount.textContent = `${items.length} источников`;
  elements.draftList.innerHTML = `
    ${inSettings ? renderSettingsSwitcher("status") : ""}
    ${items.map(i => `
    <article class="status-card"><strong>${escapeHtml(i.source)}</strong> <span class="${i.enabled ? 'status-good' : 'status-bad'}">${i.enabled ? 'вкл' : 'выкл'}</span></article>
  `).join("")}
  `;
  elements.draftDetail.innerHTML = renderBackButton() + `<div class="detail-empty">${inSettings ? "Настройки mini app и системные параметры." : "Настройки mini app и состояния источников."}</div>`;
  if (!items.length) {
    elements.draftDetail.innerHTML = renderBackButton() + `<div class="detail-empty">${renderGuidedState({ eyebrow: "Настройки", title: "Источники еще не показаны", body: "Здесь появятся переключатели и системные состояния источников, как только раздел загрузит конфигурацию." })}</div>`;
  }
  syncMobileNavigation();
}

function renderPlans() {
  elements.listTitle.textContent = "Планы";
  elements.draftCount.textContent = `${state.plans.length} шт`;
  setEmptyState(state.plans.length > 0, {
    eyebrow: "Планы",
    title: "Планы пока не собраны",
    body: "Соберите недельный план во вкладке Создать, и здесь появятся карточки с темами и связями к черновикам.",
    actionLabel: "Открыть создание",
    action: "openCreateTool('plan')",
  });
  elements.draftList.innerHTML = state.plans.map(p => `
    <article ${interactiveCardAttrs(`Открыть план ${p.plan_id}`)} class="plan-card overview-card${p.plan_id === state.selectedPlan?.plan_id ? " active" : ""} interactive-card" onclick="openPlan('${p.plan_id}')">
      <div class="overview-card-top">
        <div class="draft-kind">${contentKindIcon("plan")}<span>План</span></div>
        <span class="overview-card-date">${escapeHtml(formatPlanDate(p.created_at) || p.plan_id)}</span>
      </div>
      <h3 class="draft-topic">${escapeHtml(formatPlanDate(p.created_at) ? `План от ${formatPlanDate(p.created_at)}` : p.plan_id)}</h3>
      <div class="draft-preview">${escapeHtml(stripMarkdown(p.raw_text || ""))}</div>
      <div class="draft-meta overview-card-footer">
        ${tagMarkup(`${(p.entries || []).length} карточек`, "source-plan")}
        ${tagMarkup(`${(p.related_drafts || []).length} черновиков`, "status-review")}
      </div>
    </article>
  `).join("");
  if (!state.selectedPlan) {
    elements.draftDetail.innerHTML = `${renderBackButton()}<div class="detail-empty">${renderGuidedState({ eyebrow: "План", title: "Откройте план недели", body: "Внутри плана можно создавать draft по каждой карточке и сразу открывать связанный материал." })}</div>`;
  }
  syncMobileNavigation();
}

function renderReels() {
  elements.listTitle.textContent = "Рилсы";
  elements.draftCount.textContent = `${state.reels.length} шт`;
  setEmptyState(state.reels.length > 0, {
    eyebrow: "Рилсы",
    title: "Рилсы пока не созданы",
    body: "Откройте вкладку Создать и соберите новый рилс: сценарий, концепцию и кадры для раскадровки.",
    actionLabel: "Создать рилс",
    action: "openCreateTool('reels')",
  });
  elements.draftList.innerHTML = state.reels.map(r => `
    <article ${interactiveCardAttrs(`Открыть рилс ${r.topic}`)} class="reels-card overview-card${r.draft_id === state.selectedReels?.draft_id ? " active" : ""} interactive-card" onclick="openReels('${r.draft_id}')">
      <div class="overview-card-top">
        <div class="draft-kind">${contentKindIcon("reels")}<span>Рилс</span></div>
        <span class="overview-card-date">${escapeHtml(formatPlanDate(r.created_at) || "Видео")}</span>
      </div>
      <h3 class="draft-topic">${escapeHtml(r.topic)}</h3>
      <div class="draft-preview">${escapeHtml(stripMarkdown(r.preview || ""))}</div>
      <div class="draft-meta overview-card-footer">
        ${tagMarkup(statusLabel(r.status || "draft"), statusTone(r.status || "draft"))}
        ${tagMarkup(`${r.images_ready || 0}/${r.frame_count || 0} кадров`, "progress")}
        ${tagMarkup(sourceLabel(r.source || "/miniapp"), sourceTone(r.source || "/miniapp"))}
      </div>
    </article>
  `).join("");
  syncMobileNavigation();
}

function renderReelsDetail(r) {
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <div class="detail-top">
        <p class="eyebrow">${uiIcon("reel")}<span>Рилсы • ${escapeHtml(sourceLabel(r.source || "/miniapp"))}</span></p>
        <h2 class="detail-title">${escapeHtml(r.topic)}</h2>
        <div class="draft-meta">
          ${tagMarkup(statusLabel(r.status || "draft"), statusTone(r.status || "draft"))}
          ${tagMarkup(`${r.images_ready || 0}/${r.frame_count || 0} кадров`, "progress")}
          ${tagMarkup(sourceLabel(r.source || "/miniapp"), sourceTone(r.source || "/miniapp"))}
        </div>
        <div class="actions-row">
          <button class="secondary-button" type="button" onclick="saveReelsScenario('${r.draft_id}', this)">${actionLabel("text", "Сохранить концепцию")}</button>
          <button class="secondary-button" type="button" onclick="regenerateReelsStoryboard('${r.draft_id}', this)">${actionLabel("regenerate", "Пересобрать рилс")}</button>
          <button class="secondary-button" type="button" onclick="regenerateAllReelsFrames('${r.draft_id}', this)">${actionLabel("reel", "Сгенерировать кадры")}</button>
          <button class="secondary-button" type="button" onclick="updateDraft('status', {status:'rejected'}, this)">${actionLabel("reject", "Не согласовано")}</button>
          <button class="secondary-button" type="button" onclick="sendDraftToChat('${r.draft_id}', this)">${actionLabel("chat", "В чат")}</button>
          <button class="secondary-button" type="button" onclick="deleteDraft('${r.draft_id}', 'reels', this)">${actionLabel("trash", "Удалить")}</button>
        </div>
      </div>
      <section class="section">
        <h3>${sectionHeadingIcon("Сценарий")}Концепция и сценарий</h3>
        <label class="prompt-note-field">
          <span>Концепция</span>
          <textarea id="reelsConceptField" placeholder="Коротко: идея, настроение, подход">${escapeHtml(r.payload?.concept || "")}</textarea>
        </label>
        <label class="prompt-note-field">
          <span>Сценарий</span>
          <textarea id="reelsScenarioField" placeholder="Полный текст сценария">${escapeHtml(r.payload?.scenario || "")}</textarea>
        </label>
      </section>
      ${renderReelsFrames(r.draft_id, r.frames)}
    </div>
  `;
}

function renderPlanDetail(p) {
  const entries = Array.isArray(p.entries) ? p.entries : [];
  const relatedDrafts = Array.isArray(p.related_drafts) ? p.related_drafts : [];
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <div class="detail-top">
        <p class="eyebrow">${uiIcon("card")}<span>План • ${escapeHtml(formatPlanDate(p.created_at) || p.plan_id)}</span></p>
        <h2 class="detail-title">${escapeHtml(p.plan_id)}</h2>
        <div class="draft-meta">
          ${tagMarkup(`${entries.length} карточек`, "source-plan")}
          ${tagMarkup(`${relatedDrafts.length} связанных черновиков`, "status-review")}
        </div>
      </div>
      <section class="section">
        <h3>${uiIcon("text")}Краткое описание плана</h3>
        <div class="detail-preview detail-markdown">${renderMarkdown(p.raw_text)}</div>
      </section>
      <section class="section">
        <h3>${uiIcon("slides")}Карточки плана</h3>
        <div class="plan-entries">
          ${entries.map((entry, index) => {
            const related = relatedDraftsForEntry(p, entry);
            return `
              <article class="plan-entry-card">
                <div class="plan-entry-top">
                  <div>
                    <strong class="plan-entry-title">${escapeHtml(entry.topic || `Карточка ${index + 1}`)}</strong>
                    <div class="draft-meta">
                      ${entry.day_label ? tagMarkup(entry.day_label, "status-neutral") : ""}
                      ${entry.platform ? tagMarkup(entry.platform, "source-content") : ""}
                      ${entry.goal ? tagMarkup(entry.goal, "status-review") : ""}
                      ${tagMarkup(planEntryFormatLabel(entry), "source-plan")}
                    </div>
                  </div>
                  <button class="primary-button" type="button" onclick="generateDraftFromPlan('${p.plan_id}', ${index}, this)">${actionLabel("sparkle", `Создать ${planEntryFormatLabel(entry)}`)}</button>
                </div>
                ${entry.angle ? `<div class="detail-preview">${escapeHtml(entry.angle)}</div>` : ""}
                ${related.length ? `
                  <div class="related-drafts-inline">
                    ${related.map((draft) => `
                      <button class="secondary-button" type="button" onclick="openPlanRelatedDraft('${escapeHtml(draft.kind)}', '${escapeHtml(draft.draft_id)}')">${actionLabel(draft.kind === "reels" ? "reel" : "eye", `Открыть ${kindLabel(draft.kind)}`)}</button>
                    `).join("")}
                  </div>
                ` : `
                  <div class="plan-entry-hint">Черновик по этой карточке ещё не создан.</div>
                `}
              </article>
            `;
          }).join("")}
        </div>
      </section>
    </div>
  `;
}

function renderKeywords() {
  const inSettings = state.tab === "settings";
  const topics = state.keywords?.items || [];
  const selectedTopic = topics.find((topic) => topic.topic_idx === state.selectedKeywordTopicIdx) || null;
  elements.listTitle.textContent = inSettings ? "Настройки" : "Ключи";
  elements.draftCount.textContent = `${topics.length} тем`;
  setEmptyState(topics.length > 0, {
    eyebrow: "Ключи",
    title: "Темы пока не загружены",
    body: "Когда справочник ключей будет доступен, здесь появятся темы с RU/EN ключами и тегами для редактирования.",
  });
  elements.draftList.innerHTML = `
    ${inSettings ? renderSettingsSwitcher("keywords") : ""}
    ${topics.map(t => `
    <article ${interactiveCardAttrs(`Открыть тему ${t.name}`)} class="keyword-topic${t.topic_idx === state.selectedKeywordTopicIdx ? " active" : ""} interactive-card" onclick="openKeywordTopic(${t.topic_idx})">
      <h3>${escapeHtml(t.name)}</h3>
      <div class="draft-meta">
        <span class="tag">${escapeHtml(`${Object.values(t.fields || {}).reduce((sum, items) => sum + (Array.isArray(items) ? items.length : 0), 0)} ключей`)}</span>
      </div>
    </article>
  `).join("")}
  `;
  if (!selectedTopic) {
    elements.draftDetail.innerHTML = renderBackButton() + `<div class="detail-empty">${renderGuidedState({ eyebrow: "Ключи", title: "Откройте тему для редактирования", body: "Внутри темы можно добавлять и удалять RU/EN ключи и теги без выхода из mini app." })}</div>`;
    syncMobileNavigation();
    return;
  }
  elements.draftDetail.innerHTML = `
    <div class="detail-grid">
      ${renderBackButton()}
      <div class="detail-top">
        <p class="eyebrow">${uiIcon("text")}<span>Ключи</span></p>
        <h2 class="detail-title">${escapeHtml(selectedTopic.name)}</h2>
      </div>
      <section class="section">
        <h3>${uiIcon("card")}Редактор ключей</h3>
        <div class="keyword-fields">
          ${keywordFieldEntries(selectedTopic).map(({ field, label, items }) => `
            <div class="keyword-field">
              <strong>${escapeHtml(label)}</strong>
              <div class="keyword-items">
                ${items.map((item) => `
                  <span class="keyword-chip">
                    <span>${escapeHtml(item)}</span>
                    <button type="button" aria-label="Удалить ${escapeHtml(item)}" onclick='removeKeywordItem(${selectedTopic.topic_idx}, ${JSON.stringify(String(field))}, ${JSON.stringify(String(item))}, this)'>×</button>
                  </span>
                `).join("") || `<span class="plan-entry-hint">Пока пусто.</span>`}
              </div>
              <form class="keyword-form" onsubmit='event.preventDefault(); addKeywordItem(${selectedTopic.topic_idx}, ${JSON.stringify(String(field))}, this, this.querySelector("button"));'>
                <input name="word" type="text" placeholder="Добавить значение" />
                <button class="secondary-button" type="submit">${actionLabel("plus", "Добавить")}</button>
              </form>
            </div>
          `).join("")}
        </div>
      </section>
    </div>
  `;
  syncMobileNavigation();
}
