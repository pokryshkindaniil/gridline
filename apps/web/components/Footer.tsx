import Link from "next/link";
import { PageContainer } from "./ui";

export default function Footer() {
  return (
    <footer className="mt-24 border-t border-border bg-surface-muted/60 py-10 text-sm text-text-secondary">
      <PageContainer>
        <div className="flex flex-col justify-between gap-4 sm:flex-row">
          <p>GRIDLINE is open source (AGPL-3.0). Schedules link back to their original source.</p>
          <div className="flex gap-6">
            <Link href="/sources" className="hover:text-text-primary">Data sources &amp; health</Link>
            <Link href="/calendar/create" className="hover:text-text-primary">Create a calendar</Link>
          </div>
        </div>
      </PageContainer>
    </footer>
  );
}
