import manifest from "./media-manifest.json";

// Media is resolved by canonical slug. Missing assets deliberately fall back to text.

export interface LogoAsset {
  entity: string;
  assetType: "team-logo" | "manufacturer-logo";
  src: string;
  alt: string;
  sourcePage: string;
  originalUrl: string;
  license: string;
  licenseUrl: string | null;
  author: string;
  attribution: string | null;
  retrieved: string;
  modifications: string;
  notes: string;
  trademarkNote: string;
}
interface Entry { name: string; aliases?: string[]; series?: string[]; logo: LogoAsset | null }

export interface HeroAsset {
  entity: string;
  assetType: "series-hero";
  src: string;
  alt: string;
  width: number;
  height: number;
  focus: string | null;
  sourcePage: string;
  originalUrl: string;
  license: string;
  licenseUrl: string | null;
  author: string;
  attribution: string | null;
  retrieved: string;
  modifications: string;
  notes: string;
}
export interface SeriesMediaEntry {
  name: string;
  descriptor: string | null;
  accent: string | null;
  logo: LogoAsset | null;
  hero: HeroAsset | null;
}
interface Registry {
  teams: Record<string, Entry>; manufacturers: Record<string, Entry>; series?: Record<string, SeriesMediaEntry>;
}

const REGISTRY = manifest as unknown as Registry;

export function slugify(value: string): string {
  return value.normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

const ALIASES = new Map<string, string>(
  Object.entries(REGISTRY.manufacturers).flatMap(([slug, e]) => (e.aliases ?? []).map((a) => [a, slug] as [string, string])),
);

export function teamLogo(slug: string | null | undefined, seriesSlug?: string | null): LogoAsset | null {
  const e = slug ? REGISTRY.teams[slug] : undefined;
  if (!e?.logo) return null;
  if (e.series && seriesSlug && !e.series.includes(seriesSlug)) return null;
  return e.logo;
}

export function manufacturerLogo(name: string | null | undefined): LogoAsset | null {
  if (!name) return null;
  const s = slugify(name);
  return REGISTRY.manufacturers[ALIASES.get(s) ?? s]?.logo ?? null;
}

const NO_SERIES_MEDIA: SeriesMediaEntry = { name: "", descriptor: null, accent: null, logo: null, hero: null };

export const seriesMedia = (slug: string | null | undefined): SeriesMediaEntry =>
  (slug && REGISTRY.series?.[slug]) || NO_SERIES_MEDIA;
