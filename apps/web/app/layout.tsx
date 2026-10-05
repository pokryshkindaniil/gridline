import type { Metadata } from "next";
import Footer from "@/components/Footer";
import Header from "@/components/Header";
import TimezoneSync from "@/components/TimezoneSync";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "GRIDLINE — your motorsport calendar, always up to date", template: "%s · GRIDLINE" },
  description: "Session-level motorsport schedules with official-source provenance and permanent calendar subscriptions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <TimezoneSync />
        <Header />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
