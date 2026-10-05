import Link from "next/link";
import NavLinks from "./NavLinks";
import { buttonClass, PageContainer } from "./ui";

export default function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-border/70 bg-background/85 backdrop-blur">
      <PageContainer>
        <div className="flex flex-wrap items-center justify-between gap-x-4 py-2 sm:h-14 sm:flex-nowrap sm:py-0">
          <Link href="/" className="text-[15px] font-bold tracking-[0.18em]">GRIDLINE</Link>
          <div className="order-last -mx-2 w-full no-scrollbar overflow-x-auto sm:order-none sm:mx-0 sm:w-auto"><NavLinks /></div>
          <Link href="/calendar/create" className={`${buttonClass("primary", "sm")} hidden !h-9 !px-3.5 sm:inline-flex`}>
            Subscribe
            <svg viewBox="0 0 16 16" className="h-4 w-4 opacity-80 transition-transform duration-150 group-hover:translate-x-0.5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
              <path d="M3 8h10M9 4l4 4-4 4" />
            </svg>
          </Link>
        </div>
      </PageContainer>
    </header>
  );
}
