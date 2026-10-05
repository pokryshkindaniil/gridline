"use client";

import { useState } from "react";

export interface LogoCandidate { kind: string; src: string | null | undefined; alt: string }

export function useLogoChain(candidates: LogoCandidate[]) {
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set());
  const pick = candidates.find((c) => c.src && !failed.has(c.src)) ?? null;
  const onError = () => { if (pick?.src) setFailed((f) => new Set(f).add(pick.src!)); };
  return { pick, onError };
}

export function LogoImg({ src, alt, className = "", onError }: { src: string; alt: string; className?: string; onError: () => void }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className={`max-h-full max-w-full object-contain object-left ${className}`} loading="lazy" decoding="async" draggable={false} onError={onError} />;
}
