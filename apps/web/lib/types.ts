// Mirrors the public API schemas used by the web app.
export type Category = "formula" | "endurance" | "gt" | "rally" | "stock_car" | "moto" | "other";
export type SessionType = "practice" | "qualifying" | "sprint" | "race" | "warmup" | "test" | "other";

export interface Series {
  slug: string; name: string; short_name: string; category: Category;
  official_url: string; logo_url: string | null; active: boolean;
}
export interface EventOut {
  id: string; slug: string; name: string; series_slug: string; series_short_name: string; year: number;
  circuit_name: string | null; city: string | null; country_code: string | null; timezone: string;
  start_date: string; end_date: string; official_url: string | null; status: string;
}
export interface SeriesDetail extends Series {
  next_event: EventOut | null; next_session: SessionOut | null;
  season_year: number | null; event_count: number;
}
export interface SessionOut {
  id: string;
  event: { id: string; slug: string; name: string; circuit_name: string | null; country_code: string | null; timezone: string };
  series: Series; name: string; session_type: SessionType; start_at: string; end_at: string | null;
  status: "scheduled" | "delayed" | "cancelled" | "completed"; source_url: string; source_name: string;
  source_updated_at: string | null; checked_at: string; is_fixture: boolean;
}
export interface Weekend {
  start_date: string; end_date: string; timezone: string; session_count: number; series_count: number; sessions: SessionOut[];
}
export interface Driver { slug: string; first_name: string; last_name: string; nationality_code: string | null; image_url: string | null }
export interface Vehicle {
  manufacturer: string | null; manufacturer_slug?: string | null; model: string | null; model_slug?: string | null;
  class_name: string | null; race_number: string | null; image_url: string | null; fallback_logo_url: string | null;
}
export interface Entry { race_number: string | null; vehicle: Vehicle | null; drivers: Driver[] }
export interface Team {
  slug: string; name: string; short_name: string | null; logo_url: string | null; website_url: string | null;
  series: Series; vehicle: Vehicle | null; entries: Entry[];
  source_name?: string | null; source_url?: string | null; checked_at?: string | null; is_fixture?: boolean;
}
export interface TeamDetail extends Team { upcoming_events: EventOut[]; event: EventOut | null }
export interface EntryEvent {
  event: EventOut; competition: string | null; entry_count: number; driver_count: number;
  source_name: string | null; source_url: string | null; checked_at: string | null; is_fixture: boolean; is_default: boolean;
}
export interface Feed {
  public_token: string; public_url: string; webcal_url: string; series: Series[]; session_types: SessionType[];
  timezone: string; include_emoji: boolean; created_at: string; updated_at: string;
}
export interface FeedCreated { public_url: string; webcal_url: string; edit_url: string; public_token: string; edit_token: string }
export interface Change {
  detected_at: string; session_id: string; series_short_name: string; event_name: string; session_name: string;
  field_name: string; old_value: string | null; new_value: string | null; source_url: string;
}
export interface SourceHealth {
  source_id: string; series: string; source_name: string; official_url: string; live: boolean;
  status: "healthy" | "degraded" | "stale" | "failing" | "fixture_only"; last_successful_sync: string | null;
  last_attempt: string | null; records_seen: number | null; records_changed: number | null;
  last_error: string | null; limitation: string | null;
}
