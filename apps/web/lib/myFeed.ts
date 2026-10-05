// Convenience only: remembers the last feed in this browser. The URL token is the source of truth.
const KEY = "gridline:my-feed";
export interface MyFeed { publicToken: string; editToken: string }

export function saveMyFeed(feed: MyFeed): void {
  try { localStorage.setItem(KEY, JSON.stringify(feed)); } catch { /* storage unavailable */ }
}
export function loadMyFeed(): MyFeed | null {
  try { const raw = localStorage.getItem(KEY); return raw ? (JSON.parse(raw) as MyFeed) : null; } catch { return null; }
}
export function clearMyFeed(): void {
  try { localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}
