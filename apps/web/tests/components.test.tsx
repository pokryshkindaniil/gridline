import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DriverCard from "@/components/DriverCard";
import SessionRow from "@/components/SessionRow";
import { flag, formatDateRange, formatTime, isoDay, timeAgo } from "@/lib/format";
import type { Driver, Entry, SessionOut } from "@/lib/types";

const drv = (i: number): Driver => ({ slug: `d${i}`, first_name: `First${i}`, last_name: `Last${i}`, nationality_code: "GB", image_url: null });
const entry = (n: number): Entry => ({ race_number: "50", vehicle: null, drivers: Array.from({ length: n }, (_, i) => drv(i)) });

describe("DriverCard", () => {
  it.each([1, 2, 3, 5])("renders %i drivers with the car number", (n) => {
    render(<DriverCard entry={entry(n)} />);
    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getAllByText(/^Last\d$/)).toHaveLength(n);
  });
  it("uses a compact grid for more than 3 drivers", () => {
    const { container } = render(<DriverCard entry={entry(5)} />);
    expect(container.querySelector("ul")?.className).toContain("grid-cols-2");
  });
});

describe("SessionRow", () => {
  const s: SessionOut = {
    id: "1", event: { id: "e", slug: "barcelona", name: "Barcelona", circuit_name: "Circuit de Barcelona", country_code: "ES", timezone: "Europe/Madrid" },
    series: { slug: "gtwc", name: "GT World Challenge Europe", short_name: "GTWC", category: "gt", official_url: "", logo_url: null, active: true },
    name: "Race 1", session_type: "race", start_at: "2026-10-03T12:00:00Z", end_at: null, status: "scheduled",
    source_url: "https://example.org", source_name: "GTWC", source_updated_at: null, checked_at: "2026-10-04T10:00:00Z", is_fixture: false,
  };
  it("shows time in the requested timezone, series, session and source link", () => {
    render(<ul><SessionRow session={s} tz="Europe/Madrid" /></ul>);
    expect(screen.getByText("14:00")).toBeInTheDocument();
    expect(screen.getByText("GTWC")).toBeInTheDocument();
    expect(screen.getByText("Race 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /official source/i })).toHaveAttribute("href", "https://example.org");
  });
  it("marks cancelled sessions and dev data", () => {
    render(<ul><SessionRow session={{ ...s, status: "cancelled", is_fixture: true }} tz="UTC" /></ul>);
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    expect(screen.getByText("Dev data")).toBeInTheDocument();
  });
});

describe("format helpers", () => {
  it("converts UTC instants to the display timezone", () => {
    expect(formatTime("2026-10-03T12:00:00Z", "Asia/Tokyo")).toBe("21:00");
    expect(isoDay("2026-10-03T23:30:00Z", "Asia/Tokyo")).toBe("2026-10-04");
  });
  it("formats ranges, flags and relative time", () => {
    expect(formatDateRange("2026-10-02", "2026-10-04")).toBe("2–4 October");
    expect(flag("GB")).toBe("🇬🇧");
    const now = Date.parse("2026-10-04T12:00:00Z");
    expect(timeAgo("2026-10-04T11:48:00Z", now)).toBe("12 min ago");
  });
});
