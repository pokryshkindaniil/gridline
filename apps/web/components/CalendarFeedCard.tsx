"use client";

import { useState } from "react";
import { Button } from "./ui";

export function subscribeLinks(webcalUrl: string, httpUrl: string) {
  return {
    apple: webcalUrl,
    google: `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcalUrl)}`,
    outlook: `https://outlook.live.com/calendar/0/addfromweb?url=${encodeURIComponent(httpUrl)}&name=GRIDLINE`,
  };
}

export default function CalendarFeedCard({ webcalUrl, httpUrl }: { webcalUrl: string; httpUrl: string }) {
  const [copied, setCopied] = useState(false);
  const links = subscribeLinks(webcalUrl, httpUrl);
  const local = /localhost|127\.0\.0\.1/.test(httpUrl);

  async function copy() {
    try { await navigator.clipboard.writeText(webcalUrl); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="rounded-3xl bg-surface-muted p-6 sm:p-8">
      <p className="text-sm font-medium text-text-secondary">Your subscription URL</p>
      <p className="mt-2 break-all rounded-xl bg-surface px-4 py-3 font-mono text-sm" data-testid="webcal-url">{webcalUrl}</p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Button href={links.apple} icon="calendar">Apple Calendar</Button>
        <Button href={links.google} variant="secondary" icon="external">Google Calendar</Button>
        <Button href={links.outlook} variant="secondary" icon="external">Outlook</Button>
        <Button onClick={copy} variant="secondary" icon="copy">{copied ? "Copied ✓" : "Copy webcal URL"}</Button>
      </div>
      {local && (
        <p className="mt-4 text-sm text-warning">
          This URL points at localhost, so only calendar apps on this machine can reach it. Google and Outlook need a publicly reachable GRIDLINE deployment.
        </p>
      )}
    </div>
  );
}
