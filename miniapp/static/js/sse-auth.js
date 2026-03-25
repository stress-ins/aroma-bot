/**
 * SSE authentication helper.
 *
 * Exchanges Telegram initData (sent via header) for a short-lived opaque
 * token that can be safely placed in EventSource query strings without
 * leaking the full initData into server logs or proxy caches.
 */

let _cachedToken = null;
let _expiresAt = 0;

function _initDataHeaders() {
  const initData = window.Telegram?.WebApp?.initData;
  return initData ? { "X-Telegram-Init-Data": initData } : {};
}

function _initDataQs() {
  const initData = window.Telegram?.WebApp?.initData;
  if (!initData) return "";
  return `?init_data=${encodeURIComponent(initData)}`;
}

/**
 * Fetch (or reuse cached) short-lived SSE token and return a query string
 * like `?token=abc123` suitable for EventSource URLs.
 */
export async function sseQueryString() {
  const now = Date.now();
  if (_cachedToken && _expiresAt - now > 30_000) {
    return `?token=${encodeURIComponent(_cachedToken)}`;
  }
  try {
    const resp = await fetch("/api/auth/sse-token", {
      method: "POST",
      headers: { ..._initDataHeaders(), "Content-Type": "application/json" },
    });
    if (!resp.ok) return _initDataQs();
    const data = await resp.json();
    _cachedToken = data.token;
    _expiresAt = now + 4 * 60 * 1000; // 4 min (server TTL = 5 min)
    return `?token=${encodeURIComponent(_cachedToken)}`;
  } catch {
    return _initDataQs();
  }
}

/** Invalidate cached token (e.g. on auth error). */
export function invalidateSseToken() {
  _cachedToken = null;
  _expiresAt = 0;
}
