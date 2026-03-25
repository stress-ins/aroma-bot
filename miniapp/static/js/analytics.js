/**
 * Lightweight usage analytics tracker.
 * Batches events and flushes every 5 seconds (or on page unload via sendBeacon).
 */
export function createAnalyticsModule(deps) {
  const { getInitDataHeaders } = deps;
  let sessionId = crypto.randomUUID();
  let queue = [];
  let flushTimer = null;

  /**
   * Queue an analytics event for batched delivery.
   * @param {string} eventName - e.g. "page_view", "draft_create", "publish"
   * @param {string} [category=""] - "navigation", "content", "reference", "social"
   * @param {object} [data={}] - arbitrary event payload
   */
  function track(eventName, category, data) {
    queue.push({
      event_name: eventName,
      category: category || "",
      data: data || {},
      session_id: sessionId,
      ts: Date.now(),
    });
    if (!flushTimer) {
      flushTimer = setTimeout(flush, 5000);
    }
  }

  /**
   * Flush queued events to the backend.
   */
  async function flush() {
    if (!queue.length) return;
    const batch = queue.splice(0);
    flushTimer = null;
    try {
      await fetch("/api/analytics/event", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getInitDataHeaders() },
        body: JSON.stringify({ events: batch }),
      });
    } catch {
      // Re-queue on failure for next flush attempt
      queue.unshift(...batch);
    }
  }

  /**
   * Track a page/tab navigation event.
   */
  function trackPageView(mode, tab) {
    track("page_view", "navigation", { mode, tab });
  }

  // Flush remaining events when the page becomes hidden (sendBeacon for reliability)
  if (typeof navigator.sendBeacon === "function") {
    window.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden" && queue.length) {
        const headers = getInitDataHeaders();
        const payload = JSON.stringify({ events: queue.splice(0) });
        // sendBeacon doesn't support custom headers, so fall back to fetch with keepalive
        try {
          fetch("/api/analytics/event", {
            method: "POST",
            headers: { "Content-Type": "application/json", ...headers },
            body: payload,
            keepalive: true,
          });
        } catch {
          // Best-effort — ignore failures on unload
        }
        if (flushTimer) {
          clearTimeout(flushTimer);
          flushTimer = null;
        }
      }
    });
  }

  return { track, flush, trackPageView };
}
