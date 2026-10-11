import { ImageResponse } from "next/og";

export const alt = "GRIDLINE: motorsport calendars that stay up to date";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 84px",
          backgroundColor: "#0d1119",
          color: "#f7f8fa",
          fontFamily: "Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ width: 12, height: 48, backgroundColor: "#f14d49" }} />
          <div style={{ fontSize: 42, fontWeight: 800, letterSpacing: 8 }}>GRIDLINE</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <div style={{ fontSize: 72, fontWeight: 750, letterSpacing: -2 }}>
            Every session. One calendar.
          </div>
          <div style={{ fontSize: 32, color: "#b8c1d1" }}>
            Formula 1 · FIA WEC · GT World Challenge Europe
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 22, color: "#a4afbf", letterSpacing: 3 }}>
          LIVE SCHEDULES · AUTOMATIC CALENDAR UPDATES
        </div>
      </div>
    ),
    size,
  );
}
