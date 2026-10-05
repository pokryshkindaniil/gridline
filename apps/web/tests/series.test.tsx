import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SeriesCard from "@/components/SeriesCard";
import { seriesMedia, teamLogo } from "@/lib/media";
import type { SeriesMediaEntry } from "@/lib/media";
import type { SeriesDetail } from "@/lib/types";

const series = (slug: string, name: string, over: Partial<SeriesDetail> = {}): SeriesDetail => ({
  slug, name, short_name: name.slice(0, 3).toUpperCase(), category: "formula", official_url: "", logo_url: null, active: true,
  next_event: null, next_session: null, season_year: 2026, event_count: 24, ...over,
});
const hero = (src = "/assets/series/x.jpg") => ({
  entity: "x", assetType: "series-hero" as const, src, alt: "", width: 1600, height: 900, focus: "50% 60%", sourcePage: "p",
  originalUrl: "o", license: "CC BY-SA 4.0", licenseUrl: null, author: "A. Photographer", attribution: "A. Photographer",
  retrieved: "2026-10-05", modifications: "none", notes: "",
});
const media = (over: Partial<SeriesMediaEntry> = {}): SeriesMediaEntry => ({ name: "", descriptor: "Single-seater", accent: null, logo: null, hero: hero(), ...over });

describe("series media registry", () => {
  it("has a curated hero with a credit for every public championship, none for IMSA", () => {
    for (const slug of ["formula-1", "fia-wec", "gt-world-challenge-europe"]) {
      const m = seriesMedia(slug);
      expect(m.hero?.src).toMatch(/^\/assets\/series\//);
      expect(m.hero?.author).toBeTruthy();
      expect(m.hero?.license).toBeTruthy();
    }
    expect(seriesMedia("imsa-weathertech").hero).toBeNull();
  });
  it("unknown series get the neutral fallback, not a crash", () => {
    expect(seriesMedia("nope")).toMatchObject({ hero: null, logo: null, descriptor: null });
    expect(seriesMedia(null).hero).toBeNull();
  });
  it("a team logo is scoped to its series", () => {
    expect(teamLogo("alpine", "formula-1")?.src).toMatch(/alpine/);
    expect(teamLogo("alpine", "fia-wec")).toBeNull();   // a same-named team elsewhere does not inherit it
    expect(teamLogo("alpine")?.src).toMatch(/alpine/);  // no series given: registry key only
  });
});

describe("series card", () => {
  it("is one whole-card link with name, descriptor · season, event count and the photo credit", () => {
    render(<SeriesCard series={series("formula-1", "Formula 1")} media={media()} />);
    const card = screen.getByTestId("series-card");
    expect(card.tagName).toBe("A");
    expect(card).toHaveAttribute("href", "/series/formula-1");
    expect(within(card).getByRole("heading", { name: "Formula 1" })).toBeInTheDocument();
    expect(screen.getByTestId("series-facts")).toHaveTextContent("Single-seater · 2026");
    expect(screen.getByTestId("series-events")).toHaveTextContent("24 events");
    expect(screen.getByTestId("hero-credit")).toHaveTextContent("Photo: A. Photographer · CC BY-SA 4.0");
    expect(card.querySelectorAll("a")).toHaveLength(0);  // no nested links
  });

  it("renders the curated image decoratively, with the crop focus from the registry", () => {
    const { container } = render(<SeriesCard series={series("a", "A")} media={media()} />);
    const img = container.querySelector("img")!;
    expect(img).toHaveAttribute("src", "/assets/series/x.jpg");
    expect(img).toHaveAttribute("alt", "");
    expect(img.style.objectPosition).toBe("50% 60%");
    expect(screen.getByTestId("series-card")).toHaveAttribute("data-hero", "image");
  });

  it("falls back to the neutral branded background when there is no hero", () => {
    const { container } = render(<SeriesCard series={series("a", "A")} media={media({ hero: null })} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByTestId("series-fallback")).toBeInTheDocument();
    expect(screen.getByTestId("series-card")).toHaveAttribute("data-hero", "fallback");
    expect(screen.queryByTestId("hero-credit")).toBeNull();
  });

  it("falls back, with no broken image, when the hero file fails to load", () => {
    const { container } = render(<SeriesCard series={series("a", "A")} media={media()} />);
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByTestId("series-card")).toHaveAttribute("data-hero", "fallback");
    expect(screen.getByRole("heading", { name: "A" })).toBeInTheDocument();
  });

  it("copes with a series that has no events yet and no descriptor", () => {
    render(<SeriesCard series={series("a", "A", { event_count: 0, season_year: null })} media={media({ descriptor: null })} />);
    expect(screen.getByTestId("series-events")).toHaveTextContent("Schedule coming soon");
    expect(screen.queryByTestId("series-facts")).toBeNull();
  });

  it("is responsive-safe: consistent min height, whole-card link, no fixed widths", () => {
    render(<SeriesCard series={series("a", "A")} media={media()} />);
    const cls = screen.getByTestId("series-card").className;
    expect(cls).toContain("min-h-[22rem]");
    expect(cls).toContain("w-full");
    expect(cls).not.toMatch(/\bw-\[\d/);
  });
});

vi.mock("@/lib/api", () => ({
  api: vi.fn(async () => [
    series("formula-1", "Formula 1", { event_count: 24 }),
    series("fia-wec", "FIA World Endurance Championship", { event_count: 8, category: "endurance" }),
    series("gt-world-challenge-europe", "GT World Challenge Europe", { event_count: 10, category: "gt" }),
    series("wrc", "World Rally Championship", { active: false, event_count: 0, season_year: null }),
  ]),
}));

describe("/series page", () => {
  it("renders every enabled series as a card in a 1 / 2 / 3 column grid, and keeps coming-soon series out of it", async () => {
    const { default: SeriesDirectory } = await import("@/app/series/page");
    render(await SeriesDirectory());
    const cards = screen.getAllByTestId("series-card");
    expect(cards.map((c) => c.getAttribute("href"))).toEqual(["/series/formula-1", "/series/fia-wec", "/series/gt-world-challenge-europe"]);
    const grid = screen.getByTestId("series-grid");
    expect(grid.className).toContain("grid-cols-1");
    expect(grid.className).toContain("sm:grid-cols-2");
    expect(grid.className).toContain("lg:grid-cols-3");
    expect(cards.every((c) => c.getAttribute("data-hero") === "image")).toBe(true);  // curated heroes from the registry
    expect(screen.getByTestId("series-soon")).toHaveTextContent("World Rally Championship");
    expect(screen.queryByText(/imsa/i)).toBeNull();
  });
});
