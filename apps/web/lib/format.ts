// All instants arrive as UTC ISO strings and are converted to a display zone only here.

export function isoDay(iso: string, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)!.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function formatDayHeading(iso: string, tz: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, weekday: "short", day: "numeric", month: "short" })
    .format(new Date(iso)).replace(",", "").toUpperCase();
}

export function formatTime(iso: string, tz: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
}

export function timeAgo(iso: string, now: number = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function formatDateRange(start: string, end: string): string {
  const s = new Date(start + "T00:00:00Z"), e = new Date(end + "T00:00:00Z");
  const month = (d: Date) => d.toLocaleString("en-GB", { month: "long", timeZone: "UTC" });
  return s.getUTCMonth() === e.getUTCMonth()
    ? `${s.getUTCDate()}–${e.getUTCDate()} ${month(e)}`
    : `${s.getUTCDate()} ${month(s)} – ${e.getUTCDate()} ${month(e)}`;
}

export function flag(code: string | null | undefined): string {
  if (!code || code.length !== 2) return "";
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}

export const CATEGORY_LABEL: Record<string, string> = {
  formula: "Formula", endurance: "Endurance", gt: "GT", rally: "Rally", stock_car: "Stock car", moto: "Moto", other: "Other",
};
export const TYPE_LABEL: Record<string, string> = {
  practice: "Practice", qualifying: "Qualifying", sprint: "Sprint", race: "Race", warmup: "Warm-up", test: "Test", other: "Other",
};
