import { cn } from "@/lib/utils";

/** Content band width. Wide enough for two columns, narrow enough to read a line without tracking. */
export const CONTAINER = "mx-auto w-full max-w-[1100px] px-5 sm:px-8";

/**
 * One band of the landing page. `scroll-mt-24` keeps an anchored section below the sticky nav
 * instead of hiding its heading behind it, and the section is only labelled when it has a heading.
 */
export function Section({
  id,
  label,
  className,
  children,
}: {
  id?: string;
  /** Visible or sr-only text that names this region for a screen reader jumping by landmark. */
  label?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      aria-label={label}
      className={cn("scroll-mt-24 py-14 sm:py-20", className)}
    >
      <div className={CONTAINER}>{children}</div>
    </section>
  );
}

export function Container({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn(CONTAINER, className)}>{children}</div>;
}

/** Section heading. Level 2 throughout, so the document keeps one h1 and a flat outline. */
export function SectionHeading({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <h2
      className={cn(
        "text-3xl font-semibold tracking-tight text-balance sm:text-4xl",
        className,
      )}
    >
      {children}
    </h2>
  );
}
