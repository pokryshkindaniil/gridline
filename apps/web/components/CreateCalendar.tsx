"use client";

import Link from "next/link";
import { useState } from "react";
import type { FeedCreated, Series, SessionType } from "@/lib/types";
import { saveMyFeed } from "@/lib/myFeed";
import CalendarFeedCard from "./CalendarFeedCard";
import CalendarStyleSelector from "./CalendarStyleSelector";
import SeriesSelector from "./SeriesSelector";
import SessionTypeSelector from "./SessionTypeSelector";
import TimezonePicker from "./TimezonePicker";
import { Button } from "./ui";

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="py-8">
      <h2 className="mb-5 flex items-baseline gap-3 text-2xl font-semibold tracking-tight">
        <span className="text-base font-medium text-text-secondary">{n}</span>{title}
      </h2>
      {children}
    </section>
  );
}

export default function CreateCalendar({ series }: { series: Series[] }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [types, setTypes] = useState<SessionType[]>(["qualifying", "race"]);
  const [includeEmoji, setIncludeEmoji] = useState(true);
  const [tz, setTz] = useState(() => (typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "UTC"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<FeedCreated | null>(null);

  async function submit() {
    setBusy(true); setError(null);
    try {
      const res = await fetch("/api-proxy/feeds", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ series: selected, session_types: types, timezone: tz, include_emoji: includeEmoji }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`);
      const feed: FeedCreated = await res.json();
      saveMyFeed({ publicToken: feed.public_token, editToken: feed.edit_token });
      setCreated(feed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally { setBusy(false); }
  }

  if (created) {
    return (
      <div className="space-y-8 py-8">
        <p className="text-lg text-text-secondary">Done. Add it to your calendar app once — it updates itself from here on.</p>
        <CalendarFeedCard webcalUrl={created.webcal_url} httpUrl={created.public_url} />
        <div className="rounded-2xl border border-border p-5 text-sm text-text-secondary">
          <p className="font-medium text-text-primary">Keep your management link private</p>
          <p className="mt-1">It lets you change or revoke this feed. We saved it in this browser; bookmark it to manage from elsewhere.</p>
          <Link href={created.edit_url} className="mt-3 inline-block text-accent hover:underline">Manage this feed →</Link>
        </div>
      </div>
    );
  }

  const ready = selected.length > 0 && types.length > 0;
  return (
    <div className="divide-y divide-border">
      <Step n={1} title="Choose series"><SeriesSelector series={series} selected={selected} onChange={setSelected} /></Step>
      <Step n={2} title="Choose sessions"><SessionTypeSelector selected={types} onChange={setTypes} /></Step>
      <Step n={3} title="Timezone">
        <TimezonePicker value={tz} onChange={setTz} />
        <p className="mt-3 text-sm text-text-secondary">Events carry exact UTC times, so they are correct in any calendar. This sets how times read in descriptions.</p>
      </Step>
      <Step n={4} title="Event titles">
        <CalendarStyleSelector includeEmoji={includeEmoji} onChange={setIncludeEmoji} />
      </Step>
      <div className="py-8">
        {error && <p role="alert" className="mb-4 text-danger">{error}</p>}
        <Button onClick={submit} disabled={!ready || busy} icon="arrow">{busy ? "Creating…" : "Subscribe to calendar"}</Button>
        {!ready && <p className="mt-3 text-sm text-text-secondary">Pick at least one series and one session type.</p>}
      </div>
    </div>
  );
}
