"use client";

import type { Vehicle } from "@/lib/types";
import { LogoImg, useLogoChain } from "./Logo";

/**
 * ENTRY column: race number (strong), manufacturer + model, class, and a small secondary manufacturer logo.
 * Formula groups (several single-driver cars sharing one model) pass `number = null`: the numbers live on the
 * driver cards there. No car photography — the manufacturer logo is the only image and it is optional.
 */
export default function EntryInfo({
  number, vehicle, manufacturerLogoUrl,
}: { number: string | null; vehicle: Vehicle | null; manufacturerLogoUrl?: string | null }) {
  const make = vehicle?.manufacturer ?? null;
  const model = vehicle?.model ?? null;
  const cls = vehicle?.class_name ?? null;
  const { pick, onError } = useLogoChain([
    { kind: "manufacturer-logo", src: vehicle?.fallback_logo_url, alt: `${make ?? "Manufacturer"} logo` },
    { kind: "manufacturer-logo", src: manufacturerLogoUrl, alt: `${make ?? "Manufacturer"} logo` },
  ]);
  const car = [make, model].filter(Boolean).join(" ");
  return (
    <div className="min-w-0" data-testid="entry-info">
      {number && (
        <p className="tabular text-5xl font-semibold leading-none tracking-tight" data-testid="race-number">
          <span aria-hidden className="mr-0.5 text-3xl font-medium text-text-secondary">#</span>{number}
        </p>
      )}
      {car && <p className={`break-words text-[15px] font-medium leading-snug ${number ? "mt-3" : ""}`} data-testid="entry-car">{car}</p>}
      {(cls || pick) && (
        <div className="mt-2 flex min-h-5 items-center gap-3">
          {cls && <span className="rounded-full border border-border px-2 py-0.5 text-[11px] font-semibold uppercase leading-4 tracking-wide text-text-secondary" data-testid="entry-class">{cls}</span>}
          {pick && (
            <span className="flex h-5 w-16 items-center opacity-80" data-testid="manufacturer-logo">
              <LogoImg src={pick.src!} alt={pick.alt} onError={onError} />
            </span>
          )}
        </div>
      )}
    </div>
  );
}
