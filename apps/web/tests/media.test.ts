// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import manifest from "@/lib/media-manifest.json";
import { manufacturerLogo, slugify, teamLogo } from "@/lib/media";

const PUBLIC = path.resolve(import.meta.dirname, "../public");
const ALLOWED = /^(CC0|Public domain|CC BY)(?!-SA)/;
const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const REQUIRED = ["entity", "assetType", "src", "alt", "sourcePage", "originalUrl", "license", "author", "retrieved", "modifications", "trademarkNote"] as const;

const all = (): { kind: "teams" | "manufacturers"; slug: string; a: any }[] =>
  (["teams", "manufacturers"] as const).flatMap((kind) =>
    Object.entries(manifest[kind] as Record<string, any>).map(([slug, e]) => ({ kind, slug, a: e.logo })));

describe("media registry", () => {
  it("is keyed by slugs and records full provenance for every asset", () => {
    expect(all().length).toBeGreaterThan(0);
    for (const { kind, slug, a } of all()) {
      expect(slug, `${kind}/${slug}`).toMatch(SLUG);
      for (const f of REQUIRED) expect(a[f], `${kind}/${slug}.${f}`).toBeTruthy();
      expect(a.entity).toBe(slug);
      expect(a.assetType).toBe(kind === "teams" ? "team-logo" : "manufacturer-logo");
      expect(a.sourcePage).toMatch(/^https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
      expect(a.originalUrl).toMatch(/^https:\/\/upload\.wikimedia\.org\//);
      expect(a.license, `${kind}/${slug} licence`).toMatch(ALLOWED);
      expect(a.retrieved).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(a.trademarkNote).toMatch(/trademark/i);          // copyright status never implies trademark rights
      if (a.license.startsWith("CC BY")) expect(a.attribution, `${slug} needs attribution`).toBeTruthy();
    }
  });

  it("every asset exists on disk and every logo file on disk is registered (no orphans, no car photos)", () => {
    const registered = new Set(all().map(({ a }) => a.src));
    for (const src of registered) expect(existsSync(path.join(PUBLIC, src)), src).toBe(true);
    const onDisk = (["teams", "manufacturers"] as const).flatMap((k) => readdirSync(path.join(PUBLIC, "assets/logos", k)).map((f) => `/assets/logos/${k}/${f}`));
    expect(onDisk.filter((f) => !registered.has(f))).toEqual([]);
    expect(existsSync(path.join(PUBLIC, "assets/teams"))).toBe(false);
  });

  it("documents provenance and the trademark caveat in NOTICE.md", () => {
    const notice = readFileSync(path.join(PUBLIC, "assets/NOTICE.md"), "utf8");
    expect(notice).toMatch(/trademark/i);
    expect(notice).toContain("Investigated and not used");
    for (const { slug } of all()) expect(notice).toContain(`\`${slug}\``);
  });
});

describe("registry lookup", () => {
  it("slugify matches the backend (accents, punctuation, case)", () => {
    expect(slugify("Mercedes - AMG Team MANN-FILTER")).toBe("mercedes-amg-team-mann-filter");
    expect(slugify("Ecurie Écosse")).toBe("ecurie-ecosse");
  });
  it("finds a team logo by slug and nothing for an unknown team (missing registry entry)", () => {
    expect(teamLogo("mclaren")?.src).toBe("/assets/logos/teams/mclaren.png");
    expect(teamLogo("some-team-we-never-heard-of")).toBeNull();
    expect(teamLogo(null)).toBeNull();
  });
  it("normalises manufacturer names, honours aliases, and returns null for unknown makes", () => {
    expect(manufacturerLogo("BMW")?.src).toMatch(/manufacturers\/bmw\./);
    expect(manufacturerLogo("Mercedes-AMG")?.src).toMatch(/mercedes-amg\./);
    expect(manufacturerLogo("Mercedes-Benz")?.entity).toBe("mercedes");
    expect(manufacturerLogo("Red Bull")).toBeNull();  // the drinks brand is not a Red Bull Racing identity
    expect(manufacturerLogo("Corvette")).toBeNull();
    expect(manufacturerLogo(null)).toBeNull();
  });
});
