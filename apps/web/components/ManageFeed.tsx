"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { clearMyFeed, saveMyFeed } from "@/lib/myFeed";
import type { Feed, Series, SessionType } from "@/lib/types";
import CalendarFeedCard from "./CalendarFeedCard";
import CalendarStyleSelector from "./CalendarStyleSelector";
import SeriesSelector from "./SeriesSelector";
import SessionTypeSelector from "./SessionTypeSelector";
import TimezonePicker from "./TimezonePicker";
import { Button } from "./ui";

export default function ManageFeed({ feed, allSeries, editToken }: { feed: Feed; allSeries: Series[]; editToken: string | null }) {
  const router = useRouter();
  const [series, setSeries] = useState(feed.series.map((s) => s.slug));
  const [types, setTypes] = useState<SessionType[]>(feed.session_types);
  const [tz, setTz] = useState(feed.timezone);
  const [includeEmoji, setIncludeEmoji] = useState(feed.include_emoji);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = tz !== feed.timezone || includeEmoji !== feed.include_emoji || series.slice().sort().join() !== feed.series.map((s) => s.slug).sort().join() || types.slice().sort().join() !== feed.session_types.slice().sort().join();

  const headers = { "content-type": "application/json", "x-edit-token": editToken ?? "" };

  async function save() {
    setBusy(true); setMsg(null);
    const res = await fetch(`/api-proxy/feeds/${feed.public_token}`, { method: "PATCH", headers, body: JSON.stringify({ series, session_types: types, timezone: tz, include_emoji: includeEmoji }) });
    setBusy(false);
    if (!res.ok) { setMsg((await res.json().catch(() => ({}))).detail ?? "Could not save"); return; }
    if (editToken) saveMyFeed({ publicToken: feed.public_token, editToken });
    setMsg("Saved. Calendar apps pick this up on their next refresh.");
    router.refresh();
  }

  async function revoke() {
    if (!confirm("Revoke this feed? Calendar apps subscribed to it will stop updating.")) return;
    const res = await fetch(`/api-proxy/feeds/${feed.public_token}`, { method: "DELETE", headers });
    if (!res.ok) { setMsg("Could not revoke feed"); return; }
    clearMyFeed();
    router.refresh();
  }

  if (!editToken) {
    return <p className="rounded-2xl bg-surface-muted p-5 text-text-secondary">Open the full management link (with its secret token) to edit this feed. The subscription URL above is read-only.</p>;
  }
  return (
    <div className="space-y-10">
      <section><h3 className="mb-4 text-xl font-semibold">Series</h3><SeriesSelector series={allSeries} selected={series} onChange={setSeries} /></section>
      <section><h3 className="mb-4 text-xl font-semibold">Sessions</h3><SessionTypeSelector selected={types} onChange={setTypes} /></section>
      <section><h3 className="mb-4 text-xl font-semibold">Timezone</h3><TimezonePicker value={tz} onChange={setTz} /></section>
      <section><h3 className="mb-4 text-xl font-semibold">Event titles</h3><CalendarStyleSelector includeEmoji={includeEmoji} onChange={setIncludeEmoji} /></section>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={!dirty || busy || series.length === 0 || types.length === 0}>Save changes</Button>
        <Button variant="danger" onClick={revoke}>Revoke feed</Button>
        {msg && <p role="status" className="text-sm text-text-secondary">{msg}</p>}
      </div>
    </div>
  );
}

export { CalendarFeedCard };
