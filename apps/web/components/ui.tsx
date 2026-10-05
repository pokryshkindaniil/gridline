import Link from "next/link";
import type { ReactNode } from "react";

export function PageContainer({ children, narrow = false }: { children: ReactNode; narrow?: boolean }) {
  return <div className={`mx-auto w-full px-5 sm:px-8 ${narrow ? "max-w-3xl" : "max-w-6xl"}`}>{children}</div>;
}

export function SectionHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 pb-8 pt-12 sm:pt-16">
      <h1 className="text-4xl font-semibold tracking-tight sm:text-6xl">{title}</h1>
      {subtitle && <p className="text-lg text-text-secondary sm:text-xl">{subtitle}</p>}
      {children}
    </div>
  );
}

export function FilterPill({ href, active, children }: { href: string; active?: boolean; children: ReactNode }) {
  return (
    <Link
      href={href}
      scroll={false}
      aria-current={active ? "true" : undefined}
      className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm transition-colors ${
        active ? "bg-text-primary text-background" : "bg-surface-muted text-text-secondary hover:text-text-primary"
      }`}
    >
      {children}
    </Link>
  );
}

export function SeriesBadge({ name }: { name: string }) {
  return <span className="text-xs font-semibold uppercase tracking-wider text-text-secondary">{name}</span>;
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="rounded-2xl bg-surface-muted px-6 py-14 text-center">
      <p className="text-lg font-medium">{title}</p>
      {body && <p className="mx-auto mt-2 max-w-md text-text-secondary">{body}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

const ICONS = {
  calendar: (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <rect x="2" y="3" width="12" height="11" rx="1.5" /><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" />
    </svg>
  ),
  arrow: (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  ),
  external: (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M5 11l6-6M6 5h5v5" />
    </svg>
  ),
  copy: (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <rect x="5" y="5" width="9" height="9" rx="1.5" /><path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5" />
    </svg>
  ),
};

export const buttonClass = (variant: "primary" | "secondary" | "danger" = "primary", size: "md" | "sm" = "md") =>
  `group inline-flex items-center justify-center gap-2 rounded-lg border font-medium tracking-tight transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-40 ${
    size === "md" ? "h-11 px-[18px] text-[15px]" : "h-10 px-4 text-sm"
  } ${
    variant === "primary" ? "border-text-primary bg-text-primary text-white hover:border-[#3a3a3f] hover:bg-[#3a3a3f] active:bg-black"
    : variant === "danger" ? "border-border bg-surface text-danger hover:border-danger/40 hover:bg-danger/5"
    : "border-border bg-surface text-text-primary hover:border-[#c7c7cc] hover:bg-surface-muted"
  }`;

export function Button({
  children, onClick, href, variant = "primary", disabled, type = "button", icon,
}: {
  children: ReactNode; onClick?: () => void; href?: string; variant?: "primary" | "secondary" | "danger";
  disabled?: boolean; type?: "button" | "submit"; icon?: keyof typeof ICONS;
}) {
  const cls = buttonClass(variant);
  const content = (
    <>
      {children}
      {icon && <span className="transition-transform duration-150 group-hover:translate-x-0.5 opacity-80">{ICONS[icon]}</span>}
    </>
  );
  if (href) return <a href={href} className={cls}>{content}</a>;
  return <button type={type} onClick={onClick} disabled={disabled} className={cls}>{content}</button>;
}
