"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { nav, product } from "@/app/(landing)/content";
import { HOME_BY_ROLE, useSession } from "@/lib/auth/session-provider";
import { Container } from "@/components/landing/section";
import { cn } from "@/lib/utils";

/**
 * Public site nav. It is a client component for one reason: whether to offer the demo or the
 * dashboard depends on a Supabase session, and that only exists in the browser.
 *
 * The demo CTA is rendered first and swapped only once a session is actually known. Hiding the
 * primary action while the session resolves would cost every visitor the thing the page exists for.
 */
export function LandingNav() {
  const { status, profile } = useSession();
  const signedIn = status === "authenticated" && profile != null;

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
      <Container className="flex min-h-16 items-center justify-between gap-4 py-3">
        <Link
          href="/"
          className="inline-flex min-h-11 items-center text-lg font-semibold tracking-tight"
        >
          {product.name}
        </Link>

        <nav aria-label="This page" className="hidden items-center gap-1 sm:flex">
          {nav.links.map((link) => (
            <NavKey key={link.label} link={link} />
          ))}
        </nav>

        {signedIn ? (
          <Button asChild size="lg" className="px-5 text-sm sm:px-6 sm:text-base">
            <Link href={HOME_BY_ROLE[profile.role]}>{nav.dashboardLabel}</Link>
          </Button>
        ) : (
          <Button asChild size="lg" className="px-5 text-sm sm:px-6 sm:text-base">
            <Link href="#demo">{nav.ctaLabel}</Link>
          </Button>
        )}
      </Container>
    </header>
  );
}

function NavKey({ link }: { link: (typeof nav.links)[number] }) {
  const className =
    "inline-flex min-h-11 items-center rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground";

  if ("external" in link && link.external) {
    return (
      <a href={link.href} className={className} rel="noopener noreferrer" target="_blank">
        {link.label}
      </a>
    );
  }
  return (
    <Link href={link.href} className={cn(className)}>
      {link.label}
    </Link>
  );
}
