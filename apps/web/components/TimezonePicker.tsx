"use client";

export default function TimezonePicker({ value, onChange }: { value: string; onChange: (tz: string) => void }) {
  const zones: string[] = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [value];
  return (
    <select
      value={value} onChange={(e) => onChange(e.target.value)} aria-label="Timezone"
      className="w-full rounded-xl bg-surface-muted px-4 py-3 text-base outline-none focus-visible:ring-2 focus-visible:ring-accent sm:max-w-sm"
    >
      {!zones.includes(value) && <option value={value}>{value}</option>}
      {zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}
    </select>
  );
}
