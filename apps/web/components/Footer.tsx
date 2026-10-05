import Link from "next/link";
import { PageContainer } from "./ui";

export default function Footer() {
  return (
    <footer className="mt-24 border-t border-border bg-surface-muted/60 py-10 text-sm text-text-secondary">
      <PageContainer>
        <div className="flex flex-col justify-between gap-4 sm:flex-row">
          <p>GRIDLINE is open source (AGPL-3.0). Schedules link back to their original source.</p>
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            <a
              href="https://github.com/pokryshkindaniil/gridline"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 hover:text-text-primary"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
                <path d="M12 .7A11.3 11.3 0 0 0 8.4 22.8c.6.1.8-.3.8-.6v-2.2c-3.4.7-4.1-1.4-4.1-1.4-.5-1.4-1.3-1.8-1.3-1.8-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-6A4.7 4.7 0 0 1 5.7 7.5c-.1-.3-.5-1.6.1-3.3 0 0 1-.3 3.4 1.2a11.8 11.8 0 0 1 6.2 0c2.4-1.6 3.4-1.2 3.4-1.2.6 1.7.2 3 .1 3.3a4.7 4.7 0 0 1 1.2 3.2c0 4.7-2.8 5.7-5.5 6 .4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A11.3 11.3 0 0 0 12 .7Z" />
              </svg>
              GitHub
            </a>
            <Link href="/sources" className="hover:text-text-primary">Data sources &amp; health</Link>
            <Link href="/calendar/create" className="hover:text-text-primary">Create a calendar</Link>
          </div>
        </div>
      </PageContainer>
    </footer>
  );
}
