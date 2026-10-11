import type { Metadata } from "next";
import { SITE_DESCRIPTION, SITE_URL } from "@/lib/seo";
import Footer from "@/components/Footer";
import Header from "@/components/Header";
import TimezoneSync from "@/components/TimezoneSync";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  applicationName: "GRIDLINE",
  title: {
    default: "Motorsport Calendar for F1, WEC & GTWC | GRIDLINE",
    template: "%s | GRIDLINE",
  },
  description: SITE_DESCRIPTION,
  verification: { google: "Ux9zZS2hiknafTIkDhwB9tLWdgMbBc97Ok9xuwvtqdY" },
  openGraph: {
    type: "website",
    siteName: "GRIDLINE",
    locale: "en_US",
    title: "Motorsport Calendar for F1, WEC & GTWC | GRIDLINE",
    description: SITE_DESCRIPTION,
  },
  twitter: { card: "summary_large_image" },
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
