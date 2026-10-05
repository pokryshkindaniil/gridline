import { flag } from "@/lib/format";
import type { Driver, Entry } from "@/lib/types";

function Avatar({ d, size }: { d: Driver; size: string }) {
  return d.image_url ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={d.image_url} alt="" className={`${size} shrink-0 rounded-full object-cover`} loading="lazy" />
  ) : (
    <span aria-hidden className={`${size} grid shrink-0 place-items-center rounded-full bg-surface-muted text-xs font-semibold text-text-secondary`}>
      {d.first_name[0]}{d.last_name[0]}
    </span>
  );
}

function Identity({ d, avatar, compact }: { d: Driver; avatar: string; compact?: boolean }) {
  return (
    <li className="flex items-center gap-3">
      <Avatar d={d} size={avatar} />
      <div className="min-w-0">
        <p className={`break-words leading-tight ${compact ? "text-sm" : "text-[15px]"}`}>
          <span className="text-text-secondary">{d.first_name} </span>
          <span className="font-semibold">{d.last_name}</span>
        </p>
        {d.nationality_code && (
          <p className="text-xs text-text-secondary"><span aria-hidden>{flag(d.nationality_code)} </span>{d.nationality_code}</p>
        )}
      </div>
    </li>
  );
}

export default function DriverCard({ entry, showNumber = true }: { entry: Entry; showNumber?: boolean }) {
  const n = entry.drivers.length;
  const number = showNumber && entry.race_number && (
    <p className="tabular text-5xl font-semibold leading-none tracking-tight">{entry.race_number}</p>
  );
  if (n <= 1) {
    return (
      <div data-testid="driver-card" data-drivers={n} className="min-w-0">
        {number}
        <ul className="mt-3">{entry.drivers.map((d) => <Identity key={d.slug} d={d} avatar="h-10 w-10" />)}</ul>
      </div>
    );
  }
  const many = n > 3;
  return (
    <div data-testid="driver-card" data-drivers={n} className={`grid min-w-0 items-start gap-x-4 ${number ? "grid-cols-[4.25rem_1fr]" : "grid-cols-1"}`}>
      {number && <div>{number}</div>}
      <ul className={`gap-x-5 gap-y-2.5 ${many ? "grid grid-cols-2" : "space-y-2.5"}`}>
        {entry.drivers.map((d) => <Identity key={d.slug} d={d} avatar="h-8 w-8" compact={many} />)}
      </ul>
    </div>
  );
}
