import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EntryInfo from "@/components/EntryInfo";
import TeamRow from "@/components/TeamRow";
import type { Driver, Entry, Team, Vehicle } from "@/lib/types";

const drv = (n: string): Driver => ({ slug: n.toLowerCase(), first_name: n, last_name: "X", nationality_code: null, image_url: null });
const veh = (over: Partial<Vehicle> = {}): Vehicle => ({
  manufacturer: "Ferrari", manufacturer_slug: "ferrari", model: "SF-26", model_slug: "sf-26", class_name: null,
  race_number: null, image_url: null, fallback_logo_url: null, ...over,
});
const series = (slug: string, category: "formula" | "endurance" | "gt") =>
  ({ slug, name: slug, short_name: slug.toUpperCase(), category, official_url: "", logo_url: null, active: true });
const team = (name: string, slug: string, entries: Entry[], s = series("formula-1", "formula")): Team =>
  ({ slug, name, short_name: null, logo_url: null, website_url: null, series: s, vehicle: entries[0]?.vehicle ?? null, entries });

describe("vehicle model is shown wherever an entry is shown", () => {
  it("shows manufacturer + model (Ferrari SF-26) with the race number and driver on a Formula 1 team", () => {
    const t = team("Ferrari", "ferrari", [
      { race_number: "16", vehicle: veh(), drivers: [drv("Charles")] },
      { race_number: "44", vehicle: veh(), drivers: [drv("Lewis")] },
    ]);
    render(<TeamRow team={t} />);
    expect(screen.getByTestId("entry-car")).toHaveTextContent("Ferrari SF-26");
    expect(screen.getAllByTestId("driver-card")).toHaveLength(2);
    expect(screen.getByText("Charles")).toBeInTheDocument();
  });

  it("shows #number, manufacturer + model and class on an endurance entry (Ferrari 499P, Hypercar)", () => {
    const e: Entry = { race_number: "50", vehicle: veh({ model: "499P", model_slug: "499p", class_name: "Hypercar" }), drivers: [drv("A"), drv("B"), drv("C")] };
    render(<TeamRow team={team("AF Corse", "af-corse", [e], series("fia-wec", "endurance"))} />);
    const info = screen.getByTestId("entry-info");
    expect(within(info).getByTestId("race-number")).toHaveTextContent("50");
    expect(within(info).getByTestId("entry-car")).toHaveTextContent("Ferrari 499P");
    expect(within(info).getByTestId("entry-class")).toHaveTextContent("Hypercar");
  });

  it("shows BMW M4 GT3 EVO with its class for a GT entry (Team WRT, Pro)", () => {
    const e: Entry = { race_number: "32", vehicle: veh({ manufacturer: "BMW", manufacturer_slug: "bmw", model: "M4 GT3 EVO", class_name: "Pro" }), drivers: [drv("A"), drv("B")] };
    render(<TeamRow team={team("Team WRT", "team-wrt", [e], series("gt-world-challenge-europe", "gt"))} />);
    expect(screen.getByTestId("entry-car")).toHaveTextContent("BMW M4 GT3 EVO");
    expect(screen.getByTestId("entry-class")).toHaveTextContent("Pro");
  });

  it("falls back to the manufacturer only when the model is missing: nothing is invented", () => {
    render(<EntryInfo number="16" vehicle={veh({ model: null, model_slug: null })} />);
    expect(screen.getByTestId("entry-car").textContent).toBe("Ferrari");
  });

  it("a missing manufacturer with a model shows the model alone; a missing vehicle renders no car line and does not break", () => {
    const { rerender } = render(<EntryInfo number="7" vehicle={veh({ manufacturer: null, manufacturer_slug: null })} />);
    expect(screen.getByTestId("entry-car").textContent).toBe("SF-26");
    rerender(<EntryInfo number="7" vehicle={null} />);
    expect(screen.queryByTestId("entry-car")).toBeNull();
    expect(screen.getByTestId("race-number")).toHaveTextContent("7");
  });

  it("keeps the same grid structure whether or not the model is known (layout never shifts)", () => {
    const withModel = team("A", "a", [{ race_number: "1", vehicle: veh(), drivers: [drv("P")] }, { race_number: "2", vehicle: veh(), drivers: [drv("Q")] }]);
    const noModel = team("B", "b", [{ race_number: "1", vehicle: veh({ model: null }), drivers: [drv("P")] }, { race_number: "2", vehicle: veh({ model: null }), drivers: [drv("Q")] }]);
    const { container } = render(<><TeamRow team={withModel} /><TeamRow team={noModel} /></>);
    const rows = [...container.querySelectorAll("[data-testid=team-row]")];
    expect(rows[0].className).toBe(rows[1].className);
    for (const r of rows) {
      expect(r.querySelectorAll("[data-testid=entry-info]")).toHaveLength(1);
      expect(r.querySelectorAll("[data-testid=driver-card]")).toHaveLength(2);
    }
  });
});
