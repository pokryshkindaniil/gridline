"use client";

export default function CalendarStyleSelector({
  includeEmoji,
  onChange,
}: {
  includeEmoji: boolean;
  onChange: (value: boolean) => void;
}) {
  const pill = (active: boolean) =>
    "rounded-full px-5 py-2 text-sm font-medium transition-colors " +
    (active
      ? "bg-text-primary text-background"
      : "bg-surface-muted text-text-secondary hover:text-text-primary");

  return (
    <div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Calendar event title style">
        <button type="button" aria-pressed={!includeEmoji} onClick={() => onChange(false)} className={pill(!includeEmoji)}>
          Plain
        </button>
        <button type="button" aria-pressed={includeEmoji} onClick={() => onChange(true)} className={pill(includeEmoji)}>
          Emoji
        </button>
      </div>
      <p className="mt-3 text-sm text-text-secondary">
        {includeEmoji ? "🏁 Race · ⏱️ Qualifying · 🧪 Practice" : "Race · Qualifying · Practice"}
      </p>
    </div>
  );
}
