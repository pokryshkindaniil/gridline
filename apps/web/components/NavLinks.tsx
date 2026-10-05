"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "This weekend", match: (p: string) => p === "/" },
  { href: "/calendar", label: "Calendar", match: (p: string) => p === "/calendar" },
  { href: "/series", label: "Series", match: (p: string) => p.startsWith("/series") || p.startsWith("/teams") },
  { href: "/my-feed", label: "My feed", match: (p: string) => p.startsWith("/my-feed") || p.startsWith("/manage") || p === "/calendar/create" },
];

export default function NavLinks() {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-1 text-sm">
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`whitespace-nowrap rounded-full px-3 py-1.5 transition-colors ${
            l.match(path) ? "text-text-primary" : "text-text-secondary hover:text-text-primary"
          }`}
        >
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
