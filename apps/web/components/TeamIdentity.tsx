"use client";

import Link from "next/link";
import type { Team } from "@/lib/types";
import { LogoImg, useLogoChain } from "./Logo";

export default function TeamIdentity({
  team, link, eventId, teamLogoUrl, manufacturerLogoUrl, manufacturerName,
}: {
  team: Team; link: boolean; eventId?: string;
  teamLogoUrl?: string | null; manufacturerLogoUrl?: string | null; manufacturerName?: string | null;
}) {
  const { pick, onError } = useLogoChain([
    { kind: "team-logo", src: team.logo_url, alt: `${team.name} logo` },
    { kind: "team-logo", src: teamLogoUrl, alt: `${team.name} logo` },
    { kind: "manufacturer-logo", src: manufacturerLogoUrl, alt: `${manufacturerName ?? team.name} logo` },
  ]);
  const name = team.name.trim();
  const kind = pick ? pick.kind : name ? "wordmark" : "placeholder";
  const title = link
    ? <Link href={`/teams/${team.slug}?series=${team.series.slug}${eventId ? `&event=${eventId}` : ""}`} className="hover:text-accent">{team.name}</Link>
    : team.name;

  return (
    <header className="min-w-0 lg:self-start lg:pt-7" data-testid="team-identity" data-mark={kind}>
      {pick && (
        <div
          className={pick.kind === "team-logo" ? "mb-3 flex h-14 w-44 max-w-full items-center" : "mb-3 flex h-8 w-28 max-w-full items-center opacity-60"}
          data-testid="team-mark" data-secondary={pick.kind !== "team-logo" ? "true" : undefined}
        >
          <LogoImg src={pick.src!} alt={pick.alt} onError={onError} />
        </div>
      )}
      {kind === "placeholder" && (
        <svg viewBox="0 0 56 56" role="img" aria-label="GRIDLINE placeholder" className="mb-3 h-14 w-14 text-border" data-testid="team-mark">
          <g fill="none" stroke="currentColor" strokeWidth="3"><path d="M6 14h44M6 28h44M6 42h44" /><path d="M16 6v44M40 6v44" opacity=".5" /></g>
        </svg>
      )}
      <h3 className="break-words text-xl font-semibold leading-tight tracking-tight" data-testid="team-name">
        {title}
      </h3>
      <p className="mt-1 text-text-secondary">{team.series.name}</p>
    </header>
  );
}
