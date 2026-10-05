"use client";

import Link from "next/link";
import { useState } from "react";
import type { SeriesMediaEntry } from "@/lib/media";
import type { SeriesDetail } from "@/lib/types";

export default function SeriesCard({ series, media }: { series: SeriesDetail; media: SeriesMediaEntry }) {
  const [broken, setBroken] = useState(false);
  const hero = media.hero && !broken ? media.hero : null;
  const facts = [media.descriptor, series.season_year ? String(series.season_year) : null].filter(Boolean).join(" · ");
  const events = series.event_count > 0 ? `${series.event_count} event${series.event_count === 1 ? "" : "s"}` : null;

  return (
    <Link
      href={`/series/${series.slug}`}
      data-testid="series-card"
      data-hero={hero ? "image" : "fallback"}
      aria-label={series.name}
      className="group relative flex w-full min-h-[22rem] flex-col justify-between overflow-hidden rounded-2xl bg-[#1d1d1f] text-white outline-offset-4 sm:min-h-[26rem]"
    >
      {hero ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={hero.src} alt="" loading="lazy" decoding="async" draggable={false} onError={() => setBroken(true)}
          style={hero.focus ? { objectPosition: hero.focus } : undefined}
          className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.02]"
        />
      ) : (
        <svg aria-hidden viewBox="0 0 400 400" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full text-white/[0.07]" data-testid="series-fallback">
          <g fill="none" stroke="currentColor" strokeWidth="2"><path d="M0 120h400M0 200h400M0 280h400" /><path d="M110 0v400M290 0v400" opacity=".6" /></g>
        </svg>
      )}
      <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-black/15" />
      {media.accent && <div aria-hidden className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: media.accent }} />}

      <div className="relative flex items-start justify-between gap-4 p-6">
        <span className="text-xs font-semibold uppercase tracking-[0.14em] text-white/80">{series.short_name}</span>
        {media.logo && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={media.logo.src} alt={media.logo.alt} className="h-8 max-w-[7rem] object-contain object-right" />
        )}
      </div>

      <div className="relative p-6 pt-24">
        <h2 className="text-3xl font-semibold leading-tight tracking-tight sm:text-[2rem]">{series.name}</h2>
        {facts && <p className="mt-2 text-[15px] text-white/80" data-testid="series-facts">{facts}</p>}
        <div className="mt-5 flex items-end justify-between gap-4">
          <p className="tabular text-sm text-white/80" data-testid="series-events">{events ?? "Schedule coming soon"}</p>
          <span aria-hidden className="text-white/80 transition-transform duration-150 group-hover:translate-x-0.5">→</span>
        </div>
        {hero && (
          <p className="mt-4 text-[10px] leading-snug text-white/50" data-testid="hero-credit">
            Photo: {hero.attribution ?? hero.author} · {hero.license}
          </p>
        )}
      </div>
    </Link>
  );
}
